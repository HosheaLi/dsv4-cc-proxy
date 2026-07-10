<div align="center">

# dsv4-cc-proxy

**让 DeepSeek V4 与 Claude Code 无缝配合**

Anthropic API 兼容性代理，内置**看门狗自愈**、**上游弹性重试**和**跨平台支持**。

```
Claude Code ←→ localhost:16889 (dsv4-cc-proxy) ←→ api.deepseek.com/anthropic
```

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![CI](https://github.com/HosheaLi/dsv4-cc-proxy/actions/workflows/ci.yml/badge.svg)](https://github.com/HosheaLi/dsv4-cc-proxy/actions)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)]()
[![PyPI version](https://img.shields.io/pypi/v/dsv4-cc-proxy)](https://pypi.org/project/dsv4-cc-proxy/)
[![PyPI downloads](https://img.shields.io/pypi/dm/dsv4-cc-proxy)](https://pypi.org/project/dsv4-cc-proxy/)
[![Docker Pulls](https://img.shields.io/docker/pulls/hosheali/dsv4-cc-proxy)](https://hub.docker.com/r/hosheali/dsv4-cc-proxy)
[![Docker Image Size](https://img.shields.io/docker/image-size/hosheali/dsv4-cc-proxy/latest)](https://hub.docker.com/r/hosheali/dsv4-cc-proxy)
[![GHCR](https://img.shields.io/badge/GHCR-available-blue)](https://github.com/HosheaLi/dsv4-cc-proxy/pkgs/container/dsv4-cc-proxy)
[![GitHub release](https://img.shields.io/github/v/release/HosheaLi/dsv4-cc-proxy)](https://github.com/HosheaLi/dsv4-cc-proxy/releases)
[![GitHub stars](https://img.shields.io/github/stars/HosheaLi/dsv4-cc-proxy?style=social)](https://github.com/HosheaLi/dsv4-cc-proxy)
[![GitHub last commit](https://img.shields.io/github/last-commit/HosheaLi/dsv4-cc-proxy)](https://github.com/HosheaLi/dsv4-cc-proxy/commits/main)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen)](coverage.svg)
[![Homebrew](https://img.shields.io/badge/homebrew-available-FBB040?logo=homebrew)](https://github.com/HosheaLi/homebrew-tap)
[![Scoop](https://img.shields.io/badge/scoop-available-blue?logo=scoop)](https://github.com/HosheaLi/scoop-bucket)

</div>

---

## v2.1.0 新特性

| 功能 | 说明 |
|------|------|
| 🔄 **看门狗模式** | `--watchdog` 标志启用崩溃自动恢复——父进程监控子进程，崩溃后自动重启 |
| 🔁 **上游重试 + 回退** | 指数退避自动重试 + 可选回退地址（`PROXY_UPSTREAM_FALLBACK`），DeepSeek 不可达时自动切换 |
| 🪟 **Windows 兼容性** | PID 文件自动适配 `%TEMP%`，启动错误通过 stderr + 事件日志可见 |
| 🍎 **macOS 安装脚本** | `scripts/install_macos.sh` 自动检测 Python，处理 Homebrew 外部管理环境，自动回退到 venv |
| 🚨 **端口冲突检测** | 启动前主动检测端口占用——避免静默失败和看门狗重启循环 |
| 🔍 **启动失败可见性** | 全平台：致命错误输出到 stderr。Windows：同时写入事件日志 |
| ✨ **提示词字符标准化** | Unicode 排版引号自动转 ASCII 单引号，日期格式统一（`2026/06/30` → `2026-06-30`），避免 DeepSeek 解析异常 |

## 为什么需要这个代理

DeepSeek V4 实现了 Anthropic API 格式，但有 4 个关键的不兼容问题会导致 Claude Code 无法正常运行。这个代理在中间透明地修复它们。

| # | 问题 | 症状 | 修复 |
|---|------|------|------|
| 1 | tool_use assistant 消息缺少 thinking 块 | `reasoning_content` 400 错误 | 在每个 tool_use 前注入空 thinking 块 |
| 2 | DeepSeek 无条件返回 thinking/signature_delta SSE 事件 | Claude Code 报 `Tool result missing due to internal error` | 从 SSE 响应流中剥离 thinking 事件 |
| 3 | `thinking.type=adaptive`（Claude Code 默认值）+ `reasoning_effort` 不被 DeepSeek 支持 | 流式截断 / 400 错误 | 标准化为 `disabled` + 移除 reasoning_effort |
| 4 | 系统提示词中的 Unicode 排版引号（如 `'` `'` `'`）和日期斜杠格式（`2026/06/30`）导致 DeepSeek 解析异常 | 工具调用参数截断、JSON 格式错乱 | 递归标准化为 ASCII 单引号 + `YYYY-MM-DD` 日期格式 |

非 DeepSeek 模型请求和非 `/messages` 端点的请求零开销透传。

## Codex 支持

dsv4-cc-proxy 也支持 [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses) 格式与 DeepSeek Chat Completions API 之间的协议翻译，让 Codex（及其他 OpenAI Responses API 客户端）能使用 DeepSeek V4 模型。

```
Codex (Claude Code) ──→ localhost:16889 ──→ https://api.deepseek.com/chat/completions
```

### 端点

| 端点 | 说明 |
|------|------|
| `POST /v1/responses` | 将 Responses API 请求翻译为 Chat Completions，再将响应翻译回 Responses 格式 |
| `POST /v1/responses/compact` | 暂不支持（返回 501） |

### 环境变量

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `CODEX_DEFAULT_MODEL` | `deepseek-v4-pro` | Codex 请求的默认模型名 |
| `CODEX_MODEL_MAP` | `{}` | 客户端模型名到 DeepSeek 模型名的 JSON 映射（如 `{"claude-sonnet-4-6": "deepseek-v4-pro"}`） |
| `CODEX_UPSTREAM` | `https://api.deepseek.com/chat/completions` | DeepSeek Chat Completions API 地址 |

### 使用方法

将 Codex 指向同一个代理地址：

```json
"OPENAI_BASE_URL": "http://localhost:16889"
```

代理会自动识别 Responses API 请求（`/v1/responses`）并执行相应的翻译。所有现有的 Anthropic API 代理功能不变。

## 快速开始

### 方式一：pip 安装（推荐）

```bash
pip install dsv4-cc-proxy

# 启动代理（默认 16889 端口）
dsv4-cc-proxy

# 停止代理
dsv4-cc-proxy --stop
```

### 方式二：Homebrew（macOS）

```bash
brew install hosheali/tap/dsv4-cc-proxy

# 启动代理
dsv4-cc-proxy

# 注册为后台服务（开机自启）
brew services start hosheali/tap/dsv4-cc-proxy
```

### 方式三：pipx（隔离环境）

```bash
pipx install dsv4-cc-proxy
dsv4-cc-proxy
```

### 方式四：Docker

```bash
docker run -d -p 16889:16889 --name dsv4-cc-proxy hosheali/dsv4-cc-proxy:latest
```

或使用 docker compose：

```bash
docker compose up -d
```

### 配置 Claude Code

在 `settings.local.json` 中添加：

```json
"ANTHROPIC_BASE_URL": "http://localhost:16889"
```

## 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `PROXY_UPSTREAM` | `https://api.deepseek.com/anthropic` | DeepSeek API 地址 |
| `PROXY_UPSTREAM_FALLBACK` | *(空=关闭)* | 主上游不可达时的备选回退地址。需兼容 Anthropic API |
| `PROXY_UPSTREAM_RETRY_COUNT` | `2` | 每个上游目标的重试次数 |
| `PROXY_UPSTREAM_RETRY_BASE_DELAY` | `1.0` | 指数退避基础延迟（秒）：`delay = base × 2^attempt` |
| `PROXY_HOST` | `127.0.0.1` | 监听地址 |
| `PROXY_PORT` | `16889` | 监听端口 |
| `PROXY_LOG_LEVEL` | `warning` | 日志级别（调试用 `info`） |
| `PROXY_DUMP_DIR` | *(空=关闭)* | 流量捕获目录。⚠ 含用户对话数据 |
| `PROXY_WATCHDOG_MAX_RESTARTS` | `5` | 看门狗放弃前的最大重启次数 |
| `PROXY_WATCHDOG_RESTART_DELAY` | `2` | 重启间隔秒数 |
| `PROXY_WATCHDOG_POLL_INTERVAL` | `0.5` | 子进程存活轮询间隔秒数 |

> Codex 使用请参考上方 [Codex 支持](#codex-支持) 章节。

## 效果对比

| 场景 | 无代理 | 有代理 |
|------|--------|--------|
| tool_use 消息缺少 thinking | 400 错误 | 自动注入空 thinking |
| Claude Code 发送 `thinking.type=adaptive` | 流截断 / 400 | 标准化为 disabled |
| DeepSeek 返回 thinking SSE 事件 | Tool result missing 错误 | 静默剥离 |
| 非 messages 端点 | — | 零开销透传 |
| 非 DeepSeek 模型 | — | 零开销透传 |

## 平台指南

### macOS（launchd 自启）

**推荐：使用安装脚本一键部署：**

```bash
# 自动检测 Python，必要时创建 venv，安装为 LaunchAgent
bash scripts/install_macos.sh

# 或手动指定 Python 路径
bash scripts/install_macos.sh /path/to/python3
```

**手动安装：**

```bash
# 先编辑 plist 文件中路径为你的实际环境！
cp scripts/com.deepseek.thinking-proxy.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist
```

> **注意：** 停止 launchd 管理的代理前需先卸载：`launchctl unload ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist`。直接使用 `--stop` 无效，因为 `KeepAlive` 会自动重启。

### Windows（计划任务自启）

```batch
:: 一键安装（开机自启、崩溃重启）
powershell -ExecutionPolicy RemoteSigned -File scripts\install_windows_service.ps1 -Install

:: 手动启动终端模式
scripts\start.bat

:: 或使用 PowerShell
powershell -ExecutionPolicy RemoteSigned -File scripts\start.ps1
```

> **注意：** `--stop` 依赖 POSIX 信号，**Windows 上不支持**。请使用 `Ctrl+C` 或 `taskkill`。

### 看门狗模式（所有平台）

裸进程环境（无平台守护进程时）推荐使用：

```bash
dsv4-cc-proxy --watchdog
# 子进程崩溃 → 自动重启（最多 PROXY_WATCHDOG_MAX_RESTARTS 次）
```

> **注意：** 使用 launchd（macOS）、计划任务（Windows）或 Docker restart 策略时不需要 `--watchdog`——平台守护进程已经处理了进程恢复。

### Linux（systemd）

创建 `/etc/systemd/system/dsv4-cc-proxy.service`：

```ini
[Unit]
Description=dsv4-cc-proxy — DeepSeek Anthropic API proxy
After=network.target

[Service]
Type=simple
User=your-user
ExecStart=/usr/local/bin/dsv4-cc-proxy
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dsv4-cc-proxy
```

## Docker 部署（手动构建）

```bash
docker build -t dsv4-cc-proxy .
docker run -d -p 16889:16889 --name dsv4-cc-proxy dsv4-cc-proxy
```

## 工作原理

```
┌─────────────┐     ┌──────────────────┐     ┌────────────────────┐
│ Claude Code │ ──→ │  dsv4-cc-proxy   │ ──→ │  api.deepseek.com  │
│             │     │  localhost:16889  │     │  /anthropic        │
└─────────────┘     └──────────────────┘     └────────────────────┘
                           │
                   ┌───────┴────────┐
                   │  三层修复        │
                   │  1. thinking    │
                   │     注入        │
                   │  2. thinking    │
                   │     标准化      │
                   │  3. SSE 事件    │
                   │     剥离        │
                   └────────────────┘
```

代理拦截 `POST /v1/messages`，对 `deepseek-v4*` 模型做三层处理，其他请求透明透传。

## 运行测试

```bash
pip install dsv4-cc-proxy[test]
pytest tests/ -v
```

### 健康检查

```bash
curl http://localhost:16889/health
# → {"status":"ok","version":"2.1.0","upstream":"https://api.deepseek.com/anthropic","upstream_fallback":null}
```

## 目录结构

```
.
├── dsv4_cc_proxy/
│   ├── __init__.py                  # 包入口，导出 VERSION + create_app
│   ├── __main__.py                  # CLI 入口 — dsv4-cc-proxy 命令
│   ├── _version.py                  # VERSION = "2.0.0"（唯一版本来源）
│   ├── proxy.py                     # 核心代理逻辑（工厂模式）
│   └── codex/                       # Codex（Responses API）协议翻译模块
│       ├── __init__.py
│       ├── config.py
│       ├── translate.py
│       ├── tools.py
│       └── sse.py
├── tests/
│   ├── test_proxy.py                # 22 个单元测试
│   ├── test_codex.py                # Codex 配置测试
│   ├── test_translate.py            # 请求翻译测试
│   ├── test_tools.py                # 工具格式转换测试
│   ├── test_sse.py                  # SSE 流式测试
│   ├── test_main.py                 # CLI 测试
│   └── test_responses.py            # Codex HTTP 路由测试
├── scripts/
│   ├── start.bat                    # Windows 批处理启动
│   ├── start.ps1                    # PowerShell 启动
│   ├── install_windows_service.ps1  # Windows 计划任务安装
│   ├── install_macos.sh             # macOS LaunchAgent 安装脚本
│   └── com.deepseek.thinking-proxy.plist  # macOS launchd 模板
├── Dockerfile                       # Docker 多阶段构建
├── docker-compose.yml               # Docker Compose
├── pyproject.toml                   # 构建配置、entry point
├── MANIFEST.in                      # 打包额外文件
├── .github/workflows/ci.yml         # GitHub Actions CI
├── LICENSE                          # MIT 许可证
└── CONTRIBUTING.md                  # 贡献指南
```

## 贡献

欢迎贡献代码！请查阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解开发流程和规范。

## 许可证

[MIT](LICENSE)
