# Phase 3: Tool Support - Pattern Map

**Mapped:** 2026-06-06
**Files analyzed:** 4 (2 new, 2 modified)
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `dsv4_cc_proxy/codex/tools.py` (NEW) | utility | transform | `dsv4_cc_proxy/codex/config.py` | exact (same role, same subpackage, pure-function pattern) |
| `dsv4_cc_proxy/codex/__init__.py` (MODIFIED) | utility | N/A | current `dsv4_cc_proxy/codex/__init__.py` | exact (direct extension) |
| `dsv4_cc_proxy/codex/translate.py` (MODIFIED) | service | transform | current `dsv4_cc_proxy/codex/translate.py` | exact (one-line addition to existing function) |
| `tests/test_tools.py` (NEW) | test | N/A | `tests/test_translate.py` | exact (same subpackage, same AAA test structure) |

## Pattern Assignments

### `dsv4_cc_proxy/codex/tools.py` (utility, transform)

**Analog:** `dsv4_cc_proxy/codex/config.py` (primary, for module structure), `dsv4_cc_proxy/codex/translate.py` (secondary, for logging and `_` prefix style)

**Imports pattern** (config.py lines 13-20):
```python
from __future__ import annotations

import copy
import json
import logging

logger = logging.getLogger("deepseek-proxy")
```

Notes:
- `from __future__ import annotations` — must be first import (config.py L13, translate.py L16)
- `copy` — needed for deepcopy wrapping (translate.py L18)
- `json` — needed only if logging JSON content; for tools.py may be omitted if only dict operations
- `logging` — consistent `logger = logging.getLogger("deepseek-proxy")` (config.py L19, translate.py L24, proxy.py L71)

**Module docstring pattern** (translate.py lines 1-14):
```python
# dsv4-cc-proxy / codex — 工具定义格式转换
#
# convert_tools() 将 OpenAI Responses API 扁平工具格式转换为
# DeepSeek Chat Completions 嵌套格式，并递归剥离不兼容 JSON Schema 字段。
#
# 环境变量: (无 — 纯函数，无外部依赖)
#
# 职责:
#   - 扁平 → 嵌套格式转换: {type, name, description, parameters}
#     → {type, function: {name, description, parameters}} (CODX-07)
#   - JSON Schema 递归清理: 剥离 default/readOnly/writeOnly/examples/
#     minLength/maxLength/minItems/maxItems, 移除空 enum 数组 (CODX-10)
```

Note: Use same level-1 comment block `# ` style as translate.py and config.py, not docstring `"""`.

**Internal function prefix pattern** (translate.py lines 30, 53, 73, 194):
```python
# ---- 内部辅助函数 ----

def _convert_tool_format(tool: dict) -> dict:
    """扁平工具格式 → 嵌套格式转换。"""
    ...

def _clean_schema(schema: dict) -> dict:
    """递归剥离 DeepSeek 不兼容的 JSON Schema 字段。"""
    ...
```

Note:
- Internal functions use `_` prefix (translate.py: `_extract_content_text`, `_merge_system_messages`, `_translate_input_items`, `_ensure_reasoning_content`)
- Section comments use `# ---- 描述 ----` between function groups (translate.py L27, L208)
- Docstring uses `"""..."""` with Chinese description

**WARNING logging pattern** (translate.py lines 88, 112, 171):
```python
logger.warning("[CODEX] unknown input item type: %s, skipping", item_type)
```

Example for tools.py:
```python
logger.warning("[CODEX] unknown tool type: %s, passing through", tool_type)
```

Notes:
- Prefix log messages with `[CODEX]` (translate.py L88, config.py L41)
- Use `%s` style format strings (not f-strings) — consistent with translate.py L88, L112, L171 and proxy.py L162
- DEBUG level for normal operations: `logger.debug(...)` (translate.py L183, L205, config.py L67)
- WARNING level for unexpected but recoverable cases

**Single public function export pattern** (config.py lines 49-84):
```python
# ---- 公开 API ----


def convert_tools(tools: list[dict]) -> list[dict]:
    """Responses API 工具列表 → DeepSeek Chat 兼容格式。

    Pure function: 不修改输入（deepcopy 保护）。

    Args:
        tools: 工具定义字典列表（不会被修改）。

    Returns:
        格式转换 + schema 清理后的工具定义列表。

    处理步骤:
    1. 深拷贝输入
    2. 对每个工具调用 _convert_tool_format()
    3. 若有 parameters，调用 _clean_schema()
    4. 返回全部 tools 列表
    """
    body = copy.deepcopy(tools)
    ...
    return body
```

