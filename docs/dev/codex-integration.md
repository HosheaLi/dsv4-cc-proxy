---
title: Codex Integration
type: tool
category: infrastructure
tags: [deepseek, proxy, codex, responses-api, sse, streaming]
created: 2026-06-07
updated: 2026-06-07
---

# Codex Integration

## 概述

dsv4-cc-proxy 支持将 [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses) 格式的请求翻译为 [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion)，使 Codex CLI（及使用 Responses API 的其他客户端）能在 DeepSeek V4 模型上运行。

解决的问题：Codex CLI 原生使用 OpenAI Responses API（`POST /v1/responses`），而 DeepSeek 仅提供 Chat Completions API（`POST /chat/completions`）。两个 API 在请求格式、工具调用格式、SSE 流式事件序列上完全不同。代理在中间完成三层处理：请求翻译、工具格式转换、SSE 流响应翻译。

## 架构

```
Codex (Claude Code) ──→ localhost:16889 ──→ https://api.deepseek.com/chat/completions
                          │
                          │ (三层处理)
                          │
                          ←── Responses API JSON/SSE ←────────────────────
                          │
            ┌─────────────┼─────────────┐
            │             │             │
            ▼             ▼             ▼
       translate.py    tools.py       sse.py
       (请求翻译)      (工具转换)     (SSE 状态机)
```

代理在 `/v1/responses` 路由处拦截请求，依次通过 translate.py（请求翻译）、tools.py（工具格式转换）处理后发送到 DeepSeek Chat Completions API。收到响应后，根据 `stream` 参数选择：非流式通过 translate.py 逆向翻译，流式通过 sse.py 状态机逐事件翻译。

## 模块依赖图

```
config.py <── translate.py <── proxy.py (responses_handler)
                     │
                     ├── tools.py <── translate.py
                     │
                     └── sse.py  <── proxy.py (_handle_stream_response)
```

- `config.py` — 环境变量加载（CODEX_DEFAULT_MODEL、CODEX_MODEL_MAP、CODEX_UPSTREAM），零依赖纯函数
- `translate.py` — Responses API ↔ Chat Completions 请求/响应翻译，调用 `tools.py` 做工具格式转换
- `tools.py` — 扁平工具格式 ↔ 嵌套格式互转，JSON Schema 不兼容字段清理
- `sse.py` — Chat Completions SSE 流 → Responses API SSE 事件流的有状态翻译引擎

## 翻译流程：请求

Responses API 输入 → Chat Completions messages 的翻译规则：

| Responses API 字段 | Chat Completions 映射 |
|-------------------|----------------------|
| `input[].role: "user"` | `messages[{role: "user", content}]` |
| `input[].role: "assistant"` | `messages[{role: "assistant", content}]` |
| `input[].role: "developer"` | 合并到 system message |
| `instructions` | `system`（优先级高于 developer） |
| `tools[]` | `tools[]`（经 tools.py 格式转换） |
| `tool_choice` | 透传 |
| `reasoning.effort` | `thinking: {"type": "enabled"}` |
| `model` | 经 CODEX_MODEL_MAP 映射或使用 CODEX_DEFAULT_MODEL |
| `stream: true/false` | 透传 |
| `metadata` | 透传 |
| `temperature` / `max_output_tokens` | 透传 |

### function_call / function_call_output 处理

- Responses API 中 tool 调用使用 `function_call` / `function_call_output` 格式
- 翻译为 Chat Completions 的 `tool_calls` / `tool` role 格式
- function_call 的 `arguments` 始终为 JSON 字符串，与 Chat Completions 格式兼容

### 模型名解析

两层模型映射策略：
1. `CODEX_MODEL_MAP` JSON 对象中精确匹配或最长前缀匹配
2. 匹配失败时回退到 `CODEX_DEFAULT_MODEL`（默认 `deepseek-v4-pro`）

## 翻译流程：流式响应

DeepSeek Chat SSE → Responses API SSE 的逐事件翻译过程。

### Chat Completions SSE delta 格式

```
data: {"id":"...","choices":[{"index":0,"delta":{"content":"Hello","reasoning_content":"..."},"finish_reason":null}]}
```

### Responses API SSE 事件格式

