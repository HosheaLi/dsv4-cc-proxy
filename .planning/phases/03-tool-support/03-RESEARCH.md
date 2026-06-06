# Phase 3: Tool Support - Research

**Researched:** 2026-06-06
**Domain:** Tool format conversion and JSON Schema auto-repair for DeepSeek strict mode compliance
**Confidence:** HIGH

## Summary

This phase implements `dsv4_cc_proxy/codex/tools.py` — a pure-function module that solves two transformations on the request body's `tools` array:

1. **Format conversion (CODX-07):** OpenAI Responses API uses a flat structure `{type, name, description, parameters}`, while DeepSeek Chat Completions requires nesting under `function`: `{type, function: {name, description, parameters}}`. The conversion wraps flat fields into the `function` key, preserving already-nested tools as-is.

2. **Schema auto-repair (CODX-10):** DeepSeek's strict mode validates function parameter schemas against a limited subset of JSON Schema. Unsupported fields (`default`, `readOnly`, `writeOnly`, `examples`, `minLength`, `maxLength`, `minItems`, `maxItems`, empty `enum`) must be stripped recursively from all nested schema paths (`properties`, `$defs`, `anyOf`, `items`).

Both operations are callable from `translate_request()` as a single `convert_tools()` call, maintaining the existing translation chain pattern. No new dependencies are added — only Python stdlib `json`, `logging`, and `copy`.

Integration is straightforward: `translate_request()` calls `convert_tools(body["tools"])` after message translation and model resolution, before returning the body. The `__init__.py` gains `convert_tools` as a third top-level export alongside `resolve_model` and `translate_request`.

**Primary recommendation:** Implement `tools.py` with `convert_tools()` as the single public entry point, splitting internal logic into `_convert_tool_format()` (format wrapping) and `_clean_schema()` (recursive field stripping), following the same pure-function, no-class, `_`-prefix convention established by `translate.py`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Tool format conversion | API / Backend | — | Operates on request body in the proxy layer before upstream dispatch |
| Schema field stripping | API / Backend | — | Pure data transformation on in-memory dicts, no I/O involved |
| Nested schema recursion | API / Backend | — | Recursive traversal of in-memory JSON Schema structures |
| Error handling (invalid schema) | API / Backend | — | Raises exceptions that propagate to HTTP handler in Phase 5 |
| Integration with translate_request | API / Backend | — | `translate_request()` calls `convert_tools()` in the same translation chain |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `json` | — | JSON parsing and serialization | Already the project standard (`translate.py`, `config.py`) |
| Python stdlib `copy` | — | `copy.deepcopy` for immutability | Already the project standard (`translate.py` line 242) |
| Python stdlib `logging` | — | WARNING/DEGUB logging for edge cases | Already the project standard (`logger = logging.getLogger("deepseek-proxy")`) |

### Needing No New Dependencies
The entire Phase 3 implementation uses only Python stdlib modules. This aligns with the project's zero-extra-dependency philosophy. All schema traversal is in-memory dict manipulation.

**Alternatives Considered**
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual recursive dict traversal | `jsonschema` library | Adds external dependency for what is < 80 lines of dict manipulation |
| Manual format checking | `pydantic` models for tool schemas | Overkill for simple wrapping of known fields; adds heavyweight validation |

**Installation:**
No new packages needed. Run existing test dependencies:
```bash
pip install -e ".[test]"
```

**Version verification:**
```bash
npm view dsv4-cc-proxy version  # N/A — Python package
python3 --version  # 3.14.5 (confirmed available)
```

## Architecture Patterns

### System Architecture Diagram

```
translate_request(request_body)
    │
    ├── body = copy.deepcopy(request_body)
    ├── instructions = body.pop("instructions")
    ├── input_array = body.pop("input")
    ├── Translate input items → messages[]
    ├── Merge system messages
    ├── Resolve model
    ├── Rename max_output_tokens → max_tokens
    │
    ├── convert_tools(body["tools"])  ← Phase 3 integration point
    │       │
    │       ├── For each tool in tools[]:
    │       │       ├── _convert_tool_format(tool)
    │       │       │       └── {type, name, desc, params} → {type, function: {name, desc, params}}
    │       │       │           If already nested (has "function" key) → pass through
    │       │       │           If unknown type → WARNING + pass through
    │       │       │
    │       │       └── If parameters exists:
    │       │               └── _clean_schema(parameters)
    │       │                       └── Recursively strip: default, readOnly, writeOnly,
    │       │                           examples, minLength, maxLength, minItems, maxItems
    │       │                           Remove empty enum: []
    │       │                           Traverse → properties.*, $defs.*, anyOf[*], items
    │       │
    │       └── Return modified tools[]
    │
    └── body["messages"] = messages
    └── Return body
```