Notes:
- Single public function per module (config.py has `resolve_model`, translate.py has `translate_request`)
- Pure function pattern: `copy.deepcopy(tools)` protects input immutability (translate.py L242)
- Null-safe iteration: tools can be None, empty list, or absent from body — guard accordingly

**Existing tool interaction patterns in `_translate_input_items`** (translate.py lines 115-141):
```python
# ---- function_call type ----
elif item_type == "function_call":
    tool_entry = {
        "id": item["id"],
        "type": "function",
        "function": {
            "name": item["name"],
            "arguments": item["arguments"],
        },
    }
```

Note: This is the _message-level_ tool format (tool_call inside assistant message), distinct from the _tool-definition_ format in tools.py (tool array at request body top level). The nesting structure `{type, function: {name, ...}}` is shared but the field set differs.

---

### `dsv4_cc_proxy/codex/__init__.py` (modified, utility, N/A)

**Analog:** `dsv4_cc_proxy/codex/__init__.py` (current file)

**Current pattern** (lines 1-6):
```python
# dsv4-cc-proxy / codex — Codex CLI 协议翻译子包

from dsv4_cc_proxy.codex.config import resolve_model
from dsv4_cc_proxy.codex.translate import translate_request

__all__ = ["resolve_model", "translate_request"]
```

**Modified version** (add third export):
```python
# dsv4-cc-proxy / codex — Codex CLI 协议翻译子包

from dsv4_cc_proxy.codex.config import resolve_model
from dsv4_cc_proxy.codex.tools import convert_tools
from dsv4_cc_proxy.codex.translate import translate_request

__all__ = ["resolve_model", "convert_tools", "translate_request"]
```

Note:
- Import order: config → tools → translate (alphabetical by module name)
- `__all__` list maintains same ordering as imports

---

### `dsv4_cc_proxy/codex/translate.py` (modified, service, transform)

**Analog:** Current `dsv4_cc_proxy/codex/translate.py` (self-modification)

**Changes needed:**
1. Add import: `from dsv4_cc_proxy.codex.tools import convert_tools` (between config import and logger, line 22)
2. Add `convert_tools()` call inside `translate_request()` body, after line 281 (`body.pop("include", None)`) and before line 283 (`body["messages"] = messages`):

```python
# 8. 工具定义格式转换 (Phase 3, CODX-07, CODX-10)
if "tools" in body:
    body["tools"] = convert_tools(body["tools"])
```

**Placement logic:**
- After removing Responses-only fields (line 281: `body.pop("include", None)`) — because tools translation doesn't depend on include
- Before setting messages (line 283: `body["messages"] = messages`) — because tools and messages are independent at this stage
- After model resolution (line 274) — tools format is model-agnostic

---

### `tests/test_tools.py` (new, test, N/A)

**Analog:** `tests/test_translate.py`

**Imports pattern** (test_translate.py lines 1-14):
```python
"""dsv4-cc-proxy codex 工具转换单元测试。

覆盖: 格式转换、schema 字段剥离、递归清理、边界情况。
运行: python3 -m pytest tests/test_tools.py -v
"""

import copy
import json

import dsv4_cc_proxy.codex.tools as codex_tools
```

Note:
- Module docstring uses `"""..."""` (not `#` comment block)
- Import the module under test as `codex_tools` following `codex_translate` / `codex_config` pattern
- `copy` needed for immutability tests (test_translate.py L520)

**Test grouping pattern** (test_translate.py lines 17-18):
```python
# =============================================================================
# 组 1: 格式转换
# =============================================================================
```

Use section separator comments (`# ====...====`) for clear test groups.

**AAA test pattern** (test_translate.py lines 22-35):
```python
def test_convert_flat_to_nested():
    """验证扁平 {type, name, desc, params} → 嵌套 {type, function: {name, desc, params}}。"""
    body = [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get current weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
            },
        }
    ]
    result = codex_tools.convert_tools(body)

    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert "function" in result[0]
    assert result[0]["function"]["name"] == "get_weather"
    assert result[0]["function"]["description"] == "Get current weather"
    assert "parameters" in result[0]["function"]
    assert "name" not in result[0]  # 扁平字段已移除
```

**Immutability test pattern** (test_translate.py lines 500-522):
```python
def test_convert_tools_immutable(monkeypatch):
    """验证 convert_tools 不修改输入列表。"""
    body = [
        {
            "type": "function",
            "name": "get_weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
            },
        }
    ]
    body_copy = copy.deepcopy(body)
    codex_tools.convert_tools(body)
    assert body == body_copy
```

Note: tools.py doesn't use env vars, so `monkeypatch` + `reload` pattern from test_translate.py is NOT needed. Tests can import and call directly.

