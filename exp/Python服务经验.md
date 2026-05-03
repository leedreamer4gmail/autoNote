# Python服务经验
作者：copilot

记录时间：2026-05-02

---

## 1. Python 字符串内嵌 HTML/JS 时的转义陷阱

### 问题现象

用 Python `http.server` 手写 HTML 页面，把 HTML + JavaScript 作为普通字符串嵌入 Python 代码：

```python
HTML_PAGE = """\
<!DOCTYPE html>
...
<script>
if (/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(note.content)) ...
setStatus('常见原因：\n• content 里有真实换行（改为 \\n）', true);
</script>
"""
```

部署后浏览器页面上所有按钮和事件完全无效，但服务器端 API 本身正常。

### 根本原因

Python 普通字符串（`"""..."""`）会解析所有 `\x`、`\n`、`\t` 等转义序列：

| Python 源码 | Python 字符串值 | 浏览器收到 | 结果 |
|---|---|---|---|
| `\x00` | null byte (U+0000) | null byte 嵌入 `<script>` | **JS 解析报错，整个脚本失效** |
| `\n` （在 JS 字符串字面量内） | 真实换行 | 单引号字符串里有换行 | **JS 语法错误** |

**一个 null byte 就足以让浏览器拒绝解析整个 `<script>` 块**，所有按钮、事件监听器全部不注册。

### 解决方法

把 HTML 模板定义为**原始字符串** `r"""..."""`：

```python
HTML_PAGE = r"""<!DOCTYPE html>
...
<script>
// \x00 在这里是字面量 \x00（4个字符），浏览器 JS 引擎正确解释为正则字符类
if (/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(note.content)) ...
// \n 在这里是字面量 \n（2个字符），JS 引擎解释为换行转义
setStatus('常见原因：\n• content 里有真实换行（改为 \\n）', 'err');
</script>
"""
```

原始字符串中：
- `\x00` → 保持 4 字符原样 → 浏览器 JS 正确解释为正则中的十六进制转义 ✓
- `\n` → 保持 2 字符原样（反斜杠+n）→ JS 字符串字面量里合法的换行转义 ✓
- `\\n` → 保持 3 字符（反斜杠+反斜杠+n）→ JS 解释为字面量 `\n` 文本，用于向用户展示 `\n` 这两个字符 ✓
- 源码中的真实换行 → 仍然保留为真实换行，页面格式不变 ✓

### 注意事项

- 原始字符串首行不能用 `"""\` 开头（那样第一个字符是反斜杠），改为 `r"""<!DOCTYPE`
- 原始字符串内不能出现 `"""` 序列（会提前结束字符串）
- 原始字符串结尾不能是奇数个反斜杠（Python 原始字符串限制）

### 影响范围

任何在 Python 字符串里直接嵌入 JavaScript 源码的场景都有此风险，包括：
- `http.server.BaseHTTPRequestHandler` 自定义页面
- Flask/Django 直接 `return` HTML 字符串（不走模板引擎时）
- Jinja2 外的任何硬编码 HTML

### 经验总结

> **凡是 Python 字符串内嵌 JS，一律用 `r"""..."""` 原始字符串，永久避免此类问题。**
