# Phase 2: Request Translation - Research

**Researched:** 2026-06-05
**Domain:** OpenAI Responses API -> DeepSeek Chat Completions API message translation
**Confidence:** HIGH

## Summary

Phase 2 delivers a single pure-function translation layer (`translate_request`) that converts OpenAI Responses API request bodies into DeepSeek Chat Completions format. This is purely a dict-to-dict transformation — no HTTP, no SSE, no tool format conversion.

The core challenge is mapping the Responses API's typed `input` array (message, function_call, function_call_output, reasoning items) into Chat Completions' `messages` array, while handling the DeepSeek-specific requirement that assistant messages with `tool_calls` always include a `reasoning_content` field (even if empty string).

The translation follows vendor isolation: all code goes into `dsv4_cc_proxy/codex/translate.py`, following the established pure-function, no-class pattern from `proxy.py` and `config.py`. The test file will be `tests/test_translate.py`, following the AAA pattern from `test_codex.py`.

**Primary recommendation:** Implement a single-entry-point pure function (`translate_request`) with internal `_`-prefixed helpers, following the exact decision tree documented in CONTEXT.md D-01 through D-13. No deviations from the locked decisions.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `instructions` field merge | Translation layer (codex/translate.py) | — | Pure data transformation, no I/O or routing |
| `input` item type dispatch | Translation layer | — | Each item type maps to a known Chat role/structure |
| `function_call` -> tool_calls attach | Translation layer | — | Operates on in-memory messages array, before network send |
| `function_call_output` -> tool message | Translation layer | — | Direct role mapping |
| reasoning -> reasoning_content fold | Translation layer | — | Satisfies DeepSeek validation at request boundary |
| assistant + tool_calls reasoning fix | Translation layer | — | Injects empty string if missing; part of input preprocessing |

All capabilities are owned by the translation layer (codex/translate.py). No tier delegation is needed — this is a preprocessing step that operates entirely on the request body before any HTTP send.

## User Constraints (from CONTEXT.md)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Module file organization
- **D-01:** New `dsv4_cc_proxy/codex/translate.py`, consistent with technical plan. Phase 2 only includes request translation logic, Phase 4 adds `sse.py`
- **D-02:** translate.py only exports the main translation function in `dsv4_cc_proxy/codex/__init__.py`, consistent with existing `config.py` exporting `resolve_model`

#### Function architecture
- **D-03:** Single entry function `translate_request(request_body: dict) -> dict` — pure function, no input mutation, returns brand new dict
- **D-04:** All internal helpers use `_` prefix (e.g., `_translate_input_items`, `_merge_system_messages`, `_attach_tool_calls`), only `translate_request` exported. Consistent with `proxy.py`'s `_filter_sse_line`, `_inject_thinking_blocks` convention

#### System message merge
- **D-05:** `instructions` top-level field + developer role messages merged into a single system message with `\n\n` separator, placed at the front of messages array. If both empty, no system message generated

#### function_call edge cases
- **D-06:** When function_call has no preceding assistant message, create synthetic assistant: `{"role": "assistant", "content": None, "tool_calls": [...]}`

#### Content extraction
- **D-07:** When message content is array format, extract all `input_text` type `text` fields joined by `\n`; when content is plain string, use directly

#### Unknown type handling
- **D-08:** Unknown input item types, log WARNING and skip the item, do not interrupt translation flow

#### Reasoning multi-turn maintenance
- **D-09:** Reasoning items folded into the subsequent first assistant message's `reasoning_content` field. Multiple reasoning items concatenated. If no subsequent assistant message, do not inject reasoning
- **D-10:** Reasoning item content extraction: extract `type: "reasoning_text"` text from `content` array concatenated; also preserve `summary` text
- **D-11:** During translation, check every assistant message: if it has `tool_calls` but no `reasoning_content` field, inject `reasoning_content: ""` to satisfy DeepSeek validation
- **D-12:** Reasoning -> thinking parameter mapping NOT implemented in Phase 2, deferred to Phase 4 (SSE streaming phase)
- **D-13:** Anomalous sequences (e.g., reasoning -> user rather than reasoning -> assistant) only log WARNING and skip reasoning, no structural repair

