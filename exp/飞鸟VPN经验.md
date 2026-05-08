# 飞鸟VPN经验
作者：copilot

记录时间：2026-04-29  
最后更新：2026-05-01

## 1. 当前状态结论（已更正，见第 13 节 + 第 14 节）

本次修复历经多轮调整，**最终方案是恢复使用飞鸟官方客户端**，不再手动管理 `core.exe`。

当前正确使用方式：

- 开机默认不运行飞鸟，系统代理为关闭状态
- 需要翻墙时，双击桌面快捷方式 `飞鸟加速.lnk` 启动官方客户端
- 在飞鸟官方界面里选择节点、全局代理或规则模式
- 不需要时，在飞鸟官方界面里断开或退出

当前确认状态（2026-04-30 更新）：

- 桌面快捷方式：`C:\Users\Administrator\Desktop\飞鸟加速.lnk` → `E:\飞鸟加速\飞鸟加速.exe`
- FeiniaoClashCoreFix 计划任务：**已删除**（不再需要）
- 手动启动脚本（bat/ps1）：**均已删除**
- 飞鸟当前使用端口：**20835**（非老版本的 19973，GUI 每次启动可能分配随机端口）
- 系统代理（飞鸟运行时）：ProxyEnable=1，ProxyServer=127.0.0.1:20835
- WinHTTP：127.0.0.1:20835
- 用户环境变量：HTTP_PROXY / HTTPS_PROXY / ALL_PROXY 均持久化为 20835

⚠️ **飞鸟 GUI 每次启动可能分配不同端口**（见第 14 节），见下文快速修复命令。

详见第 13 节的经验更正，以及第 14 节的 2026-04-30 补充。

## 2. 最初故障现象

用户反馈：

- 之前飞鸟 VPN 可以正常访问外网。
- 重启电脑后不能访问外网。
- 飞鸟客户端界面看起来仍然能选服务器，也能显示部分延迟。
- 但实际访问 Google 等外网失败。

初步表现不是普通断网，因为国内网络仍然正常。

验证结果：

- 国内站点和国内 DNS 连通正常。
- `www.baidu.com:443` 可以连通。
- `www.google.com:443` 直连失败。
- `www.google.com` 被本地 DNS 解析到异常地址，例如 `174.132.167.252` 和 `2001::1`，说明请求没有经过 VPN 的代理 DNS/代理通道。

## 3. 排查过程

### 3.1 检查网卡和路由

先查看 Windows 网卡状态，发现：

- 物理无线网卡 `WLAN` 正常在线。
- 虚拟网卡 `LetsTAP` 存在，但状态为 `Disconnected`。
- IPv4 默认路由仍然走普通网关 `192.168.101.1`。
- 路由表里没有 VPN 接管后的默认路由。

这说明飞鸟没有通过 TAP/TUN 模式接管全局路由。

### 3.2 检查系统代理

检查注册表：

- `ProxyEnable = 0`
- `ProxyServer = 127.0.0.1:19973`

这说明系统里残留了飞鸟以前使用的代理地址，但代理开关是关闭的。

结果就是：

- VPN 核心即使曾经配置过代理端口，Windows 应用也不会自动走它。
- 浏览器和普通应用会继续直连。
- 直连外网自然失败。

### 3.3 检查飞鸟进程

发现飞鸟相关进程存在：

- `E:\飞鸟加速\飞鸟加速.exe`
- `E:\飞鸟加速\core.exe`

说明飞鸟程序并不是完全没启动。

继续检查监听端口，发现：

- 飞鸟界面监听 `127.0.0.1:12345`
- 一个 core 监听 `127.0.0.1:22560` 和 `127.0.0.1:23629`
- 但主代理端口 `127.0.0.1:19973` 没有监听
- 主控制端口 `127.0.0.1:19092` 也没有监听

这很关键：飞鸟客户端在跑，但真正给系统用的主代理核心没有跑起来。

### 3.4 检查飞鸟本地数据目录

找到飞鸟数据目录：

`C:\Users\Administrator\AppData\Local\com.fnjs.clash\data`

里面有：

- `clash\config.yaml`
- `clash\Country.mmdb`
- `clash\geoip.dat`
- `clash\geosite.dat`
- `clashExtra\config.yaml`
- `log\2026-04-29-00-00.log`

其中主配置是：

`C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash\config.yaml`

主配置里关键项：

```yaml
mixed-port: 19973
mode: rule
external-controller: 127.0.0.1:19092
dns:
  enable: true
```

这说明正常情况下飞鸟应该启动一个 Clash 核心，监听 `127.0.0.1:19973`。

### 3.5 读取日志

飞鸟日志显示主核心曾经短暂成功启动：

```text
RESTful API listening at: 127.0.0.1:19092
Mixed(http+socks) proxy listening at: 127.0.0.1:19973
```

但随后客户端又执行了停止动作：

```text
stopCalsh
clash core terminated
```

后面留下的 `clashExtra` 核心使用的是：

- 控制端口：`127.0.0.1:22560`
- 混合代理端口：`127.0.0.1:23629`

这个 extra 核心在日志里对 Google 走了 `DIRECT`，结果直连失败：

```text
www.google.com:443 error: connect failed
```

所以当时机器上处于一种很别扭的状态：

- 飞鸟界面和 extra 核心还活着。
- 真正应该给系统用的主核心没活着。
- Windows 系统代理开关也是关闭的。
- 外网请求最终还是直连失败。

## 4. 根因分析

这次故障不是单纯的节点坏了，也不是电脑完全断网。

真正原因是多个问题叠在一起：

