---
phase: 06-testing-release
plan: 03
subsystem: documentation
tags: [readme, changelog, codex, ci, oidc, pypi, docker]
requires: []
provides:
  - Codex Support documentation in README.md and README.zh-CN.md
  - CHANGELOG.md [2.0.0] release entry
  - docs/dev/codex-integration.md technical design document
  - CI improvements: PyPI OIDC, coverage badge, single Python version, Docker sha tag
affects: [phase-06-release, downstream maintainers]

tech-stack:
  added: [coverage-badge (CI only)]
  patterns: [PyPI OIDC Trusted Publishing, coverage badge commit-back with [skip ci]]

key-files:
  created:
    - docs/dev/codex-integration.md
  modified:
    - README.md
    - README.zh-CN.md
    - CHANGELOG.md
    - .github/workflows/ci.yml

key-decisions:
  - "Removed Homebrew tap update from CI (deferred to future iteration per CONTEXT.md)"
  - "Coverage badge committed back to repo with [skip ci] to prevent infinite CI loop"
  - "Test matrix simplified to single Python 3.12 (proxy is a service, not a library)"
  - "Project structure updated to reflect actual existing test files (test_e2e.py created in separate plan)"

patterns-established:
  - "Coverage badge generation: install coverage-badge, generate SVG, commit with [skip ci]"
  - "PyPI publishing: OIDC Trusted Publishing with id-token: write instead of API token"
  - "Docker tags: semver version + major.minor + latest + sha"
  - "Full test suite: pytest tests/ -v --cov=dsv4_cc_proxy --cov-report=term"

requirements-completed: [D-07, D-08, D-09, D-10, D-14, D-15, D-16, D-17]

duration: 15min
completed: 2026-06-07
---

# Phase 6 Plan 3: Documentation and CI Improvements Summary

**Codex Support documentation in README (EN+ZH), CHANGELOG [2.0.0] entry, codex-integration.md technical design doc, and CI improvements (PyPI OIDC, coverage badge, single Python version, Docker sha tag)**

## Performance

- **Duration:** 15 min
- **Started:** 2026-06-07T08:15:00Z
- **Completed:** 2026-06-07T08:30:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Added Codex Support chapter (with endpoints, env vars, usage) to both English and Chinese READMEs
- Added coverage badge reference to README badge row
- Updated project structure and version string in both READMEs
- Added [2.0.0] changelog entry with Added/Changed categories
- Created docs/dev/codex-integration.md (209 lines) with YAML frontmatter, architecture diagram, module dependency graph, request/streaming translation flows, SSE lifecycle event sequence, and testing guide
- Simplified CI test matrix from 3 Python versions to single 3.12
- Switched test suite from partial (`tests/test_proxy.py`) to full (`pytest tests/ -v --cov=...`)
- Added coverage badge generation with commit-back on main branch
- Added `id-token: write` for PyPI OIDC Trusted Publishing, removed API token authentication
- Added Docker `type=sha` label tag
- Removed deferred Homebrew tap update step from CI

## Task Commits

Each task was committed atomically:

1. **Task 1: Update README.md + README.zh-CN.md — Codex Support chapters** - `7f6af5b` (docs)
2. **Task 2: Update CHANGELOG.md + Create docs/dev/codex-integration.md** - `59b6450` (docs)
3. **Task 3: Update .github/workflows/ci.yml — CI improvements** - `27cab49` (ci)

**Plan metadata:** *(committed below)*

## Files Created/Modified
- `README.md` - Added Codex Support chapter, coverage badge, Codex env var reference, updated project structure
- `README.zh-CN.md` - Chinese translation of all README changes
- `CHANGELOG.md` - Added [2.0.0] release entry at top
- `docs/dev/codex-integration.md` (NEW, 209 lines) - Technical design document for Codex integration
- `.github/workflows/ci.yml` - Simplified test matrix, full test suite, coverage badge, PyPI OIDC, Docker sha tag, removed Homebrew tap

## Decisions Made
- Removed Homebrew tap update from CI (deferred to future iteration per CONTEXT.md)
- Coverage badge committed back to repo with `[skip ci]` to prevent infinite CI loop
- Test matrix simplified to single Python 3.12 (proxy is a service, not a library)
- Project structure updated to reflect only existing test files (test_e2e.py created in separate plan 06-02)
- Used `python -m pytest tests/ -v --cov=dsv4_cc_proxy --cov-report=term` as the standard full test command

## Deviations from Plan

None - plan executed exactly as written.

### Note on project structure
The plan asked to update the project structure to include codex/ subpackage. I also removed `test_e2e.py` from the listing since it does not exist yet (created in plan 06-02). This is not a deviation but a factual correction to maintain accuracy.

## Issues Encountered
None - all changes applied cleanly, all acceptance criteria verified.

## User Setup Required

None - no external service configuration required. All changes are documentation and CI configuration only.

### PyPI OIDC prerequisite
PyPI OIDC Trusted Publishing requires one-time setup on pypi.org before it will work:
1. Login to pypi.org as project owner
2. Go to `dsv4-cc-proxy` project → "Manage" → "Publishing"
3. Add OIDC provider: GitHub, repository `HosheaLi/dsv4-cc-proxy`
4. Workflow file: `.github/workflows/ci.yml`, environment: (leave blank)
This is a manual step documented for the release phase.

## Next Phase Readiness
- Documentation complete for Codex integration (README, CHANGELOG, technical docs)
- CI configured for PyPI OIDC publishing (awaiting one-time PyPI setup)
- CI generates coverage badge automatically on main branch
- All file changes ready for version bump to 2.0.0 and release

---
*Phase: 06-testing-release*
*Completed: 2026-06-07*
