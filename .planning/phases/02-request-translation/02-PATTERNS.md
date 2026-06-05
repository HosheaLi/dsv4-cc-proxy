# Phase 2: Request Translation - Pattern Map

**Mapped:** 2026-06-05
**Files analyzed:** 3 (2 new, 1 modify)
**Analogs found:** 3 / 3

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `dsv4_cc_proxy/codex/translate.py` | service/utility | transform | `dsv4_cc_proxy/codex/config.py` | exact (same role, same subpackage, same data flow) |
| `dsv4_cc_proxy/codex/__init__.py` | config/module | export | `dsv4_cc_proxy/codex/__init__.py` | exact (same file, add export) |
| `tests/test_translate.py` | test | unit test | `tests/test_codex.py` | exact (same codex module test patterns) |

## Pattern Assignments

### `dsv4_cc_proxy/codex/translate.py` (service/utility, transform)

**Analog:** `dsv4_cc_proxy/codex/config.py` (primary) + `dsv4_cc_proxy/proxy.py` (secondary for `_` helpers)

**Imports pattern** (lines 1-17 of config.py, proxy.py):
```python
# dsv4-cc-proxy / codex — Response → Chat 请求翻译
#
# translate_request() 将 OpenAI Responses API 请求体翻译为
# DeepSeek Chat Completions 请求体格式。
#
# 环境变量: (无 — 不使用 env var)

from __future__ import annotations

import copy
import json
import logging

from dsv4_cc_proxy.codex.config import CODEX_UPSTREAM

logger = logging.getLogger("deepseek-proxy")
```
- `from __future__ import annotations` always first (config.py line 13, proxy.py line 15)
- stdlib imports in alpha order (config.py lines 15-17, proxy.py lines 17-22)
- `logging.getLogger("deepseek-proxy")` — project-wide logger name (config.py line 19, proxy.py line 71)
- Only imports needed: `copy` (deepcopy), `json` (serialization), `logging`, and `CODEX_UPSTREAM` from sibling config module

**Logger pattern** (config.py line 19):
```python
logger = logging.getLogger("deepseek-proxy")
```
- Placed directly after imports, before config/function definitions
- Same logger name used throughout project (proxy.py line 71 also uses `"deepseek-proxy"`)

**Public function export pattern (entry point)** (config.py lines 52-54):
```python
def translate_request(request_body: dict) -> dict:
    """将 Responses API 请求体翻译为 Chat Completions 请求体。

    Args:
        request_body: Responses API 请求字典（不会被修改）。

    Returns:
        翻译后的 Chat Completions 请求字典。

    处理步骤:
    1. 深拷贝输入
    2. 提取 instructions + developer role 消息合并为 system 消息
    3. 翻译 input[] 数组中的每个 item:
       - message → 按 role 映射
       - function_call → 附加到前一条 assistant 的 tool_calls
       - function_call_output → tool role 消息
       - reasoning → 折叠到下一个 assistant 的 reasoning_content
       - 未知类型 → WARNING + 跳过
    4. Post-process: 检查所有 assistant 消息，有 tool_calls 缺
       reasoning_content 时注入空字符串
    5. 设置 model 字段 (调用 resolve_model)
    """
    body = copy.deepcopy(request_body)
    # ... translation logic ...
    return result
```
- Pure function: inputs never mutated (D-03), deep copy at entry
- Signature with type hint (config.py line 52: `def resolve_model(model_name: str) -> str:`)
- Docstring explaining args, returns, and processing steps (config.py lines 53-60)
- Returns brand new dict — no side effects

**Internal helper pattern (`_` prefix)** (config.py lines 31-46, proxy.py lines 103-107):
```python
def _merge_system_messages(
    instructions: str | None,
    developer_messages: list[dict],
) -> dict | None:
    """合并 instructions 和 developer role 消息为 system 消息。

    如果两者皆空则返回 None。非空时用 \n\n 连接各部分。
    """
    parts = []
    if instructions:
        parts.append(instructions)
    for msg in developer_messages:
        content = _extract_content_text(msg.get("content"))
        if content:
            parts.append(content)
    if not parts:
        return None
    return {"role": "system", "content": "\n\n".join(parts)}
```
- All internal helpers use `_` prefix (config.py: `_parse_model_map`; proxy.py: `_inject_thinking_blocks`, `_filter_sse_line`)
- Single responsibility per helper

**Unknown type handling pattern (WARNING + skip)** (config.py lines 41-46):
```python
def _translate_input_item(item: dict, ...) -> ...:
    """翻译单个 input item。"""
    item_type = item.get("type", "")
    if item_type == "message":
        return _translate_message_item(item, ...)
    elif item_type == "function_call":
        return _attach_tool_calls(item, ...)
    elif item_type == "function_call_output":
        return _translate_function_call_output(item, ...)
    elif item_type == "reasoning":
        return _fold_reasoning(item, ...)
    else:
        logger.warning("[CODEX] unknown input item type: %s, skipping", item_type)
        return None  # caller skips None returns
```
- Uses `logger.warning` (config.py lines 41, 45)
- Uses `[CODEX]` prefix for module-scoped log messages (config.py lines 41, 45, 67, 79, 83)
- Never raises for unknown types (D-08) — returns sentinel, caller collects results with filter

