# VSCode经验
作者：copilot
版本：1.1

记录时间：2026-05-01
最后更新：2026-05-05（Copilot 跟随当前 Windows/VPN 代理修复）

---

## 0. 快速修复命令（2026-05-05 更新）

目标：让 VS Code/Copilot 跟随当前已经打开的 VPN 官方客户端，不单独启动后台 core，不创建自启动脚本，也不把环境变量固定到某个旧端口。

每次切换 VPN 后，在实际 PowerShell 终端中执行以下命令。端口必须替换为当前 `ProxyServer` 或实际监听端口，例如本次飞鸟为 `19033`：

```powershell
# 1. 确认当前 Windows 用户代理和本机监听端口
Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' |
	Select-Object ProxyEnable,ProxyServer,ProxyOverride
netstat -ano | findstr LISTENING | findstr 127.0.0.1

# 2. 修复 WinINET 和 WinHTTP（假设当前 VPN 端口为 19033，请替换为实际端口）
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Type DWord -Value 1
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyServer -Type String -Value '127.0.0.1:19033'
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyOverride -Type String -Value 'localhost;127.*;192.168.*;<local>'
netsh winhttp set proxy "127.0.0.1:19033" "localhost;127.*;192.168.*;<local>"

# 3. 验证 Copilot 相关端点
curl.exe -s -o NUL -w "github=%{http_code}`n" --max-time 20 https://api.github.com
curl.exe -s -o NUL -w "copilot=%{http_code}`n" --max-time 20 https://api.githubcopilot.com/_ping
curl.exe -s -o NUL -w "copilot_proxy=%{http_code}`n" --max-time 20 https://copilot-proxy.githubusercontent.com/_ping
```

**注意：** 不要在沙盒环境中执行这些命令，沙盒无法真正修改注册表。如果 VS Code 已经打开很久，修复后仍不恢复模型列表，就完全退出所有 VS Code 窗口后重新打开。

---

## 0.1 Copilot 模型不可用但浏览器能上 Google（2026-05-05）

**现象：** 浏览器可以正常访问 Google，但 VS Code Copilot 的 Sonnet 等模型不可用。

**本次状态：**

| 层级 | 修复前 | 修复后 |
|------|--------|--------|
| WinINET | `127.0.0.1:19033` | `127.0.0.1:19033` |
| WinHTTP | `127.0.0.1:1081`，无进程监听 | `127.0.0.1:19033` |
| 用户环境变量 | 空 | 保持为空 |
| 当前 VPN | 飞鸟官方客户端，主 core 监听 `19033` | 不额外启动 core |

**根因：** 浏览器主要跟随 WinINET，所以能上 Google；但 VS Code/Copilot 的部分联网路径可能受 WinHTTP 影响。WinHTTP 残留旧端口 `1081`，且该端口无监听，于是 Copilot 相关请求可能连接失败。

**修复原则：**

- 当前 VPN 官方客户端打开时，只同步它正在使用的端口。
- 不持久化 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 到固定端口，避免下次 VPN 端口变化后 Copilot 继续踩旧端口。
- 不创建计划任务、自启动脚本，不单独后台启动 `core.exe`。
- 关闭 VPN 官方客户端后，不应为了 Copilot 留一个独立代理后台。

**验证结果：**

```text
github_19033=200
copilot_19033=200
copilot_proxy_19033=200
github_default=200
copilot_default=200
copilot_proxy_default=200
```

如果这些端点都返回 `200`，网络侧已经恢复；若模型列表仍未刷新，重启 VS Code 让扩展重新读取系统代理。

---

## 1. 故障现象

VS Code GitHub Copilot Chat 报错：

```text
connect ECONNREFUSED 127.0.0.1:20835
```

- 环境变量 `HTTP_PROXY=http://127.0.0.1:20835`
- 但当前实际代理端口已变为 `1081`（QingZhou）
- `netsh winhttp show proxy` 显示 `127.0.0.1:20835`，与当前实际端口不一致
- 系统注册表 `ProxyServer` 残留旧值 `localhost:1081`，`ProxyEnable=0`

