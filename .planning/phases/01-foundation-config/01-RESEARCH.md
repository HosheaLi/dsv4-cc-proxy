# Phase 1: Foundation & Config - Research

**Researched:** 2026-06-05
**Domain:** Python sub-package structure, environment-variable-based configuration, model resolution algorithm
**Confidence:** HIGH

## Summary

Phase 1 establishes the `codex/` sub-package skeleton under `dsv4_cc_proxy/` (vendor isolation mode) and implements a deterministic model mapping configuration system. Three environment variables (`CODEX_DEFAULT_MODEL`, `CODEX_MODEL_MAP`, `CODEX_UPSTREAM`) control Codex-to-DeepSeek model resolution via a two-layer algorithm: exact match first, then longest-prefix match, then default fallback. The implementation follows the existing `proxy.py` patterns: module-level `os.getenv`, pure functions, no classes, no extra dependencies.

**Primary recommendation:** Create `dsv4_cc_proxy/codex/__init__.py` + `config.py` with flat-export API (`from dsv4_cc_proxy.codex import resolve_model`), pure-function resolution logic, and `tests/test_codex.py` with >=90% coverage.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 子包结构
- **D-01:** Phase 1 最小化创建 `dsv4_cc_proxy/codex/__init__.py` + `config.py`，后续 Phase 按需添加 `translate.py`、`tools.py`、`sse.py`
- **D-02:** 使用扁平导入暴露公共 API：`from dsv4_cc_proxy.codex import resolve_model`，与现有 `from dsv4_cc_proxy import create_app` 风格一致

#### 模型映射
- **D-03:** 两层映射：精确匹配优先 → 前缀匹配（最长前缀优先）→ 回退 `CODEX_DEFAULT_MODEL`
- **D-04:** `CODEX_MODEL_MAP` 格式为扁平键值对 JSON：`{"claude-sonnet-4-6": "deepseek-v4-pro", "claude-": "deepseek-v4-flash"}`
- **D-05:** 未匹配到任何映射时，回退到 `CODEX_DEFAULT_MODEL` 的值，确保始终解析到有效模型
- **D-06:** 配置方式遵循现有模式：`os.getenv` + 纯函数（无 dataclass/类），保持与 `proxy.py` 一致

#### 环境变量
- **D-07:** Codex 相关 env var 使用 `CODEX_` 前缀，与现有 `PROXY_` 前缀平行
- **D-08:** Phase 1 定义三个环境变量：
  - `CODEX_DEFAULT_MODEL` — 默认目标 DeepSeek 模型（如 `deepseek-v4-pro`）
  - `CODEX_MODEL_MAP` — JSON 格式的模型名映射表
  - `CODEX_UPSTREAM` — Chat Completions 端点地址，默认 `https://api.deepseek.com/v1`

#### 测试
- **D-09:** 测试文件 `tests/test_codex.py`，与 `tests/test_proxy.py` 并列
- **D-10:** 纯函数测试，覆盖率 ≥90%，覆盖正常路径 + 边界条件 + 异常处理（JSON 解析错误、空映射表、重叠前缀等）

### Claude's Discretion
- `config.py` 内部函数拆分（如 `parse_model_map()` 是否独立导出）
- 日志记录策略（哪些映射结果需要 log）
- 精确的测试用例设计（具体边界值、异常场景选择）

