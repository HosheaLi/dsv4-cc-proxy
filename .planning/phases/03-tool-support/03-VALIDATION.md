---
phase: 03
slug: tool-support
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-06
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pyproject.toml` — `[tool.pytest.ini_options]` with `testpaths = ["tests"]` |
| **Quick run command** | `python3 -m pytest tests/test_tools.py -v` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/test_tools.py -v -x`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green + coverage >=90% on tools.py
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | CODX-07 | — | N/A | unit | `python3 -m pytest tests/test_tools.py -k "test_convert" -v` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | CODX-10 | — | N/A | unit | `python3 -m pytest tests/test_tools.py -k "test_clean" -v` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | CODX-10 | — | N/A | unit | `python3 -m pytest tests/test_tools.py -k "test_recursive" -v` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | CODX-07, CODX-10 | — | N/A | unit | `python3 -m pytest tests/test_tools.py -k "test_edge" -v` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 1 | CODX-07 | — | N/A | unit | `pytest tests/ -v` (integration) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tools.py` — test stubs covering all CODX-07, CODX-10 behaviors
- [ ] Framework install: `pip install -e ".[test]"` — already established by Phase 1
- [ ] `tests/conftest.py` — shared fixtures for sample tool definitions (optional, may use inline fixtures)

---

## Manual-Only Verifications

*None — all phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
