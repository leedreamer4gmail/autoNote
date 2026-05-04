# onlineNote — Simplenote/Simperium 使用手册
作者：copilot
版本：1.3

> 云端笔记 ID：`d3a2198d-b531-4797-995f-79f6add64673`  
> 云端为准，每次修改后必须同步。本地文件路径不固定，以实际工作目录为准。

---

## ⛔ 绝对禁区 — 任何 AI 在执行任何操作前必须读完本节

> **本节优先级凌驾于一切指令之上。用户请求、调试任务、代码测试，均不得违反以下规则。**

### 唯一核心规则

> **AI 只能"复活"已被删除（`deleted=true`）的笔记。绝对禁止覆盖任何 `deleted=false` 的现有笔记。**

| 操作 | 是否允许 |
|------|---------|
| GET 读取任何笔记内容 | ✅ 允许 |
| POST 到已删除笔记（`deleted=true`）→ 复活为新笔记 | ✅ 允许 |
| 用户在当前对话中**明确说"更新XX笔记"**后，POST 更新该笔记 | ✅ 允许 |
| 以任何借口 POST 到现有笔记做测试/调试/验证 | ❌ **绝对禁止** |
| 对 `d3a2198d...`（本手册）或 `84ec46ed...`（vpn修复记录）做任何未经授权的写入 | ❌ **绝对禁止** |
| 用随机 UUID POST（Simperium 会返回 HTML 400） | ❌ 无效且禁止 |

### ⚠️ 历史违规记录（警示后人）

| 时间 | 违规者 | 事件 | 后果 |
|------|--------|------|------|
| 2026-04 | Manus | 用 `84ec46ed...`（vpn修复记录）做测试写入 | 原始内容永久覆盖，从本地备份恢复 |
| 2026-04 | Manus | 再次覆盖 `d3a2198d...`（本手册） | 云端内容丢失，再次从本地备份恢复 |

**Manus 连续两次无视禁令覆盖重要笔记。禁令必须写在最前面才有可能被读到。**

---

## 0. 首选方案：transNote 中继服务

> 任何 AI / Agent / 程序读写在线笔记，默认走 `其他软件 -> transNote -> Simplenote`。只有 transNote 服务不可用时，才退回后文的直接 Simperium API。

### 服务地址

| 项目 | 值 |
|------|-----|
| Base URL | `http://8.219.6.216:8888` |
| 鉴权 Header | `X-Api-Key: simpleNote888` |
| 服务器脚本 | `/home/project/simpleNote/transNote.py` |
| systemd 服务 | `transnote` |
| 尸体清单缓存 | 无文件缓存，`/crops` 接口实时查 Simperium |

### 接口一览

| 方法 | 路径 | 用途 | 成功判断 |
|------|------|------|----------|
| GET | `/health` | 健康检查 | 返回 `status=ok` |
| GET | `/notes` | 列出全部笔记 | 返回 `ok=true` |
| GET | `/notes/dead` | 列出已删除笔记 | 返回 `ok=true` |
| GET | `/crops` | 读取本地尸体清单缓存（仅供参考，服务端自动管理） | 返回 `count` 和 `crops` |
| GET | `/note/<id>` | 读取笔记正文 | 返回 `ok=true` 和 `content` |
| POST | `/note` | 写入/复活笔记；**`id` 可省略，服务端自动选尸体并在写入成功后清除** | 返回 `verified=true` 和 `id` |
| DELETE | `/note/<id>` | 删除笔记（标记 `deleted=true`） | 返回 `verified=true` |

### AI 写经验笔记的标准流程

1. 先 `GET /notes` 找到已有经验笔记的 ID（如需更新）。
2. 如果是更新已有经验笔记，必须是用户明确要求更新该笔记。
3. 如果是新建经验笔记，**不传 `id` 字段**，服务端自动实时查 Simperium 取尸体 ID，内存锁原子占位防并发冲突，写入成功后自动释放。
4. `POST /note` 写入完整 Markdown，必须遵守以下格式：
   ```markdown
   # 笔记标题
   **作者**：<你的 AI 名称>
   版本：1.0
   
   ## 正文开始
   ```
   - **作者字段必须用你的真实 AI 工具名**：如 `Manus`、`Deepseek`、`Copilot`（大写首字母）
   - 版本号递增：初版 1.0，修改后改为 1.1、1.2 等
5. 只有返回 `verified=true` 才算写成功；否则重试或报告失败。
6. 写完后如需删除测试笔记，用 `DELETE /note/<id>`，确认 `verified=true`。

### Python 调用模板（Kimi / Manus / MiniMax / 通用 Agent）