### Deferred Ideas (OUT OF SCOPE)
无 — 讨论全程在 Phase 1 范围内
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CODX-16 | `CODEX_DEFAULT_MODEL` 环境变量设置默认目标模型 | 配置模式复用 `proxy.py` 的 `os.getenv` + 默认值 `deepseek-v4-flash`；纯函数 `resolve_model()` 在无匹配时回退到此值 |
| CODX-17 | `CODEX_MODEL_MAP` JSON 映射支持精确匹配 + 前缀匹配 | 两层解析算法：`_parse_model_map()` 解析 JSON → `resolve_model()` 先查精确匹配，再查最长前缀匹配 |
| CODX-18 | Codex 发送的任意模型名都有确定的映射结果（不报 404） | 三层兜底设计：精确匹配 → 前缀匹配 → `CODEX_DEFAULT_MODEL` → 永远返回有效 DeepSeek 模型字符串 |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Model mapping config | **API / Backend** | — | 配置在代理层加载，不涉及下游；纯函数解析，无外部依赖 |
| Model name resolution | **API / Backend** | — | 解析算法完全在代理的内存中进行，不经过网络或数据库 |
| Env var loading | **API / Backend** | — | 模块级 `os.getenv` 在导入时执行，是 Starlette 启动前的配置加载阶段 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `os` | 3.11+ | 环境变量加载 | 项目零额外依赖约束；`proxy.py` 已使用此模式 |
| Python stdlib `json` | 3.11+ | `CODEX_MODEL_MAP` JSON 解析 | 项目零额外依赖约束；`proxy.py` 已使用 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.3 (local) | 测试框架 | 测试 `resolve_model()` 纯函数 |
| setuptools | >=75 | 子包自动发现 | `include = ["dsv4_cc_proxy*"]` 已配置，自动包含 `codex` 子包 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pure dict/function config | Pydantic Settings | 违反 D-06 无类约束；引入额外依赖 |
| Manual prefix matching | `fnmatch` / `re` | `str.startswith()` 已足够；前缀匹配无通配符需求 |
| Try/except JSON parse | `json.loads` with default fallback | 相同；保持 `proxy.py` 风格一致 |

**Installation:**
```bash
pip install -e ".[test]"
```

**Version verification:** No new dependencies are introduced in Phase 1. The existing `pyproject.toml` dependencies (httpx, starlette, uvicorn) remain unchanged.

## Architecture Patterns

### System Architecture Diagram

```
                            ┌─────────────────────────────┐
                            │      Environment Vars        │
                            │  CODEX_DEFAULT_MODEL         │
                            │  CODEX_MODEL_MAP (JSON)      │
                            │  CODEX_UPSTREAM              │
                            └──────────┬──────────────────┘
                                       │ os.getenv (module init)
                                       ▼
┌─────────────────────────────────────────────────────────┐
│              codex/ 配置层 (config.py)                    │
│                                                         │
│  _parse_model_map(raw_json) ──► dict (exact+prefix map) │
│                                                         │
│  resolve_model(model_name) ──► string (DeepSeek model)  │
│       │                                                  │
│       ├─ 1. Exact match?     ──► return mapped model    │
│       ├─ 2. Prefix match?    ──► return longest prefix  │
│       └─ 3. Default fallback ──► CODEX_DEFAULT_MODEL    │
└──────────────────────────┬──────────────────────────────┘
                           │ resolve_model("gpt-5.3-codex")
                           ▼
              "deepseek-v4-flash"  (deterministic result)
```

### Recommended Project Structure
```
dsv4_cc_proxy/
├── codex/                    # 新建子包 (Phase 1 最小化)
│   ├── __init__.py           # 扁平导入: from .config import resolve_model
│   └── config.py             # 环境变量加载 + 模型映射解析 + 解析 API
├── proxy.py                  # 不变
├── __init__.py               # 不变
├── __main__.py               # 不变
└── _version.py               # 不变

tests/
├── test_proxy.py             # 不变 (22 个现有测试)
└── test_codex.py             # 新建 (>=90% 覆盖率)

.docs/                        # 不变
```