### Recommended Project Structure
```
dsv4_cc_proxy/
├── codex/
│   ├── __init__.py       # Export resolve_model, translate_request, convert_tools
│   ├── config.py         # Model mapping (Phase 1 — done)
│   ├── translate.py      # Request translation (Phase 2 — done)
│   └── tools.py          # NEW: convert_tools + internal helpers
│
tests/
├── test_codex.py         # Model mapping tests (Phase 1 — done)
├── test_translate.py     # Translation tests (Phase 2 — done)
└── test_tools.py         # NEW: Tool conversion + schema repair tests
```

### Pattern 1: _convert_tool_format — Flat to Nested Wrapping
**What:** Detect tool objects in Responses API flat format and wrap fields under `function` key.
**When to use:** On every tool in the `tools` array that has `type: "function"` and lacks a `function` key.
**Verified approach:**

```
Input:  {"type": "function", "name": "get_weather", "description": "X", "parameters": {...}}
Output: {"type": "function", "function": {"name": "get_weather", "description": "X", "parameters": {...}}}

Input:  {"type": "function", "function": {"name": "get_weather", ...}}  (already nested)
Output: (unchanged — pass through)
```

Known fields to wrap: `name`, `description`, `parameters`, `strict` (if present). All other top-level keys in a flat-format tool can be logged as WARNING and skipped (or treated as extra function fields). The `function` key always contains name + description + parameters; `strict` can optionally be included.

**Source:** [VERIFIED: OpenAI Responses API tool format] — flattened structure vs Chat Completions nested structure confirmed by web search cross-referenced with project CONTEXT.md design decisions.

### Pattern 2: _clean_schema — Recursive Field Stripping
**What:** Walk a JSON Schema dictionary recursively, removing all keys in the unsupported field set. Continue traversal into `properties` values, `$defs` values, `anyOf` list items, and `items`.
**When to use:** After format conversion, on every tool's `parameters` dict that is a valid dict.
**Source:** [CITED: DeepSeek API Docs function_calling] — strict mode supported subset.

