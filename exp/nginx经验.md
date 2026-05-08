# nginx经验

作者：copilot
日期：2026-05-05

---

## 1. 服务器网络隔离时的部署方案

### 问题描述
服务器无法直接访问 GitHub（DNS 隔离或网络限制），无法执行 `git clone`：
```
fatal: could not read Username for 'https://github.com': No such device or address
```

### 解决方案
使用 **本地导出 + SCP 上传** 方案：

#### 步骤
```powershell
# 1. 在本地生成 git 仓库的压缩包
cd <项目目录>
git archive --format zip -o project.zip main

# 2. 通过 SCP 上传到服务器
scp -i ~/.ssh/id_rsa project.zip root@<服务器IP>:<目标目录>/

# 3. 在服务器上解压
ssh -i ~/.ssh/id_rsa root@<服务器IP> "cd <目标目录> && unzip -o project.zip -d project"
```

#### 优点
- 无需服务器网络连接 GitHub
- 适合网络隔离的生产环境
- 文件完整性有保障（git archive 只打包跟踪的文件）

### 影响范围
- 所有需要在隔离网络中部署代码的场景
- 特别适用于云服务器、内网生产环境

---

## 2. PowerShell SSH 命令中的分号处理

### 问题描述
从 PowerShell 通过 SSH 执行多条 bash 命令时，使用分号分隔会报错：
```powershell
ssh user@host "command1; command2"
# Error: bash: -c: line 1: syntax error near unexpected token `;'
```

### 原因
PowerShell 将分号视为 PowerShell 的命令分隔符，而不是传递给 bash 的分隔符，导致命令格式错误。

### 解决方案
使用 `&&` 或 `||` 替代，或将复杂命令拆分为多个 SSH 调用：

```powershell
# ❌ 不推荐 - 分号处理有问题
ssh user@host "cd /path && mkdir dir; ls"

# ✅ 推荐方案 1 - 使用 && 连接
ssh user@host "cd /path && mkdir dir && ls"

# ✅ 推荐方案 2 - 分离为多个 SSH 调用
ssh user@host "cd /path && mkdir dir"
ssh user@host "ls /path"

# ✅ 推荐方案 3 - 用 bash -c 显式指定解释器
ssh user@host bash -c 'cd /path; mkdir dir; ls'
```

### 影响范围
- 所有在 PowerShell 中使用 SSH 执行远程命令的场景
- 特别是多条命令组合的场景

---

## 3. Python HTTP 服务后台启动

### 问题描述
需要在服务器上启动 Python HTTP 服务，使其在后台持续运行，不受 SSH 会话关闭影响。

### 解决方案
使用 `nohup` 启动服务，并重定向输出到日志文件：

```bash
# 启动服务
cd <服务目录>
nohup python3 api_server.py > server.log 2>&1 &

# 验证进程
ps aux | grep python3

# 查看监听端口
netstat -tlnp | grep python3

# 查看日志
tail -f server.log
```

#### 关键参数
- `nohup`：使进程对 SIGHUP 信号免疫，SSH 断开连接后进程继续运行
- `> server.log 2>&1`：重定向 stdout 和 stderr 到日志文件
- `&`：放入后台执行

#### 验证启动
- **进程检查**：`ps aux | grep python3` 看是否有对应进程
- **端口检查**：`netstat -tlnp | grep <端口号>` 验证服务已监听
- **日志检查**：`cat <logfile>` 查看启动消息

### 影响范围
- Python 服务、Node.js 应用、任何需要长期后台运行的程序
- 生产环境中的持久化服务启动

---

## 4. 部署工作流总结

### 完整流程
```
本地开发
  ↓
git commit + git push (到 GitHub)
  ↓
git archive 生成压缩包
  ↓
scp 上传到服务器
  ↓
服务器解压 + 验证文件
  ↓
nohup 启动服务
  ↓
netstat 验证监听
```

### 检查清单
- [ ] 代码已 commit 到本地仓库
- [ ] GitHub 仓库已创建
- [ ] `git push` 成功
- [ ] `git archive` 生成了压缩包
- [ ] `scp` 上传完成
- [ ] 服务器文件完整（验证关键文件存在）
- [ ] 服务已启动（ps 查看进程）
- [ ] 监听端口正确（netstat 查看）

---

## 5. 清理废弃 nginx 路由和 systemd 服务

### 问题描述
功能迭代后旧路径（如 `/liushui`）已并入新路径（`/company`），需要清理旧的 nginx location、systemd 服务和相关文件，避免端口和配置冗余。

### 操作步骤

```bash
# 1. 停止并禁用旧 systemd 服务
systemctl stop <service-name>
systemctl disable <service-name>
rm /etc/systemd/system/<service-name>.service
systemctl daemon-reload

# 2. 删除 nginx 旧 location 块（用 sed 定位行号再删除）
grep -n '# 旧路由注释' /etc/nginx/sites-enabled/default
sed -i '<开始行>,<结束行>d' /etc/nginx/sites-enabled/default

# 3. 注意：nginx 可能有多个 sites-enabled 配置文件都有旧路由！
# 要检查所有配置文件
grep -rn '旧路由关键词' /etc/nginx/
# 然后逐一清理

# 4. 重载 nginx
nginx -t && nginx -s reload

# 5. 删除旧服务对应的文件目录
rm -rf /path/to/old/service/html
```

### 踩坑：sed 行号删除范围要精确

用 `sed -i '<行1>,<行2>d'` 删除 nginx location 块时，如果范围计算有误（多删了行），可能破坏下一个 location 块的结构，导致 nginx 测试失败。

**修复方法**：在被删位置用 `sed -i '<行号>a\补回内容'` 逐行补回缺失的行，然后 `nginx -t` 验证。

### 验证方式
```bash
# 旧路由返回 404 或根路径 fallback（不再被代理到旧端口）
curl -sk -o /dev/null -w '%{http_code}' https://example.com/old-path/
# 新路由正常 200
curl -sk -o /dev/null -w '%{http_code}' https://example.com/new-path
```

### 影响范围
- nginx 配置变更影响全部线上请求路由
- 多个 sites-enabled 配置文件可能各自包含旧路由，必须逐一排查
