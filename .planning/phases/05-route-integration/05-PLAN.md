---
phase: 05
plan: 01
type: execute
wave: 1
depends_on: []
security_review: true
files_modified:
  - dsv4_cc_proxy/proxy.py
  - tests/test_responses.py
autonomous: true
requirements:
  - CODX-01
  - CODX-02
  - CODX-19
  - CODX-20
  - CODX-21
must_haves:
  truths:
    - "POST /v1/responses with stream:true returns text/event-stream SSE with correct event types (CODX-01)"
    - "POST /v1/responses with stream:false returns complete JSON response in Responses API format (CODX-02)"
    - "POST /v1/responses/compact returns HTTP 501 with valid error JSON body (CODX-19)"
    - "Existing POST /v1/messages routes continue to work — all 22 existing proxy tests pass (CODX-20)"
    - "Authorization header from Codex request passes through to DeepSeek API unchanged (CODX-21)"
    - "Upstream error responses (400/401/429/500) are translated to standard Responses API error format: {error: {type, code, message, param}}"
  artifacts:
    - path: "dsv4_cc_proxy/proxy.py"
      provides: "responses_handler, compact_handler, _handle_stream_response, _handle_non_stream_response, _translate_chat_to_responses, _translate_upstream_error, _build_error, _iter_lines"
      contains: "POST /v1/responses 路由集成, 流式 SSE 代理, 非流式 JSON 响应翻译, compact 501, 错误翻译"
    - path: "tests/test_responses.py"
      provides: "HTTP 集成测试 (TestClient + httpx mock)"
      contains: "8-9 测试: 流式 SSE, 非流式 JSON, compact 501, auth 透传, 上游错误翻译, proxy 回归"
  key_links:
    - from: "dsv4_cc_proxy/proxy.py :: responses_handler"
      to: "dsv4_cc_proxy/codex/translate.py :: translate_request"
      via: "纯函数调用, 返回 Chat Completions 请求体"
    - from: "dsv4_cc_proxy/proxy.py :: _handle_stream_response"
      to: "dsv4_cc_proxy/codex/sse.py :: translate_sse_stream"
      via: "异步生成器模式: async for sse_event in translate_sse_stream(json_stream())"
    - from: "dsv4_cc_proxy/proxy.py :: _handle_non_stream_response"
      to: "dsv4_cc_proxy/codex/translate.py :: _translate_chat_to_responses"
      via: "同步纯函数: Chat JSON → Responses API JSON"
    - from: "dsv4_cc_proxy/proxy.py :: _get_client()"
      to: "dsv4_cc_proxy/proxy.py :: responses_handler"
      via: "复用现有懒加载 httpx AsyncClient, 600s timeout"
    - from: "dsv4_cc_proxy/proxy.py :: create_app() routes"
      to: "dsv4_cc_proxy/proxy.py :: catch-all /{path:path}"
      via: "Starlette 路由顺序匹配, /v1/responses 在 catch-all 之前"
---

<objective>
在 proxy.py 中注册 `/v1/responses` HTTP 端点，集成 Phase 1-4 的 codex 模块（translate_request、translate_sse_stream、convert_tools、resolve_model），实现认证透传和压缩端点。代码纯增量，不修改现有 proxy 逻辑。

**Purpose:** 将 Phase 1-4 构建的翻译模块通过 HTTP handler 粘合起来，让 Codex CLI 能直接使用此代理与 DeepSeek V4 通信。

**Output:**
- `dsv4_cc_proxy/proxy.py` — 新增 responses_handler、compact_handler、辅助函数、路由注册、导入 codex 模块
- `tests/test_responses.py` — HTTP 集成测试 (8-9 测试用例)
</objective>

<execution_context>
@/Users/lihaoxuan/.claude/get-shit-done/workflows/execute-plan.md
@/Users/lihaoxuan/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md (Phase 5 section)
</context>

<security_analysis>
STRIDE Threat Model for Route Integration:

