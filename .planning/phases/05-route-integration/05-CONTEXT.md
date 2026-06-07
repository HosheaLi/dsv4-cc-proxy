# Phase 5: Route Integration - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Phase Boundary

在 `proxy.py` 中注册 `/v1/responses` HTTP 端点，集成 Phase 1-4 的 codex 模块（translate_request、translate_sse_stream、convert_tools、resolve_model），实现认证透传和压缩端点。保证不影响现有 Anthropic `/v1/messages` 路由。

此阶段仅交付 HTTP handler 和路由注册。不涉及新翻译逻辑、工具转换、或 SSE 状态机功能。

Success Criteria（来自 ROADMAP.md）:
1. `POST /v1/responses` with `stream: true` returns text/event-stream SSE with correct event types
2. `POST /v1/responses` with `stream: false` returns complete JSON response in Responses API format
3. `POST /v1/responses/compact` returns HTTP 501 with valid error JSON body
4. Existing `POST /v1/messages` routes continue to work — all 22 existing proxy tests pass
5. `Authorization` header from Codex request passes through to DeepSeek API unchanged

</domain>

<decisions>
## Implementation Decisions

### Handler Architecture
- **D-01:** 单一 handler 内分支 — 创建 `responses_handler()` 函数，解析 request JSON 的 `stream` 字段后内部分支到流式/非流式处理路径。与现有 `proxy()` 的星状路由分发模式一致，减少路由冗余
- **D-02:** 路由注册：`Route("/v1/responses", responses_handler, methods=["POST"])`，放置在 catch-all `/{path:path}` 之前。Starlette 路由按序匹配，先注册先匹配

### Non-stream Response Strategy
- **D-03:** `stream: false` 时直接请求 DeepSeek Chat Completions 非流式 API（不加 `stream: true`），拿到完整 JSON 响应后翻译为 Responses API 格式。不引入内存累积组装逻辑，最简单直接

### Error Handling
- **D-04:** 完整错误翻译 — 将 DeepSeek API 返回的 HTTP 错误（400/401/429/503 等）映射为标准 Responses API 错误格式：`error: {type, code, message, param}`。解析 DeepSeek 错误码映射到对应 OpenAI 标准错误类型
- **D-05:** 确保 `Content-Type` 正确设置。对于非流式错误返回 `application/json`，流式错误返回 `text/event-stream`（以正确事件类型结束流）

### Authentication Passthrough
- **D-06:** `Authorization` header 从 Codex 请求原样转发到 DeepSeek API。复用 proxy.py 现有的 header 转发模式（strip `host` header，保留 `authorization`）

### Compact Endpoint
- **D-07:** `POST /v1/responses/compact` 返回 HTTP 501，JSON 体 `{"error": {"type": "not_supported", "message": "..."}}`。与 Phase 2 CONTEXT.md D-12（compaction 推迟）一致

### httpx Client
- **D-08:** 复用 proxy.py 现有的 `_get_client()` + `_shared_client` 懒加载客户端模式。与现有 httpx 连接池共享，使用 `CODEX_UPSTREAM` 作为 base URL 构建 `request`。如果现有 client timeout 不满足 codex 场景，codex handler 内创建独立 `httpx.AsyncClient` 实例

### Testing
- **D-09:** 引入 `starlette.testclient.TestClient` 做 HTTP 集成测试，mock httpx 异步客户端。覆盖完整请求→响应路径
- **D-10:** 测试覆盖场景：
  1. `stream: true` — 验证响应 Content-Type 为 `text/event-stream`，事件类型序列正确
  2. `stream: false` — 验证返回完整 Responses API JSON 结构
  3. `POST /v1/responses/compact` — 验证 501 状态码 + 错误体
  4. 错误转发 — DeepSeek 返回错误时，验证 Responses API 错误格式
  5. 无 `Authorization` header — 验证请求被拒绝或正确转发
  6. 现有 `/v1/messages` 路由不受影响 — 验证 22 个 proxy 测试全通过
  7. JSON 格式错误 — 验证 handler 优雅处理无效请求体

### Claude's Discretion
- `responses_handler()` 内部辅助函数的具体拆分（如 `_is_stream_request`、`_build_deepseek_request`、`_translate_response_error` 等）
- 日志记录的详细级别
- 具体错误码映射表（哪些 DeepSeek 错误码映射到 OpenAI 的 `invalid_request_error` / `rate_limit_error` / `server_error` 等）
- TestClient 中 httpx mock 的具体实现方式（`httpx.AsyncClient` mock vs `respytest` vs 自定义 mock）
- 流式响应中 `response.completed` 事件的 `usage` 信息（从 DeepSeek 最后一个 chunk 的 `usage` 字段提取或设置为 placeholder）
- 非流式响应的 JSON 翻译函数（从 Chat Completions JSON 响应直接翻译为 Responses API 格式，不经过 sse.py）

