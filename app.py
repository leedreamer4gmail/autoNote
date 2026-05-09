#!/usr/bin/env python3
"""autoNote main service.

This is the new self-owned note system. The database stores Markdown content as
the source of truth; titles are derived from Markdown when needed.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file


BASE_DIR = Path(__file__).resolve().parent
WWW_DIR = BASE_DIR / "www"
DB_PATH = Path(os.environ.get("AUTONOTE_DB", BASE_DIR / "notedb.db"))
CONFIG_FILE = BASE_DIR / "frontend.conf"
DEFAULT_USER = os.environ.get("AUTONOTE_USER", "leedreamer")
DEFAULT_PORT = int(os.environ.get("PORT", "8888"))

WRITE_LOCK = threading.RLock()

app = Flask(__name__)


def load_config() -> dict[str, str]:
    config: dict[str, str] = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip().lower()] = value.strip()
    return config


CONFIG = load_config()
API_KEY = os.environ.get("AUTONOTE_API_KEY") or os.environ.get("NOTE_API_KEY") or CONFIG.get("apikey", "simpleNote888")
PORT = int(CONFIG.get("port", DEFAULT_PORT))


def parse_prompt_llm_config() -> dict[str, str]:
    prompt_path = BASE_DIR / "promt.md"
    if not prompt_path.exists():
        return {}
    text = prompt_path.read_text(encoding="utf-8", errors="ignore")
    config: dict[str, str] = {}
    key_match = re.search(r"(?:^|\n)\s*key\s*[:：]\s*(\S+)", text, re.I)
    base_match = re.search(r"base_url[^\n:：]*[:：]\s*(https?://\S+)", text, re.I)
    model_match = re.search(r"(?:^|\n)\s*model\s*[:：]\s*(\S+)", text, re.I)
    if key_match:
        config["api_key"] = key_match.group(1).strip()
    if base_match:
        config["base_url"] = base_match.group(1).strip()
    if model_match:
        config["model"] = model_match.group(1).strip()
    return config


def normalize_lucy_model(model: str) -> str:
    model = str(model or "").strip()
    deepseek_aliases = {
        "deepseek-v4-flash": "deepseek-v4-flash",
        "deepseek-v4-pro": "deepseek-v4-pro",
    }
    return deepseek_aliases.get(model.lower(), model)


def load_lucy_config() -> dict[str, str]:
    prompt_config = parse_prompt_llm_config()
    api_key = (
        os.environ.get("LUCY_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or CONFIG.get("lucy_api_key")
        or CONFIG.get("deepseek_api_key")
        or prompt_config.get("api_key")
        or ""
    )
    base_url = (
        os.environ.get("LUCY_BASE_URL")
        or os.environ.get("DEEPSEEK_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or CONFIG.get("lucy_base_url")
        or CONFIG.get("deepseek_base_url")
        or CONFIG.get("base_url")
        or prompt_config.get("base_url")
        or "https://api.deepseek.com"
    )
    model = (
        os.environ.get("LUCY_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or CONFIG.get("lucy_model")
        or CONFIG.get("deepseek_model")
        or CONFIG.get("model")
        or prompt_config.get("model")
        or "DeepSeek-V4-Flash"
    )
    timeout = os.environ.get("LUCY_TIMEOUT") or CONFIG.get("lucy_timeout") or "45"
    return {"api_key": api_key, "base_url": base_url, "model": normalize_lucy_model(model), "timeout": timeout}


LUCY_CONFIG = load_lucy_config()


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_text() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db() -> None:
    with connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                user TEXT NOT NULL,
                folder TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                tag TEXT NOT NULL DEFAULT '[]',
                enable TEXT NOT NULL DEFAULT 'T',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_enable ON notes(enable)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at)")


@contextmanager
def write_tx():
    with WRITE_LOCK:
        conn = connect_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()


def require_api_key() -> bool:
    key = request.headers.get("X-Api-Key", "")
    if key != API_KEY:
        return False
    return True


def auth_error():
    return jsonify({"ok": False, "error": "invalid X-Api-Key"}), 403


def request_data() -> dict:
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict(flat=True)
    if not isinstance(data, dict):
        return {}
    return data


def normalize_user(value: object) -> str:
    user = str(value or DEFAULT_USER).strip()
    return user or DEFAULT_USER


def normalize_folder(value: object) -> str:
    return str(value or "").strip()[:80]


def normalize_tags(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            value = parsed if isinstance(parsed, list) else [value]
        except json.JSONDecodeError:
            value = re.split(r"[,，\s]+", value)
    if not isinstance(value, list):
        value = [str(value)]
    tags: list[str] = []
    for raw_tag in value:
        tag = str(raw_tag or "").strip().strip("#")[:30]
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) >= 5:
            break
    return tags


def parse_tags(text: str) -> list[str]:
    tags = re.findall(r"#([A-Za-z0-9_\-\u4e00-\u9fff]{1,30})", text)
    if tags:
        return normalize_tags(tags)

    words = tokenize(text)
    useful = [w for w in words if len(w) >= 2 and not w.isdigit()]
    return normalize_tags(useful[:5])


def markdown_title(content: str) -> str:
    for line in content.splitlines():
        text = line.strip()
        if not text:
            continue
        text = re.sub(r"^#{1,6}\s*", "", text).strip()
        return text[:80] or "未命名笔记"
    return "未命名笔记"


def short_summary(text: str) -> str:
    title = markdown_title(text)
    title = re.sub(r"经验$", "", title).strip()
    return title[:24] or "新增记录"


def tokenize(text: str) -> set[str]:
    text = text.lower()
    tokens = set(re.findall(r"[a-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", text))
    for token in list(tokens):
        if len(token) > 8 and re.search(r"[\u4e00-\u9fff]", token):
            tokens.update(token[i : i + 2] for i in range(len(token) - 1))
    return tokens


def note_from_row(row: sqlite3.Row) -> dict:
    content = row["content"]
    try:
        tags = json.loads(row["tag"] or "[]")
    except json.JSONDecodeError:
        tags = []
    return {
        "id": row["id"],
        "user": row["user"],
        "folder": row["folder"],
        "content": content,
        "tag": tags,
        "tags": tags,
        "enable": row["enable"],
        "title": markdown_title(content),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def fetch_note(note_id: str) -> dict | None:
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return note_from_row(row) if row else None


def list_notes(user: str, q: str = "", include_disabled: bool = False, folder: str = "") -> list[dict]:
    sql = "SELECT * FROM notes WHERE user = ?"
    params: list[object] = [user]
    if not include_disabled:
        sql += " AND enable = 'T'"
    if folder:
        sql += " AND folder = ?"
        params.append(folder)
    if q:
        sql += " AND (content LIKE ? OR folder LIKE ? OR tag LIKE ?)"
        needle = f"%{q}%"
        params.extend([needle, needle, needle])
    sql += " ORDER BY updated_at DESC"
    with connect_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [note_from_row(row) for row in rows]


def create_note(user: str, content: str, folder: str = "", tags: list[str] | None = None) -> dict:
    content = str(content or "").strip()
    if not content:
        raise ValueError("content is required")
    note_id = str(uuid.uuid4())
    stamp = now_text()
    tags = normalize_tags(tags)
    with write_tx() as conn:
        conn.execute(
            """
            INSERT INTO notes(id, user, folder, content, tag, enable, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'T', ?, ?)
            """,
            (note_id, user, folder, content, json.dumps(tags, ensure_ascii=False), stamp, stamp),
        )
    return fetch_note(note_id) or {"id": note_id}


def update_note(note_id: str, content: str | None = None, folder: str | None = None, tags: list[str] | None = None) -> dict:
    old = fetch_note(note_id)
    if not old:
        raise KeyError("note not found")
    new_content = old["content"] if content is None else str(content).strip()
    if not new_content:
        raise ValueError("content is required")
    new_folder = old["folder"] if folder is None else normalize_folder(folder)
    new_tags = old["tags"] if tags is None else normalize_tags(tags)
    with write_tx() as conn:
        conn.execute(
            """
            UPDATE notes
               SET content = ?, folder = ?, tag = ?, updated_at = ?
             WHERE id = ?
            """,
            (new_content, new_folder, json.dumps(new_tags, ensure_ascii=False), now_text(), note_id),
        )
    return fetch_note(note_id) or {"id": note_id}


def set_note_enable(note_id: str, enable: bool) -> dict:
    if not fetch_note(note_id):
        raise KeyError("note not found")
    with write_tx() as conn:
        conn.execute(
            "UPDATE notes SET enable = ?, updated_at = ? WHERE id = ?",
            ("T" if enable else "F", now_text(), note_id),
        )
    return fetch_note(note_id) or {"id": note_id}


def delete_note(note_id: str) -> None:
    with write_tx() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        if cur.rowcount == 0:
            raise KeyError("note not found")


def truncate_text(text: str, limit: int) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n..."


def handbook_for_lucy() -> str:
    path = WWW_DIR / "autonotehb.md"
    if not path.exists():
        return ""
    return truncate_text(path.read_text(encoding="utf-8", errors="ignore"), 5000)


def lucy_chat_url(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def extract_json_object(text: str) -> dict:
    text = str(text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}


def candidate_notes_for_lucy(user: str, content: str, folder: str, tags: list[str], limit: int = 8) -> list[dict]:
    incoming = {"content": content, "folder": folder, "tags": tags}
    scored: list[tuple[float, dict]] = []
    for note in list_notes(user):
        scored.append((similarity_score(incoming, note), note))
    scored.sort(key=lambda item: item[0], reverse=True)
    candidates: list[dict] = []
    for score, note in scored[:limit]:
        candidates.append(
            {
                "id": note["id"],
                "title": note["title"],
                "folder": note["folder"],
                "tags": note["tags"],
                "score": round(score, 3),
                "content": truncate_text(note["content"], 7000),
            }
        )
    return candidates


def build_lucy_messages(user: str, text: str, folder: str, tags: list[str], candidates: list[dict]) -> list[dict]:
    system = """
