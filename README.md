# DSV4 → CC Proxy

**DeepSeek Anthropic API 兼容性代理** — 让 Claude Code 在 DeepSeek V4 模型上稳定运行。

## 解决的问题

DeepSeek V4 实现了 Anthropic API 格式，但有 3 个关键的兼容性差异。此代理逐层修复它们：

| # | 问题 | 症状 | 修复 |
|---|------|------|------|
| 1 | tool_use 消息缺 thinking 块 | `reasoning_content` 400 错误 | 请求端注入空 thinking 块 |
| 2 | 无条件返回 thinking SSE 事件 | `Tool result missing due to internal error` | 响应端剥离 thinking 事件 |
| 3 | `thinking.type=adaptive` + `reasoning_effort` | 流式截断 / zero output / 400 冲突 | 标准化为 `disabled` + 移除 effort |

## 快速开始

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r proxy/requirements.txt

# 3. 启动代理（默认 16889 端口）
python3 proxy/deepseek-thinking-proxy.py

# 4. 配置 Claude Code
# settings.local.json 设置:
# "ANTHROPIC_BASE_URL": "http://localhost:16889"
```

## 目录结构

```
.
├── proxy/
│   ├── deepseek-thinking-proxy.py   # 代理核心 (v1.8)
│   ├── test_proxy.py                # 22 个单元测试
│   ├── requirements.txt             # Python 依赖
│   ├── com.deepseek.thinking-proxy.plist  # macOS launchd 自启 (可选)
│   └── .gitignore
└── README.md
```

## 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `PROXY_UPSTREAM` | `https://api.deepseek.com/anthropic` | DeepSeek API 地址 |
| `PROXY_HOST` | `127.0.0.1` | 监听地址 |
| `PROXY_PORT` | `16889` | 监听端口 |
| `PROXY_LOG_LEVEL` | `warning` | 日志级别 (`info` 调试用) |
| `PROXY_DUMP_DIR` | (空=关闭) | 流量捕获目录。⚠ 含用户对话数据 |

## 运行测试

```bash
cd proxy
python3 -m pytest test_proxy.py -v
```

## 自启 (macOS)

```bash
cp proxy/com.deepseek.thinking-proxy.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist
```

## 健康检查

```bash
curl http://localhost:16889/health
# → {"status":"ok","version":"1.8","upstream":"https://api.deepseek.com/anthropic"}
```

## 工作原理

```
Claude Code ←→ localhost:16889 (本代理) ←→ api.deepseek.com/anthropic
```

代理拦截 `POST /v1/messages`，对 `deepseek-v4*` 模型做三层处理：
1. **请求端注入**: assistant 消息含 tool_use 但无 thinking 时，插入空 thinking 块
2. **请求标准化**: `thinking.type=adaptive` 等非标准值转为 `disabled`，同步移除 `reasoning_effort`
3. **响应过滤**: 在 SSE 流中剥离 DeepSeek 无条件返回的 thinking/thinking_delta/signature_delta 事件

其他请求（非 deepseek-v4、非 messages 端点）纯流式透传，零额外开销。