| Threat | Component | Risk | Mitigation |
|--------|-----------|------|------------|
| **Spoofing (S)** | Authorization header forwarding | Medium | Auth header 原样转发到 DeepSeek API。不验证 token 格式，不记录 token。DeepSeek API 负责认证校验 |
| **Tampering (T)** | Request body parsing | Low | `request.json()` 解析。无效 JSON → 400 错误。`translate_request()` 输入验证由 Phase 2 保证 |
| **Repudiation (R)** | 无用户身份追踪 | Low | 日志记录 `[CODEX]` 前缀的请求摘要。不记录 auth header 内容。IP 和 timestamp 由 upstream web server 处理 |
| **Info Disclosure (I)** | Error message leaking | Low | 错误翻译从 DeepSeek body 提取 message 时，只提取 `error.message` 字段。不暴露内部 proxy 细节 |
| **Denial of Service (D)** | 上游连接泄漏 | Medium | httpx client 复用连接池（max_keepalive=8）。`aclose()` 在 finally 块中释放。600s timeout 防止挂起 |
| **Elevation of Privilege (E)** | 无身份验证绕过 | Low | `/v1/responses` 是公开路由（与 `/v1/messages` 相同级别）。无敏感内部操作 |
</security_analysis>

<task type="auto">
  <name>Task 1: 实现 responses_handler 和 compact_handler</name>
  <files>dsv4_cc_proxy/proxy.py</files>
  <action>
## Task 1: 实现 responses_handler 和 compact_handler

### 1.1 新增导入 (proxy.py 顶部)

```python
from dsv4_cc_proxy.codex.config import CODEX_UPSTREAM
from dsv4_cc_proxy.codex.sse import translate_sse_stream
from dsv4_cc_proxy.codex.translate import translate_request
```

### 1.2 实现 responses_handler

```python
async def responses_handler(request):
    """POST /v1/responses — Codex CLI 协议代理入口。"""
    logger.info("[CODEX] POST /v1/responses")

    # 1. 解析 JSON
    try:
        request_body = await request.json()
    except json.JSONDecodeError:
        return _build_error(400, "invalid_request_error", "invalid_json",
                           "Request body is not valid JSON")

    # 2. 构建上游 headers
    headers = {
        "content-type": "application/json",
        "authorization": request.headers.get("authorization", ""),
    }

    # 3. 翻译请求体
    try:
        chat_request = translate_request(request_body)
    except Exception:
        logger.exception("[CODEX] translate_request failed")
        return _build_error(400, "invalid_request_error", "translation_failed",
                           "Failed to translate request")

    # 4. 构建 upstream URL
    upstream_url = f"{CODEX_UPSTREAM}/chat/completions"

    # 5. 按 stream 分支
    is_stream = request_body.get("stream", False)
    if is_stream:
        return await _handle_stream_response(chat_request, headers, upstream_url)
    else:
        return await _handle_non_stream_response(chat_request, headers, upstream_url)
```

### 1.3 实现 _handle_stream_response

```python
async def _handle_stream_response(chat_request: dict, headers: dict, upstream_url: str):
    """流式: Chat delta chunk → SSE 事件流。"""
    chat_request["stream"] = True
    client = _get_client()

    try:
        req = client.build_request(
            method="POST", url=upstream_url, headers=headers,
            content=json.dumps(chat_request, ensure_ascii=False).encode("utf-8"),
        )
        upstream_resp = await client.send(req, stream=True)
    except Exception:
        logger.exception("[CODEX] upstream request failed")
        return _build_error(502, "proxy_error", "upstream_unavailable",
                           "Failed to reach DeepSeek API")

    # 非 200: 读 body 翻译为错误响应
    if upstream_resp.status_code != 200:
        body = b""
        async for chunk in upstream_resp.aiter_bytes():
            body += chunk
        await upstream_resp.aclose()
        return _translate_upstream_error(upstream_resp.status_code, body)

    async def event_stream():
        async def json_stream():
            try:
                async for line in _iter_lines(upstream_resp):
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            yield chunk
                        except json.JSONDecodeError:
                            continue
                    elif line.strip() == "data: [DONE]":
                        continue
            finally:
                await upstream_resp.aclose()

        async for sse_event in translate_sse_stream(json_stream()):
            yield sse_event.encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        status_code=200,
    )
```

### 1.4 实现 _handle_non_stream_response

