# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.2] - 2026-06-19

### Fixed
- **Codex 多轮对话 tool_calls 匹配错误** — `function_call` 翻译时 `call_id` 提取优先级错误导致 400 响应：
  - Codex CLI 的 `function_call` item 同时包含 `id`（item 标识）和 `call_id`（工具调用匹配标识）
  - 旧逻辑 `item.id or item.call_id` 优先取 `id`，导致 `tool_calls[].id` 与后续 tool 消息的 `tool_call_id` 不匹配
  - DeepSeek API 校验 tool_use/tool_result 配对失败返回 `insufficient tool messages following tool_calls message`
  - 修复为 `item.call_id or item.id`，确保与 `function_call_output.call_id` 一致

## [2.0.1] - 2026-06-18

### Fixed
- **Codex CLI 文本不显示** — 修复三个 SSE 兼容性问题：
  - 所有流式事件统一包含 `sequence_number`（之前仅 delta 事件有）
  - response 对象字段名 `created` → `created_at`（对齐 Responses API 规范）
  - `content_part.added` 移除不规范的多余 `item_id` 字段
- 缺失 `response.output_text.done` 和 `response.content_part.done` SSE 事件
- `function_call_arguments.done` 字段 `delta` → `arguments`
- pyproject.toml 项目 URL 指向正确的仓库名 dsv4-cc-proxy
- adaptive/auto thinking 映射为 enabled，响应端透传 thinking
- translate usage 字段名修复及 input items KeyError

### Added
- SSE keepalive 心跳（3s 间隔）防止 Codex CLI 超时断开
- 参考实现对比文档（ai-adapter / llama.cpp PR #21174）

## [2.0.0] - 2026-06-07

### Added
- Codex 子包（config.py / translate.py / tools.py / sse.py）— OpenAI Responses API 协议翻译
- proxy Codex handler（/v1/responses 和 /v1/responses/compact 路由）
- E2E 集成测试（tests/test_e2e.py）
- __main__.py CLI 测试（tests/test_main.py）
- 技术文档 docs/dev/codex-integration.md
- CI 覆盖率徽章生成
- PyPI OIDC Trusted Publishing 发布
- Docker semver sha 标签

### Changed
- 版本升至 2.0.0（Codex 双协议支持 — MAJOR 版本）
- README / README.zh-CN.md 增加 Codex 支持章节
- CI 全面运行 `pytest tests/ -v`（全量测试）
- CI 中 PyPI 发布从 API token 切换为 OIDC
- 测试重构消除冗余，改善组织

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
