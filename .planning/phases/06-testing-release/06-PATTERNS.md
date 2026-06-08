# Phase 6: Testing & Release - Pattern Map

**Mapped:** 2026-06-07
**Files analyzed:** 10 (3 new, 7 modified)
**Analogs found:** 10 / 10

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `tests/test_e2e.py` | test | request-response | `tests/test_responses.py` | role-match |
| `tests/test_main.py` | test | request-response | `tests/test_codex.py` (monkeypatch) + `tests/test_responses.py` (fixture) | partial |
| `docs/dev/codex-integration.md` | doc | n/a | `docs/dev/deepseek-thinking-proxy.md` | exact |
| `tests/test_responses.py` | test | request-response | Self (existing file, add classes) | exact |
| `tests/test_proxy.py` | test | request-response | Self (existing file, add functions) | exact |
| `.github/workflows/ci.yml` | config | n/a | Self (existing file, add jobs/steps) | exact |
| `dsv4_cc_proxy/_version.py` | config | n/a | Self (existing file, bump version) | exact |
| `README.md` | doc | n/a | Self (existing file, add section) | exact |
| `README.zh-CN.md` | doc | n/a | Self (existing file, add section) | exact |
| `CHANGELOG.md` | doc | n/a | Self (existing file, add entry) | exact |

## Pattern Assignments

### `tests/test_e2e.py` (test, request-response - NEW)

**Analog:** `tests/test_responses.py` (lines 1-70)

**Imports pattern** (lines 1-16):
```python
"""dsv4-cc-proxy E2E 集成测试。

覆盖: 非流式 JSON 响应、流式 SSE 事件、compact 501、auth 透传。

运行: python3 -m pytest tests/test_e2e.py -v
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from dsv4_cc_proxy.proxy import create_app
```

**Test fixture pattern** (lines 19-21):
```python
@pytest.fixture
def client():
    return TestClient(create_app())
```

**Mock class pattern** (lines 27-59) — reuse `_MockStreamResponse` and `_MockJSONResponse` from test_responses.py:
```python
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


def _make_mock_client(mock_response):
    """创建 mock httpx.AsyncClient 返回指定响应。"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.build_request.return_value = MagicMock(spec=httpx.Request)
    mock_client.send.return_value = mock_response
    return mock_client
```

**Test class pattern with class-level organization** (lines 76-86 from TestCompact):
```python
class TestNonStreamE2E:
    """非流式 Codex 请求 -> DeepSeek -> Responses API JSON 响应。"""

    def test_non_stream_e2e(self, client):
        mock_chat_resp = _MockJSONResponse(status_code=200, json_data={
            "id": "chat-e2e",
            "choices": [{"message": {"content": "Hello, world!"}}],
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
```

**Core E2E SSE test pattern** (from TestStream in test_responses.py, lines 200-243):
```python
class TestStreamE2E:
    """流式 Codex 请求 -> DeepSeek -> Responses API SSE 事件流。"""

    _MINIMAL_STREAM_CHUNKS = [
        b'data: {"id":"chat-e2e","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":"stop"}],"usage":{"input_tokens":5,"output_tokens":1,"total_tokens":6}}\n\n',
    ]

    def test_stream_e2e_content_type(self, client):
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
        assert "response.created" in resp.text
        assert "response.completed" in resp.text
```

**E2E compact 501 test pattern** (from TestCompact in test_responses.py, lines 76-86):
```python
class TestCompactE2E:
    """Compact 端点 -> 501 响应。"""

    def test_compact_e2e(self, client):
        resp = client.post("/v1/responses/compact", json={})
        assert resp.status_code == 501
        body = resp.json()
        assert body["error"]["type"] == "not_supported"
        assert body["error"]["code"] == "501"
```

**E2E auth passthrough test pattern** (from TestAuthPassthrough in test_responses.py, lines 246-310):
```python
class TestAuthE2E:
    """Authorization header 透传验证。"""

    def test_auth_passthrough_e2e(self, client):
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
                json={"model": "gpt-5", "input": [{"role": "user", "content": "Hello"}], "stream": False},
                headers={"authorization": "Bearer test-key-123"},
            )

        assert resp.status_code == 200
        call_kwargs = mock_client.build_request.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        assert kwargs.get("headers", {}).get("authorization") == "Bearer test-key-123"
```

---

### `tests/test_main.py` (test, request-response - NEW)

**Analog:** `tests/test_codex.py` for monkeypatch + env var pattern; RESEARCH.md for CLI testing pattern