### 4.1 主 Clash 核心没有正常持续运行

飞鸟主配置本来应该启动 `127.0.0.1:19973`，但实际这个端口没有监听。

手动启动主核心时，第一次失败信息是：

```text
Can't find MMDB, start download
can't download MMDB: Get "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.metadb"
Parse config error: rules[...] [GEOIP,CN,DIRECT] error: can't download MMDB
```

意思是：

- 当前 core 版本需要 `geoip.metadb`。
- 本地目录里只有 `Country.mmdb`、`geoip.dat`、`geosite.dat`。
- 找不到 `geoip.metadb` 后，它尝试去 GitHub 下载。
- 但此时代理还没起来，GitHub 访问失败。
- 于是核心启动失败。

这是一个典型的“代理核心启动依赖外网文件，但外网访问又依赖代理核心”的循环故障。

### 4.2 系统代理开关被关闭

注册表里虽然有：

```text
ProxyServer = 127.0.0.1:19973
```

但：

```text
ProxyEnable = 0
```

所以浏览器和大多数普通应用不会使用这个代理。

### 4.3 飞鸟界面会重新改代理状态

修复过程中发现，飞鸟界面进程运行时可能会把 `ProxyEnable` 改回 `0`。

因此本次最终选择：

- 停掉飞鸟界面进程。
- 保留手动启动的主 `core.exe`。
- 由 Windows 系统代理直接指向主核心端口。

这样可以绕过界面错误状态对系统代理的干扰。

### 4.4 DNS 被直连环境污染或劫持

未走代理时，`www.google.com` 解析到了异常地址。

这不是主因，但会加重故障表现。

代理核心正常后，外网域名请求由 Clash 规则和代理链路处理，不再依赖这个错误的直连结果。

## 5. 实际修复动作

### 5.1 补齐核心需要的 GeoIP 文件

飞鸟主核心需要 `geoip.metadb`，但目录里没有。

本地已有 `Country.mmdb`，因此复制一份作为 `geoip.metadb`：

```powershell
Copy-Item `
  'C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash\Country.mmdb' `
  'C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash\geoip.metadb' `
  -Force
```

复制后确认：

- `Country.mmdb` 存在
- `geoip.metadb` 存在
- 两者大小一致：`8252235` 字节

### 5.2 使用正确的数据目录启动主核心

启动命令：

```powershell
Start-Process `
  -FilePath 'E:\飞鸟加速\core.exe' `
  -ArgumentList @(
    '-d','C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash',
    '-f','C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash\config.yaml'
  ) `
  -WorkingDirectory 'C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash' `
  -WindowStyle Hidden
```

启动后确认监听：

```text
127.0.0.1:19973  core.exe
127.0.0.1:19092  core.exe
```

### 5.3 启用 Windows 用户代理

设置当前用户代理：

```powershell
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' `
  -Name ProxyEnable -Type DWord -Value 1

Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' `
  -Name ProxyServer -Type String -Value '127.0.0.1:19973'

Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' `
  -Name ProxyOverride -Type String -Value 'localhost;127.*;192.168.*;<local>'
```

并刷新 WinINET 设置。

当前状态：

```text
ProxyEnable   : 1
ProxyServer   : 127.0.0.1:19973
ProxyOverride : localhost;127.*;192.168.*;<local>
```

### 5.4 同步 WinHTTP 代理

执行：

```powershell
netsh winhttp set proxy 127.0.0.1:19973 "localhost;127.*;192.168.*;<local>"
```

当前状态：

```text
代理服务器:  127.0.0.1:19973
绕过列表  :  localhost;127.*;192.168.*;<local>
```

### 5.5 设置命令行环境变量

为了让 curl、部分开发工具、部分 CLI 程序也走代理，设置用户环境变量：

```powershell
[Environment]::SetEnvironmentVariable('HTTP_PROXY','http://127.0.0.1:19973','User')
[Environment]::SetEnvironmentVariable('HTTPS_PROXY','http://127.0.0.1:19973','User')
[Environment]::SetEnvironmentVariable('ALL_PROXY','socks5://127.0.0.1:19973','User')
```

当前终端验证过：

```text
HTTP_PROXY  = http://127.0.0.1:19973
HTTPS_PROXY = http://127.0.0.1:19973
ALL_PROXY   = socks5://127.0.0.1:19973
```

### 5.6 停止干扰进程

停止了飞鸟界面进程和不参与当前代理的 extra 核心，只保留主核心。

最终保留：

```text
core.exe -d C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash -f C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash\config.yaml
```

### 5.7 创建登录自启动任务

创建任务：

```text
FeiniaoClashCoreFix
```

作用：登录 Windows 后自动启动飞鸟主核心。

当前状态：

```text
TaskName            State
FeiniaoClashCoreFix Ready
```

## 6. 修复后验证

### 6.1 核心端口验证

确认主核心正在监听：

```text
127.0.0.1:19973  core.exe
127.0.0.1:19092  core.exe
```

### 6.2 显式代理访问验证

执行：

```powershell
curl.exe -I --max-time 20 -x http://127.0.0.1:19973 https://www.google.com
```

结果：

```text
HTTP/1.1 200 Connection established
HTTP/1.1 200 OK
```

### 6.3 PowerShell 显式代理验证

执行：

```powershell
Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 -Proxy 'http://127.0.0.1:19973' https://www.google.com
```

结果：

```text
StatusCode StatusDescription
200        OK
```

### 6.4 默认代理访问验证

执行：

```powershell
curl.exe -I --max-time 20 https://www.google.com
```

结果：

```text
HTTP/1.1 200 Connection established
HTTP/1.1 200 OK
```

说明 curl 当前已经能通过代理访问外网。

## 7. 目前还存在的隐患

### 7.1 飞鸟界面可能再次关闭系统代理

这是目前最大的隐患。

修复过程中观察到：飞鸟界面进程可能会把 `ProxyEnable` 改回 `0`。

因此现在的稳定方案是：

- 不依赖飞鸟界面。
- 直接由后台 `core.exe` 提供代理。
- 系统代理手动固定到 `127.0.0.1:19973`。

如果重新打开飞鸟界面并点击连接/断开，它可能再次改动代理状态。

### 7.2 登录自启动任务可能和飞鸟官方客户端抢端口

如果之后又设置飞鸟官方客户端开机自启，那么可能出现两个核心都想监听 `19973` 的情况。

通常结果是：

- 先启动的核心占用端口。
- 后启动的核心失败。

目前建议：

- 保留 `FeiniaoClashCoreFix`。
- 不开启飞鸟客户端自己的开机自启。

### 7.3 `geoip.metadb` 是由 `Country.mmdb` 复制得到

这次是用本地已有的 `Country.mmdb` 补齐文件名，使核心跳过联网下载。

目前验证可用，但它本质上是兼容性修复。

如果以后飞鸟更新了 core 或规则库，最好让客户端自身更新出正式的 `geoip.metadb`。

### 7.4 节点可用性仍取决于服务端

本次修好的是本地核心、代理开关、启动链路。

如果将来某个节点服务端不可用，仍可能出现：

- 能连代理，但访问慢。
- 某个地区节点失败。
- 延迟测试失败。

这类问题需要切换节点，不属于本次本地故障。

### 7.5 本机 DNS 直连仍可能解析异常

未走代理时，`www.google.com` 仍可能解析到异常 IP。

只要系统代理正常，这个问题影响不大。

但如果代理开关被关掉，外网会再次表现为打不开。

## 8. 以后如果又坏了，快速检查命令

### 8.1 检查代理核心是否运行

```powershell
Get-NetTCPConnection -LocalPort 19973,19092 -State Listen -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,OwningProcess,@{Name='Process';Expression={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName}}
```

正常应看到：

```text
127.0.0.1  19973  core
127.0.0.1  19092  core
```

### 8.2 检查系统代理

```powershell
Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' |
  Select-Object ProxyEnable,ProxyServer,ProxyOverride
