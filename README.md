# autoNote — Simplenote HTTP 代理服务

一个轻量级 HTTP 服务，用于通过 Simplenote API 进行笔记的读写和管理。适合集成到自动化工具、AI Agent 或第三方应用中。

## 功能特性

- ✅ **HTTP 接口** — 无需直接调用 Simperium API，简化集成流程
- ✅ **写入验证** — POST 笔记后自动回读，确保内容确实写入
- ✅ **笔记列表** — 快速列出所有笔记、已删除笔记
- ✅ **尸体复用** — 自动缓存已删除笔记 ID，便于新建笔记时重用
- ✅ **API 认证** — 支持 Header 密钥认证，避免误用
- ✅ **自动启动** — systemd 服务配置，重启自恢复

## 快速开始

### 前置条件

- Python 3.7+
- Simplenote 账号（带 Simperium 访问令牌）

### 安装

```bash
git clone https://github.com/leedreamer4gmail/autoNote.git
cd autoNote
# 无需额外依赖，仅用标准库
```

### 配置

设置环境变量（或在 `frontend.conf` 中配置）：

```bash
export SIM_TOKEN="your_simperium_access_token"
export NOTE_API_KEY="your_api_key"  # HTTP 认证密钥，默认 simpleNote888
```

### 启动服务

**本地测试：**
```bash
python3 transNote.py
```

**后台服务（Linux/macOS）：**
```bash
sudo cp transnote.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable transnote
sudo systemctl start transnote
sudo systemctl status transnote
```

## API 文档

服务默认监听 `http://localhost:8888`，所有请求需要 Header：`X-Api-Key: <your_api_key>`

### 健康检查（无需认证）

```
GET /health
→ {"status": "ok"}
```

### 列出所有笔记

```
GET /notes
→ [
    {"id": "uuid-1", "title": "笔记标题1"},
    {"id": "uuid-2", "title": "笔记标题2"}
  ]
```

### 列出已删除笔记（可复活）

```
GET /notes/dead
→ [
    {"id": "uuid-deleted", "title": "已删除的笔记"}
  ]
```

### 读取笔记内容

```
GET /note/<note_id>
→ {"id": "uuid", "content": "笔记内容", "tags": ["tag1", "tag2"]}
```

### 新建或更新笔记

```
POST /note
Content-Type: application/json
X-Api-Key: your_api_key

{
  "id": "uuid",           # 新建时可用已删除笔记的 ID，或 POST 会自动生成
  "content": "笔记内容",
  "tags": ["tag1", "tag2"]
}

→ {"stored_chars": 42}    # 写入后的字数
```

### 删除笔记

```
DELETE /note/<note_id>
X-Api-Key: your_api_key

→ {"deleted": true}       # 标记为删除，可通过 /notes/dead 查看
```

## 使用场景

- **AI Agent 集成** — Copilot/Kimi 通过 HTTP 调用读写笔记
- **自动化脚本** — Python/Node.js 脚本无缝对接 Simplenote
- **多设备同步** — 将 Simplenote 作为跨平台笔记中枢
- **监控告警** — 定时写入日志、错误信息到云笔记

## 配置详解

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SIM_TOKEN` | Simperium 访问令牌 | `2c7c5ce...` |
| `NOTE_API_KEY` | HTTP 请求认证密钥 | `simpleNote888` |
| `PORT` | 监听端口 | `8888` |

### 文件配置（可选）

创建 `frontend.conf`，格式如下：

```
apikey=your_custom_api_key
port=9999
```

优先级：环境变量 > 配置文件 > 默认值

## 故障排查

### 连接被拒 (ECONNREFUSED)

- 检查服务是否启动：`netstat -tuln | grep 8888`
- 检查防火墙：`sudo ufw allow 8888`

### 403 Unauthorized

- 确认 Header 中 `X-Api-Key` 正确
- 检查 `SIM_TOKEN` 是否有效（可在 https://app.simplenote.com 查看）

### Simperium API 返回 412/502

- 这是 Simperium 的已知行为，服务会自动验证写入
- 如果 GET 回读内容正确，写入成功

## 开发和贡献

```bash
# 查看日志
sudo journalctl -u transnote -f

# 本地测试
python3 -m http.server 8888  # 或直接运行 python3 transNote.py
curl -H "X-Api-Key: simpleNote888" http://localhost:8888/health
```

## 许可证

MIT License

## 作者

**copilot** — Simplenote 云端解决方案

---

**相关资源：**
- [Simplenote 官网](https://simplenote.com/)
- [Simperium API 文档](https://simperium.com/docs/)
- [服务部署经验](exp/Python服务经验.md)