### Pattern 1: Configuration Loading
**What:** Module-level `os.getenv` with typed defaults and inline error handling, identical to `proxy.py` lines 33-51.
**When to use:** All env vars; matches project's established pattern (D-06).
**Example:**
```python
# Source: dsv4_cc_proxy/proxy.py (lines 33-51) — existing pattern
DEEPSEEK_BASE = os.getenv("PROXY_UPSTREAM", "https://api.deepseek.com/anthropic")
HOST = os.getenv("PROXY_HOST", "127.0.0.1")
try:
    PORT = int(os.getenv("PROXY_PORT", "16889"))
except (TypeError, ValueError):
    print("Error: PROXY_PORT must be an integer", file=sys.stderr)
    sys.exit(1)
```

### Pattern 2: Flat Export
**What:** Sub-package `__init__.py` directly imports and re-exports public API symbols.
**When to use:** All sub-package entry points; matches `dsv4_cc_proxy/__init__.py` pattern.
**Example:**
```python
# Source: dsv4_cc_proxy/__init__.py (line 8-10) — existing pattern
from dsv4_cc_proxy._version import VERSION
from dsv4_cc_proxy.proxy import create_app

__all__ = ["VERSION", "create_app"]
```

### Anti-Patterns to Avoid
- **Mixing `os.getenv` and pydantic/dataclass config:** Violates D-06; project explicitly uses dict-only approach
- **Using `re.match` or glob patterns for prefix matching:** Unnecessary; `str.startswith()` is sufficient since mappings are literal prefixes
- **Validating model names against DeepSeek known models:** Phase 1 is purely mechanical mapping; validation adds coupling to upstream model inventory
- **Caching model map in a module-level variable that gets mutated:** `_parse_model_map()` should return a new dict each time, or the parsed result should be stored read-only

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Model name mapping | Custom config format with YAML/TOML | Plain JSON env var (`CODEX_MODEL_MAP`) | D-04 specifies JSON; matches Codex-relay design; avoids extra parser dependency |
| Prefix matching with wildcards | `fnmatch` / glob patterns | `str.startswith()` | Mappings are literal prefixes (D-03); no wildcard semantics needed |
| Config validation | Pydantic / attrs validators | `try/except` on `json.loads` | D-06 pure function + existing pattern; JSON parse errors are the only failure mode |

**Key insight:** Phase 1 is deliberately minimal — there is nothing here that benefits from a library. The entire config module should be ~60-80 lines of pure Python, all standard library.

## Common Pitfalls

### Pitfall 1: Prefix Match Priority Ambiguity
**What goes wrong:** Two prefix keys both match but shorter one wins due to iteration order.
**Why it happens:** `dict` items iterate in insertion order (Python 3.7+), but relying on order is fragile.
**How to avoid:** Explicitly compute prefix match candidates, then pick `max(candidates, key=len)`. Never use "first match wins" on unordered dict keys.
**Warning signs:** Test fails when map keys are reordered; code uses `next()` or `break` on iterated dict.

### Pitfall 2: CODEX_MODEL_MAP Is Invalid JSON
**What goes wrong:** `os.getenv("CODEX_MODEL_MAP", "{}")` returns a malformed string → `json.loads` raises.
**Why it happens:** User supplies a JSON with trailing comma, unquoted keys, or wrong encoding.
**How to avoid:** Wrap `json.loads` in `try/except json.JSONDecodeError`, log a warning, fall back to empty dict `{}`. Never let parse errors crash the proxy.
**Warning signs:** Proxy crashes on startup; user sees a traceback from config.py.

### Pitfall 3: Exact Match vs. Prefix Match Interaction
**What goes wrong:** A model that matches both an exact key and a prefix key is resolved via prefix instead of exact match.
**Why it happens:** Code checks prefix match before exact match, or confuses the two.
**How to avoid:** Check exact match first, return immediately if found. Only fall through to prefix logic on no exact match.
**Warning signs:** User sets `{"claude-sonnet-4-6": "deepseek-v4-pro", "claude-": "deepseek-v4-flash"}` and `claude-sonnet-4-6` resolves to Flash instead of Pro.

