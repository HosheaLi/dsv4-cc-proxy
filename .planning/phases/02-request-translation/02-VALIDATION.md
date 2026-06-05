---
phase: 2
slug: request-translation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-05
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing project framework) |
| **Config file** | `pyproject.toml` (project root) |
| **Quick run command** | `python3 -m pytest tests/test_translate.py -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds (unit tests, no I/O) |

---

## Sampling Rate

- **After every task commit:** `python3 -m pytest tests/test_translate.py -x -q`
- **After every plan wave:** `python3 -m pytest tests/ -v` (full suite including existing tests)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-XX-01 | XX | 1 | CODX-03 | — | input item type dispatch | unit | `pytest tests/test_translate.py -k "input_items" -v` | ❌ W0 | ⬜ pending |
| 02-XX-02 | XX | 1 | CODX-03 | — | user/assistant message translation | unit | `pytest tests/test_translate.py -k "message" -v` | ❌ W0 | ⬜ pending |
| 02-XX-03 | XX | 1 | CODX-03 | — | developer role -> system | unit | `pytest tests/test_translate.py -k "developer" -v` | ❌ W0 | ⬜ pending |
| 02-XX-04 | XX | 1 | CODX-03 | — | content array extraction (input_text) | unit | `pytest tests/test_translate.py -k "extract_content" -v` | ❌ W0 | ⬜ pending |
| 02-XX-05 | XX | 1 | CODX-04 | — | instructions + developer merge | unit | `pytest tests/test_translate.py -k "merge_system" -v` | ❌ W0 | ⬜ pending |
| 02-XX-06 | XX | 1 | CODX-04 | — | empty instructions -> no system | unit | `pytest tests/test_translate.py -k "no_system" -v` | ❌ W0 | ⬜ pending |
| 02-XX-07 | XX | 1 | CODX-11 | — | function_call attaches tool_calls | unit | `pytest tests/test_translate.py -k "tool_calls" -v` | ❌ W0 | ⬜ pending |
| 02-XX-08 | XX | 1 | CODX-11 | — | synthetic assistant on first function_call | unit | `pytest tests/test_translate.py -k "synthetic" -v` | ❌ W0 | ⬜ pending |
| 02-XX-09 | XX | 1 | CODX-11 | — | function_call_output -> tool message | unit | `pytest tests/test_translate.py -k "function_call_output" -v` | ❌ W0 | ⬜ pending |
| 02-XX-10 | XX | 1 | CODX-14 | — | reasoning folding into next assistant | unit | `pytest tests/test_translate.py -k "reasoning_folds" -v` | ❌ W0 | ⬜ pending |
| 02-XX-11 | XX | 1 | CODX-14 | — | empty reasoning_content injection | unit | `pytest tests/test_translate.py -k "inject_reasoning" -v` | ❌ W0 | ⬜ pending |
| 02-XX-12 | XX | 1 | CODX-14 | — | multiple reasoning concatenation | unit | `pytest tests/test_translate.py -k "multiple_reasoning" -v` | ❌ W0 | ⬜ pending |
| 02-XX-13 | XX | 1 | CODX-14 | — | reasoning without subsequent assistant | unit | `pytest tests/test_translate.py -k "no_following" -v` | ❌ W0 | ⬜ pending |
| 02-XX-14 | XX | 1 | CODX-11 | — | unknown item type WARNING+skip | unit | `pytest tests/test_translate.py -k "unknown_type" -v` | ❌ W0 | ⬜ pending |
| 02-XX-15 | XX | 1 | — | — | anomalous reasoning->user sequence | unit | `pytest tests/test_translate.py -k "anomalous" -v` | ❌ W0 | ⬜ pending |
| 02-XX-16 | XX | 1 | — | — | immutable input (deep copy enforcement) | unit | `pytest tests/test_translate.py -k "immutable" -v` | ❌ W0 | ⬜ pending |
| 02-XX-17 | XX | 1 | — | — | string content vs array content | unit | `pytest tests/test_translate.py -k "string_content" -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Task IDs (XX = plan number) to be filled when PLAN.md files are generated.*

---

## Wave 0 Requirements

- [ ] `tests/test_translate.py` — all ~15-20 unit tests for CODX-03, CODX-04, CODX-11, CODX-14
- [ ] No conftest.py needed (pure functions, no shared fixtures)
- [ ] No framework install needed (pytest already in dev dependencies)

---

## Manual-Only Verifications

*None — all Phase 2 behaviors are pure data transformations with automated unit test coverage.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
