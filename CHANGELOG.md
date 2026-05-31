# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.8.1] - 2026-05-23

### Fixed
- 同步文档中已有结构的安装方式和路径

### Added
- 掘金社区推广文案

## [1.8.0] - 2026-05-12

### Added
- Homebrew 发布支持（brew tap + brew services 自启）
- 中英双语 README（`README.md` + `README.zh-CN.md`）
- MIT 许可证（`LICENSE`）
- 贡献指南（`CONTRIBUTING.md`）
- Issue 模板（`.github/ISSUE_TEMPLATE/`）— bug_report + feature_request
- CI 流水线（`.github/workflows/ci.yml`）— 测试 + lint + Docker 构建推送
- Docker 部署支持（`Dockerfile` + `docker-compose.yml`）
- GitHub Pages 部署（CI 自动发布）
- macOS launchd 自启脚本（`scripts/com.deepseek.thinking-proxy.plist`）
- 推广文案（CSDN / V2EX / 掘金 / Reddit / HackerNews）
- 发布管线文档（`docs/dev/RELEASE.md`）
- 日志文件轮转（RotatingFileHandler）

### Changed
- 重构为 Python 标准包结构（`dsv4_cc_proxy/`），支持 `pip install`
- `_version.py` 作为唯一版本来源
- `pyproject.toml` 配置构建系统、entry point、可选依赖
- Docker 镜像支持多架构构建（`linux/amd64` + `linux/arm64`）
- Docker 标签策略：语义版本 + latest + sha
- 跨平台启动脚本统一（Windows batch/powershell + macOS launchd）

### Fixed
- 恢复 license 旧格式，CI 改用非 editable install 避免 setuptools 冲突
- 删除已弃用的 License 分类器，修复 CI 构建失败
- 移除构建产物，添加 `build/` 到 `.gitignore`
- 修复 ruff E402 lint 错误（import 移至文件顶部）

## [0.1.0] - 2026-05-10

### Added
- 项目初始化 — DSV4 → CC Proxy 核心代理
- 三层处理逻辑（thinking 注入 / 请求标准化 / SSE 过滤）
- 22 个单元测试覆盖核心功能
- 跨平台适配基础
- Docker 容器化支持
- GitHub 发布准备