```

正常应看到：

```text
ProxyEnable   : 1
ProxyServer   : 127.0.0.1:19973
ProxyOverride : localhost;127.*;192.168.*;<local>
```

### 8.3 检查 WinHTTP 代理

```powershell
netsh winhttp show proxy
```

正常应看到：

```text
代理服务器:  127.0.0.1:19973
```

### 8.4 检查 GeoIP 文件

```powershell
Get-ChildItem 'C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash' |
  Where-Object { $_.Name -match 'geoip\.metadb|Country\.mmdb|config\.yaml' }
```

正常应看到：

- `config.yaml`
- `Country.mmdb`
- `geoip.metadb`

### 8.5 快速恢复系统代理

```powershell
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Type DWord -Value 1
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyServer -Type String -Value '127.0.0.1:19973'
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyOverride -Type String -Value 'localhost;127.*;192.168.*;<local>'
netsh winhttp set proxy 127.0.0.1:19973 "localhost;127.*;192.168.*;<local>"
```

### 8.6 快速重启主核心

```powershell
Start-Process `
  -FilePath 'E:\飞鸟加速\core.exe' `
  -ArgumentList @(
    '-d','C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash',
    '-f','C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash\config.yaml'
  ) `
  -WorkingDirectory 'C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash' `
  -WindowStyle Hidden
```

## 9. 如果要回滚本次手动修复

如果以后飞鸟官方客户端更新正常，想撤销本次手动接管，可以执行下面思路。

### 9.1 删除自启动任务

```powershell
Unregister-ScheduledTask -TaskName 'FeiniaoClashCoreFix' -Confirm:$false
```

### 9.2 停止手动启动的核心

先查看：

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq 'core.exe' } |
  Select-Object ProcessId,CommandLine
```

确认是 `data\clash\config.yaml` 那个核心后再停止。

### 9.3 关闭系统代理

```powershell
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Type DWord -Value 0
netsh winhttp reset proxy
```

然后重新打开飞鸟官方客户端，让它自己接管。

## 10. 最终判断

本次故障的核心原因是：

1. 飞鸟主核心启动时找不到 `geoip.metadb`，又无法在无代理状态下从 GitHub 下载，导致主核心无法正常启动。
2. Windows 系统代理开关处于关闭状态，外网请求没有走飞鸟代理。
3. 飞鸟界面/extra 核心仍在运行，造成“看起来客户端在工作，但实际主代理没接管”的假象。

本次解决方式是：

1. 用本地 `Country.mmdb` 补齐 `geoip.metadb`。
2. 手动启动飞鸟主核心，并指定正确数据目录和配置文件。
3. 将 Windows 用户代理、WinHTTP 代理和命令行代理统一指向 `127.0.0.1:19973`。
4. 停止会干扰代理开关的飞鸟界面，只保留主核心。
5. 创建 `FeiniaoClashCoreFix` 登录自启动任务，避免重启后再次失效。

目前没有发现会立刻影响使用的隐患。主要注意点是：不要让飞鸟界面再次关闭系统代理；如果需要使用飞鸟界面切节点，操作后要重新检查 `ProxyEnable` 是否仍为 `1`。

---

