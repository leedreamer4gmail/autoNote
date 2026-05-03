#!/usr/bin/env python3
"""
transNote.py — Simplenote 云端更新服务
监听 8888 端口，代理写入/读取 Simplenote 笔记。

API:
  GET  /health           健康检查（无需鉴权）
  GET  /notes            列出所有笔记（标题+ID）
  GET  /notes/dead       列出已删除（可复活）的笔记
  GET  /crops            读取本地缓存的尸体清单（可直接用于新建笔记）
  GET  /note/<id>        读取笔记内容
  POST /note             写入/更新笔记，写后回读验证，返回 stored_chars
    DELETE /note/<id>      删除笔记（标记 deleted=true），写后回读验证

认证: 所有请求需要 Header: X-Api-Key: simpleNote888

说明:
  - POST /note 采用「写入即验证」机制：不依赖 Simperium 响应码（可能返回
    412/502 但写入已生效），而是写后用 GET 对比内容确认结果。
  - 每次查询 index 后自动更新 corpseList.txt，供下次新建笔记直接使用。

错误日志: /home/project/simpleNote/transNote.log
"""

import json
import logging
import os
import threading
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

# ── 配置 ────────────────────────────────────────────────────
PORT          = 8888
SIM_TOKEN     = os.environ.get("SIM_TOKEN", "2c7c5ce044c74d72b3666f9a675a485b")
SIM_BASE      = "https://api.simperium.com/1/chalk-bump-f49/note"
SIM_HEADERS   = {"X-Simperium-Token": SIM_TOKEN}
LOG_FILE      = "/home/project/simpleNote/transNote.log"
CONFIG_FILE   = "/home/project/simpleNote/frontend.conf"

def _load_api_key():
    """从服务器配置文件读取 API Key，文件不存在则回退环境变量/默认值。"""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("apikey="):
                    return line[len("apikey="):].strip()
    except FileNotFoundError:
        pass
    return os.environ.get("NOTE_API_KEY", "simpleNote888")

API_KEY = _load_api_key()

# ── 日志 ─────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def sim_request(method, path, body_bytes=None):
    """调用 Simperium API，返回 (status_code, response_bytes)。
    注意：POST 可能返回 412/502 但写入已生效，调用方需自行 GET 验证。"""
    url = SIM_BASE + path
    headers = dict(SIM_HEADERS)
    if body_bytes:
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        logging.error(f"sim_request {method} {path}: {e}")
        return 503, json.dumps({"error": str(e)}).encode()


import re as _re
_UUID_RE = _re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', _re.I)

# 内存占位集合：已被选中但尚未写入完成的尸体 ID
# 线程锁保证并发请求时不会抢到同一个 ID
_claimed: set = set()
_claimed_lock = threading.Lock()


def verify_deleted(note_id):
    status, data = sim_request("GET", "/index?limit=100&data=true")
    if status != 200:
        return False, f"index returned {status}"
    items = json.loads(data).get("index", [])
    for item in items:
        if item.get("id") == note_id:
            return bool((item.get("d") or {}).get("deleted")), None
    return False, "note id not found in index"


