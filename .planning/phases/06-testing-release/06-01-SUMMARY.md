---
phase: 06-testing-release
plan: 01
subsystem: testing
tags: [coverage, testing, proxy, main]
dependency_graph:
  requires: []
  provides: [__main__.py 86% cov, proxy.py 87% cov]
  affects: [release pipeline]
tech-stack:
  added: []
  patterns:
    - "AAA pattern for pure function tests"
    - "monkeypatch + tmp_path + mock for CLI tests"
    - "TestClient + _MockStreamResponse/_MockJSONResponse for HTTP integration tests"
key-files:
  created:
    - tests/test_main.py (206 lines)
  modified:
    - tests/test_responses.py (+355 lines)
    - tests/test_proxy.py (+80 lines)
decisions:
  - "test_stop_pidfile_corrupted: wraps main() in pytest.raises(ValueError) since _stop() doesn't handle ValueError"
  - "Filtered stream test uses thinking disabled in request (not enabled) to exercise the correct code path: strip_thinking=True required for filtered_stream"
metrics:
  duration: ~15 min
  completed: 2026-06-07
  total_tests: 144 (was 111 before)

---

# Phase 6 Plan 1: Test Coverage Expansion Summary

**One-liner:** Expanded test coverage for `__main__.py` (0% to 86%) and `proxy.py` (baseline to 87%) via 33 new tests in three files.

## Summary

Created `tests/test_main.py` (10 CLI unit tests), added 4 proxy() handler coverage classes to `tests/test_responses.py` (14 new tests), and appended 9 edge case tests to `tests/test_proxy.py`. Full suite grew from 111 to 144 tests, all passing with zero regression.

## Tasks Executed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create tests/test_main.py — CLI unit tests | 3f2d22d | tests/test_main.py (NEW) |
| 2 | Add proxy.py coverage tests to tests/test_responses.py | 16cd18b | tests/test_responses.py (+175 lines) |
| 3 | Add edge case tests to tests/test_proxy.py | 9ffdb17 | tests/test_proxy.py (+80), test_responses.py (+177) |

## Coverage Results

| Module | Before | After | Target |
|--------|--------|-------|--------|
| `dsv4_cc_proxy/__main__.py` | 0% | 86% | >= 85% |
| `dsv4_cc_proxy/proxy.py` | ~61% (baseline) | 87% | >= 85% |

## Test Inventory (144 total)

| Test File | Count | New | Description |
|-----------|-------|-----|-------------|
| test_codex.py | 6 | 0 | Codex config model mapping |
| test_main.py | 10 | 10 | CLI entry point |
| test_proxy.py | 31 | 9 | Pure function tests |
| test_responses.py | 35 | 14 | HTTP integration tests |
| test_sse.py | 17 | 0 | SSE state machine |
| test_tools.py | 21 | 0 | Tool format conversion |
| test_translate.py | 24 | 0 | Request translation |

## Coverage Detail

### `tests/test_main.py` (10 tests)
- stop PID file not found -> SystemExit(1)
- stop normal SIGTERM -> signal sent, file cleaned
- stop process already dead -> cleanup without crash
- stop graceful timeout -> SIGKILL after wait
- main already running -> SystemExit(1)
- main stale pidfile -> cleanup + restart
- main normal startup -> uvicorn.run called
- main startup with DUMP_DIR -> no crash
- VERSION importable
- stop corrupted pidfile -> ValueError

### `tests/test_responses.py` additions (14 tests in 6 new classes)
- TestProxyPassthrough (4): health, models passthrough, non-deepseek model, thinking disabled
- TestProxyFilteredStream (3): SSE thinking stripping, text passthrough, 200 status
- TestProxyBuildRequest (1): upstream error -> 502
- TestProxyConnectionError (1): ConnectError -> 502
- TestProxyThinkingEnabled (2): thinking enabled + tool_use, thinking adaptive
- TestResponsesConnectionError (2): stream/non-stream handler connection errors
- TestResponsesTranslationError (1): translate_request failure -> 400

### `tests/test_proxy.py` additions (9 tests)
- _thinking_requested: non-dict thinking, no thinking key, empty data
- _normalize_thinking: no messages key, unknown type
- _inject_thinking_blocks: non-dict thinking, no messages
- _filter_sse_line: wrong index delta, content_block_stop tracking

## Deviations from Plan

**1. [Rule 2] Added 5 additional coverage tests beyond plan scope**
- **Found during:** Task 2 verification (proxy.py coverage 83% needed to reach 85%)
- **Issue:** proxy.py uncovered code paths in codex handlers (connection errors, translate_request errors) and thinking-enabled proxy path
- **Fix:** Added TestProxyThinkingEnabled, TestResponsesConnectionError, TestResponsesTranslationError classes
- **Files modified:** tests/test_responses.py
- **Commit:** 9ffdb17

## Verification Results

- `python -m pytest tests/test_main.py -v --tb=short` — 10/10 passed
- `python -m pytest tests/test_responses.py -v --tb=short` — 35/35 passed
- `python -m pytest tests/test_proxy.py -v --tb=short` — 31/31 passed
- `python -m pytest tests/ -v` — 144/144 passed, zero regression
- `python -m pytest tests/ --cov=dsv4_cc_proxy/__main__.py --cov-report=term` — 86%
- `python -m pytest tests/ --cov=dsv4_cc_proxy/proxy.py --cov-report=term` — 87%

## Self-Check: PASSED

- [x] tests/test_main.py exists (206 lines, 10 test functions)
- [x] tests/test_responses.py contains all 4 plan-specified classes + 3 additional classes
- [x] tests/test_proxy.py contains 9 new edge case functions
- [x] Full suite 144/144 passing
- [x] proxy.py coverage 87%
- [x] __main__.py coverage 86%
- [x] All tasks committed individually (3f2d22d, 16cd18b, 9ffdb17)