### Folded Todos
None — no matching todos found.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 架构与设计
- `/Users/lihaoxuan/.claude/plans/codex-deepseek-v4-responses-api-deepsee-cryptic-phoenix.md` — 完整技术方案：路由设计、错误处理策略、认证透传方案
- `docs/dev/deepseek-thinking-proxy.md` — 现有 Anthropic 代理实现模式，理解 `filtered_stream()`、`_get_client()`、路由注册方式

### 现有代码
- `dsv4_cc_proxy/proxy.py` — 核心代理实现。需理解：`create_app()` 路由注册（L417-433）、`proxy()` handler 模式（L277）、`_get_client()` 懒加载客户端（L82-94）、header 转发模式（L299-314）、`StreamingResponse` 构建（L340-413）
- `dsv4_cc_proxy/codex/__init__.py` — 模块导出（translate_request / translate_sse_stream / convert_tools / resolve_model），Phase 5 handler 需导入这些函数
- `dsv4_cc_proxy/codex/config.py` — 配置模块。`CODEX_UPSTREAM` env var（默认 `https://api.deepseek.com/v1`），Phase 5 构建上游请求 URL 时需使用
- `dsv4_cc_proxy/codex/sse.py` — SSE 状态机实现。`translate_sse_stream()` 异步生成器，输出已是格式化的 Responses API 事件字符串（`event: ...\ndata: ...\n\n`），handler 直接 yield 到 StreamingResponse
- `dsv4_cc_proxy/codex/translate.py` — 请求翻译实现。`translate_request()` 纯函数，Phase 5 在发送到 DeepSeek 前调用
- `dsv4_cc_proxy/__init__.py` — 包暴露方式：`from dsv4_cc_proxy.proxy import create_app`

### 测试
- `tests/test_proxy.py` — 现有纯函数测试模式（22 个测试）。Phase 5 需验证它们全部通过表示无回归
- `tests/test_sse.py` — SSE 单元测试（17 个用例），理解 SSE 事件格式

### 需求
- `.planning/REQUIREMENTS.md` — CODX-01（流式 SSE）、CODX-02（非流式 JSON）、CODX-19（compact 501）、CODX-20（现有路由不受影响）、CODX-21（认证透传）
- `.planning/ROADMAP.md` — Phase 5 成功标准

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `proxy.py` 的 `_get_client()` + `_shared_client` — 懒加载 httpx 客户端模式。可复用，或 codex handler 创建独立端客户端
- `proxy.py` 的 header 构建模式（`build_request()` L299-314）— 移除 `host`，保留 `authorization`，添加 `content-type`。Phase 5 handler 可直接复用或参考
- `proxy.py` 的 `StreamingResponse` 使用模式 — `StreamingResponse(stream, media_type="text/event-stream")`。Phase 5 流式响应直接采用

### Established Patterns
- **路由注册**：Starlette `Route()` 对象数组传入 `Starlette(routes=[...])`，不是装饰器模式
- **Catch-all 覆盖**：现有 `/{path:path}` catch-all 处理所有路径。`/v1/responses` 路由须放在之前（Starlette 按序匹配）
- **行缓冲**：proxy.py L357-405 的 `filtered_stream()` 异步生成器。Phase 5 的流式响应不需要行缓冲，因为 `translate_sse_stream()` 直接 yield 格式化的 SSE 事件字符串
- **`[CODEX]` 日志前缀**：`logger = logging.getLogger("deepseek-proxy")`，`%s` 风格格式化
- **纯函数 + 无类**：整个 codex/ 子包保持此约束

### Integration Points
- `translate_request()` → 翻译 Codex /v1/responses 请求体为 Chat Completions 格式，放入 DeepSeek 请求
- `CODEX_UPSTREAM` (from codex/config.py) → 构建到 `{CODEX_UPSTREAM}/chat/completions` 的 httpx POST 请求
- `convert_tools()` → 已在 `translate_request()` 内部调用，Phase 5 handler 无需直接使用
- `translate_sse_stream()` → 流式模式下，将 Chat delta chunk 流转换为 Responses API SSE 事件流
- 非流式模式需要新建一个翻译函数（或直接在 handler 中实现），从 Chat Completions JSON 响应提取内容构造 Responses API JSON。sse.py 不适用于非流式场景

</code_context>

<specifics>
## Specific Ideas

- 非流式响应的 JSON 翻译需要新建函数（在 handler 中实现或提取为 utils 函数），从 Chat Completions `response["choices"][0]["message"]` 翻译为 Responses API 格式。不经过 sse.py 的原因是 sse.py 输出的是格式化 SSE 字符串，非流式需要完整 JSON 对象
- httpx client 共享需要考虑 timeout 差异。proxy.py 当前 client 的 timeout 可能不适合 codex 场景（DeepSeek V4 推理可能更慢），可能需要调整或创建独立客户端
- Starlette 1.0.0 支持 `request.json()` 异步解析 JSON，handler 内部 `await request.json()`

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

### Reviewed Todos (not folded)
None — no matching todos found.

</deferred>

---

*Phase: 05-route-integration*
*Context gathered: 2026-06-07*
