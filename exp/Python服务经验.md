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

---

## 2. 服务器缺少第三方模块导致脚本无法启动

### 问题现象

本地开发环境正常，部署到服务器后报 `ModuleNotFoundError: No module named 'openpyxl'`，服务无法启动。

### 根本原因

服务器是全新环境，只安装了 Python 标准库，未安装项目依赖的第三方包（`openpyxl`、`pandas`、`requests` 等）。

### 解决方法

**临时方案**：手动 `pip3 install openpyxl`，治标不治本，每次新服务器都要重复操作。

**永久方案**：在每个脚本头部添加 `_ensure_deps` 自动安装逻辑，启动时自检依赖，缺什么装什么：

```python
import subprocess
import sys

def _ensure_deps(*pkgs):
    for p in pkgs:
        try:
            __import__(p)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", p, "-q"])

_ensure_deps("requests", "openpyxl")  # 按需填写第三方依赖
```

**注意**：`_ensure_deps` 必须放在标准库 `import` 之后、第三方库 `import` 之前。`subprocess` 和 `sys` 必须在调用前已导入。

### 影响范围

- 所有部署到新服务器的 Python 脚本，只要依赖第三方包均可能遇到此问题
- 已修复：`流水同步/merge.py`、`流水同步/check.py`、`日报表/main.py`、`月报表_三地/main.py`、`月报表_外账/main.py`

### 经验总结

> **每个有第三方依赖的 Python 脚本都应在头部加 `_ensure_deps`，做到自包含，部署到任何环境开箱即用。**

---

## 3. _ensure_deps 已存在但仍报 ModuleNotFoundError（间接依赖漏写）

### 问题现象

`月报表_三地/main.py` 已有 `_ensure_deps("pandas", "requests")`，运行到最后导出步骤时仍抛出
`ModuleNotFoundError: No module named 'openpyxl'`。

### 根本原因

`_ensure_deps` 用 `__import__(包名)` 检测。代码写的是 `pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl")`——pandas 本身能导入成功，所以 `__import__("pandas")` 不报错，_ensure_deps 根本察觉不到 openpyxl 缺失。等到运行时 pandas 内部才去 `import openpyxl`，发现没装，崩溃。

这是典型的**间接依赖（通过第三方库的插件/引擎机制使用）漏写**，区别于直接 `import openpyxl` 的显式依赖。

### 解决方法

在 `_ensure_deps` 里**显式列出所有运行时实际需要的包，包括间接依赖**：

```python
# 修复前
_ensure_deps("pandas", "requests")

# 修复后
_ensure_deps("pandas", "requests", "openpyxl")
```

### 受影响场景

凡是通过第三方库的"引擎/后端"机制隐式依赖另一个包的，都要显式列出：
- `pd.ExcelWriter(engine="openpyxl")` → 需要显式加 `"openpyxl"`
- `pd.ExcelWriter(engine="xlsxwriter")` → 需要显式加 `"xlsxwriter"`
- `pd.read_excel(engine="xlrd")` → 需要显式加 `"xlrd"`
- `sqlalchemy` 连 MySQL 时底层用 `pymysql` → 需要显式加 `"pymysql"`

### 经验总结

> **`_ensure_deps` 里要列出所有运行时实际需要的包，不仅是直接 import 的，还包括通过引擎/插件机制间接使用的包。**
