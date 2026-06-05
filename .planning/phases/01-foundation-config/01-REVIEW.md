---
phase: 01-foundation-config
reviewed: 2026-06-05T12:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - dsv4_cc_proxy/codex/__init__.py
  - dsv4_cc_proxy/codex/config.py
  - tests/test_codex.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 01: Code Review Report — codex sub-package skeleton

**Reviewed:** 2026-06-05T12:00:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the new `dsv4_cc_proxy/codex/` sub-package (init + model mapping config) and its test suite. The code is structurally clean with proper module boundaries, type hints, docstrings, and defensive parsing. Two warnings and three info items found — no critical issues.

The module-level env-var capture pattern is well-understood by the tests (using `reload`), but has two correctness risks: the type annotation for `_parse_model_map` is unsound (promises `str` values but JSON can return arbitrary types), and the JSON config string is re-parsed on every `resolve_model` call.

---

## Warnings

### WR-01: Type annotation mismatch in `_parse_model_map` — values can be non-string

**File:** `dsv4_cc_proxy/codex/config.py:31-46`
**Issue:** The function signature declares `-> dict[str, str]`, but `json.loads(raw)` can produce dicts with non-string values. For example, `CODEX_MODEL_MAP='{"claude-": 123}'` or `CODEX_MODEL_MAP='{"claude-": ["a", "b"]}'` would silently pass through without error. The `isinstance(parsed, dict)` check on line 40 does not validate the type of values. When `resolve_model` later returns such a value on line 66/78, callers expecting a `str` could get an `int` or `list`, breaking downstream string operations.

**Fix:** Add value-type validation inside `_parse_model_map`:

```python
def _parse_model_map(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            logger.warning("[CODEX] CODEX_MODEL_MAP is not a JSON object, ignoring")
            return {}
        # Validate that all values are strings
        for k, v in parsed.items():
            if not isinstance(v, str):
                logger.warning("[CODEX] CODEX_MODEL_MAP value for %r is not a string, ignoring", k)
                return {}
        return parsed
    except json.JSONDecodeError:
        logger.warning("[CODEX] CODEX_MODEL_MAP parse error, using empty map")
        return {}
```

---

### WR-02: Repeated JSON parsing on every `resolve_model` call

**File:** `dsv4_cc_proxy/codex/config.py:25,62`
**Issue:** `_RAW_MODEL_MAP` is stored as a raw JSON string at module level (line 25), and `_parse_model_map()` is called on every invocation of `resolve_model()` (line 62). For a config that is read once at process start and never changes, this re-parses the JSON every time a model name needs to be resolved. While JSON parsing of a small dict is cheap, repeated unnecessary work is a code smell — especially in a hot path that may be called for every request.

**Fix:** Parse once at module load time and store the parsed dict:

```python
# At module level (replaces lines 25, 31-46):
_RAW_MODEL_MAP = os.getenv("CODEX_MODEL_MAP", "{}")
_MODEL_MAP: dict[str, str] = {}

def _init_model_map() -> None:
    global _MODEL_MAP
    _MODEL_MAP = _parse_model_map(_RAW_MODEL_MAP)

_init_model_map()

def resolve_model(model_name: str) -> str:
    # Use _MODEL_MAP instead of calling _parse_model_map
    if model_name in _MODEL_MAP:
        ...
```

This requires updating the test pattern to still work with `reload(codex_config)`, which it will, since `reload` re-executes the module top-level code, re-calling `_init_model_map()`.

---

## Info

### IN-01: Missing test coverage for non-string values in model map

**File:** `tests/test_codex.py`
**Issue:** The test suite validates exact match, prefix match, default fallback, empty map, and invalid JSON — all important cases. However, there is no test for the scenario where `CODEX_MODEL_MAP` contains non-string values (e.g., integers, lists, null). Given WR-01 (type annotation mismatch), this is an untrusted-input edge case that should be covered.

**Fix:** Add a test:

```python
def test_non_string_value_rejected(monkeypatch):
    """Non-string values in CODEX_MODEL_MAP should fall back to default."""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", json.dumps({"claude-": 123}))
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("claude-sonnet-4") == "deepseek-v4-flash"
```

This test would currently fail (it would return `123`). Should pass once WR-01 is fixed.

---

### IN-02: Redundant re-import of `resolve_model` in each test

**File:** `tests/test_codex.py:21,33,43,52,61,72`
**Issue:** Every test function independently imports `resolve_model` after `reload(codex_config)`:

```python
reload(codex_config)
from dsv4_cc_proxy.codex.config import resolve_model
```

The `from ... import` is identical in all six tests. This is slightly redundant and adds noise. A single top-level `from dsv4_cc_proxy.codex.config import resolve_model` would work fine, with only `reload(codex_config)` needed in each test to refresh the module-level state.

**Fix:** Move the import to module level, keep only `reload(codex_config)` in each test:

```python
from importlib import reload
import dsv4_cc_proxy.codex.config as codex_config
from dsv4_cc_proxy.codex.config import resolve_model  # single import here

def test_exact_match_overrides_prefix(monkeypatch):
    monkeypatch.setenv(...)
    reload(codex_config)  # no re-import needed
    assert resolve_model("claude-sonnet-4-6") == "deepseek-v4-pro"
```

---

### IN-03: `resolve_model` can return empty string if configured

**File:** `dsv4_cc_proxy/codex/config.py:84`
**Issue:** The docstring states "从不返回 None 或空字符串", but the function will return an empty string if either `CODEX_DEFAULT_MODEL` is set to `""` or a map entry maps to `""`. While this is an unusual configuration, the contract is technically violated. Consider a guard:

```python
return CODEX_DEFAULT_MODEL or "deepseek-v4-flash"
```

Also consider validating map values in `_parse_model_map` (see WR-01 for the approach). This is low severity — a reasonable operator would not map to an empty string — but the docstring promise is worth keeping.

---

_Reviewed: 2026-06-05T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
