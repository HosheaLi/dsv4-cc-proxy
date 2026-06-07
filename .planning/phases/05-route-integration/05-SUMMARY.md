---
phase: 05-route-integration
plan: 01
subsystem: api
tags: codex, responses-api, sse, starlette, httpx

requires:
  - phase: 01-foundation-config
    provides: codex/config.py (CODEX_UPSTREAM, resolve_model)
  - phase: 02-request-translation
    provides: codex/translate.py (translate_request)
  - phase: 03-tool-support
    provides: codex/tools.py (convert_tools, _clean_schema)
  - phase: 04-sse-state-machine
    provides: codex/sse.py (translate_sse_stream)

provides:
  - POST /v1/responses HTTP handler for Codex CLI protocol compatibility
  - POST /v1/responses/compact stub returning 501
  - SSE streaming for stream:true requests via translate_sse_stream
  - Non-streaming JSON translation via _translate_chat_to_responses
  - DeepSeek upstream error translation to Responses API error format
  - Authorization header passthrough
  - HTTP integration test suite (21 tests) with mock upstream

affects:
  - 06-cli-integration
  - e2e-testing

tech-stack:
  added: []
  patterns:
    - HTTP handler with stream/non-stream branching at entry point
    - Mock upstream response classes for Starlette TestClient integration tests
    - Authentication header passthrough without validation

key-files:
  created:
    - tests/test_responses.py
  modified:
    - dsv4_cc_proxy/proxy.py

key-decisions:
  - "Mock upstream responses with _MockStreamResponse and _MockJSONResponse classes instead of real http connection"
  - "ERROR_CODE_MAP includes 408/422 in addition to plan-specified codes for completeness"
  - "_translate_chat_to_responses placed in proxy.py (not translate.py) to keep translation-level code in codex/ and handler-level glue in proxy.py"
  - "_MockJSONResponse supports both json() and aiter_bytes() for use in both stream and non-stream error paths"

patterns-established: []

requirements-completed:
  - CODX-01
  - CODX-02
  - CODX-19
  - CODX-20
  - CODX-21

duration: 12min
completed: 2026-06-07
---

# Phase 05 Plan 01: Route Integration Summary

**POST /v1/responses HTTP routes, SSE streaming proxy, non-streaming JSON translation, DeepSeek error translation, and 21 HTTP integration tests**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-07T01:00:00Z
- **Completed:** 2026-06-07T01:12:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Implemented `responses_handler` for POST /v1/responses with stream/non-stream branching
- Implemented `compact_handler` returning 501 for POST /v1/responses/compact
- Implemented `_handle_stream_response` using translate_sse_stream async generator
- Implemented `_handle_non_stream_response` translating Chat JSON to Responses API format
- Implemented `_translate_upstream_error` with full error code map (400-503)
- Implemented `_translate_chat_to_responses` supporting reasoning_content, content, and tool_calls
- Added ERROR_CODE_MAP with 10 HTTP status code mappings including 408 and 422
- Registered new routes in create_app() before catch-all {path:path} route
- Wrote 21 HTTP integration tests covering compact 501, invalid JSON, streaming lifecycle, non-streaming JSON, auth passthrough, upstream error translation, and pure function tests
- All 111 tests pass (90 existing + 21 new), zero regression
- Coverage excluding __main__.py at 90.9%

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement responses_handler and compact_handler** - `a61f7a3` (feat)
2. **Task 2: Write HTTP integration tests** - `b226f45` (test)

## Files Created/Modified

- `dsv4_cc_proxy/proxy.py` — Added codex module imports, ERROR_CODE_MAP, _build_error, _translate_upstream_error, _translate_chat_to_responses, _iter_lines, _handle_stream_response, _handle_non_stream_response, responses_handler, compact_handler, updated create_app() routes (+249 lines)
- `tests/test_responses.py` — New HTTP integration test file with mock upstream classes, 11 test groups across 21 test functions (+512 lines)

## Decisions Made

- Mock upstream responses with `_MockStreamResponse` and `_MockJSONResponse` classes instead of real HTTP connections — enables deterministic testing without network
- ERROR_CODE_MAP includes 408/422 in addition to plan-specified codes for completeness, matching the plan's discretionary area guidance
- `_translate_chat_to_responses` placed in proxy.py (not translate.py) to keep translation-level code in codex/ package and handler-level glue in proxy.py
- `_MockJSONResponse` supports both `json()` and `aiter_bytes()` for use in both stream and non-stream error paths

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added aiter_bytes() to _MockJSONResponse**
- **Found during:** Task 2 (test_stream_upstream_401_error)
- **Issue:** `_handle_stream_response` calls `aiter_bytes()` on non-200 upstream responses to read the error body. The `_MockJSONResponse` class lacked this method, causing the streaming error path test to fail with AttributeError
- **Fix:** Added `aiter_bytes()` generator yielding `self.content` to `_MockJSONResponse`
- **Files modified:** tests/test_responses.py
- **Verification:** `test_stream_upstream_401_error` passes, no regression
- **Committed in:** b226f45 (Task 2 commit)

**2. [Rule 3 - Blocking] Removed unused REQUEST_TOOL_CALL_KEYS constant**
- **Found during:** Task 1 self-review
- **Issue:** Unused constant `REQUEST_TOOL_CALL_KEYS` inadvertently added to proxy.py (not part of plan specification)
- **Fix:** Removed the constant
- **Files modified:** dsv4_cc_proxy/proxy.py
- **Verification:** All 111 tests pass
- **Committed in:** a61f7a3 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 missing critical functionality, 1 blocking/unused)
**Impact on plan:** Minor. Mock fix necessary for test correctness. No scope creep.

## Issues Encountered

- `StreamingResponse` from a `responses_handler` that uses `AsyncMock` inside `TestClient` requires handling the streaming path correctly — the error path in `_handle_stream_response` reads error body via `aiter_bytes()`, requiring mock to support this interface

## User Setup Required

None — no external service configuration required. Existing env vars (CODEX_UPSTREAM, CODEX_DEFAULT_MODEL, CODEX_MODEL_MAP) remain unchanged.

## Next Phase Readiness

- POST /v1/responses routes are registered and functional for both streaming and non-streaming modes
- All 4 codex translation modules (config, translate, tools, sse) are fully integrated and accessible via the HTTP handler
- Ready for Phase 6 CLI integration and end-to-end testing with Codex CLI
- Threat model mitigations are in place: auth passthrough (no recording), request body validation, connection cleanup in finally blocks, error message sanitization

---
*Phase: 05-route-integration Plan: 01*
*Completed: 2026-06-07*