**Imports pattern:**
```python
"""dsv4-cc-proxy __main__.py CLI 单元测试。

覆盖: --stop 正常/进程不存在/SIGTERM 超时, 正常启动, PID 文件冲突, 清理。

运行: python3 -m pytest tests/test_main.py -v
"""

import os
import signal
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
```

**Core CLI test pattern** (from RESEARCH.md lines 307-322 — no direct project analog exists, this is the recommended pattern):
```python
def test_main_stop_not_running(monkeypatch, tmp_path):
    """--stop 时 PID 文件不存在 -> sys.exit(1)。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    monkeypatch.setattr("sys.argv", ["dsv4-cc-proxy", "--stop", f"--pidfile={pidfile}"])

    from dsv4_cc_proxy.__main__ import main
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_main_stop_normal(monkeypatch, tmp_path):
    """--stop 正常流程 -> SIGTERM -> PID 文件清理。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    pidfile.write_text("99999")
    monkeypatch.setattr("sys.argv", ["dsv4-cc-proxy", "--stop", f"--pidfile={pidfile}"])

    with patch("dsv4_cc_proxy.__main__.os.kill") as mock_kill:
        from dsv4_cc_proxy.__main__ import main
        main()
        mock_kill.assert_called_once_with(99999, signal.SIGTERM)
    assert not pidfile.exists()


def test_main_already_running(monkeypatch, tmp_path):
    """已有实例运行 -> sys.exit(1)。"""
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    pidfile.write_text(str(os.getpid()))
    monkeypatch.setattr("sys.argv", ["dsv4-cc-proxy", f"--pidfile={pidfile}"])

    # os.kill(pid, 0) will succeed for the same process, so "already running" check triggers
    from dsv4_cc_proxy.__main__ import main
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
```

**Monkeypatch env var pattern** (from `tests/test_codex.py` lines 14-16):
```python
def test_something(monkeypatch):
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    reload(codex_config)
```

---

### `docs/dev/codex-integration.md` (doc, n/a - NEW)

**Analog:** `docs/dev/deepseek-thinking-proxy.md` (lines 1-150)

**Document structure pattern** (lines 1-20):
```markdown
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

[Description of the feature, problem it solves, and how it works at a high level.]

## 架构

```
Codex (Claude Code) ──→ localhost:16889 ──→ https://api.deepseek.com/chat/completions
                          │
                          │ (三层处理: 请求翻译 + 工具转换 + SSE 流转换)
                          │
                          ←── Responses API JSON/SSE ←────────────────────
```
```

**Documentation sections pattern** (from deepseek-thinking-proxy.md):
- Header with YAML frontmatter (lines 1-8)
- Overview (lines 10-18)
- Architecture diagram (lines 22-28)
- Environment variables table (lines 39-47)
- Detailed processing flow / logic (lines 49-59)
- Performance characteristics (lines 61-68)
- Health check (lines 114-119)
- Troubleshooting (lines 122-141)
- Version history (lines 143-150)

**Top-level sections to include for codex-integration.md:**
1. YAML frontmatter
2. Overview (problem+solution)
3. Architecture (three-layer processing diagram)
4. Module dependency graph
5. Translation flow: request (Responses API -> Chat Completions)
6. Translation flow: streaming response (Chat SSE -> Responses API SSE)
7. SSE lifecycle event sequence
8. Environment variables reference
9. Testing
10. Version history

---

### `tests/test_responses.py` (test, request-response - MODIFIED)

**Analog:** Self (existing file, add new test classes)

**Pattern for adding proxy.py missing path tests** — append new classes following existing class organization:

