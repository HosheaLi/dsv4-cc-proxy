"""dsv4-cc-proxy /v1/responses 路由 HTTP 集成测试。

覆盖: compact 501, 无效 JSON, 非流式 JSON, 流式 SSE,
      上游错误翻译, auth 透传, 回归检查。

运行: python3 -m pytest tests/test_responses.py -v
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from dsv4_cc_proxy.proxy import _translate_chat_to_responses, create_app


@pytest.fixture
def client():
    return TestClient(create_app())


# ---- Mock 辅助类 ----


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

    async def aiter_bytes(self):
        yield self.content

    async def aclose(self):
        pass


# ---- 测试辅助函数 ----


def _make_mock_client(mock_response):
    """创建 mock httpx.AsyncClient 返回指定响应。"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.build_request.return_value = MagicMock(spec=httpx.Request)
    mock_client.send.return_value = mock_response
    return mock_client


# ---- 测试用例 ----


class TestCompact:
    """POST /v1/responses/compact"""

    def test_compact_returns_501(self, client):
        """compress 端点返回 501 + JSON error body。"""
        resp = client.post("/v1/responses/compact", json={})

        assert resp.status_code == 501
        body = resp.json()
        assert body["error"]["type"] == "not_supported"
        assert body["error"]["code"] == "501"


class TestInvalidInput:
    """异常输入测试。"""

    def test_invalid_json_returns_400(self, client):
        """非 JSON 请求体返回 400。"""
        resp = client.post(
            "/v1/responses",
            content=b"not json",
            headers={"content-type": "application/json"},
        )

        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "invalid_json"


class TestNonStream:
    """POST /v1/responses stream:false — 非流式 JSON 响应。"""

    def test_non_stream_response(self, client):
        """非流式请求返回正确的 Responses API JSON 结构。"""
        mock_chat_resp = _MockJSONResponse(status_code=200, json_data={
            "id": "chat-123",
            "choices": [{"message": {"content": "Hello, world!"}}],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        })

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_chat_resp)

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

    def test_non_stream_with_reasoning(self, client):
        """非流式含 reasoning_content 时 output 包含 reasoning 和 message item。"""
        mock_chat_resp = _MockJSONResponse(status_code=200, json_data={
            "id": "chat-456",
            "choices": [{"message": {
                "reasoning_content": "thinking step by step...",
                "content": "Final answer",
            }}],
            "usage": {"input_tokens": 10, "output_tokens": 8, "total_tokens": 18},
        })

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_chat_resp)

            resp = client.post("/v1/responses", json={
                "model": "gpt-5",
                "input": [{"role": "user", "content": "Think hard"}],
                "stream": False,
            })

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["output"]) == 2
        assert body["output"][0]["type"] == "reasoning"
        assert body["output"][0]["content"][0]["text"] == "thinking step by step..."
        assert body["output"][1]["type"] == "message"
        assert body["output"][1]["content"][0]["text"] == "Final answer"

    def test_non_stream_with_tool_calls(self, client):
        """非流式含 tool_calls 时 output 包含 function_call item。"""
        mock_chat_resp = _MockJSONResponse(status_code=200, json_data={
            "id": "chat-789",
            "choices": [{"message": {
                "content": "Let me check that...",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"cmd": "ls -la"}',
                        },
                    },
                ],
            }}],
            "usage": {"input_tokens": 10, "output_tokens": 12, "total_tokens": 22},
        })

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_chat_resp)

            resp = client.post("/v1/responses", json={
                "model": "gpt-5",
                "input": [{"role": "user", "content": "Run ls"}],
                "stream": False,
            })

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["output"]) == 2
        assert body["output"][0]["type"] == "message"
        assert body["output"][1]["type"] == "function_call"
        assert body["output"][1]["name"] == "bash"
        assert body["output"][1]["call_id"] == "call_1"