## 11. 补充：事后复查发现的遗漏细节（2026-04-29 后续）

本节记录初次修复后的复查结果，以及已完成的补丁。

### 11.1 ProxyOverride 反复被第三方软件污染（已定位）

**现象**：每隔一段时间，`ProxyOverride` 就从干净值

```text
localhost;127.*;192.168.*;<local>
```

变成带重复垃圾前缀的值：

```text
;localhost.*;;localhost;127.*;192.168.*;<local>
```

**排查**：检查开机自启动项，发现以下三个软件会主动修改 WinHTTP/WinINET 代理设置：

| 软件 | 启动路径 | 原因 |
|------|---------|------|
| **通义千问（QianwenApp）** | `E:\QianwenApp\qianwen.exe` | Chrome Electron 内核，其自动更新程序 `QianwenUpdater` 的启动参数里明确包含 `--vmodule=*/components/winhttp/*=1`，说明它会在更新检查时操作 WinHTTP/WinINET 设置 |
| **OneDrive** | `C:\...\OneDrive.exe /background` | 已知会在代理设置变化时写回 ProxyOverride |
| **百度网盘** | `E:\BaiduNetdisk\YunDetectService.exe` | 已知会修改系统代理旁路列表 |

**影响**：不会导致代理失效（`ProxyEnable` 和 `ProxyServer` 不受影响），但 ProxyOverride 里出现的 `localhost.*` 模式是这些软件自己追加进去的，会让旁路规则略微膨胀。

**已知风险**：如果这些软件误将 `ProxyEnable` 改成 `0`，代理就会中断。目前尚未观察到这种情况，但属于潜在隐患。

**建议**：如果代理突然失效，先用第 8.5 节的快速恢复命令重置代理设置，再检查上述软件是否有更新动作日志。

---

### 11.2 自启动任务缺少崩溃自动重启（已修复）

**问题**：初次创建 `FeiniaoClashCoreFix` 时，`RestartCount = 0`，意味着 `core.exe` 崩溃后任务不会自动拉起，代理会持续断掉直到下次登录。

**修复**：已重建任务，新参数如下：

```powershell
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -ExecutionTimeLimit (New-TimeSpan -Days 365) `
  -MultipleInstances IgnoreNew `
  -RestartCount 5 `
  -RestartInterval (New-TimeSpan -Minutes 1)
```

当前任务参数（已验证）：

```text
RestartCount      : 5
RestartInterval   : PT1M
MultipleInstances : IgnoreNew
ExecutionTimeLimit: P365D
```

含义：`core.exe` 崩溃后每隔 1 分钟自动尝试重启，最多重试 5 次；重复触发时忽略新实例，不会产生多个核心进程争端口。

---

### 11.3 自启动任务以 Limited 权限运行（已确认，当前够用）

**检查**：

```text
UserId    : Administrator
RunLevel  : Limited
LogonType : Interactive
```

`Limited`（非管理员级别）对当前的代理模式（HTTP/SOCKS5 系统代理，端口 19973）是够用的——`core.exe` 绑定 127.0.0.1 不需要提权。

**注意**：如果以后需要开启 TUN/TAP 模式（全局路由接管），`core.exe` 需要安装 TAP 驱动路由规则，届时 `RunLevel` 需要改为 `HighestAvailable`。

---

### 11.4 `geoip.metadb` 文件格式问题（已知兼容性修复）

**现状**：当前 `geoip.metadb` 是由 `Country.mmdb`（MaxMind MMDB 格式）直接复制而来。

MetaCubeX（Mihomo-meta）官方的 `geoip.metadb` 使用的是自定义的 `db` 格式（包含更多字段），与 MaxMind 标准 MMDB 不完全一致。

**为什么目前能用**：核心在 GEOIP 规则匹配（如 `GEOIP,CN,DIRECT`）时读取的主要字段是 IP 所属国家代码，这部分两种格式兼容。

**潜在风险**：如果规则配置里用到了 MetaCubeX 扩展字段（如 ASN 匹配），可能匹配失败并 fallback。目前日志里未见报错。

**最终建议**：等代理稳定后，手动访问以下地址下载官方文件（需要代理开着）：

```
https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.metadb
```

覆盖 `C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash\geoip.metadb`。

---

### 11.5 用户删除 OneDrive 和通义千问后的清理补丁（2026-04-29 二次复查）

**背景**：用户手动删除了 OneDrive 和通义千问主程序，但复查发现 ProxyOverride 仍然被污染。

**原因**：

1. **百度网盘的 `YunDetectService.exe`** 仍在自启动列表且当时可能正在运行：
   ```text
   HKCU:\...\Run\BaiduYunDetect = "E:\BaiduNetdisk\YunDetectService.exe"
   ```

2. **通义千问更新程序残留**：删除主程序后，注册表自启动项 `QianwenUpdaterTaskUser1.0.0.3` 未被清除，其可执行文件目录 `C:\Users\Administrator\AppData\Local\QianwenUpdater\` 仍然存在并可以被触发。

**已执行操作**：

```powershell
# 停止进程
Stop-Process -Name 'YunDetectService','BaiduNetdisk' -Force -ErrorAction SilentlyContinue

# 删除自启动注册表项
Remove-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'BaiduYunDetect'
Remove-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'QianwenUpdaterTaskUser1.0.0.3'

