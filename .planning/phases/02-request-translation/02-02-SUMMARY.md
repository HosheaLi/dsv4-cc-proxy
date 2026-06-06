---
phase: 02-request-translation
plan: 02
subsystem: codex-translate
tags:
  - test
  - translate
  - unit-test
  - codex
requires: []
provides:
  - tests/test_translate.py
affects: []
tech-stack:
  added: []
  patterns:
    - AAA pattern with no fixtures or mocks
    - monkeypatch.setenv + reload for env var dependent tests
    - copy.deepcopy for immutability verification
    - Inline dict construction for test data
key-files:
  created:
    - tests/test_translate.py
  modified: []
decisions:
  - All env-var-dependent tests reload both codex.config and codex.translate modules
  - function_call attached to existing assistant produces 2 messages (not 3) — the function_call tool_calls are appended to the existing assistant, not a separate message
metrics:
  duration: 0.03h
  completed: "2026-06-06"
---

# Phase 2 Plan 2: translate_request Test Suite Summary

## One-liner

Created `tests/test_translate.py` with 23 test cases across 6 groups covering all `translate_request()` translation behaviors, following AAA pattern with zero fixtures or mocks.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create test_translate.py with comprehensive test cases | `c1d4c0e` | `tests/test_translate.py` |

## Requirements Coverage

| Requirement | Tests | Status | Notes |
|-------------|-------|--------|-------|
| CODX-03 | `test_message_content_array`, `test_string_content`, `test_assistant_message`, `test_simple_user_message` | Verified | input array item type dispatch including user/assistant messages, content array extraction |
| CODX-04 | `test_merge_instructions_and_developer`, `test_no_system_when_empty`, `test_instructions_only_no_developer`, `test_developer_only_no_instructions` | Verified | System message merge from instructions + developer role, no empty system when both empty |
| CODX-11 | `test_function_call_to_tool_calls`, `test_synthetic_assistant`, `test_multiple_function_calls`, `test_function_call_output_to_tool` | Verified | function_call -> tool_calls attach, synthetic assistant, function_call_output -> tool role |
| CODX-14 | `test_reasoning_folds_to_next_assistant`, `test_reasoning_content_extraction`, `test_inject_reasoning_content`, `test_reasoning_no_following_assistant`, `test_reasoning_anomalous_sequence` | Verified | Reasoning folding, content extraction, empty string injection, edge cases |

## Test Groups

### Group 1: Basic Message Translation (6 tests)
- `test_simple_user_message` — instructions + user message -> system + user
- `test_string_content` — plain string content passes through
- `test_message_content_array` — array content (input_text) joined with \n
- `test_message_content_none` — None content passes through
- `test_assistant_message` — assistant role preserved
- `test_no_input_empty` — empty input with no instructions = empty messages

### Group 2: System Message Merge (4 tests)
- `test_merge_instructions_and_developer` — instructions + developer merged with \n\n (CODX-04)
- `test_no_system_when_empty` — no system when both empty (Pitfall 4)
- `test_instructions_only_no_developer` — system from instructions only
- `test_developer_only_no_instructions` — system from developer only

### Group 3: Tool Call Translation (4 tests)
- `test_function_call_to_tool_calls` — function_call attaches to existing assistant (CODX-11)
- `test_synthetic_assistant` — synthetic assistant when no preceding assistant (D-06)
- `test_multiple_function_calls` — multiple calls attach to same assistant
- `test_function_call_output_to_tool` — function_call_output -> tool role (CODX-11)

### Group 4: Reasoning Processing (5 tests)
- `test_reasoning_folds_to_next_assistant` — reasoning folded into assistant (CODX-14, D-09, D-10)
- `test_reasoning_content_extraction` — multiple reasoning_text blocks joined with \n
- `test_inject_reasoning_content` — empty string injection on tool_calls assistant (D-11)
- `test_reasoning_no_following_assistant` — trailing reasoning discarded (D-09)
- `test_reasoning_anomalous_sequence` — reasoning -> user sequence logged, skipped (D-13)

### Group 5: Edge Cases (2 tests)
- `test_unknown_type_skipped` — unknown type logged and skipped (D-08)
- `test_translate_request_immutable` — input dict not mutated (D-03)

### Group 6: Model Resolution (2 tests)
- `test_model_resolved_via_config` — model mapped via CODEX_MODEL_MAP env var
- `test_max_output_tokens_renamed` — max_output_tokens -> max_tokens

## Results

| Metric | Value |
|--------|-------|
| Test count | 23 |
| Pass rate | 23/23 (100%) |
| Existing tests | 28/28 (100%, no regression) |
| Total tests | 51/51 (100%) |
| File size | 562 lines |
| Execution time | 0.05s |

## Deviations from Plan

**None** — the plan was executed exactly as written. All 13 specified acceptance criteria are met.

## Edge Cases Discovered

1. **`test_function_call_to_tool_calls` assertion fix**: The plan expected 3 messages for a user+assistant+function_call input, but the actual behavior produces 2 messages — the function_call is attached to the existing assistant via `tool_calls`, not added as a separate message. The assertion was corrected to match the actual pure-function behavior (2 messages, with assistant having `tool_calls` plus `reasoning_content: ""` via D-11 injection).

2. **Config reload requirement for env-var-dependent tests**: Tests that verify model resolution via `CODEX_MODEL_MAP` or `CODEX_DEFAULT_MODEL` env vars must reload both `codex.config` AND `codex.translate` modules. Reloading only the translate module doesn't cascade to re-import config values. This follows the existing `test_codex.py` pattern.

## Known Stubs

None found.

## Self-Check: PASSED
- `tests/test_translate.py` exists: FOUND (562 lines)
- All 23 tests pass: VERIFIED
- No regression in existing tests: VERIFIED
- Commit `c1d4c0e` exists: VERIFIED
