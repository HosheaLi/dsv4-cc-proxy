---
phase: 03-tool-support
reviewed: 2026-06-06T10:30:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - dsv4_cc_proxy/codex/__init__.py
  - dsv4_cc_proxy/codex/tools.py
  - dsv4_cc_proxy/codex/translate.py
  - tests/test_tools.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-06-06T10:30:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the Codex protocol translation subpackage (`dsv4_cc_proxy/codex/`) and its test suite (`tests/test_tools.py`). The codebase is well-structured with clear responsibilities separation between `tools.py` (format conversion), `translate.py` (request translation), and `config.py` (model mapping). The code uses pure-function patterns with deep-copy protection consistently. Two warnings were found: missing JSON Schema recursion paths for `allOf`/`oneOf` in `_clean_schema` could cause DeepSeek API rejection for tools using those constructs, and reasoning accumulation logic in `_translate_input_items` incorrectly associates all previous reasoning blocks with the last assistant message in multi-turn scenarios. No critical security issues were detected.

## Warnings

### WR-01: Missing `allOf` and `oneOf` recursion in `_clean_schema`

**File:** `dsv4_cc_proxy/codex/tools.py:64-99`
**Issue:** `_clean_schema` recursively handles `anyOf` (lines 90-93) but does not handle `allOf` or `oneOf`, which are standard JSON Schema keywords that can contain nested schemas with incompatible fields (`default`, `readOnly`, `writeOnly`, etc.). If a tool definition uses `allOf` or `oneOf`, nested incompatible fields will not be stripped, potentially causing DeepSeek API to reject the schema.

**Fix:** Add recursion for `allOf` and `oneOf` after the existing `anyOf` block at line 93:

```python
    # 5. 递归: anyOf
    if "anyOf" in schema and isinstance(schema["anyOf"], list):
        for item in schema["anyOf"]:
            if isinstance(item, dict):
                _clean_schema(item)

    # 6. 递归: allOf (missing)
    if "allOf" in schema and isinstance(schema["allOf"], list):
        for item in schema["allOf"]:
            if isinstance(item, dict):
                _clean_schema(item)

    # 7. 递归: oneOf (missing)
    if "oneOf" in schema and isinstance(schema["oneOf"], list):
        for item in schema["oneOf"]:
            if isinstance(item, dict):
                _clean_schema(item)

    # 8. 递归: items
    ...
```

**Also update the file-level docstring** (line 12) to mention `allOf`/`oneOf`.

---

### WR-02: All pending reasoning blocks injected only into last assistant message

**File:** `dsv4_cc_proxy/codex/translate.py:152-190`
**Issue:** `_translate_input_items` accumulates ALL reasoning blocks into a global `pending_reasoning` list during item processing (lines 166-168). At post-processing (lines 174-190), all accumulated reasoning is combined and folded into the LAST assistant message only. In multi-turn conversations where reasoning items appear before multiple different assistant messages, earlier reasoning blocks are incorrectly associated with later assistant responses and earlier reasoning is lost.

**Example problematic sequence:**
- user A → reasoning 1 → assistant A → user B → reasoning 2 → assistant B
- After processing: `messages = [userA, assistantA, userB, assistantB]`
- `pending_reasoning` = `["reasoning_1", "reasoning_2"]`
- Both folded into `assistantB` only; `assistantA` gets no `reasoning_content`

**Fix:** Instead of global accumulation with post-processing, fold `pending_reasoning` inline when an assistant message is encountered during item iteration. This ensures each reasoning block is associated with the immediately following assistant message:

```python
        elif role == "assistant":
            msg = {
                "role": "assistant",
                "content": _extract_content_text(item.get("content")),
            }
            # Inject pending reasoning before this assistant
            if pending_reasoning:
                msg["reasoning_content"] = "\n".join(pending_reasoning)
                pending_reasoning.clear()
            messages.append(msg)
```

Then the post-processing loop (lines 174-190) can be removed entirely, or kept only as a safety net for edge cases where `pending_reasoning` remains at the end.

---

## Info

### IN-01: Redundant conditional around `resolve_model` call

**File:** `dsv4_cc_proxy/codex/translate.py:275`

```python
body["model"] = resolve_model(original_model) if original_model else CODEX_DEFAULT_MODEL
```

The ternary is redundant because `resolve_model("")` already returns `CODEX_DEFAULT_MODEL` at config.py:83. The conditional also bypasses the debug log inside `resolve_model`.

**Fix:** Simplify to:
```python
body["model"] = resolve_model(original_model)
```

---

### IN-02: Missing `definitions` recursion in `_clean_schema`

**File:** `dsv4_cc_proxy/codex/tools.py:83-87`
**Issue:** JSON Schema uses both `$defs` (modern, 2019-09+) and `definitions` (deprecated but still produced by many tools). The function only recurses into `$defs`. Schemas using the older `definitions` keyword will not have nested incompatible fields cleaned.

**Fix:** Add alongside `$defs`:
```python
if "$defs" in schema and isinstance(schema["$defs"], dict):
    for sub_schema in schema["$defs"].values():
        if isinstance(sub_schema, dict):
            _clean_schema(sub_schema)

# Also handle the deprecated 'definitions' keyword
if "definitions" in schema and isinstance(schema["definitions"], dict):
    for sub_schema in schema["definitions"].values():
        if isinstance(sub_schema, dict):
            _clean_schema(sub_schema)
```

---

### IN-03: Missing test gap — `parameters` as `list` type

**File:** `tests/test_tools.py:280-294`
**Issue:** Group 5 (Error Handling) tests `parameters` as `None`, `str`, and `int`, but does not test `parameters` as a `list` (the `elif isinstance(params, list)` branch in tools.py:145-151). While the `pytest.raises` match pattern `"Invalid tool parameters"` covers both branches, the list-specific error message `"expected dict, got list"` is never verified.

**Fix:** Add a test case:
```python
def test_invalid_parameters_list_type_raises_valueerror():
    with pytest.raises(ValueError, match="got list"):
        codex_tools.convert_tools([{
            "type": "function", "name": "bad",
            "parameters": ["not", "a", "dict"],
        }])
```

---

_Reviewed: 2026-06-06T10:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