class TestStream:
    """POST /v1/responses stream:true — 流式 SSE 响应。"""

    # 一个最简单的 Chat delta chunk：仅含 response.created 等元事件
    _MINIMAL_STREAM_CHUNKS = [
        b'data: {"id":"chat-1","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":"stop"}],"usage":{"input_tokens":5,"output_tokens":1,"total_tokens":6}}\n\n',
    ]

    def test_stream_response_content_type(self, client):
        """流式响应的 Content-Type 为 text/event-stream。"""
        mock_resp = _MockStreamResponse(status_code=200, chunks=self._MINIMAL_STREAM_CHUNKS)

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_resp)

            resp = client.post("/v1/responses", json={
                "model": "gpt-5",
                "input": [{"role": "user", "content": "Hello"}],
                "stream": True,
            })

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

    def test_stream_events_lifecycle(self, client):
        """流式 SSE body 包含 response.created, in_progress, completed 等生命周期事件。"""
        mock_resp = _MockStreamResponse(status_code=200, chunks=self._MINIMAL_STREAM_CHUNKS)

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_resp)

            resp = client.post("/v1/responses", json={
                "model": "gpt-5",
                "input": [{"role": "user", "content": "Hello"}],
                "stream": True,
            })

        assert resp.status_code == 200
        body = resp.text

        # 验证关键事件类型出现在 SSE 流中
        assert "response.created" in body
        assert "response.in_progress" in body
        assert "response.completed" in body


class TestAuthPassthrough:
    """Authorization header 透传。"""

    def test_auth_header_passthrough(self, client):
        """Authorization header 原样传递到上游请求。"""
        mock_chat_resp = _MockJSONResponse(status_code=200, json_data={
            "id": "chat-auth",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        })

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.build_request.return_value = MagicMock(spec=httpx.Request)
            mock_client.send.return_value = mock_chat_resp
            mock_get_client.return_value = mock_client

            resp = client.post(
                "/v1/responses",
                json={
                    "model": "gpt-5",
                    "input": [{"role": "user", "content": "Hello"}],
                    "stream": False,
                },
                headers={"authorization": "Bearer test-key-123"},
            )

        assert resp.status_code == 200

        # 验证 authorization header 传到了上游请求
        call_kwargs = mock_client.build_request.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        assert kwargs.get("headers", {}).get("authorization") == "Bearer test-key-123"

    def test_no_auth_header_defaults_empty(self, client):
        """无 authorization header 时传入空字符串，不崩溃。"""
        mock_chat_resp = _MockJSONResponse(status_code=200, json_data={
            "id": "chat-noauth",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        })

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.build_request.return_value = MagicMock(spec=httpx.Request)
            mock_client.send.return_value = mock_chat_resp
            mock_get_client.return_value = mock_client

            resp = client.post(
                "/v1/responses",
                json={
                    "model": "gpt-5",
                    "input": [{"role": "user", "content": "Hello"}],
                    "stream": False,
                },
                # 不传 authorization header
            )

        assert resp.status_code == 200

        call_kwargs = mock_client.build_request.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        assert kwargs.get("headers", {}).get("authorization") == ""


class TestUpstreamError:
    """上游错误翻译。"""

    def test_upstream_401_error(self, client):
        """上游返回 401 -> authentication_error。"""
        mock_err_resp = _MockJSONResponse(status_code=401, json_data={
            "error": {"message": "Invalid API key"},
        })

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_err_resp)

            resp = client.post("/v1/responses", json={
                "model": "gpt-5",
                "input": [{"role": "user", "content": "Hello"}],
                "stream": False,
            })

        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["type"] == "authentication_error"
        assert body["error"]["code"] == "401"
        assert "Invalid API key" in body["error"]["message"]

    def test_upstream_429_error(self, client):
        """上游返回 429 -> rate_limit_error。"""
        mock_err_resp = _MockJSONResponse(status_code=429, json_data={
            "error": {"message": "Rate limit exceeded"},
        })

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_err_resp)

            resp = client.post("/v1/responses", json={
                "model": "gpt-5",
                "input": [{"role": "user", "content": "Hello"}],
                "stream": False,
            })

        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["type"] == "rate_limit_error"
        assert body["error"]["code"] == "429"
        assert "Rate limit exceeded" in body["error"]["message"]

    def test_upstream_500_error(self, client):
        """上游返回 500 -> server_error。"""
        mock_err_resp = _MockJSONResponse(status_code=500, json_data={
            "error": {"message": "Internal server error"},
        })

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_err_resp)

            resp = client.post("/v1/responses", json={
                "model": "gpt-5",
                "input": [{"role": "user", "content": "Hello"}],
                "stream": False,
            })

        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["type"] == "server_error"
        assert body["error"]["code"] == "500"

    def test_upstream_error_without_detail(self, client):
        """上游错误 body 无 error.message 时使用默认消息。"""
        mock_err_resp = _MockJSONResponse(status_code=401, json_data={
            "error": {},
        })

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_err_resp)

            resp = client.post("/v1/responses", json={
                "model": "gpt-5",
                "input": [{"role": "user", "content": "Hello"}],
                "stream": False,
            })

        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["message"] == "Invalid API key"