```python
async def _handle_non_stream_response(chat_request: dict, headers: dict, upstream_url: str):
    """非流式: 获取完整 Chat JSON → 翻译为 Responses API JSON。"""
    chat_request["stream"] = False
    client = _get_client()

    try:
        req = client.build_request(
            method="POST", url=upstream_url, headers=headers,
            content=json.dumps(chat_request, ensure_ascii=False).encode("utf-8"),
        )
        upstream_resp = await client.send(req, stream=False)
    except Exception:
        logger.exception("[CODEX] upstream request failed")
        return _build_error(502, "proxy_error", "upstream_unavailable",
                           "Failed to reach DeepSeek API")

    if upstream_resp.status_code != 200:
        body = getattr(upstream_resp, 'content', b"")
        await upstream_resp.aclose()
        return _translate_upstream_error(upstream_resp.status_code, body)

    chat_response = upstream_resp.json()
    await upstream_resp.aclose()

    response_body = _translate_chat_to_responses(chat_response, chat_request.get("model", ""))
    return JSONResponse(response_body, status_code=200)
```

### 1.5 实现 _translate_chat_to_responses

```python
def _translate_chat_to_responses(chat_response: dict, model: str) -> dict:
    """将 Chat Completions JSON → Responses API JSON (非流式)。"""
    choices = chat_response.get("choices") or [{}]
    choice = choices[0] if choices else {}
    message = choice.get("message", {})

    output = []

    # reasoning_content → output item
    reasoning = (message.get("reasoning_content") or "").strip()
    if reasoning:
        output.append({
            "id": f"item_{len(output)}",
            "type": "reasoning",
            "status": "completed",
            "content": [{"type": "reasoning_text", "text": reasoning}],
        })

    # content → output item
    content = (message.get("content") or "").strip()
    if content:
        output.append({
            "id": f"item_{len(output)}",
            "type": "message",
            "status": "completed",
            "content": [{"type": "output_text", "text": content}],
            "role": "assistant",
        })

    # tool_calls → output items
    for tc in message.get("tool_calls", []):
        tc_id = tc.get("id", "")
        func = tc.get("function", {})
        output.append({
            "id": tc_id,
            "type": "function_call",
            "status": "completed",
            "name": func.get("name", "unknown"),
            "arguments": func.get("arguments", ""),
            "call_id": tc_id,
        })

    return {
        "id": f"resp_{chat_response.get('id', 'unknown')}",
        "object": "response",
        "model": model,
        "status": "completed",
        "output": output,
        "usage": chat_response.get("usage", {
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        }),
    }
```

### 1.6 实现 _translate_upstream_error + ERROR_CODE_MAP

```python
ERROR_CODE_MAP = {
    400: ("invalid_request_error", "Bad request"),
    401: ("authentication_error", "Invalid API key"),
    403: ("permission_error", "Access denied"),
    404: ("invalid_request_error", "Endpoint not found"),
    429: ("rate_limit_error", "Rate limit exceeded"),
    500: ("server_error", "DeepSeek server error"),
    502: ("server_error", "Upstream service unavailable"),
    503: ("server_error", "Service overloaded"),
}

def _translate_upstream_error(status_code: int, body: bytes) -> JSONResponse:
    """将 DeepSeek 错误翻译为 Responses API 错误格式。"""
    error_type, default_message = ERROR_CODE_MAP.get(
        status_code, ("server_error", "Unknown error")
    )

    detail = default_message
    try:
        ds_error = json.loads(body)
        if isinstance(ds_error, dict):
            err_obj = ds_error.get("error", {})
            if isinstance(err_obj, dict):
                detail = err_obj.get("message", default_message)
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    return JSONResponse(
        {
            "error": {
                "type": error_type,
                "code": str(status_code),
                "message": detail,
                "param": None,
            }
        },
        status_code=status_code,
    )
```

### 1.7 实现 _build_error + _iter_lines

```python
def _build_error(status_code: int, error_type: str, code: str, message: str) -> JSONResponse:
    """构建 Responses API 标准错误响应。"""
    return JSONResponse(
        {"error": {"type": error_type, "code": code, "message": message, "param": None}},
        status_code=status_code,
    )

async def _iter_lines(response: httpx.Response):
    """将 httpx 流式响应拆行为异步行生成器。"""
    buffer = ""
    async for chunk in response.aiter_bytes():
        text = chunk.decode("utf-8", errors="replace")
        buffer += text
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            yield line
    if buffer.strip():
        yield buffer
```

### 1.8 实现 compact_handler