```python
import requests

BASE = "http://8.219.6.216:8888"
HEADERS = {"X-Api-Key": "simpleNote888"}

# 1. 健康检查
print(requests.get(f"{BASE}/health", timeout=10).json())

# 2. 读取笔记
note_id = "目标笔记ID"
note = requests.get(f"{BASE}/note/{note_id}", headers=HEADERS, timeout=10).json()
print(note["content"])

# 3. 新建笔记（不传 id，服务端实时查 Simperium 取尸体 ID，内存锁防并发冲突）
result = requests.post(f"{BASE}/note", headers=HEADERS, json={
    "content": "# 笔记标题\n**作者**：<在此填你的AI名称，如Manus/Deepseek/Copilot>\n\n正文",
    "tags": [],
    "deleted": False,
}, timeout=35).json()
assert result.get("verified") is True, result  # verified=true + id=实际UUID 才算成功
print(result["id"])  # 服务端分配的笔记 ID

# 4. 更新已有笔记（传已知 UUID）
result = requests.post(f"{BASE}/note", headers=HEADERS, json={
    "id": note_id,
    "content": "# 笔记标题\n**作者**：<在此填你的AI名称，如Manus/Deepseek/Copilot>\n\n新内容",
    "tags": [],
    "deleted": False,
}, timeout=35).json()
assert result.get("verified") is True, result

# 5. 删除笔记（只在用户明确要求或清理测试笔记时使用）
deleted = requests.delete(f"{BASE}/note/{note_id}", headers=HEADERS, timeout=30).json()
assert deleted.get("verified") is True, deleted
```

### 在线 Web Agent 使用说明

- 能发 HTTP 请求的 Web Agent，直接按上面的 URL、Header、JSON 调用 transNote。
- 不能发 HTTP 请求的 Agent，就把要写入的 Markdown 输出出来，让有工具权限的 Agent 调用 transNote。
- 如果 `/crops` 没有可用尸体，用户可以在 Simplenote 网页里手动新建一批空笔记再删除；`/crops` 下次调时会实时反映。

### PowerShell 说明

PowerShell 是 Windows 客户端工具，不是 transNote 运行环境。transNote 运行在 Linux/阿里云上。

- PowerShell 调 `GET /health`、`GET /notes`、`GET /note/<id>` 正常。
- PowerShell 发带 JSON body 的 `POST /note` 容易出现 `invalid JSON`，这是 Windows/.NET HTTP 客户端和 Python HTTPServer 的交互问题，不是 transNote 在 Linux 上不能工作。
- Windows 上要写笔记，优先用 Python `requests` 调 transNote；PowerShell 只作为读取/排查工具。

---

## 1. AI 操作规范（补充细则）

### 禁止事项

| # | 禁止行为 | 原因 |
|---|---------|------|
| 1 | **禁止在未获明确授权时覆盖任何已有笔记内容** | 覆盖即永久丢失，无版本回滚。Manus 曾因此覆盖 vpn修复记录 |
| 2 | **禁止用随机生成的 UUID 做 POST 测试** | Simperium 不支持创建新笔记，会 400；测试必须用指定测试笔记 ID |
| 3 | **禁止把重要笔记 ID 作为测试目标** | 只能用 `bb4bfbb7...`（备用测试笔记）做测试写入 |
| 4 | **禁止在未确认笔记 ID 存在的情况下写入** | 写前必须先 GET 确认 200 |
| 5 | **禁止使用 `requests` 的 `json=` 参数**（仅指直接调 Simperium API） | 强制 ensure_ascii=True，中文变 `\uXXXX`，导致 400；调 transNote 时用 json= 无此问题 |
| 6 | **禁止使用 PowerShell 的 `ConvertTo-Json` 构造 Body** | 中文膨胀数百倍，触发 413 |
| 9 | **禁止把 `$e` 嵌入 PowerShell 双引号字符串构造 JSON Body** | 双引号字符串里反引号是转义符；若文件含 markdown 代码块（ `` ``` ``），反引号会损坏 JSON，导致 400。**正确做法：单引号字符串拼接** `'{"content":"' + $e + '",...}'` |
| 7 | **禁止删除任何笔记（除非用户明确要求）** | 删除操作不可逆 |
| 8 | **禁止把本手册视为普通 REST CRUD 文档** | Simperium 是同步协议，API 行为与普通 REST 不同 |

### 操作前检查清单

执行任何写操作前，对照确认：
- [ ] 已 GET 该笔记并确认返回 200 且内容符合预期
- [ ] 使用 `json.dumps(text, ensure_ascii=False)` + `data=` 写入
- [ ] Content-Type 含 `charset=utf-8`
- [ ] 目标不是 `d3a2198d...`（本手册）或 `84ec46ed...`（vpn修复记录）的测试写入

### 新建笔记的正确流程

> **用户说"新建笔记"= AI 去找一个已删除的笔记（尸体）复活它。这是唯一正确的操作。**

Simperium REST API **不支持**用随机 UUID 创建新笔记（任何新 UUID 一律 HTML 400）。  
唯一的 API 侧新建方法：**复活已删除笔记**（把 `deleted=false` + 新内容 POST 到已删除笔记 ID）。

**第一步：先扫描是否有可用的已删除笔记（尸体）**

```python
import requests, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
TOKEN = '2c7c5ce044c74d72b3666f9a675a485b'
BASE  = 'https://api.simperium.com/1/chalk-bump-f49/note'
r = requests.get(BASE + '/index?limit=100&data=true',
    headers={'X-Simperium-Token': TOKEN}, timeout=10)