### Pitfall 4: Module-Level Mutable State
**What goes wrong:** `_parsed_map` module variable gets mutated during test runs, causing test-order-dependent failures.
**Why it happens:** Pure functions are expected to be stateless, but module-level caches create hidden state.
**How to avoid:** Parse the model map in `resolve_model()` on each call, or use a module-level frozenset/frozen dict if caching is needed. The current design with ~3-20 map entries means parsing overhead is negligible (<100µs).

## Code Examples

Verified patterns from existing codebase:

### resolve_model() — Primary Public API
```python
# Source: Adapted from existing proxy.py patterns + architecture design
# This shows the expected implementation structure.

import json
import logging
import os

logger = logging.getLogger("deepseek-proxy")

CODEX_DEFAULT_MODEL = os.getenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
CODEX_UPSTREAM = os.getenv("CODEX_UPSTREAM", "https://api.deepseek.com/v1")
_RAW_MODEL_MAP = os.getenv("CODEX_MODEL_MAP", "{}")


def _parse_model_map(raw: str) -> dict[str, str]:
    """Parse CODEX_MODEL_MAP JSON string into a dict.

    Returns an empty dict on parse failure (logs warning). Never raises.
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


def resolve_model(model_name: str) -> str:
    """Resolve a Codex model name to a DeepSeek model string.

    Resolution order:
    1. Exact match in CODEX_MODEL_MAP
    2. Longest prefix match in CODEX_MODEL_MAP
    3. CODEX_DEFAULT_MODEL

    Never returns None or empty string — always returns a valid model name.
    """
    model_map = _parse_model_map(_RAW_MODEL_MAP)

    # 1. Exact match
    if model_name in model_map:
        resolved = model_map[model_name]
        logger.debug("[CODEX] exact match: %s → %s", model_name, resolved)
        return resolved

    # 2. Longest prefix match
    candidates = [
        model_map[key]
        for key in model_map
        if model_name.startswith(key)
    ]
    if candidates:
        # The longest prefix key wins
        # (keys iterated; we want the longest matching key's value)
        prefix_matches = {
            key: model_map[key]
            for key in model_map
            if model_name.startswith(key)
        }
        best_key = max(prefix_matches, key=len)
        resolved = prefix_matches[best_key]
        logger.debug("[CODEX] prefix match: %s → %s (via %r)", model_name, resolved, best_key)
        return resolved

    # 3. Default fallback
    logger.debug("[CODEX] default: %s → %s", model_name, CODEX_DEFAULT_MODEL)
    return CODEX_DEFAULT_MODEL
```

### codex/__init__.py — Public API Export
```python
# Source: Following dsv4_cc_proxy/__init__.py pattern
from dsv4_cc_proxy.codex.config import resolve_model

__all__ = ["resolve_model"]
```

