# Phase 1: Foundation & Config - Pattern Map

**Mapped:** 2026-06-05
**Files analyzed:** 3 (new)
**Analogs found:** 3 / 3

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `dsv4_cc_proxy/codex/__init__.py` | package-init | N/A (re-export) | `dsv4_cc_proxy/__init__.py` | exact |
| `dsv4_cc_proxy/codex/config.py` | config, utility | N/A (pure function) | `dsv4_cc_proxy/proxy.py` (lines 31-51, 229-261) | role-match |
| `tests/test_codex.py` | test | N/A (unit test) | `tests/test_proxy.py` | exact |

## Pattern Assignments

### `dsv4_cc_proxy/codex/__init__.py` (package-init, flat re-export)

**Analog:** `dsv4_cc_proxy/__init__.py` (lines 8-11)

**Imports & export pattern** (lines 8-11):
```python
# Source: dsv4_cc_proxy/__init__.py (lines 8-11)
from dsv4_cc_proxy._version import VERSION
from dsv4_cc_proxy.proxy import create_app

__all__ = ["VERSION", "create_app"]
```

**Pattern to apply:**
```python
# codex/__init__.py - flat re-export of public API
from dsv4_cc_proxy.codex.config import resolve_model

__all__ = ["resolve_model"]
```

Notes:
- Direct import from sibling sub-module (`from .config import ...`) using same relative style as `__init__.py` uses absolute
- Only `resolve_model` is public — internal helpers (`_parse_model_map`, `_RAW_MODEL_MAP`, `CODEX_UPSTREAM`) stay private
- Sub-package `__init__.py` is just a thin re-export shim, same pattern as parent package

---

### `dsv4_cc_proxy/codex/config.py` (config, utility — pure function)

**Analog:** `dsv4_cc_proxy/proxy.py` (lines 31-51 for config loading, lines 103-140 for pure function pattern)

**Imports pattern** (lines 15-29):
```python
# Source: dsv4_cc_proxy/proxy.py (lines 15-30)
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from contextlib import asynccontextmanager

import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from dsv4_cc_proxy._version import VERSION
```

**Pattern to apply for config.py imports:**
```python
# codex/config.py
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("deepseek-proxy")
```

Notes:
- Only need `json`, `logging`, `os` from stdlib — no third-party imports needed
- Logger reused from parent package (`"deepseek-proxy"`) following established convention
- `from __future__ import annotations` follows proxy.py style for forward-compatible type hints

**Config loading pattern** (lines 33-41):
```python
# Source: dsv4_cc_proxy/proxy.py (lines 33-41) — config loading via os.getenv
DEEPSEEK_BASE = os.getenv("PROXY_UPSTREAM", "https://api.deepseek.com/anthropic")
HOST = os.getenv("PROXY_HOST", "127.0.0.1")
try:
    PORT = int(os.getenv("PROXY_PORT", "16889"))
except (TypeError, ValueError):
    print("Error: PROXY_PORT must be an integer", file=sys.stderr)
    sys.exit(1)
LOG_LEVEL = os.getenv("PROXY_LOG_LEVEL", "warning")
```

**Pattern to apply for codex config:**
```python
# codex/config.py — following proxy.py's os.getenv + defaults pattern
CODEX_DEFAULT_MODEL = os.getenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
CODEX_UPSTREAM = os.getenv("CODEX_UPSTREAM", "https://api.deepseek.com/v1")
_RAW_MODEL_MAP = os.getenv("CODEX_MODEL_MAP", "{}")
```