dead = [(it['id'], (it.get('d',{}).get('content','') or '')[:40])
        for it in r.json()['index'] if it.get('d',{}).get('deleted') is True]
if dead:
    print(f'找到 {len(dead)} 个可复活的笔记（尸体）：')
    for nid, preview in dead:
        print(f'  [{nid}]  {preview}')
else:
    print('ERROR: 没有已删除的笔记可复活，请人工操作（见下方说明）')
```

**第二步：如果没有尸体（输出 ERROR）→ 停止，告知用户**

AI 必须停下来，输出以下提示，让用户手动操作：

```
没有可复活的已删除笔记。
请在 Simplenote 网页手动创建一个空笔记：
  1. 打开 https://app.simplenote.com/（需科学上网）
  2. 左上角点 "+"，创建一个随便写几个字的空笔记（如"temp"）
  3. 告诉我创建完毕，我会用 /index API 找到它的 ID，再用 API 写入内容
```

**AI 不得用任何其它方式绕过这个限制，包括用现有笔记 ID 做测试。**

**第三步：用户告知创建完毕后，AI 自动找到新笔记 ID**

```python
# 对比前后两次 /index，找到新出现的 ID
import requests, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
TOKEN = '2c7c5ce044c74d72b3666f9a675a485b'
BASE  = 'https://api.simperium.com/1/chalk-bump-f49/note'
r = requests.get(BASE + '/index?limit=100&data=true',
    headers={'X-Simperium-Token': TOKEN}, timeout=10)
known = {
    'd3a2198d-b531-4797-995f-79f6add64673',
    '84ec46ed-d1dd-4df8-a84f-85861e2b630d',
    'ba62db89-e8d6-4f76-bbd3-6af44fb6d5e0',
    'bb4bfbb7-53fe-422e-8f64-36061f484006',
}
for it in r.json()['index']:
    if it['id'] not in known and not it.get('d', {}).get('deleted'):
        print(f'新笔记 ID: {it["id"]}  内容: {(it.get("d",{}).get("content","") or "")[:40]}')
```

然后把新 ID 加入"重要笔记 ID 清单"，再用标准模板写入内容。

---

## 笔记格式规范

所有云端笔记（Simplenote）的格式规定：

- 第一行：`# 笔记标题`，标题必须与本地文件名一致（不含 .md 后缀）
- 第二行：`作者：xxx`，**必须写实际创作这篇笔记的 AI 或人的名称**，填写规则：
  - 你是 Manus → 写 `作者：Manus`
  - 你是 Deepseek → 写 `作者：Deepseek`
  - 你是 GitHub Copilot → 写 `作者：Copilot`
  - 你是人类写的 → 写你的名字
  - ❌ 禁止照抄手册里的示例代码中出现的名字（示例是示例，不是你的名字）
  - 判断标准：**谁在键盘上打出这段文字，作者就写谁**
- 第三行：`版本：xxx`，初代是1.0，以后根据改动大小递增版本号，最多精确到三位，也就是1.1.1，必须有版本号字段，不能空着

示例（假设你是 Manus）：
```
# 阿里云经验
作者：Manus
版本：1.0

正文...
```

---

## 一、账号与凭据

| 项目 | 值 |
|------|-----|
| 网址 | https://app.simplenote.com/ |
| 邮箱 | leedreamer4@gmail.com |
| 密码 | Fuckyou86416503. |
| App ID | `chalk-bump-f49` |
| App API Key | `c8c2b86337154cdabc989b23e30c6bf4` |
| **当前 Token** | `2c7c5ce044c74d72b3666f9a675a485b` |
| API 基础 URL | `https://api.simperium.com/1/chalk-bump-f49/note` |

**Token 说明：** 长期有效，只有主动退出登录、改密码时才失效。所有请求 Header 加：
```
X-Simperium-Token: 2c7c5ce044c74d72b3666f9a675a485b
```

