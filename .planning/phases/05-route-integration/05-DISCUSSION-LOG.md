# Phase 5: Route Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-07
**Phase:** 05-route-integration
**Areas discussed:** Handler architecture, Non-stream strategy, Error handling, Testing strategy

---

## Handler Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| 统一 handler 内分支 | 单一 handler 按 stream 参数内部分支，与 proxy() 模式一致 | ✓ |
| 拆成两个 handler | 两个独立 handler 分别处理流式/非流式，更隔离但冗余 | |

**User's choice:** 统一 handler 内分支
**Notes:** 与现有 proxy() 路由分发模式一致，减少路由注册数量。

---

## Non-stream Response Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| 直接非流式请求 | 请求 DeepSeek 不带 stream: true，直接翻译完整 JSON | ✓ |
| 流式请求 + 内存组装 | 始终 stream: true，在内存中累积 SSE 事件组成 JSON | |

**User's choice:** 直接非流式请求
**Notes:** 最简单直接，不引入内存组装逻辑。

---

## Error Handling

| Option | Description | Selected |
|--------|-------------|----------|
| 透传 raw 错误 | 直接转发 DeepSeek 的状态码和错误体 | |
| 翻译为 Responses API 格式 | 包装为标准 Responses API 错误格式 | ✓ |
| 基础翻译 | 保证状态码和 Content-Type 正确，但不做完整映射 | |

**User's choice:** 翻译为 Responses API 格式（完整翻译）
**Notes:** 将 DeepSeek 错误码映射到 OpenAI 标准错误类型，构建 `error: {type, code, message, param}` 格式。

---

## Testing Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| TestClient 集成测试 | 使用 starlette.testclient.TestClient 做 HTTP 集成测试 | ✓ |
| 纯函数模式继续 | handler 提取为纯函数，只测这些函数 | |

**User's choice:** TestClient 集成测试
**Notes:** 覆盖完整请求→响应路径。mock httpx 异步客户端。

---

## Claude's Discretion

Listed in CONTEXT.md `<decisions>` section under "Claude's Discretion":
- Handler 内部辅助函数拆分
- 日志详细级别
- 具体错误码映射表
- TestClient httpx mock 实现方式
- 流式响应 `response.completed` 的 usage 信息处理
- 非流式 JSON 翻译函数实现

## Deferred Ideas

None.
