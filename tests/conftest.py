"""dsv4-cc-proxy 测试共享辅助类与 fixture。

提供 _MockJSONResponse / _MockStreamResponse / _make_mock_client，
供 tests/test_responses.py 和 tests/test_e2e.py 复用。
"""

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from starlette.testclient import TestClient

from dsv4_cc_proxy.proxy import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


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


def _make_mock_client(mock_response):
    """创建 mock httpx.AsyncClient 返回指定响应。"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.build_request.return_value = MagicMock(spec=httpx.Request)
    mock_client.send.return_value = mock_response
    return mock_client