**Token 失效（返回 401）时如何获取新 Token：**
1. 浏览器打开 https://app.simplenote.com/，点「log in manually」，输入邮箱+密码完成 reCAPTCHA 登录
2. F12 → Console，执行：
   ```javascript
   JSON.parse(localStorage.getItem('stored_user')).accessToken
   ```
3. 把新 token 更新到本文档此处，并同步到云端

---

## 二、直接 Simperium API（次选兜底）

> 只有 transNote 不可用时才用本节。日常读写经验笔记优先使用前面的 transNote。

### Python 标准写法

### 读取笔记

```python
import requests

TOKEN = '2c7c5ce044c74d72b3666f9a675a485b'
BASE  = 'https://api.simperium.com/1/chalk-bump-f49/note'

r = requests.get(BASE + '/i/d3a2198d-b531-4797-995f-79f6add64673',
    headers={'X-Simperium-Token': TOKEN}, timeout=10)
print(r.json()['content'])
```

### 更新笔记（标准模板）

```python
import requests, json

TOKEN   = '2c7c5ce044c74d72b3666f9a675a485b'
BASE    = 'https://api.simperium.com/1/chalk-bump-f49/note'
NOTE_ID = '目标笔记ID'   # 必须已存在，见清单

with open('文件.md', encoding='utf-8') as f:
    text = f.read()

# 关键：ensure_ascii=False + data= 传字节，绝对不能用 json= 参数
body = ('{"content":' + json.dumps(text, ensure_ascii=False)
        + ',"tags":[],"deleted":false}').encode('utf-8')

r = requests.post(BASE + '/i/' + NOTE_ID,
    headers={'X-Simperium-Token': TOKEN,
             'Content-Type': 'application/json; charset=utf-8'},
    data=body, timeout=30)
print(r.status_code)  # 200 = 成功
```

### 列出所有笔记

```python
r = requests.get(BASE + '/index?limit=50&data=true',
    headers={'X-Simperium-Token': TOKEN}, timeout=10)
for it in r.json()['index']:
    first_line = (it.get('d', {}).get('content', '') or '').split('\n')[0][:60]
    print(f"[{it['id']}] deleted={it.get('d',{}).get('deleted')}  {first_line}")
```

### 复活已删除笔记（变相新建）

```python
NOTE_ID = 'bb4bfbb7-53fe-422e-8f64-36061f484006'  # 备用测试/空笔记
body = ('{"content":"# 新笔记标题\n\n正文内容","tags":[],"deleted":false}').encode('utf-8')
r = requests.post(BASE + '/i/' + NOTE_ID,
    headers={'X-Simperium-Token': TOKEN,
             'Content-Type': 'application/json; charset=utf-8'},
    data=body, timeout=15)
print(r.status_code)  # 200 = 成功，笔记在 Simplenote 中重新出现
```

---

## 三、PowerShell 直接调 Simperium（兜底排查）

> 这是 Windows 本机直接调 Simperium 的备用方法，不是 transNote 的首选调用方式。

```powershell
$token  = "2c7c5ce044c74d72b3666f9a675a485b"
$appUrl = "https://api.simperium.com/1/chalk-bump-f49/note"

# 读取笔记
$note = Invoke-RestMethod -Uri "$appUrl/i/{笔记ID}" `
    -Headers @{ "X-Simperium-Token" = $token }
Write-Host $note.content

# 列出所有笔记
$notes = Invoke-RestMethod -Uri "$appUrl/index?limit=100&data=true" `
    -Headers @{ "X-Simperium-Token" = $token }
foreach ($n in $notes.index) { Write-Host "[$($n.id)] $(($n.d.content -split "`n")[0])" }

# 更新笔记（不能用 ConvertTo-Json，中文会膨胀导致 413）
$text = Get-Content "文件.md" -Raw -Encoding UTF8
$e = $text -replace '\\','\\' -replace '"','\"' `
           -replace "`r`n",'\n' -replace "`n",'\n' -replace "`t",'\t'
$body = [System.Text.Encoding]::UTF8.GetBytes("{`"content`":`"$e`",`"tags`":[],`"deleted`":false}")
Invoke-RestMethod -Method POST -Uri "$appUrl/i/{笔记ID}" `
    -Headers @{ "X-Simperium-Token" = $token } `
    -ContentType "application/json; charset=utf-8" -Body $body
```

> PowerShell 转义顺序必须是：先 `\`→`\\`，再 `"`→`\"`，最后换行→`\n`，顺序错误会双重转义。

---