# 删除 QianwenUpdater 残留目录
Remove-Item 'C:\Users\Administrator\AppData\Local\QianwenUpdater' -Recurse -Force
```

**清理后 HKCU 自启动项（已确认干净）**：

| 名称 | 路径 | 代理干扰风险 |
|------|------|------------|
| Steam | `E:\steam\steam.exe -silent` | 无 |
| iFlyInput | `e:\iFlytek\iFlyIME\3.0.1750\iFlyInput.exe` | 无 |
| ctfmon | `C:\Windows\system32\ctfmon.exe` | 无（系统组件） |
| WinCleaner.FileSystem | `...\NetpowerWinCleaner\WinCleaner.FileSystem.exe` | 低（清理工具，无代理操作记录） |

**清理后代理状态（已验证）**：

```text
ProxyEnable   : 1
ProxyServer   : 127.0.0.1:19973
ProxyOverride : localhost;127.*;192.168.*;<local>   ← 干净值，无重复
```

**外网验证**：`curl -x http://127.0.0.1:19973 https://www.google.com` → `HTTP/1.1 200 OK` ✅

---

### 11.6 飞鸟界面导致 GUI stopClash 的根本原因未查明

**现象**：日志里有 `stopCalsh` 调用，然后主核心被终止。

**未查明的问题**：是版本校验失败、更新检测、还是 GUI 的正常连接/断开逻辑误触发了停止？没有找到飞鸟客户端的源码，无法确认。

**目前的规避方案**：绕过 GUI，直接用后台 `core.exe` 服务代理。如果需要切节点，可以用 Clash 的 RESTful API 操作（`127.0.0.1:19092`，secret 见 config.yaml），不需要开飞鸟界面。

---

### 11.7 再次复现：打开飞鸟 GUI 后代理又失效（2026-04-29）

**复现现象**：用户手动打开 `E:\飞鸟加速\飞鸟加速.exe` 后，外网再次不可用。

**复查结果**：

```text
飞鸟 GUI:       已启动
主 core:        仍在运行，监听 127.0.0.1:19973 / 127.0.0.1:19092
clashExtra:     被 GUI 再次拉起
ProxyEnable:    被 GUI 改成 0
ProxyServer:    仍是 127.0.0.1:19973
ProxyOverride:  再次变脏
```

这次进一步确认：**飞鸟 GUI 本身就是当前故障触发器**。主 core 没坏，节点也没坏；真正导致不可用的是 GUI 打开后把 Windows 系统代理开关关掉。

**本次恢复动作**：

1. 停止 `飞鸟加速.exe`。
2. 停止 GUI 拉起的 `clashExtra` core。
3. 保留主 core：`data\clash\config.yaml`。
4. 恢复 `ProxyEnable = 1`。
5. 恢复 `ProxyServer = 127.0.0.1:19973`。
6. 清理 `ProxyOverride = localhost;127.*;192.168.*;<local>`。
7. 同步 WinHTTP 代理。

**恢复后验证**：

```text
ProxyEnable   : 1
ProxyServer   : 127.0.0.1:19973
ProxyOverride : localhost;127.*;192.168.*;<local>

127.0.0.1:19973  core.exe
127.0.0.1:19092  core.exe

curl -x http://127.0.0.1:19973 https://www.google.com -> HTTP/1.1 200 OK
```

**新增一键恢复脚本**：

```text
D:\ai改造\飞鸟vpn一键恢复.ps1
```

以后如果误打开飞鸟 GUI 导致代理又坏，执行：

```powershell
powershell -ExecutionPolicy Bypass -File 'D:\ai改造\飞鸟vpn一键恢复.ps1'
```

即可自动完成：停 GUI、停 clashExtra、启动/保留主 core、恢复系统代理、同步 WinHTTP。

---

### 11.8 为什么“不打开飞鸟能用，打开飞鸟反而不能用”

这不是正常状态。正常情况下，飞鸟 GUI 应该负责：

1. 生成 Clash 配置。
2. 启动 `core.exe`。
3. 打开 Windows 系统代理。
4. 把系统代理指向 core 的监听端口。

本机现在异常在第 3、4 步：GUI 打开后重新生成配置，但没有正确同步系统代理。

**实测证据**：

打开 GUI 后，主配置被改成了新的随机端口：

```yaml
mixed-port: 24080
external-controller: 127.0.0.1:18548
```

而 Windows 代理仍然残留/被修复脚本固定在：

```text
ProxyServer = 127.0.0.1:19973
```

同时 GUI 还会把：

```text
ProxyEnable = 0
```

也就是把系统代理开关关掉。

所以现象就变成：

- 不打开 GUI：后台手动启动的主 core 继续监听 `19973`，系统代理也指向 `19973`，因此能用。
- 打开 GUI：GUI 重新生成随机端口配置，又关闭系统代理，导致浏览器不再走代理，因此不能用。

这说明问题不在节点，不在网络，也不在 core，而在飞鸟 GUI 当前的状态管理/配置同步逻辑。

**已做的加固修复**：

1. 将 `config.yaml` 固定回：

  ```yaml
  mixed-port: 19973
  external-controller: 127.0.0.1:19092
  ```

2. 升级 `D:\ai改造\飞鸟vpn一键恢复.ps1`：
  - 每次运行都会先把配置端口强制修回 `19973/19092`。
  - 停止 `飞鸟加速.exe`。
  - 停止 `clashExtra`。
  - 确保主 core 正在监听 `19973/19092`。
  - 恢复 `ProxyEnable=1`。
  - 恢复 `ProxyServer=127.0.0.1:19973`。
  - 同步 WinHTTP。

3. 将登录任务 `FeiniaoClashCoreFix` 从“直接启动 core.exe”改为“执行一键恢复脚本”。

这样即使 GUI 以后再次改乱配置，重启登录或手动执行脚本都能恢复到固定端口方案。

---