你是 autoNote 的秘书 Lucy。你连接 LLM，负责把用户发来的零散信息整理成 Markdown 经验笔记。
必须遵守：
1. 只输出一个 JSON 对象，不要 Markdown 代码块，不要解释。
2. 数据库没有 title 字段，标题只写在 Markdown 第一行。
3. notetools 才能写库；你只做决策和生成完整 Markdown 内容。
4. 收到新信息后，要先对比候选笔记；同类经验就 update，不同类就 new。
5. update 时 target_id 必须来自候选笔记，content 必须是更新后的完整 Markdown，不是补丁。
6. update 时尽量保留原笔记有价值内容，提升三位版本号的修订号，增加一条日期记录，再追加或整理新小节。
7. new 时 content 必须从一级标题开始，包含版本行和日期记录行。
8. tags 最多 5 个，folder 用简短中文或英文分类。
9. 删除、失效、外部同步都不要在这里做。

输出 JSON 格式：
{
  "action": "update" 或 "new",
  "target_id": "更新时填写候选笔记 id，新建时为空字符串",
  "folder": "文件夹",
  "tags": ["标签1", "标签2"],
  "content": "完整 Markdown 笔记内容",
  "reason": "一句话说明为什么更新或新建"
}
""".strip()
    handbook = handbook_for_lucy()
    payload = {
        "today": today_text(),
        "user": user,
        "incoming": {"text": text, "folder": folder, "tags": tags},
        "candidate_notes": candidates,
        "handbook": handbook,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def call_lucy_llm(user: str, text: str, folder: str, tags: list[str], candidates: list[dict]) -> tuple[dict | None, dict]:
    if not LUCY_CONFIG.get("api_key"):
        return None, {"used": False, "error": "missing lucy api key"}

    body = {
        "model": LUCY_CONFIG["model"],
        "messages": build_lucy_messages(user, text, folder, tags, candidates),
        "temperature": 0.2,
        "stream": False,
    }
    raw_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        lucy_chat_url(LUCY_CONFIG["base_url"]),
        data=raw_body,
        headers={
            "Authorization": f"Bearer {LUCY_CONFIG['api_key']}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=float(LUCY_CONFIG["timeout"])) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        return None, {"used": True, "model": LUCY_CONFIG["model"], "error": f"llm http {exc.code}: {detail}"}
    except Exception as exc:
        return None, {"used": True, "model": LUCY_CONFIG["model"], "error": str(exc)}

    content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    plan = extract_json_object(content)
    if not plan:
        return None, {"used": True, "model": LUCY_CONFIG["model"], "error": "llm returned non-json content"}
    return plan, {"used": True, "model": LUCY_CONFIG["model"], "reason": str(plan.get("reason") or "")[:160]}


def similarity_score(incoming: dict, note: dict) -> float:
    incoming_tokens = tokenize(incoming["content"])
    note_tokens = tokenize(note["content"])
    if not incoming_tokens or not note_tokens:
        token_score = 0.0
    else:
        token_score = len(incoming_tokens & note_tokens) / max(len(incoming_tokens), 1)

    incoming_tags = set(incoming["tags"])
    note_tags = set(note["tags"])
    tag_score = len(incoming_tags & note_tags) * 0.7
    folder_score = 0.8 if incoming["folder"] and incoming["folder"] == note["folder"] else 0.0
    title_score = 0.0
    incoming_title = short_summary(incoming["content"]).lower()
    note_title = markdown_title(note["content"]).lower()
    if incoming_title and (incoming_title in note_title or note_title in incoming_title):
        title_score = 1.0
    return token_score + tag_score + folder_score + title_score


def find_related_note(user: str, content: str, folder: str, tags: list[str]) -> tuple[dict | None, float]:
    incoming = {"content": content, "folder": folder, "tags": tags}
    best_note: dict | None = None
    best_score = 0.0
    for note in list_notes(user):
        score = similarity_score(incoming, note)
        if score > best_score:
            best_note = note
            best_score = score
    if best_note and best_score >= 1.0:
        return best_note, best_score
    return None, best_score


def bump_patch_version(content: str) -> str:
    def repl(match: re.Match[str]) -> str:
        major, minor, patch = (int(match.group(i)) for i in range(1, 4))
        return f"- 版本：{major}.{minor}.{patch + 1}"

    new_content, count = re.subn(r"^- 版本：(\d+)\.(\d+)\.(\d+)\s*$", repl, content, count=1, flags=re.M)
    if count:
        return new_content
    lines = content.splitlines()
    if lines and lines[0].startswith("#"):
        lines.insert(1, "- 版本：1.0.1")
        return "\n".join(lines)
    return "- 版本：1.0.1\n" + content


def insert_change_log(content: str, author: str, summary: str) -> str:
    lines = content.splitlines()
    entry = f"- {today_text()}：{author} - {summary[:20] or '补充经验'}"
    for index, line in enumerate(lines):
        if line.startswith("- 版本："):
            lines.insert(index + 1, entry)
            return "\n".join(lines)
    if lines and lines[0].startswith("#"):
        lines.insert(1, entry)
        return "\n".join(lines)
    return entry + "\n" + content


def append_experience(existing: str, raw_text: str, author: str) -> str:
    summary = short_summary(raw_text)
    content = bump_patch_version(existing)
    content = insert_change_log(content, author, f"补充{summary}")
    section = f"\n\n## {today_text()} 补充：{summary}\n\n{raw_text.strip()}\n"
    return content.rstrip() + section


def build_new_experience(raw_text: str, author: str) -> str:
    summary = short_summary(raw_text)
    if raw_text.lstrip().startswith("#") and "- 版本：" in raw_text:
        return raw_text.strip()
    return (
        f"# {summary}经验\n"
        "- 版本：1.0.0\n"
        f"- {today_text()}：{author} - 新增{summary}\n\n"
        f"## {today_text()} {summary}\n\n"
        f"{raw_text.strip()}\n"
    )


def lucy_rule_intake(user: str, text: str, author: str, folder: str, tags: list[str], llm_meta: dict | None = None) -> dict:
    related_note, score = find_related_note(user, text, folder, tags)
    if related_note:
        new_content = append_experience(related_note["content"], text, author)
        merged_tags = normalize_tags([*related_note["tags"], *tags])
        note = update_note(related_note["id"], content=new_content, folder=folder or related_note["folder"], tags=merged_tags)
        return {"action": "update", "score": round(score, 3), "note": note, "llm": llm_meta or {"used": False}}

    content = build_new_experience(text, author)
    note = create_note(user, content, folder=folder, tags=tags)
    return {"action": "new", "score": round(score, 3), "note": note, "llm": llm_meta or {"used": False}}


def apply_lucy_plan(user: str, folder: str, tags: list[str], candidates: list[dict], plan: dict, llm_meta: dict) -> dict | None:
    action = str(plan.get("action") or "").strip().lower()
    content = str(plan.get("content") or "").strip()
    plan_folder = normalize_folder(plan.get("folder")) or folder
    plan_tags = normalize_tags(plan.get("tags")) or tags
    candidate_by_id = {candidate["id"]: candidate for candidate in candidates}

    if action == "update":
        target_id = str(plan.get("target_id") or plan.get("id") or "").strip()
        if not target_id or target_id not in candidate_by_id or not content:
            return None
        target = fetch_note(target_id)
        if not target:
            return None
        note = update_note(target_id, content=content, folder=plan_folder or target["folder"], tags=plan_tags)
        return {"action": "update", "score": candidate_by_id[target_id].get("score", 0), "note": note, "llm": llm_meta}

    if action == "new" and content:
        note = create_note(user, content, folder=plan_folder, tags=plan_tags)
        return {"action": "new", "score": 0, "note": note, "llm": llm_meta}

    return None


def lucy_intake(data: dict) -> dict:
    user = normalize_user(data.get("user"))
    text = str(data.get("text") or data.get("content") or "").strip()
    if not text:
        raise ValueError("text is required")
    author = str(data.get("author") or "Lucy").strip() or "Lucy"
    folder = normalize_folder(data.get("folder"))
    tags = normalize_tags(data.get("tags")) or parse_tags(text)

    candidates = candidate_notes_for_lucy(user, text, folder, tags)
    plan, llm_meta = call_lucy_llm(user, text, folder, tags, candidates)
    if plan:
        result = apply_lucy_plan(user, folder, tags, candidates, plan, llm_meta)
        if result:
            return result
        llm_meta = {**llm_meta, "error": "llm plan failed validation"}

    return lucy_rule_intake(user, text, author, folder, tags, llm_meta)


def lucy_draft(data: dict) -> dict:
    user = normalize_user(data.get("user"))
    text = str(data.get("text") or data.get("content") or "").strip()
    if not text:
        raise ValueError("text is required")
    folder = normalize_folder(data.get("folder"))
    tags = normalize_tags(data.get("tags")) or parse_tags(text)
    candidates = candidate_notes_for_lucy(user, text, folder, tags)
    plan, llm_meta = call_lucy_llm(user, text, folder, tags, candidates)
    if plan and str(plan.get("content") or "").strip():
        return {
            "action": str(plan.get("action") or "new").strip().lower(),
            "target_id": str(plan.get("target_id") or "").strip(),
            "folder": normalize_folder(plan.get("folder")) or folder,
            "tags": normalize_tags(plan.get("tags")) or tags,
            "content": str(plan.get("content") or "").strip(),
            "llm": llm_meta,
        }

    related_note, score = find_related_note(user, text, folder, tags)
    content = append_experience(related_note["content"], text, "Lucy") if related_note else build_new_experience(text, "Lucy")
    return {
        "action": "update" if related_note else "new",
        "target_id": related_note["id"] if related_note else "",
        "score": round(score, 3),
        "folder": folder,
        "tags": tags,
        "content": content,
        "llm": llm_meta,
    }


def render_page(path: Path) -> Response:
    body = path.read_text(encoding="utf-8").replace("__API_KEY__", API_KEY)
    return Response(body, mimetype="text/html; charset=utf-8")


@app.before_request
def ensure_database():
    init_db()


@app.get("/")
@app.get("/autonote/")
def index_page():
    return render_page(WWW_DIR / "index.html")


@app.get("/manual.html")
@app.get("/autonote/manual.html")
def manual_page():
    return render_page(WWW_DIR / "manual.html")


@app.get("/autonote/gethb")
@app.get("/autonote/autonotehb.md")
def handbook():
    path = WWW_DIR / "autonotehb.md"
    return Response(path.read_text(encoding="utf-8"), mimetype="text/markdown; charset=utf-8")


@app.get("/autonote/notetemplate.md")
def note_template():
    return send_file(WWW_DIR / "notetemplate.md", mimetype="text/markdown; charset=utf-8")


@app.get("/autonote/health")
def health():
    return jsonify({"ok": True, "service": "autonote", "db": str(DB_PATH), "port": PORT, "lucy_llm": bool(LUCY_CONFIG.get("api_key")), "lucy_model": LUCY_CONFIG.get("model")})


@app.post("/autonote/lucy/intake")
def lucy_intake_route():
    if not require_api_key():
        return auth_error()
    try:
        result = lucy_intake(request_data())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    note = result["note"]
    return jsonify({"ok": True, "id": note["id"], "action": result["action"], "score": result["score"], "draft": note, "note": note, "llm": result.get("llm", {"used": False})})


@app.post("/autonote/lucy/draft")
def lucy_draft_route():
    if not require_api_key():
        return auth_error()
    try:
        result = lucy_draft(request_data())
    except ValueError as exc:
        return jsonify({"ok": False, "error": "text is required"}), 400
    return jsonify({"ok": True, **result})


@app.post("/autonote/notetools/new")
@app.post("/autonote/notetools/notes")
def new_note_route():
    if not require_api_key():
        return auth_error()
    data = request_data()
    try:
        note = create_note(
            normalize_user(data.get("user")),
            str(data.get("content") or ""),
            normalize_folder(data.get("folder")),
            normalize_tags(data.get("tags") or data.get("tag")),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "id": note["id"], "note": note})


@app.get("/autonote/notetools/notes")
def list_notes_route():
    if not require_api_key():
        return auth_error()
    user = normalize_user(request.args.get("user"))
    q = str(request.args.get("q") or "").strip()
    folder = normalize_folder(request.args.get("folder"))
    include_disabled = str(request.args.get("include_disabled") or "").lower() in {"1", "true", "t", "yes"}
    notes = list_notes(user, q=q, include_disabled=include_disabled, folder=folder)
    return jsonify({"ok": True, "count": len(notes), "notes": notes})


@app.get("/autonote/notetools/notes/<note_id>")
def get_note_route(note_id: str):
    if not require_api_key():
        return auth_error()
    note = fetch_note(note_id)
    if not note:
        return jsonify({"ok": False, "error": "note not found"}), 404
    return jsonify({"ok": True, "note": note})


@app.post("/autonote/notetools/read")
def read_note_route():
    if not require_api_key():
        return auth_error()
    note_id = str(request_data().get("id") or "").strip()
    note = fetch_note(note_id)
    if not note:
        return jsonify({"ok": False, "error": "note not found"}), 404
    return jsonify({"ok": True, "note": note})


@app.patch("/autonote/notetools/notes/<note_id>")
@app.post("/autonote/notetools/update")
def update_note_route(note_id: str | None = None):
    if not require_api_key():
        return auth_error()
    data = request_data()
    note_id = note_id or str(data.get("id") or "").strip()
    if not note_id:
        return jsonify({"ok": False, "error": "id is required"}), 400
    try:
        note = update_note(
            note_id,
            content=data.get("content") if "content" in data else None,
            folder=data.get("folder") if "folder" in data else None,
            tags=normalize_tags(data.get("tags") or data.get("tag")) if ("tags" in data or "tag" in data) else None,
        )
    except KeyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "id": note["id"], "note": note})


@app.post("/autonote/notetools/unable")
@app.post("/autonote/notetools/notes/<note_id>/disable")
def disable_note_route(note_id: str | None = None):
    if not require_api_key():
        return auth_error()
    note_id = note_id or str(request_data().get("id") or "").strip()
    try:
        note = set_note_enable(note_id, False)
    except KeyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "id": note["id"], "note": note})


@app.post("/autonote/notetools/notes/<note_id>/enable")
def enable_note_route(note_id: str):
    if not require_api_key():
        return auth_error()
    try:
        note = set_note_enable(note_id, True)
    except KeyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "id": note["id"], "note": note})


@app.delete("/autonote/notetools/notes/<note_id>")
@app.post("/autonote/notetools/del")
def delete_note_route(note_id: str | None = None):
    if not require_api_key():
        return auth_error()
    note_id = note_id or str(request_data().get("id") or "").strip()
    try:
        delete_note(note_id)
    except KeyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "id": note_id})


@app.post("/autonote/notetools/search")
def search_notes_route():
    if not require_api_key():
        return auth_error()
    data = request_data()
    notes = list_notes(
        normalize_user(data.get("user")),
        q=str(data.get("q") or data.get("text") or "").strip(),
        include_disabled=bool(data.get("include_disabled")),
        folder=normalize_folder(data.get("folder")),
    )
    return jsonify({"ok": True, "count": len(notes), "notes": notes})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORT, threaded=True)