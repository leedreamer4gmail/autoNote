# autoNote

autoNote 是一个自建 Markdown 笔记经验系统。它不再把 Simplenote 当主库，笔记以 Markdown 原文存入本地 SQLite，页面显示标题时临时从 Markdown 第一行提取。

## 当前结构

```text
autoNote/
  app.py              # 主服务：Flask + SQLite + notetools + Lucy
  notedb.db           # 运行后自动生成，本地笔记主库
  frontend.conf       # apikey/port 配置
  autonote.service    # systemd 服务示例
  www/
    index.html        # 前台笔记本界面
    manual.html       # 人工上传页面
    autonotehb.md     # 给 AI 和外部程序看的 notetools 手册
    notetemplate.md   # 经验笔记 Markdown 模板
  outside/            # 外部平台迁移工具，主系统不依赖
```

## 数据库原则

`notes` 表只保留必要字段：

| 字段 | 说明 |
|------|------|
| `id` | UUID |
| `user` | 用户 |
| `folder` | 文件夹，可空 |
| `content` | Markdown 原文 |
| `tag` | JSON 数组，最多 5 个 |
| `enable` | `T` 有效，`F` 失效 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

没有 `title` 字段。标题来自 `content` 的第一行 Markdown。

## 启动

```bash
cd /home/project/autoNote
python3 app.py
```

默认端口是 `8888`。可以在 `frontend.conf` 增加：

```ini
apikey=simpleNote888
port=8888
lucy_api_key=你的LLM密钥
lucy_base_url=https://api.deepseek.com
lucy_model=DeepSeek-V4-Flash
```

Lucy 的 LLM 配置读取优先级是环境变量、`frontend.conf`、`promt.md`。环境变量可用 `LUCY_API_KEY`、`LUCY_BASE_URL`、`LUCY_MODEL`，也兼容 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`。`DeepSeek-V4-Flash` 这类大小写写法会在请求前自动规范化为 DeepSeek API 接受的模型名。

## 页面

- 首页：`/autonote/`
- 人工上传：`/autonote/manual.html`
- 手册：`/autonote/gethb`
- 健康检查：`/autonote/health`

## API

所有写入和读取接口都需要请求头：

```http
X-Api-Key: simpleNote888
```

### notetools

- `POST /autonote/notetools/new`：新建笔记
- `POST /autonote/notetools/update`：更新笔记
- `POST /autonote/notetools/del`：删除笔记
- `POST /autonote/notetools/unable`：设置失效
- `POST /autonote/notetools/read`：读取笔记
- `POST /autonote/notetools/search`：搜索笔记
- `GET /autonote/notetools/notes?user=leedreamer&q=关键词`：列表

### Lucy

- `POST /autonote/lucy/intake`：接收前台乱文本，先找同类经验，能合并就更新，不能合并就新建。
- `POST /autonote/lucy/draft`：只生成草稿，不写库。

Lucy 已接入 OpenAI 兼容的 LLM 接口。她会读取 `autonotehb.md`、当前输入和候选笔记，让 LLM 输出 JSON 决策；后端校验后仍然通过 notetools 函数写库。LLM 临时不可用时，服务会带错误信息回退到本地规则版，避免前台不可用。

## 并发

SQLite 开启 WAL、`busy_timeout` 和 `BEGIN IMMEDIATE` 写事务；同一进程内写入再加线程锁，避免多用户同时写时抢同一个写事务。

## 外部平台

旧 Simplenote 代理已经移到 `outside/`。autoNote 主系统不依赖外部笔记平台；需要迁移时再单独使用 `outside` 里的工具。