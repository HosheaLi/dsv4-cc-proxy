# Phase 4: SSE State Machine - Pattern Map

**Mapped:** 2026-06-06
**Files analyzed:** 5 (2 new, 3 modified)
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `dsv4_cc_proxy/codex/sse.py` | utility/translator | streaming | `dsv4_cc_proxy/proxy.py` `filtered_stream()` | exact |
| `dsv4_cc_proxy/codex/__init__.py` | config/export | N/A | current `codex/__init__.py` | exact |
| `dsv4_cc_proxy/codex/translate.py` | controller/translator | CRUD (request body) | current `codex/translate.py` | exact |
| `tests/test_sse.py` | test | streaming | `tests/test_proxy.py` | role-match |
| `tests/test_translate.py` | test | CRUD | current `test_translate.py` | exact |

---

## Pattern Assignments

### `dsv4_cc_proxy/codex/sse.py` (utility/translator, streaming)

**Analog:** `dsv4_cc_proxy/proxy.py` `filtered_stream()` (lines 357-405)

**Imports pattern** (from `proxy.py` lines 1-23 + `codex/translate.py` lines 14-25):
```python
# Source: dsv4_cc_proxy/codex/translate.py lines 14-25
from __future__ import annotations

import json
import logging
from uuid import uuid4

logger = logging.getLogger("deepseek-proxy")
```
- 使用 `from __future__ import annotations`（全 codex 子包统一）
- logger 名称用 `"deepseek-proxy"`（全项目统一）
- 新增 `from uuid import uuid4` 用于生成 response id

**Async generator pattern** (from `proxy.py` lines 357-405):
```python
# Source: dsv4_cc_proxy/proxy.py filtered_stream() lines 357-383
async def filtered_stream():
    thinking_indices = set()
    buffer = ""

    try:
        async for chunk in upstream_resp.aiter_bytes():
            text = chunk.decode("utf-8", errors="replace")
            buffer += text

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                filtered, thinking_indices = _filter_sse_line(line, thinking_indices)
                if filtered is not None:
                    yield (filtered + "\n").encode("utf-8")

        if buffer.strip():
            filtered, thinking_indices = _filter_sse_line(buffer, thinking_indices)
            if filtered is not None:
                yield (filtered + "\n").encode("utf-8")
    except Exception:
        logger.exception("upstream stream read error")
```
Key patterns to copy:
- Local variable state tracking (`thinking_indices = set()` → `active_tool_indices: set[int] = set()`)
- `try/except` wrapping the entire `async for` loop
- `logger.exception()` in the except block — logs full traceback
- `async for` + `yield` generator shape

**`_` prefix internal helpers** (from `proxy.py` lines 197-221):
```python
# Source: dsv4_cc_proxy/proxy.py _filter_sse_line() lines 197-221
def _filter_sse_line(line: str, thinking_indices: set) -> tuple:
    if not line.startswith("data: "):
        return line, thinking_indices

    try:
        data = json.loads(line[6:])
    except json.JSONDecodeError:
        return line, thinking_indices

    t = data.get("type", "")

    if t == "content_block_start":
        cb = data.get("content_block", {})
        if cb.get("type") == "thinking":
            thinking_indices.add(data["index"])
            return None, thinking_indices
    # ...
    return line, thinking_indices
```
Key patterns:
- Return `(result, updated_state)` tuples from internal helpers
- `json.loads()` within try/except with `json.JSONDecodeError`
- Set tracking returned and reassigned by caller

**Pure function + no class** (from `codex/tools.py` lines 105-160):
```python
# Source: dsv4_cc_proxy/codex/tools.py convert_tools() lines 105-127
def convert_tools(tools: list[dict]) -> list[dict]:
    """Responses API 工具列表 → DeepSeek Chat 兼容格式。

    Pure function: 不修改输入（deepcopy 保护）。

    Args:
        tools: 工具定义字典列表（不会被修改）。

    Returns:
        格式转换 + schema 清理后的工具定义列表。
    """
    if not tools:
        return []

    result = copy.deepcopy(tools)
    # ...
    return result
```
Key patterns:
- No class definitions in codex/ subpackage
- Pure functions only (no side effects beyond logging)