### Claude's Discretion
- Internal helper function granularity (e.g., `_extract_content_text`, `_merge_system_messages`, `_translate_input_item`, etc.)
- Logging verbosity level
- Function parameter validation strictness
- Docstring style

### Deferred Ideas (OUT OF SCOPE)
None - all discussion was within Phase 2 scope.
</user_constraints>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CODX-03 | Responses API `input` array correctly translated to Chat Completions `messages` array | Translation mapping table documented in architecture plan [CITED: plan doc SS63-73], Responses API input item types verified [SEARCHED: OpenAI Responses API docs], DeepSeek message format verified [SEARCHED: DeepSeek Chat Completions API docs] |
| CODX-04 | `instructions` field translated to system message (merged with developer role messages) | D-05 locked decision covers merge strategy [VERIFIED: CONTEXT.md], `\n\n` separator confirmed |
| CODX-11 | function_call/function_call_output input items correctly translated | D-06 (synthetic assistant) and function_call_output -> tool role mapping verified [VERIFIED: CONTEXT.md D-06, plan doc SS71-72] |
| CODX-14 | Reasoning content maintained across turns: assistant+tool_calls messages inject `reasoning_content: ""` | D-09 through D-13 cover full reasoning strategy [VERIFIED: CONTEXT.md], DeepSeek validation requirement confirmed [SEARCHED: multiple community reports of 400 errors] |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `json` | 3.10+ | Dict serialization/deserialization | Zero extra dep, existing project pattern |
| Python stdlib `logging` | 3.10+ | Structured logging | Existing project uses `logging.getLogger("deepseek-proxy")` |
| Python stdlib `copy` (deepcopy) | 3.10+ | Immutable input guarantee (D-03) | Required for pure function that returns new dict without mutating input |

**Alternatives Considered:**
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| dict-based translation | Pydantic models | Project convention is pure dict (proxy.py 434 lines, config.py). Pydantic adds dependency and breaks existing pattern. Dict is simpler for this translation task. |
| json module | orjson / ujson | Extra deps not justified for this project size. 434 lines of code doesn't need perf optimization. |

**Version verification:** Python 3.14.5 is the runtime version. All stdlib modules above are built-in — no npm/pip verification needed.

### Installation
No new dependencies. The codex subpackage is already importable:
```bash
pip install -e ".[test]"
```

## Architecture Patterns

### System Architecture Diagram

```
POST /v1/responses  (Responses API request body)
         │
         ▼
┌─────────────────────────────────────────────┐
│  translate_request(body: dict) -> dict       │
│                                             │
│  Input: Responses API body (never mutated)   │
│                                             │
│  1. Extract `instructions`                   │
│  2. Merge developer role messages            │
│     → system message (placed first)          │
│                                             │
│  3. For each item in `input[]`:              │
│     ├─ message (user)    → user message       │
│     ├─ message (assistant) → assistant msg   │
│     ├─ message (developer)→ system (merged)  │
│     ├─ function_call     → attach tool_calls │
│     │   (to last assistant, or synthetic)    │
│     ├─ function_call_output → tool message  │
│     └─ reasoning         → fold into next    │
│                           assistant's        │
│                           reasoning_content  │
│                                             │
│  4. Inject reasoning_content: ""             │
│     on every assistant with tool_calls       │
│     lacking reasoning_content                │
│                                             │
│  5. Set model via resolve_model()            │
│                                             │
│  Output: Chat Completions request body       │
└──────────┬──────────────────────────────────┘
           │
           ▼
POST /v1/chat/completions  (to DeepSeek API)
```

### Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| `translate_request()` | Entry point. Deep-copies input, orchestrates all translation steps, returns new dict |
| `_merge_system_messages()` | Extracts `instructions` + collects `message(role=developer)` items, merges with `\n\n`, removes developer items from translated messages |
| `_translate_input_items()` | Iterates input array, dispatches each item by type to its handler |
| `_translate_message_item()` | Handles message items: extracts content (array -> string via `_extract_content_text`), maps role |
| `_attach_tool_calls()` | Handles function_call items: appends to last assistant's tool_calls[] or creates synthetic assistant |
| `_translate_function_call_output()` | Handles function_call_output items: creates tool role message |
| `_fold_reasoning()` | Handles reasoning items: stores content, folds into next assistant message's `reasoning_content` |
| `_ensure_reasoning_content()` | Post-processing: checks all assistant messages for tool_calls && !reasoning_content, injects "" |
| `_extract_content_text()` | Shared: extracts text from content array (filters `type: "input_text"` -> text, joins with `\n`) |
| `_log_and_skip()` | Shared: handles unknown item types with WARNING log |

### Recommended Project Structure
```
dsv4_cc_proxy/
├── codex/
│   ├── __init__.py          # Export: translate_request, resolve_model
│   ├── config.py            # resolve_model() [existing, Phase 1]
│   └── translate.py         # translate_request() + helpers [NEW]
├── proxy.py                 # Unchanged in Phase 2
├── __init__.py
├── __main__.py
└── _version.py             # 1.8.0

tests/
├── test_codex.py           # Phase 1 tests [unchanged]
├── test_proxy.py           # Existing 22 proxy tests [unchanged]
└── test_translate.py       # Phase 2 tests [NEW, ~15-20 tests]
```

### Pattern 1: Pure Function with Deep Copy
**What:** Entry function makes a deep copy of input, translates without mutation, returns new dict. All internal helpers are stateless.

**When to use:** Phase 2 only operates on request body dicts. No state, no side effects. Matches existing proxy.py and config.py patterns.

**Example (pattern from existing code, for reference):**
```python
# From config.py - pure function pattern
def resolve_model(model_name: str) -> str:
    """Pure function, no mutation, returns computed value."""
    model_map = _parse_model_map(_RAW_MODEL_MAP)
    if model_name in model_map:
        return model_map[model_name]
    # ...prefix match, fallback...
    return CODEX_DEFAULT_MODEL
```

### Pattern 2: Internal Helper Prefix Convention
**What:** All non-exported functions prefixed with `_`. Exported functions are the only names in `__all__`.

**When to use:** Consistent with existing `_inject_thinking_blocks`, `_normalize_thinking`, `_filter_sse_line` in proxy.py, and `_parse_model_map` in config.py.

### Pattern 3: AAA Test Structure
**What:** Arrange -> Act -> Assert. Use `monkeypatch` for env vars. Import functions directly (no mock framework).

**When to use:** All existing tests follow this pattern. No pytest fixtures or mocks needed for pure functions.

**Example (from test_codex.py):**
```python
def test_exact_match_overrides_prefix(monkeypatch):
    """精确匹配优先于前缀匹配。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", json.dumps({
        "claude-sonnet-4-6": "deepseek-v4-pro",
        "claude-": "deepseek-v4-flash",
    }))
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("claude-sonnet-4-6") == "deepseek-v4-pro"
```

### Anti-Patterns to Avoid
- **Mutating input dict:** D-03 specifically prohibits this. Always `copy.deepcopy()` at entry.
- **Using `_` as throwaway in lambda/filter:** Creates readability issues with the internal helper `_` prefix convention.
- **Early return on unknown types:** D-08 says WARNING + skip, not abort.
- **Structural repair of anomalous sequences:** D-13 says WARNING + skip reasoning, no repair.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dict deep copy | Manual copy loop | `copy.deepcopy()` | Pure function contract requires non-mutated input. stdlib `copy` is built-in. |
| JSON serialization | String concatenation | `json.dumps()` | Project uses `ensure_ascii=False`. Concatenation is error-prone. |
| Content array extraction | Custom list parsing | `_extract_content_text()` helper | Centralized extraction of `input_text` type items. Keep logic in one place. |
| Logger creation | `logging.getLogger(__name__)` | `logging.getLogger("deepseek-proxy")` | Project-wide logger name convention. Avoid per-module loggers. |
| Model resolution | Reimplementing lookup | `from dsv4_cc_proxy.codex.config import resolve_model` | Phase 1 already delivered this. Import and use. |