## 12. 与飞鸟类似的 VPN/代理客户端参考

飞鸟加速本质是一个 **Clash/Mihomo-meta 内核 + 私有 GUI** 的商业代理客户端，节点协议主要是 VMess。

以下是同类的开源/免费客户端，可以自带节点或导入机场订阅使用：

### 12.1 Clash 系（与飞鸟内核相同，兼容性最好）

| 客户端 | 特点 | 下载 |
|--------|------|------|
| **Clash Verge Rev** | 最活跃维护的 Clash GUI，Rust + Tauri 开发，内置 Mihomo 核心，支持订阅管理、规则、TUN 模式 | GitHub: clash-verge-rev/clash-verge-rev |
| **Mihomo Party** | 轻量 GUI，直接套壳 Mihomo 核心，界面简洁 | GitHub: mihomo-party-org/mihomo-party |
| **clash-nyanpasu** | 功能丰富，支持多内核切换（Clash/Mihomo/sing-box） | GitHub: LibNyanpasu/clash-nyanpasu |

**关键优势**：可以直接把飞鸟的 `config.yaml` 导入使用，因为它们用的是同一个内核格式。

### 12.2 V2Ray/Xray 系（协议覆盖更广）

| 客户端 | 特点 |
|--------|------|
| **v2rayN** | Windows 最主流的 V2Ray GUI，支持 VMess/VLESS/Trojan/SS/ShadowTLS，开源免费 |
| **Nekoray** | 支持 sing-box 和 v2ray 双内核，界面清爽，规则配置灵活 |

### 12.3 sing-box 系（新一代，性能最好）

| 客户端 | 特点 |
|--------|------|
| **sing-box** | 官方跨平台核心，协议最全，配置偏复杂，适合高阶用户 |
| **hiddify** | sing-box 的 GUI 封装，多平台支持，上手相对简单 |

### 12.4 使用建议

- **如果你有机场订阅**：推荐 **Clash Verge Rev**，直接粘贴订阅链接，自动拉取节点，配置文件和飞鸟完全兼容。

- **如果需要自建节点**：推荐 **v2rayN**，手动添加服务器更方便，界面直观。

- **注意**：上述客户端都是只提供软件，不含节点。节点需要自己购买机场服务或自建服务器。飞鸟加速是付费机场服务 + 专属 GUI 打包，如果飞鸟的节点本身没问题，继续用本次修复后的方案即可。

---

## 13. 经验更正：为什么这次又能回到飞鸟自己的 exe（2026-04-29）

本轮复查后，最终决定**不要再单独写 bat/ps1 启动 `core.exe`**，而是恢复为正常打开飞鸟官方客户端：

```text
E:\飞鸟加速\飞鸟加速.exe
```

并已在桌面重新创建官方快捷方式：

```text
C:\Users\Administrator\Desktop\飞鸟加速.lnk
```

### 13.1 为什么之前会判断成“要绕过 GUI”

当时看到的现象是：

1. 飞鸟界面能打开，但系统代理没有打开。
2. 主代理端口和 GUI 生成的端口不一致。
3. `ProxyEnable` 经常被改成 `0`。
4. 打开 GUI 后有时又拉起 `clashExtra`，导致本地同时出现多个 core。

所以当时采用了临时抢修方案：固定 `config.yaml` 端口，手动启动主 `core.exe`，再手动设置 Windows 代理。

这个方案可以救急，但有两个明显副作用：

- 飞鸟官方界面无法正常管理节点、全局代理、规则模式。
- 自己写的 PowerShell 控制台会遇到中文编码问题，节点列表显示乱码，使用体验很差。

### 13.2 为什么现在又可以直接用飞鸟官方 exe

因为后续复查确认：官方程序本身并没有坏到不能启动。

实测打开官方程序后，系统里能看到：

```text
飞鸟加速.exe
core.exe
msedgewebview2.exe
```

这说明飞鸟 GUI 能正常启动，并且能自己拉起它需要的 `core.exe`。

之前不能用，更多是因为本地被我们和飞鸟反复修改后进入了混乱状态：

1. 手动脚本固定了 `mixed-port: 19973` 和 `external-controller: 127.0.0.1:19092`。
2. 飞鸟 GUI 又会按自己的逻辑生成或切换端口。
3. Windows 代理开关、代理端口、飞鸟 GUI 状态三者没有保持一致。
4. 手动启动 core 与官方 GUI 自己启动 core 会互相抢端口、抢配置。

清掉这些外部干预后，应该让官方飞鸟重新接管：

- 启动由 `飞鸟加速.exe` 完成。
- 节点选择由飞鸟界面完成。
- 全局代理/规则模式由飞鸟界面完成。
- 不再用单独 bat/ps1 操作节点。

### 13.3 本轮已撤销的错误方向

已经删除 `D:\fix_vpn` 下此前创建的辅助脚本：

```text
飞鸟启动.bat
飞鸟启动.ps1
飞鸟停止.bat
飞鸟停止.ps1
飞鸟控制.bat
飞鸟控制.ps1
飞鸟vpn一键恢复.ps1
```

删除原因：

- 用户希望正常使用飞鸟官方 GUI，而不是另搞一套启动器。
- 控制台节点列表中文显示乱码，不适合实际使用。
- 单独启动 core 会破坏飞鸟 GUI 对节点、模式、代理开关的统一管理。

### 13.4 当前正确使用方式

以后正常使用方式应改为：

1. 开机后默认不运行飞鸟，也不启用系统代理。
2. 需要翻墙时，双击桌面 `飞鸟加速.lnk`。
3. 在飞鸟官方界面里选择节点、全局代理或规则模式。
4. 不需要时，在飞鸟官方界面里断开或退出。