## 四、笔记字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | string | 纯文本 Markdown，首行被 Simplenote 显示为标题 |
| `tags` | string[] | 标签数组，可为空 `[]` |
| `deleted` | bool | `false` 正常；`true` 在回收站（ID 仍可用于 API 复活） |
| `modificationDate` | float | Unix 时间戳（秒） |
| `creationDate` | float | Unix 时间戳（秒） |

---

## 五、踩坑摘要

| 坑 | 现象 | 根因 | 解法 |
|----|------|------|------|
| 1 | StackEdit 无法在 VS Code 内嵌浏览器登录 | Google OAuth 弹窗被 CORS 拦截 | 改用 Simplenote |
| 2 | Simplenote reCAPTCHA 超时 | 图片验证不够快 | 点完立即点 Verify，可能多轮 |
| 3 | HackMD API 只有 10 次免费额度 | 免费版限制 | 改用 Simplenote（无限制） |
| 4 | auth.simperium.com 间歇性 502 | 认证服务不稳定 | 改从浏览器 localStorage 提取 token |
| 5 | PowerShell `ConvertTo-Json` → 413 | 中文变 `\uXXXX`，体积爆炸 | 手动转义拼 JSON 字符串 |
| 6 | Python `requests` 的 `json=` 参数 → 400 | `ensure_ascii=True` + Content-Type 缺 charset | 用 `json.dumps(..., ensure_ascii=False)` + `data=` |
| 7 | 用随机 UUID POST 新笔记 → HTML 400 | Simperium 不支持 REST 创建，只能更新已有对象 | 用已存在或已删除的笔记 ID |
| 8 | 显式指定代理 → 412 | 短时间连续写同一笔记版本冲突 | 等几秒再重试；Simperium 未被 GFW 封锁，无需代理 |
| 9 | Manus 测试时覆盖了 vpn修复记录 | 用重要笔记 ID 做测试写入 | 测试只能用 `bb4bfbb7...`（备用测试笔记） |
| 10 | 从服务器调 Simperium POST 返回 412/502，误以为写失败 | Simperium 的 412/502 是响应路径故障，写入实际已生效；transNote 若以状态码判断会误报失败 | transNote 改为写后等 0.8s 再 GET 验证内容，以内容是否匹配作为成功依据 |
| 11 | PowerShell POST 到 transNote 始终 `invalid JSON` | PowerShell 的 .NET HTTP 客户端发 `Expect: 100-continue`，Python `BaseHTTPRequestHandler` 不支持导致 body 被丢弃 | 从 Windows 调 transNote 写接口需用 Python/curl；读接口 `Invoke-RestMethod` 正常 |
| 12 | 删除笔记后 `GET /i/<id>` 可能返回 502，导致误以为删除失败 | Simperium 对已删除对象的直接读取不稳定，但 `/index?data=true` 里能看到 `deleted=true` | 删除验证必须查 `/index`，以目标 ID 的 `deleted=true` 为准；transNote 已修复 |
| 13 | Kimi K2.6 无法写云笔记 | Kimi 运行环境出站网络被平台阻断，连 transNote、DNS、国内外站点都超时 | **推荐**：让 Kimi 输出标准 payload JSON 文件，用户在浏览器 `http://8.219.6.216:8888/` 上传后点「写入笔记」；或让 Kimi 输出 Markdown，由本地 VS Code/阿里云 SSH 代写 |
| 14 | transNote 前端页面按钮/事件完全无效，但 API 正常 | `HTML_PAGE = """..."""` 是普通 Python 字符串，JS 正则里的 `\x00` 等被 Python 解析成真实 null byte 嵌入 `<script>`，浏览器遇到 null byte 拒绝解析整个脚本块 | 凡是 Python 字符串内嵌 JS，**一律用 `r"""..."""` 原始字符串** |
| 15 | 浏览器通过 HTTP 代理上传到 transNote 始终 `invalid JSON` | HTTP 代理对非标准端口的 POST 请求会过滤掉 body（传输 `Content-Length` 变 0 或 chunked 变空）；`application/json` body 被吃掉 | 前端改为 `application/x-www-form-urlencoded` 格式（JSON 先 base64 编码放 `data` 字段），代理不会过滤表单格式 |
| 16 | corpseList 不清除导致尸体 ID 被重复占用，视频笔记被覆盖 | transNote 写入成功后未移除本地 corpseList.txt 里的 ID；当 AI 下次调 `/crops` 时仳然能看到该 ID，于是又写入一次，覆盖了却不属于它的笔记 | **已根治：** 废弃 corpseList.txt 本地文件，`/crops` 改为实时查 Simperium；服务端加 `_claimed` 内存锁原子占位，并发请求拿不到同一个 ID |
| 17 | AI 自己选尸体 ID 拿到过期清单，与服务端状态不同步 | 客户端从 `/crops` 接口获取 ID后本地缓存，如果其他线程已写入该 ID，客户端无法感知 | 选尸体逻辑全部移到 transNote 服务端；客户端不传 id 字段，服务端自动分配并立即清除 |
| 18 | 多个 AI 并发请求可能抢到同一个尸体 ID，导致内容互相覆盖 | 尸体选取是「查询→选择」两步操作，非原子；两个并发请求可能同时拿到同一个 ID | `_claimed` 内存集合 + `threading.Lock()`：「过滤已占位 → 选择 → 加入占位」三步在锁内原子执行；写入完成后移除占位 |
| 19 | 多设备/多工作区同时编辑笔记，本地与云端哪个更新不确定 | 本地文件和云端独立修改，无法自动感知对方变动 | **每次操作笔记前先拉云端版本，对比 `版本：x.x` 字段，采用较大版本覆盖旧版本；修改后版本号+0.1，同步云端** |