**`[CODEX]` logging prefix** (from `codex/translate.py` line 25):
```python
logger = logging.getLogger("deepseek-proxy")
# Usage: logger.info("[CODEX] SSE stream translation starting")
logger.info("[CODEX] SSE stream translation starting")
```

**Shared cross-cutting pattern: SSE event builder** (from RESEARCH.md section 3, inferable from D-12):
```python
def _build_sse_event(event_type: str, data: dict) -> str:
    """构建完整 SSE 事件行（含 event: 前缀 + data: JSON + 空行终止）。"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```
- `ensure_ascii=False` preserves Unicode (consistent with proxy.py's `_dump_json`)
- Double `\n\n` terminates each event per SSE spec

---

### `dsv4_cc_proxy/codex/__init__.py` (config/export, N/A)

**Analog:** Current `codex/__init__.py` lines 1-7

**Export pattern** (from current `__init__.py` lines 3-7):
```python
# Source: dsv4_cc_proxy/codex/__init__.py lines 3-7
from dsv4_cc_proxy.codex.config import resolve_model
from dsv4_cc_proxy.codex.tools import convert_tools
from dsv4_cc_proxy.codex.translate import translate_request

__all__ = ["convert_tools", "resolve_model", "translate_request"]
```

**Modification:** Add the new `translate_sse_stream` import to match:
```python
from dsv4_cc_proxy.codex.sse import translate_sse_stream

__all__ = ["convert_tools", "resolve_model", "translate_request", "translate_sse_stream"]
```

---

### `dsv4_cc_proxy/codex/translate.py` (controller/translator, CRUD)

**Analog:** Current `translate.py` itself

**Core pattern for reasoning.effort mapping** (insert after line 243 `body = copy.deepcopy(request_body)`):

The existing `translate_request()` function at lines 212-291 shows the pattern for request body modification. The reasoning.effort mapping follows the same deepcopy-safe pattern:

```python
# Source: dsv4_cc_proxy/codex/translate.py lines 212-243 (existing skeleton)
def translate_request(request_body: dict) -> dict:
    """将 Responses API 请求体翻译为 Chat Completions 请求体。

    Pure function: 不修改输入（deepcopy 保护）。
    """
    body = copy.deepcopy(request_body)

    # D-10: reasoning.effort → thinking mapping (NEW)
    reasoning = body.get("reasoning", {})
    if isinstance(reasoning, dict) and reasoning.get("effort") in ("low", "medium", "high"):
        body["thinking"] = {"type": "enabled"}
    # D-11: remove reasoning field after mapping
    body.pop("reasoning", None)

    # existing code continues...
```

Key patterns to follow:
- Modify `body` (deepcopy) not `request_body`
- Use `isinstance()` type guard before accessing dict entries
- Pop fields that are no longer needed

**Docstring convention** (from `translate.py` line 212-240):
```python
def translate_request(request_body: dict) -> dict:
    """将 Responses API 请求体翻译为 Chat Completions 请求体。

    Pure function: 不修改输入（deepcopy 保护）。
    返回全新字典。

    Args:
        request_body: Responses API 请求字典（不会被修改）。

    Returns:
        翻译后的 Chat Completions 请求字典。
    """
```
- `Args:` / `Returns:` sections
- First line is a Chinese description of the function

---

### `tests/test_sse.py` (test, streaming)

**Analog:** `tests/test_proxy.py` lines 151-224 (SSE filtering tests)

**Import pattern** (from `tests/test_proxy.py` lines 1-16):
```python
# Source: tests/test_proxy.py lines 7-16
"""dsv4-cc-proxy SSE state machine 单元测试。

覆盖: 基础文本流、推理流、工具调用流、类型转换、完整生命周期、边界情况。

运行: python3 -m pytest tests/test_sse.py -v
"""

import json

import pytest
from dsv4_cc_proxy.codex.sse import translate_sse_stream
```

**Async generator test pattern** (from `tests/test_translate.py` — synchronous, but for async generators, use pytest-asyncio or create a test helper):

For testing `translate_sse_stream` (an async generator), the pattern needs to use a sync wrapper. The following approach follows the project's existing testing style (no pytest-asyncio dependency):

```python
# Source: Pattern inferred from RESEARCH.md section 3.3 (新增 pattern, 非直接复制)
def _collect_events(chunks: list[dict]) -> list[str]:
    """Helper: drive async generator and collect events synchronously."""
    import asyncio

    async def _collect():
        events = []
        async for event in translate_sse_stream(chunks):
            events.append(event)
        return events
    return asyncio.run(_collect())
```

**AAA test pattern** (from `tests/test_proxy.py` lines 152-163 and `tests/test_translate.py` lines 22-36):

```python
# Source: tests/test_proxy.py _filter_sse_line tests (lines 158-163)
def test_filter_sse_passes_text():
    result, _ = _filter_sse_line(
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
        set()
    )
    assert result is not None
```

And from `tests/test_translate.py`:
```python
# Source: tests/test_translate.py test_simple_user_message (lines 22-35)
def test_simple_user_message():
    """验证简单用户消息 + instructions 翻译为 system + user 消息。"""
    body = {
        "model": "test-model",
        "input": [
            {"role": "user", "content": "Hello"}
        ],
        "instructions": "Be helpful.",
    }
    result = codex_translate.translate_request(body)

    assert len(result["messages"]) == 2
    assert result["messages"][0] == {"role": "system", "content": "Be helpful."}
    assert result["messages"][1] == {"role": "user", "content": "Hello"}
```

Key patterns:
- Docstring as the first line of the test function describing what it verifies
- Prepare input data as a local dict
- Call the function under test
- Assert on the output with multiple `assert` statements

---

### `tests/test_translate.py` (test, CRUD)

**Analog:** Current `test_translate.py` itself

**Test pattern for reasoning.effort mapping** (follows existing test structure from `test_translate.py` lines 394-417):

```python
# Source: tests/test_translate.py test_inject_reasoning_content (lines 394-417)
def test_inject_reasoning_content(monkeypatch):
    """验证有 tool_calls 的 assistant 自动注入 reasoning_content: '' (CODX-14, D-11)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [ ... ],
    }
    result = codex_translate.translate_request(body)
    assert ...
```

**New test function follows same shape:**
```python
# Source: Research D-10/D-11, follows _translate.py test convention
def test_reasoning_effort_mapping(monkeypatch):
    """验证 reasoning.effort → thinking 参数映射 (CODX-12, D-10, D-11)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "deepseek-v4-pro",
        "reasoning": {"effort": "high"},
        "input": [{"role": "user", "content": "Hello"}],
    }
    result = codex_translate.translate_request(body)

    assert result["thinking"] == {"type": "enabled"}
    assert "reasoning" not in result
```

Key patterns to copy:
- `monkeypatch.setenv()` + `reload(codex_translate)` at the top
- Docstring references requirement IDs (CODX-12)
- Assert on both the presence of new fields and absence of removed fields

---

## Shared Patterns

### 1. `_` Prefix Internal Helpers

**Source:** `dsv4_cc_proxy/proxy.py` `_filter_sse_line()` (line 197), `_inject_thinking_blocks()` (line 116), `_build_response_headers()` (line 267); `codex/translate.py` `_extract_content_text()` (line 31), `_merge_system_messages()` (line 54), `_translate_input_items()` (line 74); `codex/tools.py` `_convert_tool_format()` (line 34), `_clean_schema()` (line 64)

**Applies to:** `sse.py`

All internal helper functions in the codebase use the `_` prefix (Python convention for private). No double-underscore name mangling. This applies to all functions that are not part of the public API.

### 2. `logger.exception()` for Error Logging

**Source:** `dsv4_cc_proxy/proxy.py` lines 329, 345, 396

**Applies to:** `sse.py` `translate_sse_stream()` error handling

```python
# Source: proxy.py lines 395-396
except Exception:
    logger.exception("upstream stream read error")
```

- Always use `logger.exception()` in except blocks — it includes the full traceback
- Error message should describe the context ("what failed") not the error itself

### 3. f-string + `json.dumps()` for SSE Event Lines

**Source:** Research D-12, OpenAI Responses API spec

**Applies to:** `sse.py`

```python
# Source: Research code example (section 3.3)
f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

- `ensure_ascii=False` to preserve non-ASCII characters
- Double `\n\n` terminator required for SSE protocol

### 4. Docstring Convention

**Source:** `dsv4_cc_proxy/codex/translate.py` lines 212-240, `codex/tools.py` lines 106-121

**Applies to:** All files

```
First line: Chinese description of function purpose.
Blank line:
Pure function: 不修改输入（deepcopy 保护）。
Returns:
Args: sections when applicable.
```

### 5. Immutability via `copy.deepcopy()`

**Source:** `dsv4_cc_proxy/codex/translate.py` line 243, `codex/tools.py` line 126

**Applies to:** `sse.py` (if any input dict needs mutation safety), `translate.py` (already has it)

```python
# Source: codex/translate.py line 243
body = copy.deepcopy(request_body)
```

- `translate_request()` already uses deepcopy (line 243)
- `convert_tools()` already uses deepcopy (line 126)
- `sse.py` does not need deepcopy — it processes immutable dict chunks

### 6. Set-Based State Tracking

**Source:** `dsv4_cc_proxy/proxy.py` line 358

**Applies to:** `sse.py`

```python
# Source: proxy.py line 358
thinking_indices = set()
```

```python
# Source: sse.py (new code per D-07)
active_tool_indices: set[int] = set()
```

- Both use set to track active indices
- Set is a local variable in the async generator — fresh per invocation

### 7. `[CODEX]` Log Prefix

**Source:** `codex/translate.py` and `codex/tools.py`

**Applies to:** `sse.py`

All logging in codex/ subpackage uses the `[CODEX]` prefix to distinguish from proxy's `[INJECT]`, `[STRIP]`, `[RESP]` etc prefixes.

```python
logger.info("[CODEX] SSE stream translation starting")
```

### 8. `from __future__ import annotations`

**Source:** `codex/translate.py` line 16, `codex/tools.py` line 14

**Applies to:** `sse.py`

Every codex/ module starts with `from __future__ import annotations` for postponed evaluation of type annotations (Python 3.10+).

---

## No Analog Found

(none — all files have a close match in the existing codebase)

| File | Role | Data Flow | Analog | Match |
|------|------|-----------|--------|-------|
| `dsv4_cc_proxy/codex/sse.py` | utility/translator | streaming | `proxy.py filtered_stream()` | exact |
| `dsv4_cc_proxy/codex/__init__.py` | config/export | N/A | current `__init__.py` | exact |
| `dsv4_cc_proxy/codex/translate.py` | controller/translator | CRUD | current `translate.py` | exact |
| `tests/test_sse.py` | test | streaming | `tests/test_proxy.py` | role-match |
| `tests/test_translate.py` | test | CRUD | current `test_translate.py` | exact |

---

## Metadata

**Analog search scope:**
- `dsv4_cc_proxy/proxy.py` (434 lines) — core proxy with `filtered_stream()`, `_filter_sse_line()`, Set tracking
- `dsv4_cc_proxy/codex/translate.py` (292 lines) — request translation, `_` prefix helpers, `[CODEX]` logger
- `dsv4_cc_proxy/codex/tools.py` (161 lines) — tool format conversion, deepcopy, pure functions
- `dsv4_cc_proxy/codex/config.py` (85 lines) — config module, pure function + env var pattern
- `dsv4_cc_proxy/codex/__init__.py` (7 lines) — export pattern
- `tests/test_proxy.py` (233 lines) — SSE filtering tests
- `tests/test_translate.py` (563 lines, 23 tests) — codex translate tests
- `tests/test_tools.py` (306 lines, 21 tests) — codex tools tests
- `tests/test_codex.py` (73 lines, 7 tests) — codex config tests

**Files scanned:** 9
**Pattern extraction date:** 2026-06-06