---

## 2. 根因分析

**根本原因是 VPN 切换后，各层代理设置没有同步更新。**

具体表现为四层代理状态不一致：

| 层级 | 故障前值 | 当前实际代理 | 状态 |
|------|---------|-------------|------|
| WinINET 注册表 | `localhost:1081` / `ProxyEnable=0` | `127.0.0.1:1081` | ❌ 开关关闭，地址格式不对 |
| WinHTTP | `127.0.0.1:20835` | `127.0.0.1:1081` | ❌ 端口过期 |
| 用户环境变量 | `http://127.0.0.1:20835` | `http://127.0.0.1:1081` | ❌ 端口过期 |
| VS Code 内部 | 读取环境变量 → 20835 | 实际代理 1081 | ❌ 连接被拒 |

Copilot 报错 `ECONNREFUSED 127.0.0.1:20835` 是因为 VS Code 通过环境变量找到了 20835，但那个端口已经没有任何进程在监听。

---

## 3. 为什么 VPN 切换会导致这个问题

用户使用了多个 VPN 软件（飞鸟、QingZhou 等），它们各自使用不同端口：

| VPN 软件 | 常见端口 | 特点 |
|---------|---------|------|
| 飞鸟 | 随机分配（19973、20835、24080 等） | GUI 每次启动重新分配 |
| QingZhou | 1081 | 固定端口 |
| 其他 Clash 客户端 | 7890、7891、7892 等 | 视配置而定 |

**每次切换 VPN 后，必须同步更新以下四项，否则就会出现端口不一致：**

1. **WinINET 注册表**：`ProxyEnable=1`，`ProxyServer=127.0.0.1:<新端口>`
2. **WinHTTP**：`netsh winhttp set proxy 127.0.0.1:<新端口> "localhost;127.*;192.168.*;<local>"`
3. **用户环境变量**：`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`
4. **（可选）当前终端环境变量**：新开的终端会自动继承用户变量，已开的终端需要重启

---

## 4. 修复步骤

### 4.1 确认当前实际代理端口

```powershell
# 查看谁在监听 1081
netstat -ano | findstr LISTENING | findstr 1081
# → PID 6776 = QingZhou.exe
```

### 4.2 修复 WinINET 代理开关和地址

```powershell
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Type DWord -Value 1
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyServer -Type String -Value '127.0.0.1:1081'
```

### 4.3 修复 WinHTTP 代理

```powershell
netsh winhttp set proxy "127.0.0.1:1081" "localhost;127.*;192.168.*;<local>"
```

### 4.4 用户环境变量处理原则

2026-05-05 更正：不要再把 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 持久化到某个固定端口。飞鸟等 VPN 客户端可能每次启动分配新端口，固定环境变量会让 VS Code 或其它开发工具继续连接旧端口。

除非某个 CLI 明确只认环境变量，否则保持用户环境变量为空，让 VS Code/Copilot 跟随 Windows 系统代理和 WinHTTP。

---

## 5. 修复后验证

```powershell
# curl 通过代理访问 GitHub API
curl.exe -s -o NUL -w "%{http_code}" --max-time 15 -x http://127.0.0.1:1081 https://api.github.com
# → 200 ✅

# Copilot API
curl.exe -s -o NUL -w "%{http_code}" --max-time 15 -x http://127.0.0.1:1081 https://api.githubcopilot.com/_ping
# → 200 ✅

# Copilot Proxy
curl.exe -s -o NUL -w "%{http_code}" --max-time 15 -x http://127.0.0.1:1081 https://copilot-proxy.githubusercontent.com/_ping
# → 200 ✅
```

---

## 6. 通用解决方案：只同步当前官方客户端代理

2026-05-05 更正：本工作区当前没有 `auto_fix_proxy.py`，并且用户明确不希望通过脚本长期接管 VPN。以后按下面原则处理：

