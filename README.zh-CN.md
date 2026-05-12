<div align="center">

# dsv4-cc-proxy

**让 DeepSeek V4 与 Claude Code 无缝配合**

Anthropic API 兼容性代理，修复 DeepSeek V4 的 3 个不兼容问题。

```
Claude Code ←→ localhost:16889 (dsv4-cc-proxy) ←→ api.deepseek.com/anthropic
```

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![CI](https://github.com/HosheaLi/dsv4-cc-proxy/actions/workflows/ci.yml/badge.svg)](https://github.com/HosheaLi/dsv4-cc-proxy/actions)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)]()
[![Docker Pulls](https://img.shields.io/docker/pulls/hosheali/dsv4-cc-proxy)](https://hub.docker.com/r/hosheali/dsv4-cc-proxy)

</div>

---

## 为什么需要这个代理

DeepSeek V4 实现了 Anthropic API 格式，但有 3 个关键的不兼容问题会导致 Claude Code 无法正常运行。这个代理在中间透明地修复它们。

| # | 问题 | 症状 | 修复 |
|---|------|------|------|
| 1 | tool_use assistant 消息缺少 thinking 块 | `reasoning_content` 400 错误 | 在每个 tool_use 前注入空 thinking 块 |
| 2 | DeepSeek 无条件返回 thinking/signature_delta SSE 事件 | Claude Code 报 `Tool result missing due to internal error` | 从 SSE 响应流中剥离 thinking 事件 |
| 3 | `thinking.type=adaptive`（Claude Code 默认值）+ `reasoning_effort` 不被 DeepSeek 支持 | 流式截断 / 400 错误 | 标准化为 `disabled` + 移除 reasoning_effort |

非 DeepSeek 模型请求和非 `/messages` 端点的请求零开销透传。

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
| `PROXY_HOST` | `127.0.0.1` | 监听地址 |
| `PROXY_PORT` | `16889` | 监听端口 |
| `PROXY_LOG_LEVEL` | `warning` | 日志级别（调试用 `info`） |
| `PROXY_DUMP_DIR` | *(空=关闭)* | 流量捕获目录。⚠ 含用户对话数据 |

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

```bash
# 先编辑 plist 文件中路径为你的实际环境！
cp scripts/com.deepseek.thinking-proxy.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist
```

**注意：** 需修改 plist 中的路径（如 `/Users/yourname/.claude/proxy/`）以匹配你的配置。

### Windows（计划任务自启）

```batch
:: 一键安装（开机自启、崩溃重启）
scripts\install_windows_service.ps1 -Install

:: 手动启动终端模式
scripts\start.bat

:: 或使用 PowerShell
scripts\start.ps1
```

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
# → {"status":"ok","version":"1.8.0","upstream":"https://api.deepseek.com/anthropic"}
```

## 目录结构

```
.
├── dsv4_cc_proxy/
│   ├── __init__.py                  # 包入口，导出 VERSION + create_app
│   ├── __main__.py                  # CLI 入口 — dsv4-cc-proxy 命令
│   ├── _version.py                  # VERSION = "1.8.0"（唯一版本来源）
│   └── proxy.py                     # 核心代理逻辑（工厂模式）
├── tests/
│   └── test_proxy.py                # 22 个单元测试
├── scripts/
│   ├── start.bat                    # Windows 批处理启动
│   ├── start.ps1                    # PowerShell 启动
│   ├── install_windows_service.ps1  # Windows 计划任务安装
│   └── com.deepseek.thinking-proxy.plist  # macOS launchd（可选）
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
