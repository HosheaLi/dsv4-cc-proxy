---
phase: 06
slug: testing-release
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-07
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-cov 7.1.0 |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `python -m pytest tests/ -x` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Coverage command** | `python -m pytest tests/ --cov=dsv4_cc_proxy --cov-report=term` |

---

## Sampling Rate

- **After every task commit:** `python -m pytest tests/test_e2e.py tests/test_responses.py tests/test_main.py -x`
- **After every plan wave:** `python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | D-01 | T-06-01 / — | proxy.py coverage ≥85% | unit | `python -m pytest tests/ --cov=dsv4_cc_proxy/proxy.py --cov-report=term` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | D-01 | T-06-02 / — | __main__.py coverage ≥85% | unit | `python -m pytest tests/ --cov=dsv4_cc_proxy/__main__.py --cov-report=term` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | D-05 | — / N/A | test_responses.py 补充缺失路径 | unit | `python -m pytest tests/test_responses.py -x` | ✅ | ⬜ pending |
| 06-02-01 | 02 | 1 | D-02 | T-06-03 / — | E2E non-stream → JSON response | integration | `python -m pytest tests/test_e2e.py -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | D-02 | T-06-04 / — | E2E stream → SSE events | integration | `python -m pytest tests/test_e2e.py -x` | ❌ W0 | ⬜ pending |
| 06-02-03 | 02 | 1 | D-02 | T-06-05 / — | E2E compact → 501 | integration | `python -m pytest tests/test_e2e.py -x` | ❌ W0 | ⬜ pending |
| 06-02-04 | 02 | 1 | D-02 | T-06-06 / — | E2E auth passthrough | integration | `python -m pytest tests/test_e2e.py -x` | ❌ W0 | ⬜ pending |
| 06-03-01 | 03 | 1 | D-04 | — / N/A | 测试重构无行为变化 | manual | `python -m pytest tests/ -v` (regression) | ✅ | ⬜ pending |
| 06-04-01 | 04 | 2 | D-07,D-08,D-09,D-10 | — / N/A | 文档更新覆盖所有环境变量和端点 | manual | `grep` content checks | ✅ | ⬜ pending |
| 06-05-01 | 05 | 2 | D-14,D-15,D-17 | — / N/A | CI PyPI OIDC + badge + semver tags | CI | push tag → verify Actions | ✅ | ⬜ pending |
| 06-06-01 | 06 | 2 | D-11,D-12,D-13 | T-06-07 / — | 版本号 2.0.0 + tag + 多渠道发布 | release | tag push → verify Docker/PyPI/GitHub | ✅ | ⬜ pending |
| 06-07-01 | 07 | 3 | D-06 | — / N/A | 全量回归测试零失败 | regression | `python -m pytest tests/ -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_main.py` — stubs for __main__.py CLI test coverage
- [ ] `tests/test_e2e.py` — stubs for end-to-end integration tests
- [ ] `tests/test_responses.py` — add classes for proxy.py missing paths (filtered_stream, build_request, etc.)
- [ ] `tests/test_proxy.py` — additional tests for error handling, edge cases

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PyPI OIDC Trusted Publisher config | D-14 | Requires pypi.org account access | Visit pypi.org → project → Publishing → add GitHub OIDC provider |
| Git tag v2.0.0 creation | D-13 | Manual trigger for CI pipeline | `git tag v2.0.0 && git push origin v2.0.0` |
| Docker image pull verification | D-12 | External registry check | `docker pull hosheali/dsv4-cc-proxy:2.0.0` |
| PyPI install verification | D-12 | External registry check | `pip install dsv4-cc-proxy==2.0.0` |
| GitHub Release verification | D-12 | Manual page check | Visit https://github.com/HosheaLi/dsv4-cc-proxy/releases/tag/v2.0.0 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