# ── 前端 HTML 页面 ───────────────────────────────────────────────────
# 注意：必须用 r"""...""" 原始字符串，避免 Python 把 JS 里的 \n \x00 等
# 转义序列提前解释，导致 null byte 或真实换行嵌入 JS 源码引发语法错误。
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>transNote</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:32px 16px}
.wrap{max-width:680px;margin:0 auto}
.logo{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.logo h1{font-size:1.6rem;font-weight:800;color:white}
.logo .tag{background:rgba(255,255,255,0.25);color:white;font-size:.75rem;padding:2px 10px;border-radius:20px}
.sub{color:rgba(255,255,255,0.82);font-size:.875rem;margin-bottom:22px}
.glass{background:rgba(255,255,255,0.93);backdrop-filter:blur(12px);border-radius:20px;padding:26px 28px;margin-bottom:14px;box-shadow:0 4px 24px rgba(0,0,0,0.08)}
.sec{font-size:.72rem;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px}
.dz{border:2px dashed #c4b5fd;border-radius:14px;padding:34px;text-align:center;cursor:pointer;transition:all .2s;background:#faf5ff;position:relative}
.dz:hover,.dz.over{border-color:#7c3aed;background:#f5f3ff}
.dz input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.dz .icon{font-size:2.4rem;margin-bottom:8px}
.dz .dt{color:#7c3aed;font-weight:600;font-size:.9rem}
.dz .ds{color:#9ca3af;font-size:.8rem;margin-top:4px}
.fname{margin-top:12px;display:inline-flex;align-items:center;gap:6px;background:#ede9fe;color:#5b21b6;border-radius:8px;padding:4px 12px;font-size:.85rem;font-weight:600}
.hidden{display:none}
.chip{display:inline-flex;align-items:center;gap:6px;border-radius:8px;padding:6px 12px;font-size:.8rem;font-family:monospace;margin-bottom:12px;border:1.5px solid;word-break:break-all}
.chip.auto{background:#fdf4ff;border-color:#e879f9;color:#86198f}
.chip.ok{background:#f0fdf4;border-color:#4ade80;color:#166534}
textarea{width:100%;border:1.5px solid #e5e7eb;border-radius:10px;padding:12px;font-family:"Consolas","Monaco",monospace;font-size:.8rem;color:#374151;background:#f9fafb;resize:vertical;outline:none;transition:border-color .2s;min-height:100px}
textarea:focus{border-color:#7c3aed;background:white}
.vlist{list-style:none;margin-top:12px}
.vlist li{padding:6px 0;font-size:.875rem;color:#374151;border-bottom:1px solid #f3f4f6}
.vlist li:last-child{border-bottom:none}
.brow{display:flex;gap:10px;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:6px;padding:10px 22px;border-radius:10px;font-size:.875rem;font-weight:600;border:none;cursor:pointer;transition:all .18s ease}
.btn:disabled{opacity:.6;cursor:not-allowed;transform:none!important}
.btn-p{background:linear-gradient(135deg,#7c3aed,#6d28d9);color:white;box-shadow:0 4px 14px rgba(109,40,217,.35)}
.btn-p:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 6px 20px rgba(109,40,217,.45)}
.btn-s{background:#f3f4f6;color:#374151}
.btn-s:hover:not(:disabled){background:#e5e7eb}
.st{margin-top:12px;border-radius:10px;padding:12px 16px;font-size:.875rem;line-height:1.6;white-space:pre-wrap;transition:all .2s}
.s-idle{background:#f9fafb;color:#6b7280;border:1.5px solid #e5e7eb}
.s-ok{background:#f0fdf4;color:#166534;border:1.5px solid #86efac}
.s-warn{background:#fffbeb;color:#92400e;border:1.5px solid #fcd34d}
.s-err{background:#fef2f2;color:#991b1b;border:1.5px solid #fca5a5}
.cw{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.ctag{display:inline-flex;align-items:center;background:#f3f4f6;border:1.5px solid #e5e7eb;border-radius:6px;padding:4px 10px;font-family:monospace;font-size:.75rem;color:#6b7280;cursor:pointer;transition:all .15s}
.ctag:hover{background:#ede9fe;border-color:#a78bfa;color:#6d28d9}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{display:inline-block;width:13px;height:13px;border:2px solid rgba(255,255,255,.4);border-top-color:white;border-radius:50%;animation:spin .7s linear infinite}
</style>
</head>
<body>
<div class="wrap">
  <div class="logo"><h1>transNote</h1><span class="tag">v2</span></div>
  <p class="sub">上传 JSON 文件，将笔记内容写入 Simplenote</p>

  <div class="glass">
    <div class="sec">📂 选择 JSON 文件</div>
    <div class="dz" id="dz">
      <input type="file" id="fi" accept=".json">
      <div class="icon">📄</div>
      <div class="dt">点击选择文件，或拖入此处</div>
      <div class="ds">接受 .json 文件</div>
      <div class="fname hidden" id="fname"></div>
    </div>
  </div>

  <div class="glass hidden" id="previewCard">
    <div class="sec">👁 预览</div>
    <div id="idChip" class="chip auto"></div>
    <textarea id="pc" rows="6" readonly></textarea>
    <ul class="vlist" id="vlist"></ul>
  </div>

  <div class="glass">
    <div class="sec">🚀 操作</div>
    <div class="brow">
      <button class="btn btn-p" id="wb" onclick="writeNote()">✍️ 写入笔记</button>
      <button class="btn btn-s" onclick="loadCrops()">🔄 刷新</button>
    </div>
    <div class="st s-idle" id="st">等待操作...</div>
  </div>

  <div class="glass">
    <div class="sec">🪦 尸体槽位（服务端自动分配，无需手动选择）</div>
    <div style="display:flex;align-items:center;gap:12px">
      <span id="cropCount" style="font-size:1.1rem;font-weight:700;color:#7c3aed">加载中...</span>
    </div>
    <p style="margin-top:8px;font-size:.8rem;color:#9ca3af">写入时自动取用并立即移除，防止重复占用。</p>
  </div>
</div>
<script>
const API_KEY = "__API_KEY__";
let note = null;
const dz = document.getElementById('dz');
const fi = document.getElementById('fi');

dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('over'); });
dz.addEventListener('dragleave', () => dz.classList.remove('over'));
dz.addEventListener('drop', e => { e.preventDefault(); dz.classList.remove('over'); if (e.dataTransfer.files[0]) load(e.dataTransfer.files[0]); });
fi.addEventListener('change', () => { if (fi.files[0]) load(fi.files[0]); });

function load(file) {
  const fn = document.getElementById('fname');
  fn.textContent = '📎 ' + file.name;
  fn.classList.remove('hidden');
  const r = new FileReader();
  r.onload = ev => {
    try {
      note = JSON.parse(ev.target.result);
      const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
      const hasId = note.id && UUID.test(note.id.trim());
      const chip = document.getElementById('idChip');
      chip.className = 'chip ' + (hasId ? 'ok' : 'auto');
      chip.textContent = hasId ? ('🔑 ' + note.id) : '🎲 id 未指定 — 将自动分配尸体 ID';
      document.getElementById('pc').value = (note.content || '').substring(0, 500);
      document.getElementById('previewCard').classList.remove('hidden');
      const issues = chk(note);
      const ul = document.getElementById('vlist');
      ul.innerHTML = '';
      issues.forEach(([icon, txt]) => { const li = document.createElement('li'); li.textContent = icon + ' ' + txt; ul.appendChild(li); });
      const hasErr = issues.some(([i]) => i === '❌');
      setS('校验结果 ' + issues.length + ' 项\n' + issues.map(([i,t]) => i+' '+t).join('\n'), hasErr ? 'err' : 'ok');
    } catch(err) {
      note = null;
      document.getElementById('previewCard').classList.add('hidden');
      setS('JSON 解析失败：' + err.message + '\n\n常见原因：\n• content 里有真实换行（改为 \\n）\n• 有未转义的双引号（改为 \\"）', 'err');
    }
  };
  r.readAsText(file, 'UTF-8');
}


function chk(n) {
  const out = [];
  if (!n.content && n.content !== '') out.push(['❌', '缺少 content 字段']);
  else if (typeof n.content !== 'string') out.push(['❌', 'content 必须是字符串']);
  else {
    let bad = false;
    for (let i = 0; i < n.content.length; i++) {
      const c = n.content.charCodeAt(i);
      if (c < 32 && c !== 9 && c !== 10 && c !== 13) { bad = true; break; }
    }
    if (bad) out.push(['❌', 'content 含非法控制字符（请用 \\n 换行，勿直接回车）']);
    if (!n.content.trim()) out.push(['⚠️', 'content 内容为空']);
  }
  if (n.deleted === true) out.push(['⚠️', 'deleted=true 会删除笔记而非写入内容']);
  if (!Array.isArray(n.tags)) out.push(['⚠️', 'tags 不是数组，建议写 []']);
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (n.id && !UUID.test(n.id.trim())) out.push(['ℹ️', 'id 不是 UUID，将自动分配尸体 ID']);
  else if (!n.id) out.push(['ℹ️', '未指定 id，将自动分配尸体 ID（正常）']);
  return out;
}

async function writeNote() {
  if (!note) { setS('请先选择一个 JSON 文件。', 'err'); return; }
  const btn = document.getElementById('wb');
  btn.innerHTML = '<span class="spin"></span> 写入中...';
  btn.disabled = true;
  setS('写入中...（服务端自动分配尸体 ID）', 'idle');
  // 只传 content/tags/deleted；如果用户 JSON 里有合法 UUID 的 id，也带上（精确更新已有笔记用）
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const nid = (note.id || '').trim();
  const payload = {content: note.content, tags: note.tags || [], deleted: note.deleted || false};
  if (nid && UUID.test(nid)) payload.id = nid;
  const b64 = btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
  const formBody = 'data=' + encodeURIComponent(b64);
  try {
    const resp = await fetch('/note', {
      method: 'POST',
      headers: {'Content-Type': 'application/x-www-form-urlencoded', 'X-Api-Key': API_KEY},
      body: formBody
    });
    const d = await resp.json();
    if (d.verified) {
      setS('✅ 写入成功！\nID: ' + d.id + '\nstored_chars: ' + (d.stored_chars||'?'), 'ok');
      loadCrops();
    } else {
      setS('⚠️ 写入返回但未验证：\n' + JSON.stringify(d, null, 2), 'warn');
    }
  } catch(e) {
    setS('❌ 请求失败：' + e.message, 'err');
  } finally {
    btn.innerHTML = '✍️ 写入笔记';
    btn.disabled = false;
  }
}

async function loadCrops() {
  try {
    // /crops 直接实时查 Simperium，无需额外步骤
    const r = await fetch('/crops', {headers: {'X-Api-Key': API_KEY}});
    const d = await r.json();
    document.getElementById('cropCount').textContent = (d.count || 0) + ' 个可用';
    return true;
  } catch(e) {
    document.getElementById('cropCount').textContent = '加载失败';
    return false;
  }
}

function setS(msg, type) {
  const el = document.getElementById('st');
  el.textContent = msg;
  el.className = 'st s-' + (type||'idle');
}

loadCrops();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # 关闭默认 access log，减少噪音

    def _auth(self):
        key = self.headers.get("X-Api-Key", "")
        if key != API_KEY:
            self._send(403, {"error": "Forbidden: invalid X-Api-Key"})
            return False
        return True

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        # 支持两种 body 传输方式：
        # 1. Content-Length（直接长度）
        # 2. Transfer-Encoding: chunked（代理/浏览器可能改写为此格式）
        te = self.headers.get("Transfer-Encoding", "").lower()
        if "chunked" in te:
            chunks = []
            while True:
                size_line = self.rfile.readline().strip()
                if not size_line:
                    continue
                try:
                    chunk_size = int(size_line.split(b";")[0], 16)
                except (ValueError, IndexError):
                    break
                if chunk_size == 0:
                    break
                chunks.append(self.rfile.read(chunk_size))
                self.rfile.read(2)  # 跳过 chunk 后的 CRLF
            return b"".join(chunks)
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    # ── GET ──────────────────────────────────────────────────────────
    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "":
            body = HTML_PAGE.replace("__API_KEY__", API_KEY).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/health":
            self._send(200, {"status": "ok", "port": PORT})
            return

        if not self._auth():
            return

        if path == "/notes":
            status, data = sim_request("GET", "/index?limit=100&data=true")
            if status != 200:
                logging.error(f"GET /notes sim={status}")
                self._send(502, {"error": f"simperium {status}"})
                return
            items = json.loads(data).get("index", [])
            result = []
            for it in items:
                d = it.get("d") or {}
                content = d.get("content") or ""
                title = content.split("\n")[0][:80] if content else ""
                result.append({
                    "id": it["id"],
                    "title": title,
                    "deleted": bool(d.get("deleted"))
                })
            self._send(200, {"ok": True, "notes": result})
            return

        if path == "/notes/dead":
            status, data = sim_request("GET", "/index?limit=100&data=true")
            if status != 200:
                self._send(502, {"error": f"simperium {status}"})
                return
            items = json.loads(data).get("index", [])
            dead = []
            for it in items:
                d = it.get("d") or {}
                if d.get("deleted"):
                    content = d.get("content") or ""
                    dead.append({"id": it["id"], "preview": content[:60]})
            self._send(200, {"ok": True, "dead": dead})
            return

        if path == "/crops":
            # 实时查 Simperium，展示可用尸体数量（已占位的不算）
            status, data = sim_request("GET", "/index?limit=100&data=true")
            if status != 200:
                self._send(502, {"error": f"simperium {status}"})
                return
            items = json.loads(data).get("index", [])
            with _claimed_lock:
                ids = [
                    it["id"] for it in items
                    if (it.get("d") or {}).get("deleted")
                    and _UUID_RE.match(it["id"])
                    and it["id"] not in _claimed
                ]
            self._send(200, {"ok": True, "crops": ids, "count": len(ids)})
            return

        if path.startswith("/note/"):
            note_id = path[len("/note/"):]
            if not note_id:
                self._send(400, {"error": "missing note id"})
                return
            status, data = sim_request("GET", f"/i/{note_id}")
            if status == 200:
                content = json.loads(data).get("content", "")
                self._send(200, {"ok": True, "id": note_id, "content": content})
            else:
                self._send(502, {"ok": False, "status": status})
            return

        self._send(404, {"error": "not found"})

    # ── POST ─────────────────────────────────────────────────────────
    def do_POST(self):
        if not self._auth():
            return

        if self.path.rstrip("/") == "/note":
            raw = self._read_body()
            import base64 as _b64
            from urllib.parse import parse_qs as _pqs
            ct = self.headers.get("Content-Type", "").lower()
            # 优先处理 urlencoded（代理友好格式）
            if "application/x-www-form-urlencoded" in ct:
                try:
                    params = _pqs(raw.decode("utf-8", errors="replace"))
                    b64_val = params.get("data", [""])[0]
                    raw = _b64.b64decode(b64_val + "==")  # 补 padding
                except Exception:
                    pass
            # 降级：body 为空时从 X-Note-B64 header 读取
            elif not raw.strip():
                b64_hdr = (self.headers.get("X-Note-B64") or "").strip()
                if b64_hdr:
                    try:
                        raw = _b64.b64decode(b64_hdr)
                    except Exception:
                        pass
            try:
                body = json.loads(raw)
            except Exception:
                cl = self.headers.get("Content-Length", "?")
                te = self.headers.get("Transfer-Encoding", "?")
                self._send(400, {"error": "invalid JSON",
                                 "debug": {"cl": cl, "te": te, "raw_len": len(raw),
                                           "raw_preview": raw[:60].decode('utf-8','replace')}})
                return

            note_id = body.get("id", "").strip()
            content = body.get("content", "")
            tags    = body.get("tags", [])
            deleted = body.get("deleted", False)

            # 服务端自动选尸体：id 缺失或非 UUID 时实时从 Simperium 获取，内存锁原子占位
            if not note_id or not _UUID_RE.match(note_id):
                idx_status, idx_data = sim_request("GET", "/index?limit=100&data=true")
                if idx_status != 200:
                    self._send(503, {"error": "failed to fetch corpse list",
                                     "hint": f"simperium index returned {idx_status}"})
                    return
                dead_ids = [
                    it["id"] for it in json.loads(idx_data).get("index", [])
                    if (it.get("d") or {}).get("deleted") and _UUID_RE.match(it["id"])
                ]
                with _claimed_lock:
                    available = [i for i in dead_ids if i not in _claimed]
                    if not available:
                        self._send(503, {"error": "no corpse ID available",
                                         "hint": "add deleted notes in Simplenote to create more"})
                        return
                    note_id = available[0]
                    _claimed.add(note_id)

            if not content and not deleted:
                self._send(400, {"error": "content is required"})
                return

            payload = json.dumps(
                {"content": content, "tags": tags, "deleted": deleted},
                ensure_ascii=False
            ).encode("utf-8")

            # 写入：不依赖响应码（Simperium 可能返回 412/502 但写入已生效）
            sim_request("POST", f"/i/{note_id}?response=1", payload)

            # 写后等待 Simperium 落盘，再 GET 验证
            time.sleep(0.8)
            if deleted:
                ok, warn = verify_deleted(note_id)
                _claimed.discard(note_id)
                self._send(200, {"ok": ok, "id": note_id, "verified": ok,
                                 **({"warn": warn} if warn else {})})
                return

            vstatus, vdata = sim_request("GET", f"/i/{note_id}")
            if vstatus == 200:
                stored = json.loads(vdata)
                stored_content = stored.get("content", "")
                if stored_content == content:
                    _claimed.discard(note_id)
                    self._send(200, {"ok": True, "id": note_id, "verified": True,
                                     "stored_chars": len(stored_content)})
                else:
                    _claimed.discard(note_id)
                    logging.error(f"POST /note id={note_id} content mismatch sent={len(content)} stored={len(stored_content)}")
                    self._send(200, {"ok": False, "id": note_id, "verified": False,
                                     "warn": "content mismatch after write",
                                     "stored_chars": len(stored_content)})
            else:
                _claimed.discard(note_id)
                logging.error(f"POST /note id={note_id} verify GET={vstatus}")
                self._send(200, {"ok": False, "id": note_id, "verified": False,
                                 "warn": f"verify GET returned {vstatus}"})
            return

        self._send(404, {"error": "not found"})

    # ── DELETE ───────────────────────────────────────────────────────
    def do_DELETE(self):
        if not self._auth():
            return

        path = self.path.rstrip("/")
        if not path.startswith("/note/"):
            self._send(404, {"error": "not found"})
            return

        note_id = path[len("/note/"):].strip()
        if not note_id:
            self._send(400, {"error": "missing note id"})
            return

        payload = json.dumps(
            {"content": "", "tags": [], "deleted": True},
            ensure_ascii=False
        ).encode("utf-8")

        sim_request("POST", f"/i/{note_id}?response=1", payload)
        time.sleep(0.8)

        ok, warn = verify_deleted(note_id)
        if not ok:
            logging.error(f"DELETE /note id={note_id} verify failed: {warn}")
        self._send(200, {"ok": ok, "id": note_id, "verified": ok,
                         "deleted": ok,
                         **({"warn": warn} if warn else {})})

if __name__ == "__main__":
    os.makedirs("/home/project/simpleNote", exist_ok=True)
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"transNote service running on port {PORT}", flush=True)
    server.serve_forever()