1. 用户需要 VPN 时，打开 VPN 官方客户端。
2. 读取当前 WinINET `ProxyServer`，或从监听端口中确认 VPN 官方客户端实际端口。
3. 将 WinHTTP 同步到同一个端口。
4. 清理 `ProxyOverride` 为 `localhost;127.*;192.168.*;<local>`。
5. 不新增计划任务、自启动项、常驻脚本，不手动长期后台启动 `core.exe`。
6. 验证 GitHub/Copilot 端点均返回 `200`。

如果 VPN 官方客户端关闭后端口消失，这是符合预期的；不要为了 Copilot 单独留下后台代理核心。

---

## 7. 经验总结

| 坑 | 现象 | 根因 | 解法 |
|----|------|------|------|
| VPN 切换后 Copilot 连不上 | `ECONNREFUSED 127.0.0.1:XX` | WinHTTP/注册表仍指向旧端口 | 读取当前官方客户端端口，同步 WinINET/WinHTTP |
| 代理进程返回 502 | curl 通过代理访问返回 502 | 代理软件没连上节点（如 QingZhou 刚启动时） | 等几秒或重启代理软件，或在 GUI 中切换节点 |
| 多个 VPN 软件端口冲突 | 代理时好时坏 | 不同 VPN 使用不同端口，设置没清理 | 停用不用的 VPN，只保留一个 |
| 沙盒环境无法修改注册表 | 脚本运行但注册表未更新 | 沙盒隔离了系统调用 | 在实际 PowerShell 终端中运行脚本 |

**以后切换 VPN 后的标准操作流程：**

1. 启动新 VPN 并确认能翻墙（浏览器打开 Google）
2. 检查 WinINET `ProxyServer` 和本机监听端口，确认当前官方客户端端口
3. 将 WinHTTP 同步到同一端口，并清理 `ProxyOverride`
4. 如果仍不行，完全退出并重启 VS Code

**手动修复命令（备用）：**
```powershell
# 假设当前代理端口为 19033，请替换为实际端口
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Type DWord -Value 1
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyServer -Type String -Value '127.0.0.1:19033'
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyOverride -Type String -Value 'localhost;127.*;192.168.*;<local>'
netsh winhttp set proxy "127.0.0.1:19033" "localhost;127.*;192.168.*;<local>"
```

---

## 8. VS Code 代理设置参考

VS Code 读取代理的优先级：

1. `github.copilot.advanced.debug.useElectronFetcher` 等设置
2. 环境变量 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`
3. Windows 系统代理（WinINET）

当 Copilot 报代理连接错误时，优先检查环境变量和系统代理是否一致。

---

## 9. 代理修复完整流程验证成功（2026-05-04）

**问题：** VPN 切换后 VS Code Copilot 报 `ECONNREFUSED 127.0.0.1:20835` 错误

**修复步骤：**
1. 通过 `netstat -ano | findstr LISTENING | findstr 127.0.0.1` 确认当前实际代理端口为 1081（QingZhou）
2. 修复 WinINET 注册表：`ProxyEnable=1`，`ProxyServer=127.0.0.1:1081`，`ProxyOverride=localhost;127.*;192.168.*;<local>`
3. 修复用户环境变量：`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 全部指向 `127.0.0.1:1081`
4. 完全关闭 VS Code 后重新启动

**验证结果：**
- ✅ Copilot 恢复正常，不再报连接错误
- ✅ 代理四层状态（WinINET、WinHTTP、环境变量、VS Code 内部）全部同步一致

**关键经验：**
- 每次切换 VPN 后必须同步 WinINET/WinHTTP，否则可能出现浏览器可用但 Copilot 不可用
- 不再建议持久化用户代理环境变量到固定端口；端口变化后它会变成新的故障源
- 修复后如果仍异常，必须完全关闭并重启 VS Code，否则它可能仍使用旧网络状态
- 沙盒环境无法真正修改注册表，必须在实际 PowerShell 终端中执行修复命令
- 不建议创建脚本、计划任务或独立后台 core 来绕过官方 VPN 客户端
