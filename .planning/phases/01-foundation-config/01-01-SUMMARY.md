---
phase: 01-foundation-config
plan: 01
subsystem: config
tags: [codex, model-mapping, env-vars, json-parsing]
security_review: true

# Dependency graph
requires:
  - phase: N/A (initial phase)
    provides: N/A
provides:
  - codex/ sub-package skeleton with resolve_model API
  - Model mapping config system (env var driven, exact + prefix match)
  - Test infrastructure for env-var-dependent module-level config testing
affects:
  - 02-codex-endpoint (will consume resolve_model for request routing)
  - 03-codex-tools (will use model mapping for tool schema adaptation)

# Tech tracking
tech-stack:
  added: none (stdlib only: json, logging, os)
  patterns:
    - Vendor isolation via sub-package (codex/ separate from existing proxy.py)
    - Two-layer model resolution: exact match → longest prefix match → default fallback
    - monkeypatch.setenv + importlib.reload for module-level env var testing

key-files:
  created:
    - dsv4_cc_proxy/codex/__init__.py
    - dsv4_cc_proxy/codex/config.py
    - tests/test_codex.py
  modified: []

key-decisions:
  - "No cache of CODEX_MODEL_MAP — re-parse _RAW_MODEL_MAP on each resolve_model() call (simplicity, no stale config)"
  - "_RAW_MODEL_MAP stores raw env string at module level; parse happens per-call to avoid caching issues"
  - "Logger reused from parent package (deepseek-proxy) — consistent with proxy.py convention"

patterns-established:
  - "Sub-package init: flat re-export from sibling module with __all__ (matches parent __init__.py style)"
  - "Config loading: module-level os.getenv with hardcoded defaults (matches proxy.py pattern)"
  - "Internal helpers: _ prefixed private functions for non-public API (matches proxy.py _helper convention)"
  - "Defensive JSON parsing: try/except json.JSONDecodeError + isinstance dict check + logger.warning (T-01-01 mitigation)"
  - "Pure function design: no class, no mutable state, input→output transformation"

requirements-completed:
  - CODX-16
  - CODX-17
  - CODX-18

# Metrics
duration: 2min
completed: 2026-06-05
---

# Phase 1 Plan 1: Codex Sub-package Skeleton Summary

**codex/ sub-package with model mapping config system — CODEX_DEFAULT_MODEL + CODEX_MODEL_MAP env vars, two-layer resolution (exact match → longest prefix → default fallback)**

## Performance

- **Duration:** 2 min
- **Started:** 2026-06-05T22:19:00+08:00
- **Completed:** 2026-06-05T22:20:00+08:00
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- `codex/` sub-package created (vendor isolation pattern, no changes to existing proxy.py or parent __init__.py)
- `config.py` with 3 module-level env var constants: `CODEX_DEFAULT_MODEL`, `CODEX_UPSTREAM`, `_RAW_MODEL_MAP`
- `_parse_model_map()` defensive JSON parser — handles empty, invalid, non-dict input (never raises)
- `resolve_model()` pure function with 3-step resolution pipeline: exact match → longest prefix match → default fallback
- `test_codex.py` with 6 test functions covering all resolution paths and error conditions
- Threat model T-01-01 (env var tampering) fully mitigated: JSONDecodeError caught, non-dict rejected, safe defaults

## Task Commits

Each task was committed atomically:

1. **Task 1 — RED: Test file** - `018601f` (test(01-01): add failing test for codex model mapping config)
2. **Task 1 — GREEN: Implementation** - `b7b7162` (feat(01-01): implement codex model mapping config)
3. **Task 2: Sub-package init** - `d71935e` (feat(01-01): add codex sub-package init with flat re-export)

**TDD Gate Compliance:** RED (test) and GREEN (feat) gate commits present. REFACTOR gate skipped — code is clean, matches established patterns.

## Files Created/Modified

### Created
- `dsv4_cc_proxy/codex/__init__.py` — Sub-package entry, flat re-export of `resolve_model`
- `dsv4_cc_proxy/codex/config.py` — Model mapping config engine (env var loading, parsing, resolution)
- `tests/test_codex.py` — 6 test functions for all resolution paths

### Unmodified
- `dsv4_cc_proxy/proxy.py` — No changes
- `dsv4_cc_proxy/__init__.py` — No changes
- `tests/test_proxy.py` — No changes

## Decisions Made
- **No caching of CODEX_MODEL_MAP**: `resolve_model()` re-parses `_RAW_MODEL_MAP` on every call. Rationale: avoids stale config, simplifies code, parsing cost is negligible (tiny JSON strings).
- **Module-level _RAW_MODEL_MAP**: Captures env var at import time as raw string (not parsed). Parsing happens per-call in `resolve_model()`. This is the correct design — `reload(module)` re-evaluates the os.getenv, so tests can monkeypatch+reload.
- **Logger reuse**: Using `logging.getLogger("deepseek-proxy")` (same as proxy.py) rather than creating a new namespace. Rationale: consistent log output, avoids multi-logger confusion for operators.
- **Prefix match via dict comprehension + max(len)**: Pure dict-based approach, no trie or complex data structure. Rationale: model maps are typically <50 entries, performance is irrelevant at this scale.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. All configuration is via environment variables (CODEX_DEFAULT_MODEL, CODEX_MODEL_MAP, CODEX_UPSTREAM) with safe defaults.

## Test Results

```
tests/test_codex.py::test_exact_match_overrides_prefix PASSED
tests/test_codex.py::test_prefix_match_longest_wins PASSED
tests/test_codex.py::test_fallback_to_default PASSED
tests/test_codex.py::test_empty_map_uses_default PASSED
tests/test_codex.py::test_invalid_json_map_falls_back PASSED
tests/test_codex.py::test_prefix_not_matches_uses_default PASSED
tests/test_proxy.py — 22 passed (no regression)
Total: 28 passed in 0.04s
```

## Next Phase Readiness
- `dsv4_cc_proxy.codex.resolve_model()` is importable and fully tested
- Ready for Phase 2 (codex endpoint) which will consume `resolve_model` for request routing configuration
- Existing proxy functionality completely unaffected
- No blockers or concerns for downstream phases

## Known Stubs

None — all features are fully implemented and tested. No placeholder data, no stub components.

## Threat Surface Scan

No new threat surface beyond what was identified in the plan's threat model. All T-01-01 mitigations are implemented. No new network endpoints, auth paths, or file access patterns introduced.

---
*Phase: 01-foundation-config*
*Completed: 2026-06-05*