### Test Pattern — Pure Function, Boundary Conditions
```python
# Source: Adapted from tests/test_proxy.py pattern
import json

from dsv4_cc_proxy.codex.config import resolve_model


def test_exact_match():
    """Exact match returns mapped model directly."""
    import os
    os.environ["CODEX_MODEL_MAP"] = json.dumps({
        "claude-sonnet-4-6": "deepseek-v4-pro",
        "claude-": "deepseek-v4-flash",
    })
    os.environ["CODEX_DEFAULT_MODEL"] = "deepseek-v4-flash"
    # Reload module to pick up new env vars (or use monkeypatch)
    assert resolve_model("claude-sonnet-4-6") == "deepseek-v4-pro"


def test_prefix_match_longest_wins():
    """Longest prefix match is preferred over shorter prefix."""
    import os
    os.environ["CODEX_MODEL_MAP"] = json.dumps({
        "claude-": "deepseek-v4-flash",
        "claude-sonnet-": "deepseek-v4-pro",
    })
    os.environ["CODEX_DEFAULT_MODEL"] = "deepseek-v4-flash"
    assert resolve_model("claude-sonnet-5") == "deepseek-v4-pro"


def test_fallback_to_default():
    """Unmapped model falls back to CODEX_DEFAULT_MODEL."""
    import os
    os.environ["CODEX_MODEL_MAP"] = "{}"
    os.environ["CODEX_DEFAULT_MODEL"] = "deepseek-v4-flash"
    assert resolve_model("unknown-model") == "deepseek-v4-flash"


def test_empty_map_uses_default():
    """Empty or unset CODEX_MODEL_MAP always returns default."""
    import os
    os.environ.pop("CODEX_MODEL_MAP", None)
    os.environ["CODEX_DEFAULT_MODEL"] = "deepseek-v4-flash"
    assert resolve_model("anything") == "deepseek-v4-flash"


def test_invalid_json_map_falls_back():
    """Malformed JSON in CODEX_MODEL_MAP logs warning and returns default."""
    import os
    os.environ["CODEX_MODEL_MAP"] = "{invalid json}"
    os.environ["CODEX_DEFAULT_MODEL"] = "deepseek-v4-flash"
    assert resolve_model("any") == "deepseek-v4-flash"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| — | `codex/` sub-package | Phase 1 (new) | Isolated vendor code, no cross-contamination with `proxy.py` |
| — | Two-layer model mapping | Phase 1 (new) | Flexible: quick default via single env var, or detailed map via JSON |
| — | Pure function config | Phase 1 (new) | Matches proxy.py style, testable, no side effects |

**Deprecated/outdated:**
- N/A — Phase 1 is entirely new code, no existing patterns to deprecate.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `resolve_model()` 是公开 API 的正确函数名 | Code Examples | 与 D-02 的 `from dsv4_cc_proxy.codex import resolve_model` 一致，已在 CONTEXT.md 确认 |
| A2 | `CODEX_DEFAULT_MODEL` 默认值为 `deepseek-v4-flash` | Architecture Patterns | 文档未锁定默认值，但架构设计中提及此值。若用户期望不同默认值则需修改。 |
| A3 | `CODEX_UPSTREAM` 默认值为 `https://api.deepseek.com/v1` | Architecture Patterns | 架构设计文档提及 `https://api.deepseek.com`。与 `proxy.py` 的 `PROXY_UPSTREAM` 模式一致但路径不同。Phase 1 仅声明变量，Phase 5 使用。 |
| A4 | 测试使用 `monkeypatch` 或 `os.environ` 修改方式来测试 `resolve_model` | Code Examples | 因模块级 `os.getenv` 在导入时执行，测试需重新加载模块或使用 `monkeypatch.setenv` 策略。实际实现设计会影响测试方案。 |

## Open Questions

1. **`resolve_model()` 调用性能与缓存策略**
   - What we know: 每次调用解析 JSON（map 很小，<100µs）
   - What's unclear: 是否在模块级缓存 `_parse_model_map()` 结果（只在导入时解析一次），还是每次调用都解析
   - Recommendation: 模块级缓存 parsed map（`_MODEL_MAP_CACHE` 全局变量），用 `_load_model_map()` 懒加载。这保持纯函数语义同时避免重复 JSON 解析。但需注意测试中重设环境变量时需清缓存。

2. **`CODEX_UPSTREAM` 在 Phase 1 的落地方式**
   - What we know: D-08 声明三个环境变量
   - What's unclear: `CODEX_UPSTREAM` 是否只在 `config.py` 中声明为模块级常量（给 Phase 5 用），还是 Phase 1 不需要引用它
   - Recommendation: 在 `config.py` 中声明但不 export，保持 D-08 完整。后续 Phase 5 通过 `from dsv4_cc_proxy.codex.config import CODEX_UPSTREAM` 引用。