**Content extraction helper** (cited in RESEARCH.md as needed):
```python
def _extract_content_text(content: str | list | None) -> str | None:
    """从 content 字段提取文本。
    
    支持:
    - 字符串 → 直接返回
    - 数组 → 提取所有 type: "input_text" 的 text，用 \n 拼接
    - None → 返回 None
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and block.get("type") == "input_text"
        ]
        return "\n".join(texts) if texts else None
    return None  # 意外类型返回 None 而非崩溃
```
- Guards against unexpected types by returning `None` (matching config.py's defensive `isinstance` checks)
- `isinstance` checks preferred over duck typing (proxy.py lines 104-106, 118, 121, 124, 132, 134, 150-151)
- Dictionary `.get()` with defaults (proxy.py lines 103, 110, 118, 129, 133, 150, 159)

**Post-processing: ensure reasoning_content on assistant with tool_calls** (D-11):
```python
def _ensure_reasoning_content(messages: list[dict]) -> None:
    """后处理：检查所有 assistant 消息，有 tool_calls 但缺 reasoning_content 时注入空字符串。"""
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        if "tool_calls" in msg and "reasoning_content" not in msg:
            msg["reasoning_content"] = ""
            logger.debug("[CODEX] injected reasoning_content: '' on assistant with tool_calls")
```
- Mutates the internal messages list (already deep-copied, safe to modify)
- Follows same pattern as `_inject_thinking_blocks` (proxy.py lines 128-140) which iterates and mutates messages
- Uses `logger.debug` for verbose operations (config.py lines 67, 79, 83)

---

### `dsv4_cc_proxy/codex/__init__.py` (config/module, export)

**Analog:** `dsv4_cc_proxy/codex/__init__.py` (existing, modify)

**Current content** (lines 1-5):
```python
# dsv4-cc-proxy / codex — Codex CLI 协议翻译子包

from dsv4_cc_proxy.codex.config import resolve_model

__all__ = ["resolve_model"]
```

**After modification** (add translate_request to exports):
```python
# dsv4-cc-proxy / codex — Codex CLI 协议翻译子包

from dsv4_cc_proxy.codex.config import resolve_model
from dsv4_cc_proxy.codex.translate import translate_request

__all__ = ["resolve_model", "translate_request"]
```
- import order: sibling modules in alpha order (config before translate)
- `__all__` lists all public names (sorted alpha)
- Each public function imported individually by name (no star imports)

---

### `tests/test_translate.py` (test, unit test)

**Analog:** `tests/test_codex.py` (primary) + `tests/test_proxy.py` (secondary)

**Imports and module docstring pattern** (test_codex.py lines 1-11):
```python
"""dsv4-cc-proxy codex translate 单元测试。

覆盖: instruction/developer 合并、input item 类型分发、content 提取、
      function_call 到 tool_calls 附加、reasoning 折叠、空字符串注入。
运行: python3 -m pytest tests/test_translate.py -v
"""

import copy
import json
from importlib import reload

import dsv4_cc_proxy.codex.translate as codex_translate
```
- Module docstring with coverage summary and run command (same as test_codex.py lines 1-5, test_proxy.py lines 1-4)
- stdlib imports first in alpha order, then project imports
- Import translate module as alias (test_codex.py uses `codex_config` alias)

**Test structure: AAA pattern with monkeypatch** (test_codex.py lines 13-22):
```python
def test_simple_user_message(monkeypatch):
    """测试简单用户消息翻译。"""
    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Hello, how are you?"}
        ],
        "instructions": "You are a helpful assistant.",
    }
    result = codex_translate.translate_request(body)
    assert result["messages"][0] == {
        "role": "system", "content": "You are a helpful assistant.",
    }
    assert result["messages"][1] == {
        "role": "user", "content": "Hello, how are you?",
    }
    assert result["model"] is not None
```
- One assertion per meaningful check, but grouped logically in a single test
- No pytest fixtures or mocks — pure functions tested directly (test_codex.py and test_proxy.py both follow this)
- Test name: `test_` prefix + snake_case description of scenario (test_codex.py: `test_exact_match_overrides_prefix`)

**Test for immutable input** (following proxy.py's data_copy pattern, test_proxy.py lines 86-88):
```python
def test_translate_request_immutable(monkeypatch):
    """验证 translate_request 不修改输入。"""
    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Hello"},
            {"type": "function_call", "id": "call_1", "name": "Bash",
             "arguments": "{}", "status": "completed"},
        ],
        "instructions": "Be helpful.",
    }
    body_copy = copy.deepcopy(body)
    codex_translate.translate_request(body)
    assert body == body_copy
```
- `copy.deepcopy` for input snapshot comparison (same pattern as test_proxy.py lines 86-88)
- No module-level env vars needed for core translate function (no monkeypatch needed for most tests)

**Test for env-var-dependent behavior** (using monkeypatch + reload, test_codex.py lines 13-21):
```python
def test_model_resolved_via_config(monkeypatch):
    """验证 model 字段通过 resolve_model() 解析。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", json.dumps({
        "gpt-5.3-codex": "deepseek-v4-pro",
    }))
    reload(codex_translate)
    body = {
        "model": "gpt-5.3-codex",
        "input": [{"role": "user", "content": "Hi"}],
    }
    result = codex_translate.translate_request(body)
    assert result["model"] == "deepseek-v4-pro"
```
- `monkeypatch.setenv` + `reload(module)` for env var configuration (test_codex.py pattern)
- `reload` from `importlib` (test_codex.py line 8)

**Test for function_call + synthetic assistant** (test_proxy.py's data construction pattern):
```python
def test_synthetic_assistant_when_no_preceding(monkeypatch):
    """function_call 前无 assistant 消息时创建合成 assistant。"""
    body = {
        "input": [
            {"role": "user", "content": "Read file"},
            {"type": "function_call", "id": "call_1", "name": "Bash",
             "arguments": '{"cmd": "ls"}', "status": "completed"},
        ],
    }
    result = codex_translate.translate_request(body)
    messages = result["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] is None
    assert len(messages[1]["tool_calls"]) == 1
    assert messages[1]["tool_calls"][0]["id"] == "call_1"
```
- Inline dict construction for test data (test_proxy.py lines 38-43, 60-67)
- Assert on specific fields rather than full dict equality for complex structures

---

## Shared Patterns

### Pure Function Invariant
**Source:** `dsv4_cc_proxy/codex/config.py` (line 52), `dsv4_cc_proxy/proxy.py` (lines 103-140, 146-183, 197-221)
**Apply to:** `dsv4_cc_proxy/codex/translate.py` (all functions)
```python
# All module-level functions are pure: no side effects, no state mutation.
# translate_request() additionally deep-copies inputs to guarantee immutability:
body = copy.deepcopy(request_body)
```

### `_` Prefix Convention for Internal Helpers
**Source:** `dsv4_cc_proxy/proxy.py` lines 103 (`_has_tool_use`), 109 (`_has_thinking`), 116 (`_inject_thinking_blocks`), 146 (`_normalize_thinking`), 189 (`_thinking_requested`), 197 (`_filter_sse_line`); `dsv4_cc_proxy/codex/config.py` line 31 (`_parse_model_map`)
**Apply to:** `dsv4_cc_proxy/codex/translate.py` (all internal helpers: `_merge_system_messages`, `_translate_input_items`, `_extract_content_text`, `_attach_tool_calls`, `_fold_reasoning`, `_ensure_reasoning_content`)
```python
# Convention: single underscore prefix for module-private functions.
# Only translate_request() is exported (no underscore).
def _merge_system_messages(...): ...
def _translate_input_items(...): ...
# def translate_request(...): ...  # <-- exported, no underscore
```

### Logger Convention
**Source:** `dsv4_cc_proxy/codex/config.py` line 19, `dsv4_cc_proxy/proxy.py` line 71
**Apply to:** `dsv4_cc_proxy/codex/translate.py`
```python
logger = logging.getLogger("deepseek-proxy")
# Log levels: debug for verbose operations, warning for skipped/unknown items,
# info for structural changes.
logger.debug("[CODEX] ...")   # fine-grained trace
logger.warning("[CODEX] ...") # recoverable issues (unknown types, anomalous sequences)
```

### Module-Level Documentation Header
**Source:** `dsv4_cc_proxy/codex/config.py` lines 1-11, `dsv4_cc_proxy/proxy.py` lines 1-14
**Apply to:** `dsv4_cc_proxy/codex/translate.py` and `tests/test_translate.py`
```python
# dsv4-cc-proxy / codex — <module purpose description>
#
# <what this module does, brief>
# <any env vars used (or "none" if none)>
# <special notes>
```

### Guard Clauses with `isinstance` Checks
**Source:** `dsv4_cc_proxy/proxy.py` lines 104-106, 118, 121, 124, 132, 134, 150-151
**Apply to:** `dsv4_cc_proxy/codex/translate.py` (content extraction, item type dispatch)
```python
# Use isinstance() for type guards, not try/except for type mismatches
if not isinstance(content, list):
    return content
```

### JSON Serialization: `ensure_ascii=False`
**Source:** `dsv4_cc_proxy/proxy.py` line 235, `dsv4_cc_proxy/proxy.py` line 235, `dsv4_cc_proxy/proxy.py` line 311
**Apply to:** `dsv4_cc_proxy/codex/translate.py` (if internal JSON operations needed)
```python
json.dumps(data, ensure_ascii=False)  # preserve non-ASCII characters
```

## No Analog Found

All files in Phase 2 have exact analogs. No file requires planner to fall back to RESEARCH.md patterns.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | All 3 files have exact or role-match analogs |

## Metadata

**Analog search scope:** `dsv4_cc_proxy/` (6 Python files), `tests/` (2 test files)
**Files scanned:** 8 source/test files
**Pattern extraction date:** 2026-06-05