Notes:
- No type conversion needed (strings only for Phase 1) — no try/except required unlike `PROXY_PORT`
- Same module-level assignment pattern — config is evaluated at import time
- Private prefix `_` for `_RAW_MODEL_MAP` marks it as internal (won't be exported)

**Public API function pattern** (lines 247-287):
```python
# Source: Adapted from proxy.py pure function style + architecture design
# Expected codex/config.py implementation

def resolve_model(model_name: str) -> str:
    """Resolve a Codex model name to a DeepSeek model string.

    Resolution order:
    1. Exact match in CODEX_MODEL_MAP
    2. Longest prefix match in CODEX_MODEL_MAP
    3. CODEX_DEFAULT_MODEL

    Never returns None or empty string.
    """
    model_map = _parse_model_map(_RAW_MODEL_MAP)

    # 1. Exact match
    if model_name in model_map:
        resolved = model_map[model_name]
        logger.debug("[CODEX] exact match: %s → %s", model_name, resolved)
        return resolved

    # 2. Longest prefix match
    prefix_matches = {
        key: model_map[key]
        for key in model_map
        if model_name.startswith(key)
    }
    if prefix_matches:
        best_key = max(prefix_matches, key=len)
        resolved = prefix_matches[best_key]
        logger.debug("[CODEX] prefix match: %s → %s (via %r)", model_name, resolved, best_key)
        return resolved

    # 3. Default fallback
    logger.debug("[CODEX] default: %s → %s", model_name, CODEX_DEFAULT_MODEL)
    return CODEX_DEFAULT_MODEL
```

Notes:
- Pure function — no class, no side effects, no state mutation
- Same debug logging style as proxy.py's `_inject_thinking_blocks` (line 137)
- Follows proxy.py's function positioning: public API functions at module level, helpers prefixed with `_`

**Internal helper pattern** (lines 103-140):
```python
# Source: proxy.py lines 103-114 illustrate the _helper naming style
def _has_tool_use(content: list) -> bool:
    return any(
        isinstance(b, dict) and b.get("type") == "tool_use" for b in content
    )

def _has_thinking(content: list) -> bool:
    return any(
        isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking")
        for b in content
    )
```

**Pattern to apply for _parse_model_map helper:**
```python
# codex/config.py — following proxy.py's _helper naming convention

def _parse_model_map(raw: str) -> dict[str, str]:
    """Parse CODEX_MODEL_MAP JSON string into a dict.

    Returns empty dict on parse failure (logs warning). Never raises.
    """
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            logger.warning("[CODEX] CODEX_MODEL_MAP is not a JSON object, ignoring")
            return {}
        return parsed
    except json.JSONDecodeError:
        logger.warning("[CODEX] CODEX_MODEL_MAP parse error, using empty map")
        return {}
```

**Error handling pattern** (lines 145-155):
```python
# Source: proxy.py lines 148-155 — try/except with logging degrade
def _inject_thinking_blocks(data: dict) -> bool:
    thinking_cfg = data.get("thinking", {})
    if not isinstance(thinking_cfg, dict):
        return False
    if thinking_cfg.get("type") != "enabled":
        return False
```

Notes:
- `_parse_model_map` follows the same defensive pattern: log warning on failure, return safe default
- Never raises, always degrades gracefully — matches proxy.py design philosophy
- JSON parse errors caught with `json.JSONDecodeError`, non-dict values caught with `isinstance` check

**Validation pattern** (lines 229-244):
```python
# Source: proxy.py lines 229-244 — defensive JSON parsing
def _dump_json(filename: str, data):
    if not DUMP_DIR:
        return
    path = os.path.join(DUMP_DIR, filename)
    s = json.dumps(data, ensure_ascii=False, indent=2, default=str)
```

Notes:
- `json.dumps` with `ensure_ascii=False` preserves Unicode — matches proxy.py line 235
- Same `json` stdlib usage throughout
- No pydantic, no dataclass — plain dict/str return types

---

### `tests/test_codex.py` (test, pure function unit tests)

**Analog:** `tests/test_proxy.py` (full file, 233 lines)

**Module docstring and import pattern** (lines 1-16):
```python
# Source: tests/test_proxy.py (lines 1-16)
"""dsv4-cc-proxy 单元测试。

覆盖 pure functions: 请求端注入、thinking 标准化、SSE 过滤。
运行: python3 -m pytest tests/test_proxy.py -v
"""

import json

from dsv4_cc_proxy.proxy import (
    _filter_sse_line,
    _has_thinking,
    _has_tool_use,
    _inject_thinking_blocks,
    _normalize_thinking,
    _thinking_requested,
)
```

**Pattern to apply:**
```python
"""dsv4-cc-proxy codex config 单元测试。

覆盖: 模型映射解析、精确/前缀匹配、异常回退。
运行: python3 -m pytest tests/test_codex.py -v
"""

import json
import os

from dsv4_cc_proxy.codex.config import resolve_model
```

**Test function pattern (pure function, Arrange-Act-Assert):**
```python
# Source: tests/test_proxy.py (lines 36-45) — test with dict input, assert return value
def test_inject_thinking_disabled():
    data = {
        "model": "deepseek-v4-pro",
        "thinking": {"type": "disabled"},
        "messages": [
            {"role": "assistant", "content": [{"type": "tool_use", "id": "call_1", "name": "Bash", "input": {}}]}
        ]
    }
    assert not _inject_thinking_blocks(data)
```

**Pattern to apply for codex tests:**

```python
# tests/test_codex.py — test exact match with monkeypatch
def test_exact_match(monkeypatch):
    """精确匹配返回映射模型。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", json.dumps({
        "claude-sonnet-4-6": "deepseek-v4-pro",
        "claude-": "deepseek-v4-flash",
    }))
    # Re-import module-level config by reloading
    from importlib import reload
    import dsv4_cc_proxy.codex.config as codex_config
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("claude-sonnet-4-6") == "deepseek-v4-pro"


def test_prefix_match_longest_wins(monkeypatch):
    """最长前缀匹配优先于较短前缀。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", json.dumps({
        "claude-": "deepseek-v4-flash",
        "claude-sonnet-": "deepseek-v4-pro",
    }))
    from importlib import reload
    import dsv4_cc_proxy.codex.config as codex_config
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("claude-sonnet-5") == "deepseek-v4-pro"


def test_fallback_to_default(monkeypatch):
    """无匹配模型时回退到 CODEX_DEFAULT_MODEL。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    from importlib import reload
    import dsv4_cc_proxy.codex.config as codex_config
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("unknown-model") == "deepseek-v4-flash"


def test_empty_map_uses_default(monkeypatch):
    """空映射表始终返回默认模型。"""
    monkeypatch.delenv("CODEX_MODEL_MAP", raising=False)
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    from importlib import reload
    import dsv4_cc_proxy.codex.config as codex_config
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("anything") == "deepseek-v4-flash"


def test_invalid_json_map_falls_back(monkeypatch):
    """无效 JSON 在 CODEX_MODEL_MAP 中回退默认。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{invalid json}")
    from importlib import reload
    import dsv4_cc_proxy.codex.config as codex_config
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("any") == "deepseek-v4-flash"
```

Notes:
- Uses `monkeypatch.setenv` + `importlib.reload` pattern to handle module-level `os.getenv` (evaluated at import time)
- Each test is self-contained: sets up environment, reloads module, asserts result
- Follows same function-per-scenario organization as `test_proxy.py` (no test classes, flat function list)
- Pure function assertions: input → expected output, no side-effect checking needed

**Boundary test pattern:**
```python
# Additional tests following test_proxy.py's boundary coverage style

def test_exact_match_overrides_prefix(monkeypatch):
    """精确匹配优先于前缀匹配（当两者都匹配时）。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", json.dumps({
        "claude-": "deepseek-v4-flash",
        "claude-sonnet-4-6": "deepseek-v4-pro",
    }))
    from importlib import reload
    import dsv4_cc_proxy.codex.config as codex_config
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("claude-sonnet-4-6") == "deepseek-v4-pro"


def test_no_match_after_exact_and_prefix(monkeypatch):
    """无精确匹配且无前缀匹配时返回默认值。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("CODEX_MODEL_MAP", json.dumps({
        "claude-": "deepseek-v4-flash",
    }))
    from importlib import reload
    import dsv4_cc_proxy.codex.config as codex_config
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("gpt-5") == "deepseek-v4-pro"
```

## Shared Patterns

### Config Loading via os.getenv
**Source:** `dsv4_cc_proxy/proxy.py` lines 33-41
**Apply to:** `dsv4_cc_proxy/codex/config.py`
```python
# Module-level os.getenv with sensible defaults
VAR_NAME = os.getenv("ENV_VAR_NAME", "default_value")
```

### Pure Function Design
**Source:** `dsv4_cc_proxy/proxy.py` lines 103-183
**Apply to:** `dsv4_cc_proxy/codex/config.py` (all functions)
- No class definitions
- No mutable global state
- Input → output transformation only
- Private helpers prefixed with `_`
- Public API functions at module level without underscore

### Flat Re-export via __init__.py
**Source:** `dsv4_cc_proxy/__init__.py` lines 8-11
**Apply to:** `dsv4_cc_proxy/codex/__init__.py`
- Import the public symbol directly from its defining module
- Export via `__all__` for explicit public API surface
- Consistent calling convention: `from dsv4_cc_proxy.codex import resolve_model`

### Defensive JSON Parsing
**Source:** `dsv4_cc_proxy/proxy.py` lines 315-316
**Apply to:** `dsv4_cc_proxy/codex/config.py` `_parse_model_map`
```python
try:
    parsed = json.loads(raw)
except json.JSONDecodeError:
    # log warning, return safe default
```

### Test Structure (Pure Function, Arrange-Act-Assert)
**Source:** `tests/test_proxy.py` (full file)
**Apply to:** `tests/test_codex.py`
- One function per test scenario
- No test classes — flat module-level functions
- descriptive function names (`test_inject_thinking_disabled`, `test_prefix_match_longest_wins`)
- monkeypatch for environment variable overrides
- `importlib.reload()` when module state needs re-initialization
- Assertions only on return values (no side-effect testing)

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | | | All 3 files have close analogs in the codebase |

All three target files have direct or role-match analogs in the existing codebase. No file requires novel pattern design.

## Metadata

**Analog search scope:** `dsv4_cc_proxy/` package, `tests/` directory, `pyproject.toml`
**Files scanned:** 5 (`proxy.py`, `__init__.py`, `_version.py`, `test_proxy.py`, `pyproject.toml`)
**Pattern extraction date:** 2026-06-05
