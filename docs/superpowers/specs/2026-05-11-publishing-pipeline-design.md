# 发布管线设计

## 目标

多平台发布: PyPI + Docker Hub + Homebrew Tap，git tag 触发自动发布。

## 当前状态

- Docker Hub `hosheali/dsv4-cc-proxy`: 已发布，push main 触发，仅 `latest` + `sha` 标签
- GitHub Pages: push main 自动部署
- 无 PyPI / Homebrew / git tag
- 版本号: `VERSION = "1.8"` 硬编码

## 目标架构

### 包结构

```
P14_dsv4ToCC/
  dsv4_cc_proxy/
    __init__.py       # VERSION = "1.8.0" + 创建 Starlette app
    proxy.py          # 主代理逻辑 (从 deepseek-thinking-proxy.py 迁移)
    __main__.py        # CLI 入口 main()
  tests/
    test_proxy.py
  pyproject.toml       # setuptools, entry point: dsv4-cc-proxy
  Dockerfile           # 引用 pyproject.toml 安装
  docker-compose.yml
  scripts/             # 启动脚本 (更新路径)
  .github/workflows/
    ci.yml             # tag 触发 PyPI+Docker 发布, push main 只跑测试
```

### 发布渠道

| 渠道 | 触发 | 产物 |
|---|---|---|
| PyPI | git tag `v*` | `dsv4-cc-proxy` 包, pip install |
| Docker Hub | git tag `v*` | `hosheali/dsv4-cc-proxy:{version} {major.minor} latest` |
| Homebrew Tap | git tag `v*` → CI 更新 Formula | `brew install dsv4-cc-proxy` |
| GitHub Pages | push main | 文档站点 |

### 版本号

- 三段式语义化: `1.8.0`
- git tag 格式: `v1.8.0`
- 来源: `dsv4_cc_proxy/__init__.py` 的 `VERSION`
- pyproject.toml 从 `__init__.py` 读取版本

### CI 工作流

```
push main        → test + lint + GitHub Pages
push tag v*      → test + lint + PyPI publish + Docker build/push + Homebrew tap update
```

## 实现步骤

### Step 1: 代码重构

- 新建 `dsv4_cc_proxy/` 包目录
- 从 `proxy/deepseek-thinking-proxy.py` 提取逻辑到 `dsv4_cc_proxy/proxy.py`
- 创建 `dsv4_cc_proxy/__main__.py` 作为 CLI 入口
- `__init__.py` 管理版本号和 app 工厂
- 移动测试到 `tests/test_proxy.py`
- 创建 `pyproject.toml`

### Step 2: 本机安装改造

- 修改 launchd plist: 指向仓库源码 `python -m dsv4_cc_proxy`
- WorkingDirectory 改为项目根
- 安装依赖: `pip install -e .`

### Step 3: CI 改造

- 拆分为 test/lint job (push main + PR 触发) 和 publish job (tag 触发)
- Docker: 添加语义化版本标签
- 新增 PyPI publish job
- 新增 Homebrew tap update job

### Step 4: Homebrew Tap

- 创建 `HosheaLi/homebrew-tap` 仓库
- 添加 `Formula/dsv4-cc-proxy.rb`
- CI 自动更新 Formula 的 version + sha256

### Step 5: 首次发布

- 版本号 `1.8.0`
- git tag `v1.8.0`
- 推送到所有渠道

## 文件变更清单

| 操作 | 文件 |
|---|---|
| 新建 | `dsv4_cc_proxy/__init__.py` |
| 新建 | `dsv4_cc_proxy/proxy.py` |
| 新建 | `dsv4_cc_proxy/__main__.py` |
| 新建 | `tests/test_proxy.py` |
| 新建 | `pyproject.toml` |
| 修改 | `Dockerfile` |
| 修改 | `.github/workflows/ci.yml` |
| 修改 | `scripts/*` 中的路径引用 |
| 修改 | `~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist` |
| 新建 | `HosheaLi/homebrew-tap/Formula/dsv4-cc-proxy.rb` |
| 删除 | `proxy/deepseek-thinking-proxy.py` |
| 删除 | `proxy/test_proxy.py` |
| 删除 | `proxy/requirements.txt` |