```
event: response.output_text.delta
data: {"type":"response.output_text.delta","delta":"Hello"}
```

### delta 字段映射表

| Chat delta 字段 | Responses API 事件 | 说明 |
|----------------|-------------------|------|
| `delta.content` | `response.output_text.delta` | 普通文本增量 |
| `delta.reasoning_content` | `response.reasoning_text.delta` | 推理文本增量 |
| `delta.tool_calls[i].function.name` | `response.function_call_arguments.delta` (name) | 工具调用名 |
| `delta.tool_calls[i].function.arguments` | `response.function_call_arguments.delta` (arguments) | 工具参数增量 |

### 类型转换事件序列

当 delta 内容在 reasoning → text → tool_calls 之间切换时，需要触发 `output_item.done` + `output_item.added` 事件：

```
推理阶段 → reasoning_text.delta → ...
推理结束 → output_item.done → output_item.added(message)
文本阶段 → output_text.delta → ...
文本结束 → output_item.done → output_item.added(function_call)
工具阶段 → function_call_arguments.delta → ...
```

## SSE 生命周期事件序列

完整的非流式 SSE 事件顺序（以单次文本响应为例）：

1. **response.created** — 响应对象已创建
2. **response.in_progress** — 响应开始处理
3. **response.output_item.added (message)** — 输出项（消息）已添加
4. **response.content_part.added (text)** — 内容部分（文本）已添加
5. **response.output_text.delta** — 文本增量（可多次出现）
6. **response.content_part.done (text)** — 内容部分完成
7. **response.output_item.done (message)** — 输出项完成
8. **response.completed** — 响应完成

流式响应中可能包含多个 reasoning → text 或 text → tool_calls 切换，每次切换重复 step 3-7。工具调用场景中 `output_item.added` 类型为 `function_call` 而非 `message`。

### 非流式响应结构

非流式响应直接返回完整的 JSON body：

```json
{
  "id": "resp_xxx",
  "object": "response",
  "status": "completed",
  "output": [
    {
      "type": "message",
      "role": "assistant",
      "content": [
        {
          "type": "output_text",
          "text": "Hello, world!",
          "annotations": []
        }
      ]
    }
  ],
  "usage": {
    "input_tokens": 10,
    "output_tokens": 5,
    "total_tokens": 15
  }
}
```

## 环境变量参考

| 环境变量 | 默认值 | 用途 |
|---------|--------|------|
| `CODEX_DEFAULT_MODEL` | `deepseek-v4-pro` | Codex 请求中未指定模型时的默认值 |
| `CODEX_MODEL_MAP` | `{}` | 客户端模型名到 DeepSeek 模型名的映射。JSON 格式。支持精确匹配和最长前缀匹配 |
| `CODEX_UPSTREAM` | `https://api.deepseek.com/chat/completions` | DeepSeek Chat Completions API URL |

这些环境变量与现有 PROXY_* 环境变量独立，互不影响。

## 测试

### 单元测试

每个模块对应独立的测试文件：

| 测试文件 | 覆盖模块 | 数量 | 覆盖率 |
|---------|---------|------|--------|
| `tests/test_codex.py` | config.py | 6 个 | 91% |
| `tests/test_translate.py` | translate.py | 23 个 | 92% |
| `tests/test_tools.py` | tools.py | 21 个 | — |
| `tests/test_sse.py` | sse.py | 17 个 | 98% |
| `tests/test_responses.py` | proxy.py (Codex 路由) | 21 个 | 90.9% |

### 运行命令

```bash
# 运行所有 test
python -m pytest tests/ -v

# 运行 codex 相关测试
python -m pytest tests/test_translate.py tests/test_tools.py tests/test_sse.py tests/test_responses.py -v

# 带覆盖率报告
python -m pytest tests/ -v --cov=dsv4_cc_proxy --cov-report=term
```

### 测试模式

所有测试使用纯函数 AAA（Arrange-Act-Assert）模式。HTTP 集成测试使用 Starlette TestClient + httpx mock，不涉及真实网络请求。SSE 测试使用模拟的 chunk 序列来验证事件序列的正确性。

## 版本历史

| 版本 | 变更 |
|------|------|
| v2.0.0 | 首次实现 — Codex 双协议支持 |