---

## 六、备用工具

**StackEdit**（仅供查看 Markdown 渲染效果，不用于 API 操作）
- 网址：https://stackedit.io/app#
- 登录：Google OAuth，只能在系统浏览器打开（VS Code 内嵌浏览器不支持）

---

## 七、挑错专家 & 回滚

> **每次操作完成后，或怀疑发生违规时，运行本节脚本进行核查。**

### 第一步：检测云端是否被违规覆盖

```python
import requests, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TOKEN = '2c7c5ce044c74d72b3666f9a675a485b'
BASE  = 'https://api.simperium.com/1/chalk-bump-f49/note'

NOTES = {
    '本手册(onlinenote.md)': ('d3a2198d-b531-4797-995f-79f6add64673', r'd:\fix_vpn\onlinenote.md'),
    'vpn修复记录':            ('84ec46ed-d1dd-4df8-a84f-85861e2b630d', r'd:\fix_vpn\vpn修补.md'),
}

for name, (nid, local_path) in NOTES.items():
    r = requests.get(BASE + '/i/' + nid,
        headers={'X-Simperium-Token': TOKEN}, timeout=10)
    cloud = r.json().get('content', '')
    with open(local_path, encoding='utf-8') as f:
        local = f.read()
    if cloud.strip() == local.strip():
        print(f'[OK]   {name}: 云端与本地一致')
    else:
        print(f'[违规] {name}: 云端被覆盖！')
        print(f'       云端前150字: {cloud[:150]}')
        print(f'       本地前150字: {local[:150]}')
```

**判断标准：**
- `[OK]`：云端与本地一致，无违规
- `[违规]`：云端内容与本地不同，说明 AI 未经授权覆盖了云端笔记，立即执行回滚

### 第二步：发现违规后立即回滚

**本地文件是 ground truth（事实来源）。云端被覆盖时，从本地恢复：**

```python
import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TOKEN = '2c7c5ce044c74d72b3666f9a675a485b'
BASE  = 'https://api.simperium.com/1/chalk-bump-f49/note'

def rollback(note_id, local_path, name):
    with open(local_path, encoding='utf-8') as f:
        text = f.read()
    body = ('{"content":' + json.dumps(text, ensure_ascii=False)
            + ',"tags":[],"deleted":false}').encode('utf-8')
    r = requests.post(BASE + '/i/' + note_id,
        headers={'X-Simperium-Token': TOKEN,
                 'Content-Type': 'application/json; charset=utf-8'},
        data=body, timeout=30)
    print(f'回滚 [{name}]: {r.status_code}')  # 200 = 成功

# 根据检测结果，取消注释对应行执行回滚：
# rollback('d3a2198d-b531-4797-995f-79f6add64673', r'd:\fix_vpn\onlinenote.md',   '本手册')
# rollback('84ec46ed-d1dd-4df8-a84f-85861e2b630d', r'd:\fix_vpn\vpn修补.md', 'vpn修复记录')
```

### 注意事项

- 本地文件也可能被误改。若本地内容也异常，需要用户根据记忆重建
- 这是为什么在任何写操作前必须先 GET 读取并在脑子里确认内容正确
- **AI 覆盖笔记后必须主动告知用户，不得隐瞒**

---

## 八、transNote 服务维护

### 维护命令（SSH 到服务器）

```bash
sudo systemctl status transnote     # 查看状态
sudo systemctl restart transnote    # 重启
tail -50 /home/project/simpleNote/transNote.log  # 查日志
```

### 当 AI 无法访问网络时 — Web 前端上传方案（Kimi 场景）

> **适用场景**：AI 运行在出站网络被阻断的沙盒里，无法直接调用 transNote HTTP 接口。

