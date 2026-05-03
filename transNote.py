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


# ── 前端 HTML 页面（从 www/index.html 动态加载）───────────────────────
WWW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www")


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
            html_path = os.path.join(WWW_DIR, "index.html")
            try:
                with open(html_path, "r", encoding="utf-8") as f:
                    body_str = f.read().replace("__API_KEY__", API_KEY)
                body = body_str.encode("utf-8")
            except FileNotFoundError:
                self._send(503, {"error": "www/index.html not found"})
                return
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