**Key insight:** This phase is pure data transformation. The complexity is in the item type dispatch logic (message vs function_call vs function_call_output vs reasoning vs unknown), not in infrastructure. Every "hard problem" already has a solution in the existing codebase (deep copy, json, logger).

## Common Pitfalls

### Pitfall 1: Content Array Extraction Losing Text
**What goes wrong:** Responses API message content can be a string or an array of content blocks. The translation must handle both. If extraction uses the wrong type key (e.g., `"text"` instead of `"input_text"`), text content is silently lost. [ASSUMED based on Responses API content block format]

**Why it happens:** Content blocks in Responses API use `type: "input_text"` (not plain `"text"`) for user input text blocks. This differs from Chat Completions content block format.

**How to avoid:** Verify against OpenAI Responses API spec. D-07 specifies `input_text` type. Write a test with both string content and array content inputs.

**Warning signs:** Tests with array-format content produce empty output.

### Pitfall 2: function_call Without Preceding Assistant Creates Garbage
**What goes wrong:** If function_call is the first item in the input array (no preceding assistant exists), the code must create a synthetic assistant. Without this, tool_calls have nowhere to attach and the translation breaks.

**Why it happens:** DeepSeek Chat Completions format embeds tool_calls inside assistant messages. Responses API has them as standalone input items. This structural difference requires synthetic message creation.

**How to avoid:** D-06 explicitly covers this. Always track "last assistant message index" during input item iteration.

**Warning signs:** Function_call items at the start of the input array produce KeyError or misplaced tool_calls.