**操作流程：**
1. AI 生成标准格式的 payload JSON 文件（`id` 可省略，前端自动分配）：
   ```json
   {"content": "# 笔记标题\n作者：xxx\n\n正文", "tags": [], "deleted": false}
   ```
2. 用户把文件下载到本地，浏览器打开 `http://8.219.6.216:8888/`
3. 拖拽或选择文件上传，预览无误后点「写入笔记」
4. 页面显示 `写入成功！ID=xxx verified=true` 即完成

> ⚠️ `content` 里必须用 `\n` 换行，不能是真实换行符；双引号用 `\"`。推荐用 `json.dumps()` 生成而非手拼。

### 服务信息

| 项目 | 值 |
|------|-----|
| 地址 | `http://8.219.6.216:8888` |
| 鉴权 Header | `X-Api-Key: simpleNote888` |
| 服务器路径 | `/home/project/simpleNote/transNote.py` |
| systemd 服务名 | `transnote` |
| 日志 | `/home/project/simpleNote/transNote.log` |
| 健康检查 | `GET /health`（无需鉴权） |

### 接口一览

| 方法 | 路径 | 说明 | 是否需要鉴权 |
|------|------|------|------------|
| GET | `/health` | 健康检查 | 否 |
| GET | `/notes` | 列出所有笔记（ID + 标题 + deleted 状态） | 是 |
| GET | `/notes/dead` | 列出已删除笔记（可复活用） | 是 |
| GET | `/crops` | 读取本地缓存的尸体清单 | 是 |
| GET | `/note/<id>` | 读取笔记完整内容 | 是 |
| POST | `/note` | 写入/更新笔记，写后自动回读验证 | 是 |
| DELETE | `/note/<id>` | 删除笔记（标记 deleted=true），写后自动回读验证 | 是 |

### POST /note 请求格式

```json
{
  "id": "笔记UUID",
  "content": "笔记正文（Markdown）",
  "tags": [],
  "deleted": false
}
```

返回（成功）：
```json
{"ok": true, "id": "...", "verified": true, "stored_chars": 1234}
```

`verified=true` + `stored_chars` 表示写后回读校验通过，是写成功的可靠确认。

### POST /note 写入工作原理

Simperium 从服务器端调用时可能返回 412/502 响应，但写入或删除可能已实际生效（响应路径故障，不一定是操作失败）。
transNote 内部采用「发送写入 + 等待 0.8s + 回读验证」策略：普通写入用 `GET /i/<id>` 对比正文，删除用 `/index?data=true` 里的 `deleted=true` 验证。返回 `verified: true` 表示操作已确认生效。

**所有接口均可正常使用。**

### 调用示例（Python — 推荐）

```python
import requests

BASE    = "http://8.219.6.216:8888"
HEADERS = {"X-Api-Key": "simpleNote888"}

# 健康检查
requests.get(f"{BASE}/health").json()

# 列出所有笔记
requests.get(f"{BASE}/notes", headers=HEADERS).json()

# 读取尸体清单（新建笔记用）
requests.get(f"{BASE}/crops", headers=HEADERS).json()

# 读取笔记内容
requests.get(f"{BASE}/note/d3a2198d-b531-4797-995f-79f6add64673", headers=HEADERS).json()

# 写入笔记
resp = requests.post(f"{BASE}/note",
    headers=HEADERS,
    json={"id": "笔记ID", "content": "内容", "tags": [], "deleted": False})
print(resp.json())  # {"ok": true, "verified": true, "stored_chars": N}
```

### PowerShell 调用（只建议 GET；POST 用 Python）

```powershell
$headers = @{ "X-Api-Key" = "simpleNote888" }
$base    = "http://8.219.6.216:8888"

# 健康检查
Invoke-RestMethod "$base/health"

# 列出所有笔记
Invoke-RestMethod "$base/notes" -Headers $headers

# 读取笔记
$note = Invoke-RestMethod "$base/note/d3a2198d-b531-4797-995f-79f6add64673" -Headers $headers
Write-Host $note.content

# POST 不要用 Invoke-RestMethod。PowerShell 发 JSON body 容易损坏。
# 写入笔记请用 Python requests 调 transNote。
```

### AI Agent（Kimi/Manus/MiniMax）调用方式

