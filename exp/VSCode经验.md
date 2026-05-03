# VSCode经验
作者：copilot

记录时间：2026-05-01

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

### 4.4 持久化用户环境变量

```powershell
[Environment]::SetEnvironmentVariable('HTTP_PROXY',  'http://127.0.0.1:1081',  'User')
[Environment]::SetEnvironmentVariable('HTTPS_PROXY', 'http://127.0.0.1:1081',  'User')
[Environment]::SetEnvironmentVariable('ALL_PROXY',   'socks5://127.0.0.1:1081','User')
```

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

## 6. 通用解决方案：自动检测并修复代理不一致

为避免以后切换 VPN 再次出现此问题，编写了自动化修复脚本 `fix_copilot.py`：

**脚本逻辑：**
1. 检测当前实际代理进程（扫描 `core.exe`、`QingZhou.exe` 等常见代理进程）
2. 读取当前实际监听端口
3. 对比 WinINET、WinHTTP、环境变量是否一致
4. 不一致时自动修复为当前实际端口
5. 验证 GitHub/Copilot 连通性

**使用方法：**
```powershell
cd d:\fix_vpn
python fix_copilot.py
```

**脚本位置：** `d:\fix_vpn\fix_copilot.py`

---

## 7. 经验总结

| 坑 | 现象 | 根因 | 解法 |
|----|------|------|------|
| VPN 切换后 Copilot 连不上 | `ECONNREFUSED 127.0.0.1:XX` | 环境变量/WinHTTP/注册表仍指向旧端口 | 切换 VPN 后运行 `fix_copilot.py` 自动同步 |
| 代理进程返回 502 | curl 通过代理访问返回 502 | 代理软件没连上节点（如 QingZhou 刚启动时） | 等几秒或重启代理软件 |
| 多个 VPN 软件端口冲突 | 代理时好时坏 | 不同 VPN 使用不同端口，设置没清理 | 停用不用的 VPN，只保留一个 |

**以后切换 VPN 后的标准操作流程：**

1. 启动新 VPN 并确认能翻墙（浏览器打开 Google）
2. 运行 `python d:\fix_vpn\fix_copilot.py`
3. 重启 VS Code（让 Copilot 读取新的环境变量）
4. 如果仍不行，检查 `netstat` 确认实际代理端口

---

## 8. VS Code 代理设置参考

VS Code 读取代理的优先级：

1. `github.copilot.advanced.debug.useElectronFetcher` 等设置
2. 环境变量 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`
3. Windows 系统代理（WinINET）

当 Copilot 报代理连接错误时，优先检查环境变量和系统代理是否一致。