当前已确认：

```text
桌面快捷方式：C:\Users\Administrator\Desktop\飞鸟加速.lnk
快捷方式目标：E:\飞鸟加速\飞鸟加速.exe
目标文件存在：True
当前 ProxyEnable：0
当前 ProxyServer：空
当前 ProxyOverride：空
```

也就是说，当前电脑已经回到“默认直连，想用时打开官方飞鸟”的状态。

### 13.5 如果打开官方飞鸟后仍提示网络异常

如果官方界面仍出现类似：

```text
网络异常 http://175.178.73.208:54620/api/v2/user/agent/desc
```

这类问题通常不是本地 `core.exe` 或代理脚本问题，而是飞鸟官方服务端、账号订阅、线路接口或客户端更新接口异常。

本地能做的检查顺序：

1. 先确认系统没有被旧脚本固定代理：`ProxyEnable` 应该由飞鸟界面控制。
2. 关闭飞鸟后确认没有残留 `core.exe`。
3. 重新打开 `E:\飞鸟加速\飞鸟加速.exe`。
4. 如果界面仍然报同一个官方 API 异常，优先判断为飞鸟服务端或账号问题。

不要再优先写脚本绕过 GUI。只有在“官方客户端完全不可用，但本地已有可用 Clash 配置并且急需临时联网”的情况下，才考虑临时手动启动 `core.exe`。

### 13.6 下次处理优先级

以后遇到飞鸟问题，按这个顺序处理：

1. **先恢复官方 GUI**：确认 `E:\飞鸟加速\飞鸟加速.exe` 能打开。
2. **确认桌面快捷方式**：只保留官方快捷方式，不用 bat。
3. **清理外部干预**：删除自写脚本、计划任务、固定端口代理设置。
4. **让飞鸟自己接管代理**：节点、模式、系统代理开关都在 GUI 里操作。
5. **最后才考虑 core 手动模式**：仅作为救急，不作为长期方案。

本次最重要的经验：

> 能用官方客户端就不要绕过官方客户端。手动 core 适合救急，但不适合日常使用；否则节点切换、模式切换、代理开关都会脱离飞鸟自己的状态管理，越修越乱。

---

## 14. grok.com 无法登录 —— Cloudflare Managed Challenge 问题（2026-04-29）

### 14.1 故障现象

- 可以正常访问 Google、Gemini、x.com
- 唯独 grok.com 无法访问/登录
- 浏览器显示 Cloudflare "Just a moment..." 页面后无法通过

### 14.2 根因分析

grok.com 使用 Cloudflare，且配置了 `cType: managed`（Managed Challenge）。

诊断方法：用 curl 通过代理访问 grok.com，检查 `CF-RAY` 响应头中的节点位置代码：

```powershell
curl.exe -v --max-time 15 -x "http://127.0.0.1:{代理端口}" https://grok.com 2>&1 | Select-String 'CF-RAY|cType'
```

| 节点 | CF-RAY 后缀 | 结果 |
|------|------------|------|
| 台湾节点 | `-TPE`（台北） | Managed Challenge，浏览器也难通过 |
| 美国节点 | 无地区后缀 | Managed Challenge，浏览器通常可通过 |

**结论**：grok.com 是 xAI 的产品，Cloudflare 规则对亚洲代理节点更严格。必须走美国节点。

### 14.3 解决方式

1. 在飞鸟 GUI 中切换到**美国节点**（美国-01 到 美国-10）
2. 重新访问 grok.com，等待 Cloudflare "Just a moment..." 自动通过（需要 JavaScript）
3. 如果某个美国节点仍无法通过 challenge，换下一个美国节点

**通过 Clash API 切换节点的 PowerShell 方法**（GUI 不方便时）：

```powershell
# 1. 找到当前 API 端口（config.yaml 里的 external-controller 字段）
Select-String -Path 'C:\Users\Administrator\AppData\Local\com.fnjs.clash\data\clash\config.yaml' -Pattern 'external-controller|secret'

# 2. 写入目标节点JSON（用 Unicode 转义避免编码问题）
# 美=\u7f8e 国=\u56fd 日=\u65e5 本=\u672c 香=\u9999 港=\u6e2f 台=\u53f0 湾=\u6e7e
$node = '{"name":"\u7f8e\u56fd-01"}'   # 美国-01
[System.IO.File]::WriteAllText('C:\temp_node.json', $node, (New-Object System.Text.UTF8Encoding($false)))

# 3. 发送切换请求
curl.exe -s -X PUT -H "Authorization: Bearer {secret}" -H "Content-Type: application/json" --data-binary "@C:\temp_node.json" "http://127.0.0.1:{api端口}/proxies/PROXY"
```

> **注意**：PowerShell 5.1 在处理管道中的中文字符时会乱码，必须用 Unicode 转义写入文件后再传给 curl。直接拼接字符串传给 curl 的 `-d` 参数会导致 `{"message":"Body invalid"}`。

### 14.4 为什么 x.com 可以而 grok.com 不行

两者都用 Cloudflare，但 grok.com 的 WAF 规则独立配置，对代理/VPN IP 的限制比 x.com 更严格。

常见的拦截规则差异：

| 站点 | Cloudflare 策略 |
|------|----------------|
| x.com | 允许大部分 VPN 节点通过 |
| grok.com | 对非住宅 IP 启用 Managed Challenge，亚洲数据中心 IP 更难通过 |

### 14.5 备选方案

如果所有美国节点都无法通过 grok.com 的 Cloudflare 验证：