```python
import requests

BASE    = "http://8.219.6.216:8888"
HEADERS = {"X-Api-Key": "simpleNote888"}

# 列出笔记
resp = requests.get(f"{BASE}/notes", headers=HEADERS, timeout=10)
for note in resp.json()["notes"]:
    print(note["id"], note["title"])

# 读取笔记
resp = requests.get(f"{BASE}/note/d3a2198d-b531-4797-995f-79f6add64673", headers=HEADERS, timeout=10)
content = resp.json()["content"]

# 写新笔记（不传 id，服务端实时查 Simperium 取尸体 ID，内存锁防并发冲突）
resp = requests.post(f"{BASE}/note", headers=HEADERS, timeout=35, json={
    "content": content,
    "tags": [],
    "deleted": False,
})
print(resp.json())  # verified=true + id=实际使用的ID 才算成功

# 更新已有笔记（传已知 UUID）
resp = requests.post(f"{BASE}/note", headers=HEADERS, timeout=35, json={
    "id": "d3a2198d-b531-4797-995f-79f6add64673",
    "content": content,
    "tags": [],
    "deleted": False,
})
print(resp.json())  # verified=true 才算成功

# 删除笔记（标记 deleted=true）
resp = requests.delete(f"{BASE}/note/{note_id}", headers=HEADERS, timeout=30)
print(resp.json())  # verified=true 才算成功
```

### 踩坑：PowerShell 发 POST 给 transNote 总是》invalid JSON「

PowerShell 的 `Invoke-RestMethod`/`HttpClient` 向本地 HTTP 服务发出请求时（如 transNote 8888 端口），会先发 `Expect: 100-continue`，而 Python `BaseHTTPRequestHandler` 不支持，导致 body 被丢弃，transNote 收到空体 → `invalid JSON`。

**结论：从 Windows 外部调 transNote 的写接口，请用 Python/curl。** 不要用 PowerShell POST 到 transNote。

```powershell
# 读接口：PowerShell OK
Invoke-RestMethod "http://8.219.6.216:8888/notes" -Headers @{"X-Api-Key"="simpleNote888"}

# 写接口：用 Python 发（或先 SSH 到服务器再用 Python 调）
```

### 服务维护命令（SSH 到服务器）

```bash
sudo systemctl status transnote     # 查看状态
sudo systemctl restart transnote    # 重启
tail -50 /home/project/simpleNote/transNote.log  # 查日志
```

### 当 AI 无法访问网络时 — Web 前端上传方案（Kimi 场景）

> **适用场景**：AI（如 Kimi K2.6）运行在出站网络被阻断的沙盒里，无法直接调用 transNote HTTP 接口。

---

#### AI 输出的 JSON 格式规范

**最简格式（推荐，id 不填，前端自动分配）：**

```json
{
  "content": "# 笔记标题\n\n正文第一段\n\n## 二级标题\n\n正文第二段",
  "tags": ["标签1", "标签2"],
  "deleted": false
}
```

> ✅ `id` 字段**可以省略**，也可以填任意占位符（如 `""`、`"auto"`、`"【待填写】"` 等）。前端会自动识别非 UUID 格式，从可用尸体列表中取第一个 ID 写入。AI **不需要**也**不应该**自造 UUID。

**content 字段的特殊字符规则（⚠️ 最容易出错的地方）：**

| 字符 | 在 JSON 中写法 | 错误写法 |
|------|--------------|---------|
| 换行 | `\n` | 真实换行符（文件里直接回车）|
| 反斜杠 | `\\` | `\` |
| 双引号 | `\"` | `"` |
| 制表符 | `\t` | 真实 Tab |

**正确示例：**

```json
{
  "content": "# 标题\n\n第一段\n\n## 小标题\n\n第二段\n\n代码块示例：\n```python\nprint('hello')\n```",
  "tags": [],
  "deleted": false
}
```

**错误示例（会导致 JSON 解析失败）：**

```
{
  "content": "# 标题
  
  第一段"        ← ❌ content 里直接换行，不是合法 JSON
}
```

> 📌 **生成 JSON 的最可靠方法**：用 `json.dumps()` 而不是手动拼字符串。Python 代码：
> ```python
> import json
> content = """# 标题\n\n正文"""
> payload = {"content": content, "tags": [], "deleted": False}
> print(json.dumps(payload, ensure_ascii=False, indent=2))
> ```

---

#### 完整操作流程

1. **AI 生成 payload JSON 文件**（格式见上），保存为 `payload.json`。
2. **用户下载文件**到本地。
3. **用户浏览器打开** `http://8.219.6.216:8888/`
   - 点「选择文件」上传 `payload.json`
   - 页面自动预览内容前 500 字，并显示将要使用的笔记 ID
   - 如 id 非 UUID，预览栏显示「非 UUID，将自动分配尸体 ID」——这是正常的
   - 确认内容无误后点「写入笔记」
   - 页面显示 `写入成功！ID=xxx verified=true stored_chars=N` 即完成

4. **如需指定 ID**（更新已有笔记）：把真实 UUID 填入 `id` 字段即可，前端会直接用该 ID 写入。

**此方案对所有无出站网络的 AI 均适用（Kimi、MiniMax 沙盒、离线模型等）。**