```python
class TestProxyPassthrough:
    """proxy() passthrough path (non-/v1/messages requests)."""

    def test_passthrough_health(self, client):
        """健康检查端点透传。"""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_passthrough_non_messages(self, client):
        """非 /v1/messages 请求透传（直接调用 proxy()）。"""
        mock_resp = _MockJSONResponse(status_code=200, json_data={"status": "ok"})
        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_resp)
            resp = client.get("/v1/models")
        assert resp.status_code == 200


class TestProxyFilteredStream:
    """proxy() filtered_stream path (thinking enabled)."""

    _THINKING_STREAM_CHUNKS = [
        b'data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":"","signature":""}}\n\n',
        b'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"hello"}}\n\n',
        b'data: {"type":"content_block_stop","index":0}\n\n',
        b'data: {"type":"content_block_start","index":1,"content_block":{"type":"text","text":""}}\n\n',
        b'data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"response"}}\n\n',
        b'data: {"type":"content_block_stop","index":1}\n\n',
        b'data: {"type":"message_stop"}\n\n',
    ]

    def test_filtered_stream_strips_thinking(self, client):
        """thinking 启用的 messages 流式响应过滤 thinking 事件。"""
        mock_resp = _MockStreamResponse(status_code=200, chunks=self._THINKING_STREAM_CHUNKS)
        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_resp)
            resp = client.post("/v1/messages", json={
                "model": "deepseek-v4-pro",
                "thinking": {"type": "enabled"},
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            })
        assert resp.status_code == 200
        # No thinking events in response
        assert "thinking" not in resp.text or "text_delta" in resp.text


class TestProxyBuildRequest:
    """proxy() build_request path edge cases."""

    def test_build_request_invalid_json(self, client):
        """上游 JSONDecodeError -> 502。"""
        mock_resp = _MockJSONResponse(status_code=200, content=b"not json")
        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_resp)
            resp = client.post("/v1/responses", json={
                "model": "gpt-5",
                "input": [{"role": "user", "content": "Hello"}],
                "stream": False,
            })
        assert resp.status_code == 502


class TestProxyError:
    """proxy() error handling paths."""

    def test_upstream_connection_failure(self, client):
        """上游连接失败 -> 502。"""
        from httpx import ConnectError
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.build_request.return_value = MagicMock(spec=httpx.Request)
        mock_client.send.side_effect = ConnectError("Connection refused")

        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = mock_client
            resp = client.post("/v1/responses", json={
                "model": "gpt-5",
                "input": [{"role": "user", "content": "Hello"}],
                "stream": False,
            })
        assert resp.status_code == 502
```

---

### `tests/test_proxy.py` (test, request-response - MODIFIED)

**Analog:** Self (existing file, add functions following existing pattern)

**Function-level test pattern** (from existing test_proxy.py lines 20-24):
```python
def test_has_tool_use():
    assert _has_tool_use([{"type": "tool_use", "name": "Bash"}])
    assert not _has_tool_use([{"type": "text", "text": "hello"}])
    assert not _has_tool_use([])
    assert _has_tool_use([{"type": "text"}, {"type": "tool_use"}])
```

**Pattern for adding edge case tests** — add standalone functions with clear docstrings, sections separated by `# === Section Name ===`:
```python
# === proxy.py 边缘情况补充 ===

def test_thinking_requested_deepseek_v4():
    """_thinking_requested 对 deepseek-v4 前缀返回正确。"""
    assert _thinking_requested({"model": "deepseek-v4-pro", "thinking": {"type": "enabled"}})
    assert not _thinking_requested({"model": "deepseek-v4-pro", "thinking": {"type": "disabled"}})


def test_normalize_thinking_no_messages():
    """_normalize_thinking 无 messages 键时处理。"""
    # 无崩溃，无修改
    data = {"thinking": {"type": "adaptive"}}
    assert _normalize_thinking(data)
    assert data["thinking"]["type"] == "disabled"
```

---

### `.github/workflows/ci.yml` (config, n/a - MODIFIED)

**Analog:** Self (existing file lines 1-171)

**PyPI OIDC job pattern** (append to publish job, replace API token step, from RESEARCH.md + existing lines 98-106):
```yaml
  publish:
    runs-on: ubuntu-latest
    needs: [test, lint]
    if: startsWith(github.ref, 'refs/tags/v')
    permissions:
      contents: write
      id-token: write   # OIDC trusted publishing requires this

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: "3.12"

    - name: Install build tools
      run: pip install build

    - name: Extract version from tag
      id: tag
      run: echo "VERSION=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"

    # --- GitHub Release ---
    - name: Create GitHub Release
      uses: softprops/action-gh-release@v2
      with:
        generate_release_notes: true
        name: v${{ steps.tag.outputs.VERSION }}

    # --- PyPI publish (OIDC) ---
    - name: Build sdist & wheel
      run: python -m build

    - name: Publish to PyPI
      uses: pypa/gh-action-pypi-publish@release/v1
      with:
        print-hash: true
      # No password: OIDC uses id-token: write automatically

    # --- Coverage badge generation ---
    - name: Install coverage-badge
      run: pip install coverage-badge

    - name: Generate coverage badge
      run: coverage-badge -o coverage.svg

    - name: Upload coverage badge artifact
      uses: actions/upload-artifact@v4
      with:
        name: coverage-badge
        path: coverage.svg
```

**Coverage badge commit-back pattern** (alternative to artifact upload — add after test job):
```yaml
    # In test job, after pytest --cov
    - name: Generate coverage badge
      if: github.ref == 'refs/heads/main'
      run: |
        pip install coverage-badge
        coverage-badge -o coverage.svg

    - name: Commit coverage badge
      if: github.ref == 'refs/heads/main'
      run: |
        git config user.name "github-actions[bot]"
        git config user.email "github-actions[bot]@users.noreply.github.com"
        git add coverage.svg
        git diff --staged --quiet || git commit -m "chore: update coverage badge [skip ci]"
        git push
```