```python
async def compact_handler(request):
    """POST /v1/responses/compact — 暂不支持,返回 501。"""
    logger.info("[CODEX] POST /v1/responses/compact — 501 not_implemented")
    return JSONResponse(
        {
            "error": {
                "type": "not_supported",
                "message": "Compaction is not yet supported for Codex + DeepSeek V4",
                "code": "501",
                "param": None,
            }
        },
        status_code=501,
    )
```

### 1.9 路由注册 (修改 create_app 的 routes)

```python
routes=[
    Route("/health", health, methods=["GET"]),
    Route("/v1/responses/compact", compact_handler, methods=["POST"]),   # ← 新增
    Route("/v1/responses", responses_handler, methods=["POST"]),         # ← 新增
    Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]),
],
```
  </action>
  <verify>
1. `pytest tests/test_proxy.py -v` — 22 个现有测试全部通过
2. 手动 curl 验证:
   - `curl -X POST http://127.0.0.1:16889/v1/responses/compact` → 501 + JSON error body
3. Starlette 路由顺序: `/v1/responses` 在 `/{path:path}` 之前
  </verify>
  <done>
- [ ] responses_handler 逻辑正确 — 按 stream 分支到流式/非流式处理
- [ ] compact_handler 返回 501 + JSON error body
- [ ] _translate_chat_to_responses 完整翻译 reasoning/content/tool_calls
- [ ] _translate_upstream_error 映射 DeepSeek 错误码到 Responses API 格式
- [ ] 异常处理覆盖: JSON 解析失败 / translate_request 异常 / 上游连接失败 / 上游非 200
- [ ] 22 个现有 proxy 测试全部通过
  </done>
</task>

<task type="auto">
  <name>Task 2: 编写 HTTP 集成测试</name>
  <files>tests/test_responses.py</files>
  <action>
## Task 2: 编写 HTTP 集成测试

### 2.1 测试架构

使用 Starlette TestClient + 自定义 httpx mock 类。

Mock 策略: 不发送真实网络请求，用 AsyncMock + MockTransport 模拟 httpx AsyncClient 的行为。测试 handler 的输入→输出转换正确性和错误处理完整性。

### 2.2 Mock 类

```python
# tests/test_responses.py

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from dsv4_cc_proxy.proxy import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


class _MockStreamResponse:
    """模拟 httpx 流式响应 (aiter_bytes + aclose)。"""
    def __init__(self, status_code=200, chunks=None, headers=None):
        self.status_code = status_code
        self._chunks = chunks or []
        self.headers = httpx.Headers(headers or {"content-type": "text/event-stream"})

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")

    async def aclose(self):
        pass


class _MockJSONResponse:
    """模拟 httpx JSON 响应 (json() + content + aclose)。"""
    def __init__(self, status_code=200, json_data=None, content=None):
        self.status_code = status_code
        self._json = json_data
        self.content = content or json.dumps(json_data or {}).encode("utf-8")
        self.headers = httpx.Headers({"content-type": "application/json"})

    def json(self):
        return self._json

    async def aclose(self):
        pass
```

### 2.3 测试用例

| # | 测试名 | 场景 | 验证点 |
|---|--------|------|--------|
| 1 | `test_compact_returns_501` | POST /v1/responses/compact | 状态码 501, error.type="not_supported" |
| 2 | `test_invalid_json_returns_400` | POST /v1/responses 非 JSON | 400 status, error.code="invalid_json" |
| 3 | `test_non_stream_response` | POST /v1/responses stream:false (mock 上游) | Content-Type=application/json, 结构含 id/object/model/status/output/usage |
| 4 | `test_stream_response_content_type` | POST /v1/responses stream:true (mock SSE 上游) | Content-Type=text/event-stream |
| 5 | `test_stream_events_lifecycle` | POST /v1/responses stream:true | SSE body 包含 response.created, response.in_progress, response.completed 事件类型 |
| 6 | `test_auth_header_passthrough` | POST /v1/responses stream:false (mock 断言) | Authorization header 原样传到上游请求 |
| 7 | `test_no_auth_header_defaults_empty` | POST /v1/responses 不带 Authorization | 转发空字符串到 upstream, 不崩溃 |
| 8 | `test_upstream_401_error` | 上游返回 401 | error.type="authentication_error", error.code="401" |
| 9 | `test_upstream_429_error` | 上游返回 429 | error.type="rate_limit_error", error.code="429" |
| 10 | `test_upstream_500_error` | 上游返回 500 | error.type="server_error", error.code="500" |
| 11 | `test_existing_proxy_tests_pass` | 运行 tests/test_proxy.py | 22 tests pass (手动验证或 CI) |