**Verified approach:**
```python
UNSUPPORTED_KEYS = frozenset({
    "default", "readOnly", "writeOnly", "examples",
    "minLength", "maxLength", "minItems", "maxItems",
})

def _clean_schema(schema: dict) -> dict:
    """Recursively strip DeepSeek-unsupported fields from a JSON Schema dict."""
    # 1. Remove unsupported keys at current level
    for key in UNSUPPORTED_KEYS:
        schema.pop(key, None)

    # 2. Remove empty enum arrays
    if "enum" in schema and isinstance(schema["enum"], list) and len(schema["enum"]) == 0:
        del schema["enum"]

    # 3. Recurse into nested structures
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

**Key design note:** This function mutates its input dict (for efficiency). The caller (`convert_tools`) operates on a `copy.deepcopy` of the original tools array, so mutation is safe.

### Anti-Patterns to Avoid
- **Silently dropping invalid schemas:** D-07 requires explicit exception for non-dict `parameters`, not silent pass-through
- **Adding fields during cleaning:** D-04 prohibits auto-filling `required` or `additionalProperties: false` — DeepSeek strict mode requires both, but Codex may send non-strict tools where adding them would change behavior
- **Shallow field stripping:** D-06 requires recursive traversal — a top-level-only strip would miss nested unsupported fields in `$defs`, `anyOf`, or nested `properties`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON Schema validation | Custom schema validator | None needed — this phase only strips fields, not validates | The CONTEXT.md D-04 decision explicitly defers schema validation to a future enhancement |
| Recursive object tree traversal | Custom recursive walker | None needed — 15-line recursive function is the right fit | No existing library needed for simple dict-with-depth-unknown traversal |
| Toolkit format detection | Custom type checking | None needed — `isinstance(tool, dict)`, `tool.get("type")`, `"function" in tool` | Straightforward dict key checks, no library needed |

**Key insight:** This phase is purely about dict manipulation — wrapping keys and removing keys. No new dependencies are justified.

## Common Pitfalls

### Pitfall 1: Shallow Recursion
**What goes wrong:** Only the top-level `parameters` schema is cleaned. Nested `$defs` or `anyOf` schemas still contain unsupported fields, causing DeepSeek rejection.
**Why it happens:** It's easy to write `_clean_schema()` that cleans only one level and forgets the recursive calls.
**How to avoid:** Use a recursive function that calls itself on all nested paths. Verify with a test containing `$defs` and 3+ levels of nesting.
**Warning signs:** DeepSeek returns `400` with schema validation error for tools that look correct at first glance.

### Pitfall 2: Not Handling Already-Nested Tools
**What goes wrong:** `_convert_tool_format()` wraps an already-nested tool, producing `{type, function: {function: {name, ...}}}` (double nested).
**Why it happens:** Codex can send tools pre-formatted in Chat Completions format (e.g., when using MCP servers or other tool sources).
**How to avoid:** Check `"function" in tool` before wrapping. If `function` key exists, pass through unchanged.
**Warning signs:** DeepSeek returns `400` with "Invalid function definition" error.

### Pitfall 3: Not Protecting Against Empty Enum
**What goes wrong:** DeepSeek rejects schemas with `"enum": []` (empty array) — it expects at least one option.
**Why it happens:** Codex or upstream tools sometimes define an enum with no values (e.g., placeholder).
**How to avoid:** Check `isinstance(schema.get("enum"), list)` and `len(schema["enum"]) == 0`, then `del schema["enum"]`.
**Warning signs:** DeepSeek returns `400` referencing the enum field.

### Pitfall 4: Forgetting Non-Dict Parameters
**What goes wrong:** Schema repair crashes on `parameters: null` or `parameters: str` with AttributeError when calling `.pop()` on non-dict.
**Why it happens:** D-09 explicitly allows tools with missing `parameters`, but if present it could theoretically be non-dict (malformed input).
**How to avoid:** Guard `_clean_schema()` call with `isinstance(tool.get("parameters"), dict)`. If non-dict parameters are encountered and schema repair would be needed, raise ValueError per D-07.
**Warning signs:** Tests for edge case `parameters` types fail.

### Pitfall 5: `strict` Field Not Moved Under `function`
**What goes wrong:** Responses API tools have `strict: true` at the top level alongside `name`. If not moved under `function`, DeepSeek may treat it as an unknown key at the tool level.
**Why it happens:** The format conversion only wraps `name`, `description`, `parameters` — forgetting `strict` which is also a flat field in Responses API.
**How to avoid:** Include `strict` in the set of keys wrapped under `function`. Check both positions during conversion.
**Warning signs:** Tools with `strict: true` fail silently (strict mode not applied for DeepSeek) or produce warnings.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CoDeepSeedeX auto-repair (adds required + additionalProperties) | Contect.md D-04: strip only, never add | 2026-06-06 | Conservative: won't break non-strict tools but may need strict mode retry later |
| CoDeepSeedeX unknown key pass-through | D-07: raise exception for invalid schema | 2026-06-06 | Fail-fast instead of silent ignores |
| Schema field stripping at top level only | D-06: recursive all-level cleaning | 2026-06-06 | Future-proof for complex schemas with $defs/anyOf |

**Deprecated/outdated:**
- Older DeepSeek versions (pre-V4) enforced fewer schema restrictions — the current V4 strict mode is more rigorous about field-level validation

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Responses API `strict` field should be wrapped under `function` key | Standard Stack | `strict` ignored by DeepSeek (no error, just not applied) |
| A2 | Additional unsupported JSON Schema fields (`oneOf`, `allOf`, `if`, `then`, `else`, `not`) are not needed in D-05 stripping list | Common Pitfalls | If Codex sends these, DeepSeek may reject the request |
| A3 | `const` is supported by DeepSeek and doesn't need stripping | Standard Stack | If DeepSeek rejects `const`, it'll need to be added to the strip list |
| A4 | The `examples` field in JSON Schema always appears at the type level, not nested inside other unexpected structures | Common Pitfalls | If `examples` appears in non-standard locations, recursion must cover them |

## Open Questions

1. **Where exactly does `convert_tools()` get called inside `translate_request()`?**
   - What we know: D-02 says "after messages translation, before final output" (Claude's Discretion)
   - What's unclear: Precise line position — after model resolution? After max_output_tokens rename? Before setting messages?
   - Recommendation: Insert after `body.pop("include", None)` (line 281) and before `body["messages"] = messages` (line 284), as the tools field is serialization-agnostic and doesn't depend on other body fields.

2. **Does `strict` field need special handling or can it be simply wrapped under `function`?**
   - What we know: Responses API has `strict` at flat level, Chat Completions has it under `function`
   - What's unclear: Whether DeepSeek actually uses `strict:true` from the `function` key or requires it differently
   - Recommendation: Wrap `strict` under `function` like other fields; if DeepSeek silently ignores it (non-Beta endpoint), no harm

3. **Should `tool_choice` field in the request body be translated?**
   - What we know: Phase 3 scope is only the `tools` array, not `tool_choice`
   - What's unclear: Whether Responses API and Chat Completions use the same `tool_choice` format
   - Recommendation: Defer to Phase 5 (Route Integration) — `tool_choice` format is identical between APIs

## Environment Availability

> **Skipped:** Phase 3 is pure Python code with no external dependencies beyond what Phase 1/2 already established. No new tools, services, or CLI utilities required.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` with `testpaths = ["tests"]` |
| Quick run command | `python3 -m pytest tests/test_tools.py -v` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CODX-07 | Flat tool format → Chat nested format | unit | `python3 -m pytest tests/test_tools.py -k "test_convert" -v` | ❌ Wave 0 |
| CODX-10 | Schema field stripping (default, readOnly, writeOnly, examples, minLength, maxLength, minItems, maxItems) | unit | `python3 -m pytest tests/test_tools.py -k "test_clean_schema" -v` | ❌ Wave 0 |
| CODX-10 | Recursive cleaning through `$defs` | unit | `python3 -m pytest tests/test_tools.py -k "test_recursive" -v` | ❌ Wave 0 |
| CODX-10 | Recursive cleaning through `anyOf` | unit | `python3 -m pytest tests/test_tools.py -k "test_recursive" -v` | ❌ Wave 0 |
| CODX-10 | Empty `enum` removal | unit | `python3 -m pytest tests/test_tools.py -k "test_empty_enum" -v` | ❌ Wave 0 |
| — | Already-nested tools pass through | unit | `python3 -m pytest tests/test_tools.py -k "test_already_nested" -v` | ❌ Wave 0 |
| — | Unknown type tools pass through with WARNING | unit | `python3 -m pytest tests/test_tools.py -k "test_unknown_type" -v` | ❌ Wave 0 |
| — | Empty tools list | unit | `python3 -m pytest tests/test_tools.py -k "test_empty_tools" -v` | ❌ Wave 0 |
| — | Missing parameters — skip schema repair | unit | `python3 -m pytest tests/test_tools.py -k "test_missing_params" -v` | ❌ Wave 0 |
| — | Invalid schema (non-dict parameters) raises exception | unit | `python3 -m pytest tests/test_tools.py -k "test_invalid_schema" -v` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_tools.py -v -x` (stop at first failure)
- **Per wave merge:** `pytest tests/ -v` (all project tests, verify no regressions)
- **Phase gate:** Full suite green + coverage >=90% on tools.py before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tools.py` — covers all CODX-07, CODX-10 behaviors
- [ ] `tests/conftest.py` — existing? No. Shared fixtures could include sample tool definitions.
- [ ] Framework install: `pip install -e ".[test]"` — already established by Phase 1

