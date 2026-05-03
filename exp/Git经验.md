# Git 经验
作者：copilot

---

## 1. 新建本地仓库并 push 到 GitHub

### 场景
本地已有项目目录，GitHub 上手动创建了同名空仓库，需要将本地项目推送上去。

### 步骤
```powershell
cd <项目目录>
git init
git add .
git commit -m "init: initial commit"
git remote add origin https://github.com/<用户名>/<仓库名>.git
git branch -M main
git push -u origin main
```

---

## 2. GitHub Push Protection 阻止包含密钥的 push

### 问题描述
push 时 GitHub 报错：
```
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: - GITHUB PUSH PROTECTION
remote:   Push cannot contain secrets
```

### 原因
GitHub 的 Secret Scanning Push Protection 会扫描 commit 内容，检测到 AccessKey、Token 等敏感信息后拒绝 push。

### 解决方法
1. 编辑包含密钥的文件，将明文密钥替换为占位符（如 `<已脱敏，见本地 onlinenote.md>`）
2. 用 `git commit --amend --no-edit` 将修改合并到上一个 commit，**彻底从历史中消除密钥**
3. 重新 push

```powershell
# 脱敏文件后
git add <含密钥的文件>
git commit --amend --no-edit   # 覆盖上一个 commit，不新增提交
git push -u origin main
```

### ⚠️ 注意
- 不能只修改文件再新 commit，因为旧 commit 里的密钥还在历史中，仍会被拒绝
- 必须用 `--amend`（或 `rebase`）把密钥从历史里抹掉

### 影响范围
- 所有含明文 AccessKey ID/Secret、Token、密码的文件
- 建议将敏感信息保存在本地 `onlinenote.md` 中，仓库里只保留脱敏占位符