**Test boundary pattern** (test_translate.py lines 99-108):
```python
def test_empty_tools():
    """验证空 tools 列表返回空列表。"""
    result = codex_tools.convert_tools([])
    assert result == []

def test_no_tools_field():
    """验证 body 中无 tools 字段时不调用 convert_tools。"""
    body = {"model": "test-model", "input": []}
    result = codex_translate.translate_request(body)
    assert "tools" not in result
```

---

## Shared Patterns

### `_` prefix for internal functions
**Source:** `dsv4_cc_proxy/codex/translate.py` (lines 30, 53, 73, 194), `dsv4_cc_proxy/codex/config.py` (line 31), `dsv4_cc_proxy/proxy.py` (lines 103, 109, 116, 146, 189, 197, 231, 243, 267, 277)
**Apply to:** All internal helper functions in tools.py

All private functions in the codebase use `_` prefix. No `__` double-underscore name mangling. No `def _inner()` closures unless needed for callbacks.

```python
def _convert_tool_format(tool: dict) -> dict:
    ...

def _clean_schema(schema: dict) -> dict:
    ...
```

### `copy.deepcopy` immutability protection
**Source:** `dsv4_cc_proxy/codex/translate.py` (line 242: `body = copy.deepcopy(request_body)`)
**Apply to:** `convert_tools()` — always deepcopy the input before mutation

```python
def convert_tools(tools: list[dict]) -> list[dict]:
    result = copy.deepcopy(tools) if tools else []
    for tool in result:
        ...
    return result
```

### WARNING logging for edge cases
**Source:** `dsv4_cc_proxy/codex/translate.py` (lines 88, 112, 171), `dsv4_cc_proxy/codex/config.py` (lines 41, 45)
**Apply to:** Unknown tool types, invalid schema, anomalous cases

```python
logger.warning("[CODEX] unknown tool type: %s, passing through", tool_type)
logger.warning("[CODEX] invalid tool parameters schema: %s", tool.get("name", "?"))
```

Note: Use `%s` style with separate args (not f-strings) — consistent across translate.py, config.py, proxy.py.

### Module section comments
**Source:** `dsv4_cc_proxy/codex/translate.py` (lines 27, 208), `dsv4_cc_proxy/codex/config.py` (lines 21, 28, 49)
**Apply to:** Separating internal helpers, public API

```python
# ---- 内部辅助函数 ----
...

# ---- 公开 API ----
```

### Recursive dict traversal pattern
**Source:** `dsv4_cc_proxy/codex/translate.py` (`_extract_content_text` lines 30-50 — list traversal, though not recursive)
**Apply to:** `_clean_schema()` — recursive dict traversal for schema nesting

The project has no existing recursive dict traversal example in the codex subpackage. Reference the RESEARCH.md recommended implementation:

```python
REMOVED_KEYS = frozenset({
    "default", "readOnly", "writeOnly", "examples",
    "minLength", "maxLength", "minItems", "maxItems",
})

def _clean_schema(schema: dict) -> dict:
    """Recursively strip DeepSeek-unsupported fields from a JSON Schema dict."""
    for key in REMOVED_KEYS:
        schema.pop(key, None)

    if "enum" in schema and isinstance(schema["enum"], list) and len(schema["enum"]) == 0:
        del schema["enum"]

    for path in ("properties", "$defs"):
        if path in schema and isinstance(schema[path], dict):
            for sub_schema in schema[path].values():
                if isinstance(sub_schema, dict):
                    _clean_schema(sub_schema)

    if "anyOf" in schema and isinstance(schema["anyOf"], list):
        for item in schema["anyOf"]:
            if isinstance(item, dict):
                _clean_schema(item)

    if "items" in schema and isinstance(schema["items"], dict):
        _clean_schema(schema["items"])

    return schema
```

Note: This pattern mutates schema in-place for efficiency (caller uses deepcopy'd data).

### Exceptions for invalid data
**Source:** No existing pattern in codex subpackage (translate.py and config.py handle errors via WARNING + graceful degradation)
**Apply to:** D-07 requires raising explicit exceptions for invalid schema, not silent pass-through

```python
if not isinstance(parameters, dict):
    raise ValueError(f"Invalid tool parameters schema for '{tool_name}': expected dict, got {type(parameters).__name__}")
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| None | — | — | All 4 files have exact or role-match analogs in the existing codebase |

## Metadata

**Analog search scope:** `dsv4_cc_proxy/codex/` (3 files), `dsv4_cc_proxy/proxy.py`, `tests/` (3 files)
**Files scanned:** 6 Python files
**Pattern extraction date:** 2026-06-06
