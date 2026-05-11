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
  MANIFEST.in          # 确保 README LICENSE scripts/ 打包进 sdist
  Dockerfile           # pip install . 后使用 entry point
  docker-compose.yml
  scripts/             # 启动脚本 (更新路径)
  .github/workflows/
    ci.yml             # PR 跑 test+lint, push main 加 Pages, tag v* 触发发布
```

### 发布渠道

| 渠道 | 触发 | 产物 | 认证方式 |
|---|---|---|---|
| PyPI | git tag `v*` | `dsv4-cc-proxy` 包 | Trusted Publishing (OIDC) |
| Docker Hub | git tag `v*` | `hosheali/dsv4-cc-proxy:{version} {major.minor} latest` | GitHub Secret `DOCKERHUB_TOKEN` |
| Homebrew Tap | git tag `v*` | 自动更新 Formula, 指向 PyPI sdist | GitHub PAT `HOMEBREW_TAP_TOKEN` |
| GitHub Release | git tag `v*` | 创建 Release (作为 Homebrew 备用下载源) | GITHUB_TOKEN 自动 |
| GitHub Pages | push main | 文档站点 | GITHUB_TOKEN 自动 |

### 版本号

- 三段式语义化: `1.8.0`
- git tag 格式: `v1.8.0`
- 来源: `dsv4_cc_proxy/__init__.py` 的 `VERSION`
- pyproject.toml 通过 `version = {attr = "dsv4_cc_proxy.VERSION"}` 动态读取

### CI 工作流

```
push main + PR     → test + lint (ruff)
push main          → + GitHub Pages deploy
push tag v*        → test + lint + GitHub Release + PyPI publish + Docker build/push + Homebrew tap update
```

### 发布后验证

CI publish job 完成后自动执行:
1. `pip install dsv4-cc-proxy` 安装验证
2. `docker pull hosheali/dsv4-cc-proxy:latest` 拉取验证
3. `curl` 健康检查端点

### 失败处理

- tag 只进不退：部分发布失败时修复后重打 tag（递增 PATCH）
- 每个发布目标独立 job，失败不影响其他 job 重试

## 实现步骤

### Step 1: 代码重构

1. 创建 `dsv4_cc_proxy/__init__.py`: 定义 `VERSION = "1.8.0"`，导出 `create_app()` 工厂函数
2. 创建 `dsv4_cc_proxy/proxy.py`: 从 `proxy/deepseek-thinking-proxy.py` 迁移，纯逻辑，不含 `if __name__ == "__main__"` 块
   - 包内 import 使用绝对导入: `from dsv4_cc_proxy import VERSION`
3. 创建 `dsv4_cc_proxy/__main__.py`: CLI 入口，`def main()` 解析环境变量 + 启动 uvicorn
4. 创建 `tests/test_proxy.py`: 从 `proxy/test_proxy.py` 迁移，import 路径更新
5. 创建 `pyproject.toml`: 声明元数据 + 依赖 + `[project.scripts]` entry point
   - `requires-python = ">=3.11"`
   - `version = {attr = "dsv4_cc_proxy.VERSION"}`
6. 创建 `MANIFEST.in`: 包含 `README.md` `README.zh-CN.md` `LICENSE` `scripts/`
7. 更新 `Dockerfile`: 改为 `COPY . . && pip install . && CMD ["dsv4-cc-proxy"]`
8. 删除旧文件: `proxy/deepseek-thinking-proxy.py` `proxy/test_proxy.py` `proxy/requirements.txt`

### Step 2: 本机安装改造

1. 项目根安装: `pip install -e .`
2. 修改 `~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist`:
   - ProgramArguments: `python3 -m dsv4_cc_proxy`
   - WorkingDirectory: `/Users/lihaoxuan/code/P14_dsv4ToCC`
3. 重载: `launchctl unload && launchctl load`
4. 验证: `curl http://127.0.0.1:16889/health`

之后开发流程: 改代码 → 本机验证 → git commit → git tag v1.8.1 → git push --tags

### Step 3: CI 改造

拆分为 3 个 job:

**test** (push main + PR 触发):
- checkout → setup-python → pip install -e .[test] → pytest + ruff

**pages** (push main 触发):
- 已有，保持不变

**publish** (tag v* 触发):
- test + lint (复用 test job)
- github-release: 创建 GitHub Release (从 pyproject.toml 读版本号)
- pypi-publish: Trusted Publishing (OIDC)，无需 token
- docker-publish: 构建 + docker/metadata-action (添加 semver 标签) + push
- homebrew-update: 检出 HosheaLi/homebrew-tap → 更新 Formula 的 url/sha256 → push

认证 secret 配置:
- `DOCKERHUB_TOKEN`: Docker Hub personal access token
- `HOMEBREW_TAP_TOKEN`: GitHub personal access token (repo scope)

### Step 4: Homebrew Tap

在 `HosheaLi/homebrew-tap` 仓库中创建 `Formula/dsv4-cc-proxy.rb`:
- 使用 `virtualenv_install_with_resources` (纯 Python 包)
- url 指向 PyPI sdist: `https://files.pythonhosted.org/packages/source/d/dsv4-cc-proxy/dsv4_cc_proxy-{version}.tar.gz`
- `depends_on "python@3.13"` (仅声明 Python 依赖，无其他系统依赖)
- `service` block: keep_alive + 端口 16889

CI 自动更新: publish job 中运行脚本，用新的 version + sha256 替换 Formula 中的值并 push。

### Step 5: 首次发布

1. 确认代码在本机验证通过
2. 版本号 `1.8.0` 已在 `dsv4_cc_proxy/__init__.py`
3. `git add -A && git commit -m "release: v1.8.0 — 初始多平台发布"`
4. `git tag v1.8.0`
5. `git push origin main && git push origin v1.8.0`
6. 在 Actions 页确认 CI publish 全部成功
7. 手动验证: `pip install dsv4-cc-proxy` / `docker pull hosheali/dsv4-cc-proxy:1.8.0`
8. 验证 Homebrew: `brew tap HosheaLi/tap && brew install dsv4-cc-proxy`

## 文件变更清单

| 操作 | 文件 |
|---|---|
| 新建 | `dsv4_cc_proxy/__init__.py` |
| 新建 | `dsv4_cc_proxy/proxy.py` |
| 新建 | `dsv4_cc_proxy/__main__.py` |
| 新建 | `tests/test_proxy.py` |
| 新建 | `pyproject.toml` |
| 新建 | `MANIFEST.in` |
| 修改 | `Dockerfile` |
| 修改 | `.github/workflows/ci.yml` |
| 修改 | `scripts/*` 中的路径引用 |
| 修改 | `~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist` |
| 新建 | `HosheaLi/homebrew-tap/Formula/dsv4-cc-proxy.rb` |
| 删除 | `proxy/deepseek-thinking-proxy.py` |
| 删除 | `proxy/test_proxy.py` |
| 删除 | `proxy/requirements.txt` |