### Pitfall 3: reasoning_content Not Injected on Assistant with tool_calls
**What goes wrong:** DeepSeek rejects requests where an assistant message has `tool_calls` but no `reasoning_content` field, returning a 400 error [VERIFIED: multiple community reports, e.g., Spring AI #5027, gptme #918, Zed #44497].

**Why it happens:** Responses API does not have a `reasoning_content` field on assistant messages. The translation must add it. Without D-11's enforce step, the field is absent.

**How to avoid:** D-11 requires a post-processing pass: iterate all translated assistant messages, check `tool_calls` present and `reasoning_content` absent, inject `""`.

**Warning signs:** DeepSeek returns `"Missing reasoning_content field"` error.

### Pitfall 4: instructions Field Being None/Empty Still Generates system Message
**What goes wrong:** If `instructions` is `None` or empty string, and there are no developer role messages, the code might generate `{"role": "system", "content": ""}` which some models reject with empty content.

**Why it happens:** The conditional check is too loose — catches falsy values but not explicit None vs empty string.

**How to avoid:** D-05 says "if both empty, no system message." Check `instructions` is truthy AND there are developer messages to merge. Only generate system message if resulting content is non-empty.

**Warning signs:** Translated request has `{"role": "system", "content": ""}` at position 0.

### Pitfall 5: Reasoning Item Anomalous Sequences
**What goes wrong:** Responses API input may contain reasoning -> user (skip user) or reasoning -> reasoning (consecutive reasoning) sequences. Attempting structural repair would create complex, fragile logic.

**Why it happens:** The API allows unusual item sequences that don't correspond to natural conversation ordering.

**How to avoid:** D-13 says log WARNING and skip anomalous reasoning items. Do not attempt to "fix" the sequence.

**Warning signs:** Multi-item reasoning sequences or reasoning followed by non-assistant items.

## Code Examples

### Translation Mapping (from architecture plan)

| Responses Item | Chat Messages |
|---|---|
| `instructions` (top-level field) | `system` message (placed first) |
| `message` (role=developer) | `system` message (merged into existing system) |
| `message` (role=user) | `user` message |
| `message` (role=assistant) | `assistant` message |
| `function_call` | Appended to preceding assistant's `tool_calls[]` |
| `function_call_output` | `tool` message |
| `reasoning` | Merged into next assistant's `reasoning_content` |

### Example: Simple User Message Translation

Responses API input:
```json
{
  "model": "gpt-5.3-codex",
  "input": [
    {"role": "user", "content": "Hello, how are you?"}
  ],
  "instructions": "You are a helpful assistant."
}
```

Translated Chat Completions:
```json
{
  "model": "deepseek-v4-flash",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello, how are you?"}
  ]
}
```

### Example: Tool Call with function_call (Synthetic Assistant)

Responses API input:
```json
{
  "input": [
    {"role": "user", "content": "Read file /tmp/test"},
    {"type": "function_call", "id": "call_1", "name": "Bash", "arguments": "{\"cmd\": \"cat /tmp/test\"}", "status": "completed"},
    {"type": "function_call_output", "call_id": "call_1", "output": "file contents"}
  ]
}
```

Translated Chat Completions:
```json
{
  "messages": [
    {"role": "user", "content": "Read file /tmp/test"},
    {"role": "assistant", "content": null, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "Bash", "arguments": "{\"cmd\": \"cat /tmp/test\"}"}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": "file contents"}
  ]
}
```

Note: Phase 2 does NOT handle the tool definition format conversion (`type: "function"` wrapping, etc.) — that is Phase 3. The function_call -> tool_calls attachment here is purely structural (adding to the preceding assistant).

### Example: Reasoning Multi-Turn

Responses API input with reasoning items:
```json
{
  "input": [
    {"role": "user", "content": "Analyze this file"},
    {
      "type": "reasoning",
      "id": "rs_1",
      "content": [{"type": "reasoning_text", "text": "I need to read the file first"}],
      "summary": [{"type": "summary_text", "text": "Plan to read file"}]
    },
    {"type": "function_call", "id": "call_1", "name": "Bash", "arguments": "{}", "status": "completed"},
    {"type": "function_call_output", "call_id": "call_1", "output": "data"}
  ]
}
```

Translated Chat Completions (with reasoning folded and empty-string injected):
```json
{
  "messages": [
    {"role": "user", "content": "Analyze this file"},
    {"role": "assistant", "content": null, "reasoning_content": "I need to read the file first", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "Bash", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": "data"}
  ]
}
```

### Example: Content Array Extraction

Responses API content array:
```json
[
  {"type": "input_text", "text": "First part"},
  {"type": "input_text", "text": "Second part"}
]
```

Extracted:
```
"First part\nSecond part"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SQLite caching of reasoning state (ai-adapter approach) | Empty-string reasoning_content injection | 2025-2026 community consensus | Simpler, no storage layer, no cache invalidation. Multiple projects (gptme, Zed, Spring AI) converged on same approach. |
| Responses API direct passthrough | Translation layer with item type dispatch | Phase 2 introduces | Enables Chat Completions upstream which has broader ecosystem support |
| Per-module logger (`__name__`) | Shared `"deepseek-proxy"` logger | Existing project convention | Consistent log output, single log level control |

**Deprecated/outdated:**
- Manual dict copy loops — use `copy.deepcopy()` (D-03 pure function requirement)
- Early exit on unknown item types — D-08 requires WARNING+skip, not abort

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Responses API `input_text` content blocks use `type: "input_text"` (not `"text"`) | Common Pitfalls | Content extraction produces empty string for array-format messages |
| A2 | Responses API `reasoning` item `content` array uses `type: "reasoning_text"` | Code Examples | Reasoning content not extracted, folding produces empty string |
| A3 | Responses API `reasoning` item `summary` is an array of `summary_text` objects | Reasoning folding | Summary text not preserved, though D-10 only says "also preserve summary text" |
| A4 | `function_call` items have structure: `{type, id, name, arguments, status}` | Translation mapping | Item field extraction fails. Mitigation: D-08 WARNING+skip. |
| A5 | `function_call_output` items have structure: `{type, call_id, output}` | Translation mapping | Field extraction fails. Mitigation: D-08 WARNING+skip. |
| A6 | Content blocks only contain `type` and `text` fields (no nested structure) | Content extraction | Extraction misses text in nested structures. |

**Risk assessment:** A1-A5 are MEDIUM risk. They are based on training data about the Responses API format, which is well-documented. A6 is LOW risk — Responses API content blocks are flat.

## Open Questions

No open questions remain. All decisions are locked in CONTEXT.md. The architecture plan, existing code patterns, and DeepSeek API requirements are well-understood.

**Gap:** The exact structure of Responses API input items (function_call's `arguments` format, function_call_output's `output` format, reasoning's `summary` format) could benefit from runtime verification with an actual Codex CLI request dump. If available, capture a live request to confirm field names and nesting before finalizing extraction logic. [ASSUMED fields are currently based on training data]

**Recommendation:** Attempt to capture one live Codex -> proxy request (via `PROXY_DUMP_DIR` or curl test) before or during implementation to validate field structure assumptions.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | Translation functions | Yes | 3.14.5 | — |
| pytest | Tests | Yes | (bundled via pip install -e ".[test]") | — |

**Missing dependencies with no fallback:** None

**Missing dependencies with fallback:** None

**Step 2.6: SKIPPED (no external dependencies outside of what Phase 1 already validated)**

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (same as existing tests) |
| Config file | None — use pyproject.toml in project root if exists, otherwise pytest defaults |
| Quick run command | `python3 -m pytest tests/test_translate.py -v` |
| Full suite command | `python3 -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CODX-03 | input array item type dispatch | unit | `pytest tests/test_translate.py::test_translate_input_items -v` | Wave 0 |
| CODX-03 | user message translation | unit | `pytest tests/test_translate.py::test_translate_user_message -v` | Wave 0 |
| CODX-03 | assistant message translation | unit | `pytest tests/test_translate.py::test_translate_assistant_message -v` | Wave 0 |
| CODX-03 | developer role message -> system | unit | `pytest tests/test_translate.py::test_developer_role_to_system -v` | Wave 0 |
| CODX-03 | content array extraction (input_text) | unit | `pytest tests/test_translate.py::test_extract_content_text -v` | Wave 0 |
| CODX-04 | instructions + developer merge | unit | `pytest tests/test_translate.py::test_merge_instructions_and_developer -v` | Wave 0 |
| CODX-04 | instructions empty -> no system | unit | `pytest tests/test_translate.py::test_no_system_when_empty -v` | Wave 0 |
| CODX-11 | function_call attaches tool_calls | unit | `pytest tests/test_translate.py::test_function_call_to_tool_calls -v` | Wave 0 |
| CODX-11 | synthetic assistant on first function_call | unit | `pytest tests/test_translate.py::test_synthetic_assistant -v` | Wave 0 |
| CODX-11 | function_call_output -> tool message | unit | `pytest tests/test_translate.py::test_function_call_output_to_tool -v` | Wave 0 |
| CODX-14 | reasoning folding into next assistant | unit | `pytest tests/test_translate.py::test_reasoning_folds_to_next_assistant -v` | Wave 0 |
| CODX-14 | empty reasoning_content injection | unit | `pytest tests/test_translate.py::test_inject_reasoning_content -v` | Wave 0 |
| CODX-14 | multiple reasoning items concatenated | unit | `pytest tests/test_translate.py::test_multiple_reasoning_concatenate -v` | Wave 0 |
| CODX-14 | reasoning without subsequent assistant skipped | unit | `pytest tests/test_translate.py::test_reasoning_no_following_assistant -v` | Wave 0 |
| CODX-11 | unknown item type WARNING+skip | unit | `pytest tests/test_translate.py::test_unknown_type_skipped -v` | Wave 0 |
| — | anomalous reasoning->user sequence | unit | `pytest tests/test_translate.py::test_anomalous_reasoning_sequence -v` | Wave 0 |
| — | immutable input (deep copy enforcement) | unit | `pytest tests/test_translate.py::test_translate_request_immutable -v` | Wave 0 |
| — | string content vs array content | unit | `pytest tests/test_translate.py::test_string_content -v` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_translate.py -x -q` (quick smoke test)
- **Per wave merge:** `python3 -m pytest tests/ -v` (full suite including existing tests)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_translate.py` — main test file, all ~15-20 tests
- [ ] No conftest.py needed (pure functions, no shared fixtures)
- [ ] No framework install needed (pytest already in dev dependencies)

## Security Domain

> **Skip reason:** `security_enforcement` is not explicitly set in `.planning/config.json`. Absent key defaults to enabled. However, Phase 2 is a pure data transformation — no HTTP handling, no authentication, no user input (the input is a structured API request body being translated). The translation does not touch secrets, does not execute code, and does not produce output that gets sent to untrusted destinations. Security concerns for this phase are limited to:

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | partial | `translate_request` validates input is a dict. Unknown items are skipped with WARNING (D-08). No injection risk since output is JSON sent to DeepSeek API over TLS. |
| V6 Cryptography | no | Phase 2 does not handle encryption, hashing, or signing. |

### Known Threat Patterns

No threat patterns apply to a pure translation function. The translated output is sent over HTTPS to DeepSeek's API (handled by Phase 5 HTTP layer). The translation layer does not introduce security vulnerabilities because:

1. It receives structured dicts, not raw text — no injection surface
2. It produces JSON output, not executed code
3. It does not read/write files or network sockets
4. It does not handle authentication tokens (those pass through unmodified in Phase 5)
5. The logger is a shared project logger with controlled log levels

## Sources

### Primary (HIGH confidence)
- [CONTEXT.md] - All 13 locked decisions (D-01 through D-13) for Phase 2
- [REQUIREMENTS.md] - CODX-03, CODX-04, CODX-11, CODX-14 requirement definitions
- [Architecture plan] - Input translation mapping table, Responses->Chat field mapping, reasoning multi-turn strategy
- [proxy.py] - Existing pure function pattern, `_`-prefix convention, logger convention, dict-based operations
- [config.py] - Module-level env var pattern, `resolve_model()` API, error handling pattern
- [test_codex.py] - AAA test pattern with monkeypatch, reload for env var configuration
- [test_proxy.py] - Pure function import pattern, test structure

### Secondary (MEDIUM confidence)
- [WebSearch: OpenAI Responses API input items] - Verified item types (message, function_call, function_call_output, reasoning) and known constraints
- [WebSearch: DeepSeek reasoning_content requirement] - Verified 400 error on missing reasoning_content, community convergence on empty-string fix across multiple frameworks
- [ROADMAP.md] - Phase 2 success criteria definitions

### Tertiary (LOW confidence)
- [ASSUMED] Responses API input item field names and structures (A1-A6)
- [ASSUMED] DeepSeek assistant message `content: None` allowed with tool_calls present — community reports suggest `content: ""` as safer alternative if `None` causes issues. If problems arise during testing, switch to `content: ""` instead.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - purely Python stdlib, already established in Phase 1
- Architecture: HIGH - all decisions locked in CONTEXT.md, patterns verified in existing code
- Pitfalls: MEDIUM - DeepSeek validation requirement well-documented; Responses API field names based on training data

**Research date:** 2026-06-05
**Valid until:** 2026-07-05 (30 days — Responses API is stable, DeepSeek requirements stable)
