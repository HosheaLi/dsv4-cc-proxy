---
phase: 02-request-translation
plan: 01
subsystem: api-translation
tags: [responses-api, chat-completions, translate, codex, deepseek]

# Dependency graph
requires:
  - phase: 01-foundation-config
    provides: resolve_model(), CODEX_DEFAULT_MODEL, CODEX_UPSTREAM
provides:
  - translate_request() pure function: Responses API body -> Chat Completions body
  - Input item type dispatch (message, function_call, function_call_output, reasoning)
  - instructions + developer role message merging into system message
  - Empty-string reasoning_content injection for DeepSeek validation
affects: [02-request-translation, 03-tool-definition, 04-sse-streaming, 05-routing-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure function with copy.deepcopy for immutable input"
    - "Role-only input item shorthand support (no explicit type field)"
    - "WARNING + skip for unknown input item types (non-abort)"
    - "WARNING + discard for anomalous reasoning sequences (no structural repair)"

key-files:
  created:
    - dsv4_cc_proxy/codex/translate.py
  modified:
    - dsv4_cc_proxy/codex/__init__.py

key-decisions:
  - "D-03: translate_request uses copy.deepcopy to guarantee input immutability"
  - "D-07: Content arrays extract only type=input_text blocks, joined by newline"
  - "D-08: Unknown input item types are logged at WARNING level and skipped, never crash"
  - "D-09: Reasoning items fold into subsequent assistant's reasoning_content"
  - "D-13: Anomalous reasoning sequences (reasoning->non-assistant) WARNING+discard, no repair"

patterns-established:
  - "Role-only shorthand (no type=message) is handled as legitimate message format"
  - "All translations are stateless dict-to-dict transformations"

requirements-completed:
  - CODX-03
  - CODX-04
  - CODX-11
  - CODX-14

# Metrics
duration: 2m 22s
completed: 2026-06-06
---

# Phase 02 Plan 01: Request Translation Core -- Summary

**Pure function translate_request() converting OpenAI Responses API request bodies to DeepSeek Chat Completions format, with full input item type dispatch (message, function_call, function_call_output, reasoning) and DeepSeek-specific reasoning_content injection**

## Performance

- **Duration:** 2m 22s
- **Started:** 2026-06-06T03:37:45Z
- **Completed:** 2026-06-06T03:40:07Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `translate.py` with `translate_request` entry point and 4 internal helper functions
- Implemented all 13 locked decisions (D-01 through D-13) for request translation
- Input item type dispatch: message (user/assistant/developer), function_call, function_call_output, reasoning, unknown
- instructions + developer role messages merge into single system message with `\n\n` separator
- function_call without preceding assistant creates synthetic assistant message with tool_calls
- function_call_output maps to tool role message
- Reasoning items fold into subsequent assistant's reasoning_content field
- Post-processing ensures every assistant with tool_calls has reasoning_content (empty string if missing)
- Immutable input guarantee via copy.deepcopy at entry
- Updated `__init__.py` to export translate_request alongside resolve_model

## Task Commits

Each task was committed atomically:

1. **Task 1: Create translate.py with all request translation functions** - `20bf15d` (feat)
2. **Task 2: Update **init**.py to export translate_request** - `b0e9a9c` (feat)

## Files Created/Modified

- `dsv4_cc_proxy/codex/translate.py` - 286-line translation module with translate_request entry point and all internal helper functions
- `dsv4_cc_proxy/codex/__init__.py` - Updated to export translate_request alongside resolve_model

## Decisions Made

- Followed plan exactly as written. All 13 locked decisions (D-01 through D-13) from CONTEXT.md implemented.
- Input items with role-only shorthand (type field absent, e.g. `{"role": "user", "content": "..."}`) treated as message items matching the plan's test expectations. This was necessary for the plan's smoke test to work.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Role-only input items without explicit type field were not dispatched**

- **Found during:** Task 1 (Create translate.py)
- **Issue:** The `item_type` dispatch used `item.get("type", item.get("role", ""))`. For input items like `{"role": "user", "content": "Hello"}` (no `type` field), `item_type` resolved to `"user"` which didn't match the `"message"` branch, falling through to the unknown-type WARNING handler. This broke the plan's own smoke test.
- **Fix:** Added `item_type in ("user", "assistant", "developer")` as an additional condition alongside `item_type == "message"`, treating role-only items as shorthand message items. The role is derived from `item.get("role", item_type)` to handle both explicit and shorthand cases.
- **Files modified:** `dsv4_cc_proxy/codex/translate.py`
- **Verification:** Plan smoke test passes; all acceptance criteria verified
- **Committed in:** 20bf15d (part of Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minimal. The role-only shorthand is a legitimate Responses API input format pattern. The fix correctly handles both explicit `type="message"` and implicit role-only formats.

## Issues Encountered

None -- plan executed cleanly. The single auto-fix was caught during initial verification and resolved within the same task commit.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. translate.py is a pure data transformation -- no I/O, no network, no auth. The threat model's assessment stands: all threats are mitigated by the pure-function design and defensive coding patterns.

## Known Stubs

None. All functions are fully implemented and tested against acceptance criteria. No placeholder values, no mock data, no "coming soon" patterns.

## Next Phase Readiness

- `translate_request()` is complete and importable from `dsv4_cc_proxy.codex`
- Ready for Phase 02 Plan 02 (test phase) and Phase 3 (tool definition translation)
- A comprehensive test file `tests/test_translate.py` should be created in Wave 0 (parallel agent) or Wave 2 to cover all input item type dispatch paths

---

*Phase: 02-request-translation*
*Completed: 2026-06-06*