**Docker semver tag pattern** (already in existing file lines 118-127, keep as-is):
```yaml
    - name: Extract metadata for Docker
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: hosheali/dsv4-cc-proxy
        tags: |
          type=semver,pattern={{version}}
          type=semver,pattern={{major}}.{{minor}}
          type=raw,value=latest
```

**Add sha-xxxxx tag** (append to existing tags section):
```yaml
          type=sha
```

**Update test job to run full suite** (change line 32):
```yaml
    - name: Run tests
      run: python -m pytest tests/ -v --cov=dsv4_cc_proxy --cov-report=term
```

---

### `dsv4_cc_proxy/_version.py` (config, n/a - MODIFIED)

**Analog:** Self (line 1)

**Change:**
```python
VERSION = "2.0.0"
```

---

### `README.md` (doc, n/a - MODIFIED)

**Analog:** Self (existing file, append Codex Support section after "Why dsv4-cc-proxy" or before "Quick Start")

**Codex Support section to add** (follow existing section structure pattern):
```markdown
## Codex Support

dsv4-cc-proxy also translates between the [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses) format and DeepSeek's Chat Completions API, enabling Codex (and other OpenAI Responses API clients) to use DeepSeek V4 models.

```
Codex (Claude Code) ──→ localhost:16889 ──→ https://api.deepseek.com/chat/completions
```

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /v1/responses` | Translate Responses API requests to Chat Completions, then translate responses back |
| `POST /v1/responses/compact` | Not supported — returns 501 |

### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `CODEX_DEFAULT_MODEL` | `deepseek-v4-pro` | Default model for Codex requests |
| `CODEX_MODEL_MAP` | `{}` | JSON map of client model names to DeepSeek model names (e.g., `{"claude-sonnet-4-6": "deepseek-v4-pro"}`) |
| `CODEX_UPSTREAM` | `https://api.deepseek.com/chat/completions` | DeepSeek Chat Completions API URL |

### Usage

Point Codex to the same proxy URL:
```json
"OPENAI_BASE_URL": "http://localhost:16889"
```

The proxy auto-detects Responses API requests (`/v1/responses`) and applies the appropriate translation. All existing Anthropic API proxy features remain unchanged.
```

---

### `README.zh-CN.md` (doc, n/a - MODIFIED)

**Analog:** Self (existing file, should mirror English README's Codex Support section)

Same structure as English README, translated to Chinese.

---

### `CHANGELOG.md` (doc, n/a - MODIFIED)

**Analog:** Self (existing file, append [2.0.0] entry at top following existing format)

**Entry pattern** (follow existing [1.8.0] format at lines 16-43):
```markdown
## [2.0.0] - 2026-06-07

### Added
- Codex 子包（config.py / translate.py / tools.py / sse.py）— OpenAI Responses API 协议翻译
- proxy Codex handler（/v1/responses 和 /v1/responses/compact 路由）
- E2E 集成测试（tests/test_e2e.py）
- __main__.py CLI 测试（tests/test_main.py）
- 技术文档 docs/dev/codex-integration.md
- CI 覆盖率徽章生成
- PyPI OIDC Trusted Publishing 发布
- Docker semver sha 标签

### Changed
- 版本升至 2.0.0（Codex 双协议支持 — MAJOR 版本）
- README / README.zh-CN.md 增加 Codex Support 章节
- CI 全面运行 `pytest tests/ -v`（全量测试）
- CI 中 PyPI 发布从 API token 切换为 OIDC
- 测试重构消除冗余，改善组织
```

## Shared Patterns

### Pure Function Unit Testing (AAA)
**Source:** `tests/test_proxy.py` lines 19-232
**Apply to:** `tests/test_proxy.py` additions, `tests/test_main.py`
```python
# Pattern: Arrange-Act-Assert with clear sections
def test_something():
    # Arrange
    data = {...}
    # Act
    result = function_under_test(data)
    # Assert
    assert result == expected
```

### Async Handler Testing (TestClient + httpx mock)
**Source:** `tests/test_responses.py` lines 19-70
**Apply to:** `tests/test_e2e.py`, `tests/test_responses.py` additions
```python
# Fixture
@pytest.fixture
def client():
    return TestClient(create_app())