class TestStreamError:
    """流式路径错误处理。"""

    def test_stream_upstream_401_error(self, client):
        """流式路径上游返回 401 -> authentication_error。"""
        mock_err_resp = _MockJSONResponse(status_code=401, json_data={
            "error": {"message": "Bad auth"},
        })

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_err_resp)

            resp = client.post("/v1/responses", json={
                "model": "gpt-5",
                "input": [{"role": "user", "content": "Hello"}],
                "stream": True,
            })

        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["type"] == "authentication_error"


class TestTranslateChatToResponses:
    """_translate_chat_to_responses 纯函数测试。"""

    def test_basic_translation(self):
        """基础消息翻译。"""
        chat_response = {
            "id": "chat-1",
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
        }
        result = _translate_chat_to_responses(chat_response, "deepseek-v4-pro")
        assert result["object"] == "response"
        assert result["model"] == "deepseek-v4-pro"
        assert result["status"] == "completed"
        assert len(result["output"]) == 1
        assert result["output"][0]["type"] == "message"
        assert result["output"][0]["content"][0]["text"] == "Hello!"
        assert result["usage"]["total_tokens"] == 8

    def test_no_choices(self):
        """无 choices 时不崩溃，返回空 output。"""
        result = _translate_chat_to_responses({"id": "empty"}, "test-model")
        assert result["output"] == []

    def test_reasoning_and_content(self):
        """reasoning_content + content 同时翻译。"""
        chat_response = {
            "id": "chat-r",
            "choices": [{"message": {
                "reasoning_content": "thinking...",
                "content": "answer",
            }}],
            "usage": {},
        }
        result = _translate_chat_to_responses(chat_response, "m")
        assert len(result["output"]) == 2
        assert result["output"][0]["type"] == "reasoning"
        assert result["output"][1]["type"] == "message"

    def test_tool_calls(self):
        """tool_calls 翻译为 function_call。"""
        chat_response = {
            "id": "chat-tc",
            "choices": [{"message": {
                "content": "Using tool",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "bash", "arguments": '{"cmd":"ls"}'},
                    },
                ],
            }}],
            "usage": {},
        }
        result = _translate_chat_to_responses(chat_response, "m")
        assert len(result["output"]) == 2
        assert result["output"][1]["type"] == "function_call"
        assert result["output"][1]["name"] == "bash"
        assert result["output"][1]["call_id"] == "call_1"

    def test_empty_reasoning_skipped(self):
        """空 reasoning_content 跳过。"""
        chat_response = {
            "id": "c",
            "choices": [{"message": {
                "reasoning_content": "",
                "content": "hi",
            }}],
            "usage": {},
        }
        result = _translate_chat_to_responses(chat_response, "m")
        assert len(result["output"]) == 1
        assert result["output"][0]["type"] == "message"

    def test_empty_content_skipped(self):
        """空 content 跳过。"""
        chat_response = {
            "id": "c",
            "choices": [{"message": {
                "reasoning_content": "thinking",
                "content": "",
            }}],
            "usage": {},
        }
        result = _translate_chat_to_responses(chat_response, "m")
        assert len(result["output"]) == 1
        assert result["output"][0]["type"] == "reasoning"

    def test_default_usage_when_missing(self):
        """usage 缺失时使用默认零值不崩溃。"""
        result = _translate_chat_to_responses({"id": "x", "choices": [{"message": {}}]}, "m")
        assert result["usage"]["total_tokens"] == 0