3. **测试中如何模拟环境变量**
   - What we know: 模块级 `os.getenv` 在 `import` 时执行
   - What's unclear: 是否使用 `pytest.monkeypatch` + 重新加载模块，或者将 `resolve_model()` 设计为接受可选 env override 参数
   - Recommendation: 使用 `pytest.monkeypatch.setenv()` + `importlib.reload(module)` 模式，与纯函数测试原则一致。或者将 `resolve_model(model_name, model_map=None, default_model=None)` 设计为可选参数注入，便于测试。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | Yes | 3.14.5 | — |
| pytest | Testing | Yes | 9.0.3 | — |
| setuptools | Build/install | Yes (pip) | latest | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `python3 -m pytest tests/test_codex.py -v` |
| Full suite command | `python3 -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CODX-16 | `CODEX_DEFAULT_MODEL` 控制默认模型 | unit | `pytest tests/test_codex.py::test_fallback_to_default -x` | ❌ Wave 0 |
| CODX-17 | `CODEX_MODEL_MAP` 精确匹配 | unit | `pytest tests/test_codex.py::test_exact_match -x` | ❌ Wave 0 |
| CODX-17 | `CODEX_MODEL_MAP` 前缀匹配（最长优先） | unit | `pytest tests/test_codex.py::test_prefix_match_longest_wins -x` | ❌ Wave 0 |
| CODX-18 | 无匹配时回退默认模型 | unit | `pytest tests/test_codex.py::test_fallback_to_default -x` | ❌ Wave 0 |
| CODX-18 | 空/无效 JSON 映射回退默认 | unit | `pytest tests/test_codex.py::test_invalid_json_map_falls_back -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_codex.py -v`
- **Per wave merge:** `python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_codex.py` — covers CODX-16, CODX-17, CODX-18
- [ ] `tests/conftest.py` — shared fixtures (if needed for monkeypatching pattern)
- [ ] Install: `pip install -e ".[test]"` — already done

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | `try/except json.JSONDecodeError` on `CODEX_MODEL_MAP` |
| V6 Cryptography | no | No secrets handled in Phase 1 |

### Known Threat Patterns for Python config

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Environment variable injection (malformed JSON) | Tampering | Catch `json.JSONDecodeError`, log warning, return empty dict |
| Environment variable injection (non-dict JSON) | Tampering | Validate parsed type is `dict`, reject with warning |

Phase 1 has minimal security surface: config values flow from env vars to pure functions with no network, file, or shell I/O. The only injection vector is malformed JSON in `CODEX_MODEL_MAP`, which is mitigated by defensive parsing. No authentication or secrets are involved at this layer.

## Sources

### Primary (HIGH confidence)
- `dsv4_cc_proxy/proxy.py` — verified configuration pattern (module-level `os.getenv`), pure function style
- `dsv4_cc_proxy/__init__.py` — verified flat-export pattern
- `tests/test_proxy.py` — verified test pattern (Arrange-Act-Assert, pure function imports)
- `pyproject.toml` — verified `[tool.setuptools.packages.find]` includes `dsv4_cc_proxy*` (auto-discovers subpackages)
- `01-CONTEXT.md` — user decisions (D-01 through D-10) locked
- Architecture design doc (`codex-deepseek-v4-responses-api-deepsee-cryptic-phoenix.md`) — sub-package structure, model mapping design

### Secondary (MEDIUM confidence)
- `REQUIREMENTS.md` — verified CODX-16/17/18 requirement definitions
- `ROADMAP.md` — verified Phase 1 success criteria
- `PROJECT.md` — verified project constraints (Python 3.10+, Starlette+httpx, zero extra dependencies)

### Tertiary (LOW confidence)
- None — all claims verified against codebase or CONTEXT.md

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — directly verified from `proxy.py` and `pyproject.toml`; no new dependencies needed
- Architecture: HIGH — sub-package structure, export pattern, and config loading pattern all confirmed from existing codebase
- Pitfalls: HIGH — prefix matching priority is a well-known Python gotcha; all others derived from codebase patterns

**Research date:** 2026-06-05
**Valid until:** N/A (Phase 1 patterns are stable Python stdlib)
