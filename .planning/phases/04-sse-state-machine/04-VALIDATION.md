---
phase: 04
slug: sse-state-machine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-06
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + httpx (async) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/test_sse.py -v` |
| **Full suite command** | `pytest tests/ -v --cov=dsv4_cc_proxy` |
| **Estimated runtime** | ~3 seconds (quick) / ~15 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -v`
- **After every plan wave:** Run `pytest tests/ -v --cov=dsv4_cc_proxy`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | CODX-05 | N/A | N/A | unit | `pytest tests/test_sse.py -v` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | CODX-06 | N/A | N/A | unit | `pytest tests/test_sse.py -v` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | CODX-08 | N/A | N/A | unit | `pytest tests/test_sse.py -v` | ❌ W0 | ⬜ pending |
| 04-01-04 | 01 | 1 | CODX-09 | N/A | N/A | unit | `pytest tests/test_sse.py -v` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | CODX-12 | N/A | N/A | unit | `pytest tests/test_translate.py -v` | ✅ | ⬜ pending |
| 04-02-02 | 02 | 1 | CODX-13 | N/A | N/A | unit | `pytest tests/test_sse.py -v` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 1 | CODX-15 | N/A | N/A | unit | `pytest tests/ -v --cov` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_sse.py` — stubs for 8 test scenarios (D-15): text stream, reasoning stream, reasoning→text transition, tool call stream, multi-tool parallel, text→tool transition, full lifecycle, edge cases
- [ ] `tests/conftest.py` — shared fixtures if needed (async generator helpers, mock SSE chunk builders)
- [ ] Existing test infrastructure covers all phase requirements (`tests/test_translate.py` exists, `pyproject.toml` pytest config exists)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real DeepSeek Chat SSE → Responses SSE end-to-end | CODX-08 | Requires live API key and network connectivity | `curl` proxy endpoint with streaming request, verify event ordering via `grep -E "^event:"` |
| Codex CLI integration smoke test | CODX-05, CODX-06 | Requires Codex CLI binary with custom base URL config | Configure Codex to use proxy, send chat request, verify tool use and text streaming work |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
