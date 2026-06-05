---
phase: 1
slug: foundation-config
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-05
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `python3 -m pytest tests/test_codex.py -v` |
| **Full suite command** | `python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/test_codex.py -v`
- **After every plan wave:** Run `python3 -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | CODX-16 | N/A | N/A (config only) | unit | `pytest tests/test_codex.py::test_fallback_to_default -x` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | CODX-17 | N/A | N/A (config only) | unit | `pytest tests/test_codex.py::test_exact_match -x` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | CODX-17 | N/A | N/A (config only) | unit | `pytest tests/test_codex.py::test_prefix_match_longest_wins -x` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 1 | CODX-18 | N/A | N/A (config only) | unit | `pytest tests/test_codex.py::test_fallback_to_default -x` | ❌ W0 | ⬜ pending |
| 1-01-05 | 01 | 1 | CODX-18 | T-1-01 | Malformed JSON → empty dict, never crashes | unit | `pytest tests/test_codex.py::test_invalid_json_map_falls_back -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_codex.py` — covers CODX-16, CODX-17, CODX-18
- [ ] `tests/conftest.py` — shared fixtures (if needed for monkeypatching)
- [ ] Install: `pip install -e ".[test]"` — already done

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `from dsv4_cc_proxy.codex import resolve_model` works after `pip install -e .` | CODX-16/17/18 | Imports can pass in tests but fail from external import due to packaging issues | `python3 -c "from dsv4_cc_proxy.codex import resolve_model; print(resolve_model('test'))"` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