- 通过 **x.com 内的 Grok 入口**（https://x.com/i/grok）访问，绕开 grok.com 的独立 WAF 规则
- 考虑使用 xAI 的 API（api.x.ai）直接调用，不依赖 Web 界面


---

## 14. 2026-04-30 补充：飞鸟端口从 19973 变 20835，WinHTTP 未设置

### 故障现象

- 打开飞鸟 GUI 并选节点后，Simplenote 同步、Python requests 等均正常（说明 WinINET 代理已由飞鸟 GUI 接管）
- 但 `curl.exe` 等命令行工具无法访问外网（000）
- `netsh winhttp show proxy` 显示"直接访问（没有代理服务器）"

### 根因

飞鸟 GUI 本次启动后将配置端口改为 `20835`（系统代理已正确更新为 20835），但没有同步更新 WinHTTP 代理。

另外有两个 `core.exe` 在运行（主核心 20835 + clashExtra 23114），需要清理 clashExtra。

### 修复步骤（2026-04-30 已执行）

```powershell
# 1. 停止 clashExtra（多余的 core，端口 21474/23114）
Stop-Process -Id <clashExtra的PID> -Force

# 2. 补设 WinHTTP 代理（端口必须与飞鸟当前实际端口一致）
$port = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings').ProxyServer -replace '127.0.0.1:',''
netsh winhttp set proxy "127.0.0.1:$port" "localhost;127.*;192.168.*;<local>"

# 3. 持久化用户环境变量
[Environment]::SetEnvironmentVariable('HTTP_PROXY',  "http://127.0.0.1:$port",  'User')
[Environment]::SetEnvironmentVariable('HTTPS_PROXY', "http://127.0.0.1:$port",  'User')
[Environment]::SetEnvironmentVariable('ALL_PROXY',   "socks5://127.0.0.1:$port",'User')
```

### ⚠️ 关键注意：飞鸟端口不固定

飞鸟 GUI 每次启动分配的 `mixed-port` 可能不同（见过 19973、24080、20835 等）。

**每次飞鸟重启后**，如果 curl/Python 失效，需要：

1. 查当前实际端口：`(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings').ProxyServer`
2. 重新设 WinHTTP：`netsh winhttp set proxy 127.0.0.1:<实际端口> "localhost;127.*;192.168.*;<local>"`
3. 在新终端里，环境变量会从用户变量自动继承（如果上面的步骤 3 已持久化）

### 修复后验证（2026-04-30）

```text
代理核心:        core.exe  PID=36768  端口 20835/19336
系统代理:        ProxyEnable=1  ProxyServer=127.0.0.1:20835
WinHTTP:         127.0.0.1:20835
用户环境变量:    HTTP_PROXY=http://127.0.0.1:20835
WinINET 测试:    Invoke-WebRequest google.com → 200 ✅
curl 测试:       curl + $env:HTTPS_PROXY → 200 ✅
```

---

## 15. VS Code Copilot 连接失败 —— 代理端口不一致（2026-05-01）

### 15.1 故障现象

- VS Code GitHub Copilot Chat 报错：`connect ECONNREFUSED 127.0.0.1:20835`
- 环境变量 `HTTP_PROXY=http://127.0.0.1:20835`，但当前实际代理端口已变为 `1081`（QingZhou）
- `netsh winhttp show proxy` 显示 `127.0.0.1:20835`，与当前实际端口不一致
- 系统注册表 `ProxyServer` 残留旧值 `localhost:1081`，`ProxyEnable=0`

### 15.2 根因分析

**根本原因是 VPN 切换后，各层代理设置没有同步更新。**

具体表现为四层代理状态不一致：

| 层级 | 故障前值 | 当前实际代理 | 状态 |
|------|---------|-------------|------|
| WinINET 注册表 | `localhost:1081` / `ProxyEnable=0` | `127.0.0.1:1081` | ❌ 开关关闭，地址格式不对 |
| WinHTTP | `127.0.0.1:20835` | `127.0.0.1:1081` | ❌ 端口过期 |
| 用户环境变量 | `http://127.0.0.1:20835` | `http://127.0.0.1:1081` | ❌ 端口过期 |
| VS Code 内部 | 读取环境变量 → 20835 | 实际代理 1081 | ❌ 连接被拒 |

Copilot 报错 `ECONNREFUSED 127.0.0.1:20835` 是因为 VS Code 通过环境变量找到了 20835，但那个端口已经没有任何进程在监听。

### 15.3 为什么 VPN 切换会导致这个问题

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

### 15.4 修复步骤（2026-05-01 已执行）

```powershell
# 1. 确认当前实际代理端口（QingZhou 监听 1081）
netstat -ano | findstr LISTENING | findstr 1081
# → PID 6776 = QingZhou.exe

# 2. 修复 WinINET 代理开关和地址
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Type DWord -Value 1
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyServer -Type String -Value '127.0.0.1:1081'

# 3. 修复 WinHTTP 代理
netsh winhttp set proxy "127.0.0.1:1081" "localhost;127.*;192.168.*;<local>"

# 4. 持久化用户环境变量
[Environment]::SetEnvironmentVariable('HTTP_PROXY',  'http://127.0.0.1:1081',  'User')
[Environment]::SetEnvironmentVariable('HTTPS_PROXY', 'http://127.0.0.1:1081',  'User')
[Environment]::SetEnvironmentVariable('ALL_PROXY',   'socks5://127.0.0.1:1081','User')
```

### 15.5 修复后验证

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

### 15.6 通用解决方案：自动检测并修复代理不一致

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

### 15.7 经验总结

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