### 2.4 关键测试示例

**test_compact_returns_501:**
```python
def test_compact_returns_501(client):
    resp = client.post("/v1/responses/compact", json={})
    assert resp.status_code == 501
    body = resp.json()
    assert body["error"]["type"] == "not_supported"
```

**test_non_stream_response:**
```python
def test_non_stream_response(client):
    mock_chat_resp = _MockJSONResponse(status_code=200, json_data={
        "id": "chat-123",
        "choices": [{"message": {"content": "Hello, world!"}}],
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    })

    with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.build_request.return_value = MagicMock()  # httpx.Request
        mock_client.send.return_value = mock_chat_resp
        mock_get_client.return_value = mock_client

        resp = client.post("/v1/responses", json={
            "model": "gpt-5",
            "input": [{"role": "user", "content": "Hello"}],
            "stream": False,
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert len(body["output"]) == 1
    assert body["output"][0]["type"] == "message"
    assert body["output"][0]["content"][0]["text"] == "Hello, world!"
    assert body["usage"]["total_tokens"] == 15
```

**test_upstream_401_error:**
```python
def test_upstream_401_error(client):
    mock_err_resp = _MockJSONResponse(status_code=401, json_data={
        "error": {"message": "Invalid API key"}
    })

    with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.build_request.return_value = MagicMock()
        mock_client.send.return_value = mock_err_resp
        mock_get_client.return_value = mock_client

        resp = client.post("/v1/responses", json={
            "model": "gpt-5",
            "input": [{"role": "user", "content": "Hello"}],
            "stream": False,
        })

    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["type"] == "authentication_error"
    assert "Invalid API key" in body["error"]["message"]
```
  </action>
  <verify>
1. `pytest tests/test_responses.py -v` — 所有 10 测试通过
2. `pytest tests/test_proxy.py -v` — 22 个现有测试全部通过 (回归)
3. `pytest tests/ -v --cov=dsv4_cc_proxy --cov-report=term-missing` — coverage >= 80%
  </verify>
  <done>
- [ ] 10 个新测试全部通过
- [ ] compact 501 测试通过
- [ ] 非流式 JSON 翻译测试通过
- [ ] 流式 SSE content-type 测试通过
- [ ] 上游错误码 401/429/500 翻译测试通过
- [ ] auth 透传测试通过
- [ ] 22 个现有 proxy 测试全部通过 (零回归)
  </done>
</task>

<notes>
## Claude's Discretion Areas

以下实现细节由执行 agent 自行决策：

1. **辅助函数命名**: 具体函数名以 task 伪代码为准，如有冲突自行调整
2. **日志记录**: `[CODEX]` 前缀，参考现有 proxy.py 日志模式
3. **错误码映射表**: ERROR_CODE_MAP 的完整映射项（基础 400-503 已给出，执行时补全边界码如 408/422 等）
4. **TestClient httpx mock**: 使用 `unittest.mock.patch` 替换 `_get_client()` 返回 AsyncMock
5. **非流式 JSON 翻译**: `_translate_chat_to_responses` 的 output 数组 item 顺序和字段映射细节
6. **流式响应 usage**: `response.completed` 事件中 usage 从 DeepSeek 最后一个 chunk 提取（sse.py 已实现，handler 无需处理）
7. **httpx client timeout**: 复用现有 `_get_client()` 的 600s timeout
8. **Content-Type**: 所有错误（含流式路径）返回 `application/json`。流式错误在 StreamingResponse 启动前已转为 JSON。SSE 中错误由 translate_sse_stream 在 SSE 格式内处理

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| httpx client timeout 不匹配 Codex 场景 | Low | Medium | 现有 600s 足够 DeepSeek V4 最长推理 |
| translate_sse_stream() 与错误流不兼容 | Low | Low | 上游错误时返回 JSON error，不进入 translate_sse_stream |
| 现有 proxy 测试回归 | Very Low | High | 纯增量，不改现有逻辑。Task 2 verify 回归测试 |
| TestClient + async mock 兼容性 | Medium | Low | 备选：直接测试 handler 函数签名 |
</notes>
