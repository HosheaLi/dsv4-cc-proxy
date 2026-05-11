# 更新发布流程

## 当前发布渠道一览

| 渠道 | 地址 | 更新方式 | 状态 |
|---|---|---|---|
| GitHub 源码 | https://github.com/HosheaLi/dsv4-cc-proxy | `git push` | 已发布 |
| Docker Hub | `hosheali/dsv4-cc-proxy` | CI 自动推送 (push main 触发) | 已发布 |
| GitHub Pages | https://hosheali.github.io/dsv4-cc-proxy | CI 自动部署 (push main 触发) | 已发布 |
| PyPI | `dsv4-cc-proxy` | 待实现 (需 pyproject.toml + tag 触发 CI) | 待实现 |
| Homebrew Tap | `HosheaLi/homebrew-tap` | 待实现 (Formula + CI 自动更新) | 待实现 |

---

## 目标发布渠道 (全部实现后)

| 平台 | 安装命令 |
|---|---|
| macOS | `brew tap HosheaLi/tap && brew install dsv4-cc-proxy && brew services start dsv4-cc-proxy` |
| Windows/Linux | `pip install dsv4-cc-proxy && dsv4-cc-proxy` |
| 通用 (容器化) | `docker run -d --restart unless-stopped -p 16889:16889 hosheali/dsv4-cc-proxy:latest` |

---

## 一、发布前准备工作 (本次需完成)

### 1. 代码打包为 Python 标准包

当前项目结构:
```
proxy/
  deepseek-thinking-proxy.py    # 主程序
  test_proxy.py                 # 测试
  requirements.txt              # 依赖
```

需改造为:
```
proxy/
  dsv4_cc_proxy/
    __init__.py        # VERSION + app 创建
    proxy.py           # 主逻辑 (从 deepseek-thinking-proxy.py 拆分)
    __main__.py        # CLI 入口
  tests/
    test_proxy.py
  pyproject.toml       # 包元数据
  requirements.txt     # (保留兼容)
```

### 2. 创建 pyproject.toml

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "dsv4-cc-proxy"
version = "1.8"
description = "DeepSeek Anthropic API compatibility proxy for Claude Code"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [{name = "HosheaLi"}]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Internet :: Proxy Servers",
]
dependencies = [
    "httpx>=0.27.0",
    "uvicorn>=0.29.0",
    "starlette>=0.37.0",
]

[project.urls]
Homepage = "https://github.com/HosheaLi/dsv4-cc-proxy"
Source = "https://github.com/HosheaLi/dsv4-cc-proxy"

[project.scripts]
dsv4-cc-proxy = "dsv4_cc_proxy.__main__:main"
```

### 3. 发布 PyPI

```bash
pip install build twine
python -m build
twine upload dist/*
```

### 4. 创建 Homebrew Tap

创建仓库 `github.com/HosheaLi/homebrew-tap`，添加 `Formula/dsv4-cc-proxy.rb`。

### 5. 更新 CI (补充 PyPI 发布 + 版本 tag)

在 `.github/workflows/ci.yml` 中添加:
- tag 推送触发 PyPI 发布
- Docker 构建增加语义化版本标签 (v1.8, v1.8.0 等)

---

## 二、每次发布的标准流程 (完成上述改造后)

### 步骤 1: 更新版本号

修改 `proxy/dsv4_cc_proxy/__init__.py`:

```python
VERSION = "1.9"
```

### 步骤 2: 修改代码 + 测试通过

```bash
cd proxy
python3 -m pytest tests/test_proxy.py -v
```

### 步骤 3: 提交并打 tag

```bash
git add -A
git commit -m "release: v1.9 — 功能描述"
git tag v1.9
git push origin main
git push origin v1.9
```

### 步骤 4: 等待 CI 自动发布

推送 tag 后 GitHub Actions 自动:
- 运行测试 + lint
- 发布到 PyPI
- 构建 Docker 镜像 → Docker Hub (`hosheali/dsv4-cc-proxy:v1.9` + `:latest`)
- 更新 GitHub Pages

### 步骤 5: 验证各渠道

```bash
# PyPI
pip install dsv4-cc-proxy

# Docker Hub
docker pull hosheali/dsv4-cc-proxy:latest

# 健康检查
curl http://127.0.0.1:16889/health
```

---

## 三、本机安装方式

### 当前状态

你的本机通过 launchd 运行 `~/.claude/proxy/deepseek-thinking-proxy.py`，这是**独立复制**的代码，和开发仓库 `~/code/P14_dsv4ToCC/` 是两套文件。你在仓库改代码后，运行中的代理不会自动更新。

### 推荐做法: 改为指向仓库源码

修改 launchd plist，让服务直接运行仓库中的代码:

修改文件 `~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist`，将路径改为:

```xml
<key>ProgramArguments</key>
<array>
    <string>/Users/lihaoxuan/code/P14_dsv4ToCC/proxy/.venv/bin/python3</string>
    <string>/Users/lihaoxuan/code/P14_dsv4ToCC/proxy/dsv4_cc_proxy/__main__.py</string>
</array>
<key>WorkingDirectory</key>
<string>/Users/lihaoxuan/code/P14_dsv4ToCC/proxy</string>
```

之后本机更新只需:

```bash
cd ~/code/P14_dsv4ToCC
git pull origin main
source proxy/.venv/bin/activate
pip install -r proxy/requirements.txt
launchctl unload ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist
launchctl load ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist
```

或者等 Homebrew tap 完成后，改用:

```bash
brew services restart dsv4-cc-proxy
```

### 备选: 保持独立目录但写一个更新脚本

```bash
#!/bin/bash
# ~/code/P14_dsv4ToCC/scripts/update-local.sh
set -euo pipefail
cd ~/code/P14_dsv4ToCC
git pull origin main
cp proxy/deepseek-thinking-proxy.py ~/.claude/proxy/
cp proxy/requirements.txt ~/.claude/proxy/
~/.claude/proxy/.venv/bin/pip install -r ~/.claude/proxy/requirements.txt
launchctl unload ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist
launchctl load ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist
echo "更新完成"
curl -s http://127.0.0.1:16889/health
```

---

## 四、版本号规范

遵循语义化版本 `MAJOR.MINOR.PATCH`:
- **API 不兼容变更**: 递增 MAJOR，如 `1.8.0` → `2.0.0`
- **新增向后兼容功能**: 递增 MINOR，如 `1.8.0` → `1.9.0`
- **Bug 修复/小改进**: 递增 PATCH，如 `1.8.0` → `1.8.1`

当前版本 `1.8` 建议改为 `1.8.0` (三部分语义化版本)。

git tag 格式: `v1.8.0` (带 v 前缀，CI 自动识别发布)。

---

## 五、Docker 标签改进 (CI 改造)

当前 CI 只有 `latest` 和 `sha` 两个标签，应改为:

```yaml
tags: |
  type=semver,pattern={{version}}
  type=semver,pattern={{major}}.{{minor}}
  type=raw,value=latest
  type=sha
```

这样推送 tag `v1.8.0` 时会产生:
- `hosheali/dsv4-cc-proxy:1.8.0`
- `hosheali/dsv4-cc-proxy:1.8`
- `hosheali/dsv4-cc-proxy:latest`
