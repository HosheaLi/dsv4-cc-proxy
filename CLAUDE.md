# dsv4-cc-proxy

**DeepSeek Anthropic API 兼容性代理** — 让 Claude Code 在 DeepSeek V4 模型上稳定运行。

## 架构概要

```
proxy/dsv4_cc_proxy/           # 包源码
proxy/tests/                   # 测试
scripts/                       # 各平台启动脚本
Dockerfile                     # Docker 多阶段构建
```

三层处理（`POST /v1/messages`）:
1. **thinking 注入**: assistant tool_use 前补空 thinking 块
2. **请求标准化**: adaptive → disabled，移除 reasoning_effort
3. **SSE 过滤**: 剥离 DeepSeek 无条件返回的 thinking/thinking_delta/signature_delta

## 重要索引

| 内容 | 位置 |
|------|------|
| 发布历史 | `CHANGELOG.md` |
| 发布文档 | `docs/dev/RELEASE.md` |
| 设计文档 | `docs/dev/deepseek-thinking-proxy.md` |
| 推广文案 | `docs/promotional/` |
| 贡献指南 | `CONTRIBUTING.md` |

## 维护

- 版本号唯一来源: `dsv4_cc_proxy/_version.py`
- 测试: `pip install .[test] && pytest tests/ -v`
- 构建: `python -m build`

## 启动方式

### macOS (LaunchAgent) — 推荐

通过 `launchctl` 管理，开机自启、崩溃自动重启。

```bash
# 安装/注册
bash scripts/install_macos.sh

# 启动
launchctl load ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist

# 停止
launchctl unload ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist

# 重启
launchctl unload ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist \
  && launchctl load ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist

# 查看状态
launchctl list | grep deepseek

# 查看日志
tail -f ~/.claude/proxy/proxy.log
```

配置: `~/.claude/proxy/` 下的环境变量（`PROXY_UPSTREAM`、`PROXY_LOG_LEVEL` 等）

### 命令行 (直接启动)

```bash
# 启动 (默认端口 16889)
python -m dsv4_cc_proxy

# 启动 + 看门狗 (崩溃自动重启, 最多 5 次)
python -m dsv4_cc_proxy --watchdog

# 停止 (读取 /tmp/dsv4-cc-proxy.pid)
python -m dsv4_cc_proxy --stop

# 指定 PID 文件路径
python -m dsv4_cc_proxy --pidfile ~/.claude/proxy/proxy.pid
```

### Docker

```bash
docker-compose up -d          # 启动
docker-compose down           # 停止
docker-compose up -d --build  # 重新构建并启动
```

### Windows

- 安装服务: `powershell scripts/install_windows_service.ps1`
- 手动启动: `scripts/start.ps1` 或 `scripts/start.bat`

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PROXY_UPSTREAM` | `https://api.deepseek.com/anthropic` | 上游 API 地址 |
| `PROXY_LOG_LEVEL` | `warning` | 日志级别 |
| `PROXY_DUMP_DIR` | 空 | 调试转储目录 |
| `CODEX_DEFAULT_MODEL` | `deepseek-v4-pro` | Codex 默认模型 |
| `CODEX_MODEL_MAP` | 空 | Codex 模型映射 JSON |

<!-- GSD:project-start source:PROJECT.md -->
## Project

**dsv4-cc-proxy**

DeepSeek V4 ↔ 编程 AI CLI 兼容性代理。双向协议翻译，让 Claude Code（Anthropic Messages API）和 Codex（OpenAI Responses API）能通过 DeepSeek V4 模型运行。Starlette + httpx 异步代理，目前 434 行代码，22 个单元测试。

**Core Value:** 让开发者能用任意编程 AI 工具（Claude Code / Codex）+ DeepSeek V4 模型组合，无需等待官方兼容支持。

### Constraints

- **技术栈**：Python 3.10+、Starlette、httpx、零额外依赖
- **兼容性**：不影响现有 Anthropic Messages API 代理功能
- **测试**：纯函数测试模式（参考 `tests/test_proxy.py`），覆盖率 ≥80%
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
