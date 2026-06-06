---
phase: 03-tool-support
plan: 01
subsystem: api
tags: deepseek, codex, tool-format, schema-repair, json-schema

requires:
  - phase: 02
    provides: translate_request() function and codex request translation pattern
provides:
  - convert_tools() function for Responses API → Chat Completions tool format conversion
  - _clean_schema() recursive JSON Schema field stripping for DeepSeek strict mode
  - _convert_tool_format() flat-to-nested tool structure wrapper
affects:
  - 03-02 (__init__.py export of convert_tools)
  - 03-02 (translate_request() integration of convert_tools call)
  - 03-test (test_tools.py needs the module under test)

tech-stack:
  added: []
  patterns:
    - Pure-function module with single public export (codex subpackage convention)
    - Recursive dict traversal for nested JSON Schema structures
    - Deepcopy-protected immutability pattern
    - frozenset constants for O(1) lookup on removed keys
    - Percent-style (%s) logging with [CODEX] prefix
    - _ prefix for internal helpers, consistent with translate.py

key-files:
  created:
    - dsv4_cc_proxy/codex/tools.py
  modified: []

key-decisions:
  - "D-04: Strip-only schema cleaning — never auto-add required/additionalProperties"
  - "D-05: 8 fields stripped: default, readOnly, writeOnly, examples, minLength, maxLength, minItems, maxItems"
  - "D-06: Recursive cleaning through properties, $defs, anyOf, items paths"
  - "D-07: ValueError for non-dict parameters (fail-fast, not silent pass-through)"
  - "D-08: Already-nested tools pass through unchanged; unknown type records WARNING"
  - "D-10: Two internal helpers (_convert_tool_format, _clean_schema) with _ prefix"

patterns-established:
  - "frozenset constants for immutable O(1) lookup of removed schema keys"
  - "Recursive dict traversal with isinstance() guards on all nested paths"
  - "deepcopy protection on function entry, safe mutation inside"
  - "Percent-style (%s) logging with [CODEX] prefix"

requirements-completed:
  - CODX-07
  - CODX-10

duration: 5min
completed: 2026-06-06
---

# Phase 3 Plan 01: Tool Format Conversion and Schema Repair

**convert_tools() pure function implementing flat-to-nested tool format conversion and recursive JSON Schema field stripping for DeepSeek strict mode compliance**

## Performance

- **Duration:** 5 min
- **Started:** 2026-06-06T04:48:00Z
- **Completed:** 2026-06-06T04:53:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `dsv4_cc_proxy/codex/tools.py` (160 lines) with three functions
- Implemented CODX-07: Responses API flat tool format `{type, name, desc, params}` to Chat Completions nested format `{type, function: {name, desc, params, strict}}`
- Implemented CODX-10: Recursive stripping of 8 unsupported JSON Schema fields (default, readOnly, writeOnly, examples, minLength, maxLength, minItems, maxItems) plus empty enum removal
- Recursive cleaning traverses all four nested paths: properties, $defs, anyOf, items
- All 10 D-\* locked decisions from CONTEXT.md strictly followed
- All 15 acceptance criteria verified

## Task Commits

Each task was committed atomically:

1. **Task 1: Create tools.py with convert_tools and internal helpers** - `04c3ecf` (feat)

## Files Created/Modified

- `dsv4_cc_proxy/codex/tools.py` - Tool format conversion + schema repair module with `convert_tools()` entry point and `_convert_tool_format()` / `_clean_schema()` internal helpers

## Decisions Made

- Followed CONTEXT.md locked decisions D-01 through D-10 without deviation
- Used `frozenset` for REMOVED_KEYS constant (immutable, O(1) lookup)
- Used `copy.deepcopy()` for immutability protection on function entry
- All recursive paths guarded with `isinstance()` checks
- ValueError raised with tool name and type info for non-dict parameters (D-07)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `convert_tools()` is importable and fully verified
- Ready for Plan 03-02: export from `__init__.py` and integrate `convert_tools()` call into `translate_request()`
- All 12 smoke tests pass covering: flat-to-nested, nested pass-through, field stripping, empty enum, empty input, immutability, None input, strict field, unknown type, recursive properties/anyOf/$defs, ValueError for non-dict params

## Self-Check: PASSED

- `dsv4_cc_proxy/codex/tools.py` exists (160 lines, >=100 required)
- `convert_tools` importable: `python3 -c "from dsv4_cc_proxy.codex.tools import convert_tools"`
- All 15 acceptance criteria satisfied (verified via grep + python tests)
- No unintended deletions detected
- Commit hash `04c3ecf` exists

---
*Phase: 03-tool-support*
*Completed: 2026-06-06*
