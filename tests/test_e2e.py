"""dsv4-cc-proxy E2E 集成测试。

覆盖: 非流式 JSON 响应、流式 SSE 事件、compact 501、auth 透传。

模式参考 tests/test_responses.py: TestClient + _MockJSONResponse/_MockStreamResponse + patch("dsv4_cc_proxy.proxy._get_client")。

运行: python3 -m pytest tests/test_e2e.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from conftest import _make_mock_client, _MockJSONResponse, _MockStreamResponse

# ---- E2E 场景 1: 非流式 JSON 响应 ----


class TestNonStreamE2E:
    """POST /v1/responses stream:false — 完整非流式 E2E 链路。

    验证 Codex 请求 -> DeepSeek Chat -> Responses API JSON 翻译。
    """

    def test_non_stream_json_response(self, client):
        """非流式请求经过翻译后返回正确的 Responses API JSON 结构。"""
        mock_chat_resp = _MockJSONResponse(status_code=200, json_data={
            "id": "chat-e2e",
            "choices": [{"message": {"content": "Hello from DeepSeek"}}],
            "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
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
        assert body["output"][0]["content"][0]["text"] == "Hello from DeepSeek"


# ---- E2E 场景 2: 流式 SSE 事件 ----


class TestStreamE2E:
    """POST /v1/responses stream:true — 完整流式 E2E 链路。

    验证 Chat SSE -> Responses API SSE 事件流翻译。
    """

    _MINIMAL_STREAM_CHUNKS = [
        b'data: {"id":"chat-e2e-stream","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":"stop"}],"usage":{"input_tokens":5,"output_tokens":1,"total_tokens":6}}\n\n',
    ]

    def test_stream_sse_events(self, client):
        """流式请求返回 SSE 事件流，包含生命周期事件。"""
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

        body = resp.text
        assert "response.created" in body
        assert "response.completed" in body


# ---- E2E 场景 3: compact 501 ----


class TestCompactE2E:
    """POST /v1/responses/compact — 压缩端点返回 501。"""

    def test_compact_returns_501(self, client):
        """compress 端点返回 501 + JSON error body。"""
        resp = client.post("/v1/responses/compact", json={})

        assert resp.status_code == 501
        body = resp.json()
        assert body["error"]["type"] == "not_supported"
        assert body["error"]["code"] == "501"


# ---- E2E 场景 4: auth 透传 ----


class TestAuthE2E:
    """Authorization header 透传。"""

    def test_auth_header_passthrough(self, client):
        """Authorization header 原样传递到上游请求。"""
        mock_chat_resp = _MockJSONResponse(status_code=200, json_data={
            "id": "chat-auth-e2e",
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