## Security Domain

> **Skipped:** This phase operates exclusively on in-memory dict transformations. No I/O, no network, no file system access, no authentication. Schema stripping is a data integrity operation, not a security boundary. No ASVS categories apply.

## Sources

### Primary (HIGH confidence)
- [PROJECT: CONTEXT.md] — All D-01 through D-13 decisions, code integration patterns, test coverage requirements
- [PROJECT: translate.py] — Code patterns (`_` prefix functions, WARNING logging, `deepcopy` immutability)
- [PROJECT: __init__.py] — Export pattern for convert_tools alongside resolve_model and translate_request
- [PROJECT: test_translate.py] — AAA test patterns, monkeypatch + reload convention

### Secondary (MEDIUM confidence)
- [CITED: api-docs.deepseek.com/guides/function_calling] — Strict mode field support/unsupport lists (via web search cross-reference)
- [CITED: chat-deep.ai/docs/deepseek-tool-calls] — Verified strict mode constraints: `minLength`, `maxLength`, `minItems`, `maxItems` unsupported; `$defs`/`$ref` supported
- [CITED: search: OpenAI Responses API tool format] — Flat format vs Chat Completions nested format

### Tertiary (LOW confidence)
- [ASSUMED: CoDeepSeedeX `examples` stripping behavior] — `examples` is not explicitly documented by DeepSeek as unsupported, but it's not a standard strict mode field; stripping it is a conservative choice per D-05

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified against existing codebase patterns and no new dependencies needed
- Architecture: HIGH — integration with translate_request is clearly specified in CONTEXT.md
- Pitfalls: HIGH — derived from documented DeepSeek strict mode constraints and established anti-patterns
- Schema stripping fields: MEDIUM — the D-05 list is authoritative from CONTEXT.md, but the exact behavior of DeepSeek on unsupported fields is sourced from web search (secondary), not direct API endpoint testing

**Research date:** 2026-06-06
**Valid until:** 2026-07-06 (stable — no fast-moving dependencies, but DeepSeek API behavior could change)