# Mock helper
class _MockJSONResponse:
    def __init__(self, status_code=200, json_data=None, content=None):
        self.status_code = status_code
        self._json = json_data
        self.content = content or json.dumps(json_data or {}).encode("utf-8")
        self.headers = httpx.Headers({"content-type": "application/json"})
    def json(self):
        return self._json
    async def aclose(self):
        pass

def _make_mock_client(mock_response):
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.build_request.return_value = MagicMock(spec=httpx.Request)
    mock_client.send.return_value = mock_response
    return mock_client

# Test class pattern
class TestFeature:
    def test_case(self, client):
        mock_resp = _MockJSONResponse(status_code=200, json_data={...})
        with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
            mock_get_client.return_value = _make_mock_client(mock_resp)
            resp = client.post("/v1/responses", json={...})
        assert resp.status_code == 200
```

### CLI Testing (monkeypatch + tmp_path)
**Source:** RESEARCH.md lines 307-322 (no direct project analog; recommended pattern)
**Apply to:** `tests/test_main.py`
```python
def test_main_stop_normal(monkeypatch, tmp_path):
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    pidfile.write_text("99999")
    monkeypatch.setattr("sys.argv", ["dsv4-cc-proxy", "--stop", f"--pidfile={pidfile}"])
    with patch("dsv4_cc_proxy.__main__.os.kill") as mock_kill:
        from dsv4_cc_proxy.__main__ import main
        main()
        mock_kill.assert_called_once_with(99999, signal.SIGTERM)
    assert not pidfile.exists()
```

### Environment Variable Testing (monkeypatch + reload)
**Source:** `tests/test_codex.py` lines 14-22
**Apply to:** `tests/test_main.py` (if testing CODEX env vars indirectly)
```python
def test_something(monkeypatch):
    monkeypatch.setenv("VAR_NAME", "value")
    from importlib import reload
    import module
    reload(module)
    assert module.some_value == expected
```

### Test Class Organization
**Source:** `tests/test_responses.py` lines 76-420
**Apply to:** `tests/test_e2e.py`, `tests/test_responses.py` additions
- One class per logical path: `TestCompact`, `TestInvalidInput`, `TestNonStream`, `TestStream`, `TestAuthPassthrough`, `TestUpstreamError`, `TestStreamError`, `TestTranslateChatToResponses`
- All test methods in a class use `self` for shared constants (e.g., `self._MINIMAL_STREAM_CHUNKS`)
- Module-level helper functions for mock utilities

### SSE Lifecycle Event Sequence Translation
**Source:** `tests/test_sse.py` lines 327-347
**Apply to:** `tests/test_e2e.py` SSE tests
```python
# Strict event order verification
expected_sequence = [
    "response.created",
    "response.in_progress",
    "response.output_item.added",
    "response.output_text.delta",
    ...
    "response.completed",
]
assert len(events) == len(expected_sequence)
for i, expected_event in enumerate(expected_sequence):
    assert events[i]["event"] == expected_event
```

### Documentation Structure (Frontmatter + Sections)
**Source:** `docs/dev/deepseek-thinking-proxy.md` lines 1-150
**Apply to:** `docs/dev/codex-integration.md`
- YAML frontmatter with title/type/category/tags/created/updated
- Overview section (problem + solution)
- Architecture diagram (ASCII art)
- Environment variables table
- Logic flow / processing pipeline
- Performance characteristics
- Health check
- Troubleshooting
- Version history table

### CI Version Extraction from Tag
**Source:** `.github/workflows/ci.yml` lines 88-90
**Apply to:** Any new CI publish steps
```yaml
- name: Extract version from tag
  id: tag
  run: echo "VERSION=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"
```

### PyPI OIDC Publish
**Source:** `.github/workflows/ci.yml` lines 98-106 (current), lines 103-104 (updated pattern — remove `password:`)
**Apply to:** publish job in ci.yml
```yaml
    # Permissions section needs: id-token: write
    - name: Publish to PyPI
      uses: pypa/gh-action-pypi-publish@release/v1
      with:
        print-hash: true
      # OIDC: no password needed; id-token: write handles auth
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/test_main.py` | test | request-response | No existing CLI `__main__.py` tests in project. Testing pattern from RESEARCH.md (`monkeypatch.setattr("sys.argv", ...)`) — no project internal analog exists. |

## Metadata

**Analog search scope:** `tests/`, `docs/dev/`, `.github/workflows/`, `dsv4_cc_proxy/`
**Files scanned:** 9 (test_proxy.py, test_responses.py, test_codex.py, test_sse.py, test_translate.py, test_tools.py, deepseek-thinking-proxy.md, ci.yml, __main__.py)
**Pattern extraction date:** 2026-06-07
