---
title: DeepSeek Thinking Proxy
type: tool
category: infrastructure
tags: [deepseek, proxy, claude-code, thinking, reasoning-content]
created: 2026-05-10
updated: 2026-05-10
---

# DeepSeek Thinking Proxy

## 概述

轻量异步代理，置于 Claude Code 与 DeepSeek Anthropic API 之间，解决 DeepSeek `reasoning_content` 400 错误。

**问题根因**：Claude Code 的 `normalizeMessagesForAPI()` 只剥离 thinking 块，从不添加。当 DeepSeek 返回带 `tool_use` 但无 `thinking` 的响应时（~59% 概率），后续请求的 assistant 消息缺失 `reasoning_content` → DeepSeek 后端拒绝 → 400。

**解决方式**：代理检测到 `deepseek-v4*` + `thinking=enabled` 的 `/v1/messages` 请求中，有 `tool_use` 但无 `thinking` 的 assistant 消息时，注入空 `{"type":"thinking","thinking":""}` 块。

## 架构

```
Claude Code ──→ localhost:16889 ──→ https://api.deepseek.com/anthropic
                   │                        │
                   │ (条件注入thinking块)     │
                   │                        │
                   ←── 流式透传 ←─────────────
```

## 文件位置

| 文件 | 路径 |
|------|------|
| 代理脚本 | `~/.claude/proxy/deepseek-thinking-proxy.py` |
| 依赖声明 | `~/.claude/proxy/requirements.txt` |
| launchd plist | `~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist` |
| 日志 | `~/.claude/proxy/proxy.log` |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PROXY_UPSTREAM` | `https://api.deepseek.com/anthropic` | 上游 API 地址 |
| `PROXY_HOST` | `127.0.0.1` | 监听地址 |
| `PROXY_PORT` | `16889` | 监听端口 |
| `PROXY_LOG_LEVEL` | `warning` | 日志级别 (debug/info/warning/error) |

## 条件拦截逻辑

```
if method != POST or path !≈ /v1/messages:
    → 纯透传，不解析 body

if model 前缀 != "deepseek-v4" or thinking == disabled:
    → 纯透传，不修改

else:
    → JSON parse → 遍历 messages → 注入空 thinking 块 → 更新 Content-Length
```

## 性能特征

- **非 DeepSeek 请求**：纯流式透传，零开销
- **DeepSeek 请求**：仅 1 次 JSON.parse，注入 ~30 bytes，< 1ms
- **响应流**：始终纯透传，不缓冲
- **连接池**：共享 httpx.AsyncClient，最大 8 keepalive / 20 并发
- **缓存命中**：不改变消息顺序或 cache_control 断点，不影响 prompt cache

## 部署 (macOS launchd)

plist 位置：`~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist`

```xml
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
```

开机自启 + 崩溃自动重启。

### 管理命令

```bash
# 启动
launchctl load ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist

# 停止
launchctl unload ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist

# 重启 (已加载状态)
launchctl stop com.deepseek.thinking-proxy
launchctl start com.deepseek.thinking-proxy

# 查看状态
launchctl list | grep deepseek

# 查看日志
tail -f ~/.claude/proxy/proxy.log
```

## 项目配置

需要走代理的项目，在 `.claude/settings.local.json` 中设置：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:16889"
  }
}
```

**注意**：不要修改 `~/.claude/.claude/settings.local.json`（Claude Code 自身配置），否则 Claude Code 无法连接 API。

## 健康检查

```bash
curl http://localhost:16889/health
# → {"status":"ok","upstream":"https://api.deepseek.com/anthropic"}
```

## 故障排查

### 代理不可达
```bash
curl http://localhost:16889/health  # 无响应 → 检查 launchctl list | grep deepseek
launchctl start com.deepseek.thinking-proxy
```

### 400 reasoning_content 仍出现
```bash
grep "injected" ~/.claude/proxy/proxy.log  # 确认注入是否触发
tail -50 ~/.claude/proxy/proxy.log         # 查看完整错误
```

### Socket connection closed
- 代理 < v1.1：`async with AsyncClient` 提前关闭 → 升级到最新版
- 最新版已修复为手动生命周期管理 + try/finally

### 上游不可达 (502)
- 检查网络连通性：`curl https://api.deepseek.com/anthropic/health`
- 检查 API key 是否有效

## 版本历史

| 版本 | 变更 |
|------|------|
| v1.0 | 初始实现，基础 thinking 注入 + launchd 部署 |
| v1.1 | 修复 Content-Length 未更新 → h11 LocalProtocolError |
| v1.2 | 修复 async with AsyncClient 提前关闭 → socket connection closed |
| v1.3 | 修复流异常时 client 泄漏 + 共享连接池 + 精准路由匹配 + 日志 + 502 降级 |
