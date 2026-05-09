# autoNote notetools 使用手册 v1.2

autoNote 是自建 Markdown 笔记库。SQLite 是主库，`content` 是笔记原文，标题只从 Markdown 第一行显示时提取，数据库里不存 `title`。

## 基础规则

- API 基础路径：`/autonote`
- 认证请求头：`X-Api-Key: simpleNote888`
- 默认用户：`leedreamer`
- 标签最多 5 个。
- `enable` 为 `T` 表示有效，`F` 表示失效。
- 并发写入由 SQLite WAL、`busy_timeout`、`BEGIN IMMEDIATE` 和进程内写锁保护。

## 笔记格式

笔记内容使用 Markdown。推荐按 `notetemplate.md` 写经验：

```markdown
# Git 经验
- 版本：1.0.0
- 2026-05-08：Copilot - 新增记录

## 事件

### 场景
...

### 解决方法
...

### 坑
...
```

## notetools 接口

notetools 是确定性工具箱，没有智能。外部 AI 如果已经整理好 Markdown，直接调用 notetools。

### 新建

`POST /autonote/notetools/new`

```json
{
  "user": "leedreamer",
  "folder": "Git",
  "content": "# Git 经验\n- 版本：1.0.0\n...",
  "tags": ["Git", "经验"]
}
```

返回：

```json
{"ok": true, "id": "uuid", "note": {}}
```

### 更新

`POST /autonote/notetools/update`

```json
{
  "id": "uuid",
  "content": "# 新内容",
  "folder": "Git",
  "tags": ["Git"]
}
```

只想改内容就只传 `id` 和 `content`。

### 读取

`POST /autonote/notetools/read`

```json
{"id": "uuid"}
```

### 搜索

`POST /autonote/notetools/search`

```json
{
  "user": "leedreamer",
  "q": "Git",
  "folder": "",
  "include_disabled": false
}
```

也可以用列表接口：

`GET /autonote/notetools/notes?user=leedreamer&q=Git`

### 失效

`POST /autonote/notetools/unable`

```json
{"id": "uuid"}
```

失效不会删除内容，只是不在默认搜索里显示。

### 删除

`POST /autonote/notetools/del`

```json
{"id": "uuid"}
```

删除是硬删除。能用失效时优先失效。

## Lucy 接口

Lucy 接收原始文本，先通过 notetools 查询现有笔记，并把手册、输入内容和候选笔记交给 LLM 判断是否同类：

- 同类：LLM 返回 `update`、目标笔记 ID、整理后的完整 Markdown，然后后端通过 notetools 更新。
- 不同类：LLM 返回 `new` 和新 Markdown，然后后端通过 notetools 新建。
- LLM 只做判断和整理，不直接写数据库。
- LLM 输出必须是 JSON。后端会校验 `action`、`target_id` 和 `content`，不合格会回退本地规则。
- LLM 临时不可用时，后端会返回 `llm.error`，并用规则版 Lucy 继续处理。

### 接收并写入

`POST /autonote/lucy/intake`

```json
{
  "user": "leedreamer",
  "text": "Git push 被 GitHub Push Protection 拦截...",
  "folder": "Git",
  "tags": ["Git", "GitHub"],
  "author": "Lucy"
}
```

返回里的 `action` 为 `update` 或 `new`。
返回里的 `llm.used` 表示是否调用了 LLM，`llm.reason` 是 LLM 的一句话判断理由；如果调用失败，会有 `llm.error`。

### 只生成草稿

`POST /autonote/lucy/draft`

请求格式同 `/lucy/intake`，但不写数据库。

## 返回字段

接口返回的 `note.title` 是显示字段，从 `content` 第一行临时提取，不写入数据库。

```json
{
  "id": "uuid",
  "user": "leedreamer",
  "folder": "Git",
  "content": "# Git 经验\n...",
  "tag": ["Git"],
  "tags": ["Git"],
  "enable": "T",
  "title": "Git 经验",
  "created_at": "2026-05-08 12:00:00",
  "updated_at": "2026-05-08 12:00:00"
}
```

## 工作区经验

- 主系统不要依赖外部笔记平台；外部导入、导出、同步工具放进 `outside/`。
- notetools 保持笨而稳定，Lucy 的智能判断只调用 notetools，不直接绕过工具层写库。
- 数据库不存 `title` 可以降低维护成本，但前端和 API 返回可以临时计算 `title` 方便显示。
- Lucy 接 LLM 时不要把数据库写权限交给模型；模型只输出决策 JSON，后端校验后再调用 notetools。