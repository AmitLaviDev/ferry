---
phase: 07-tech-debt-cleanup
plan: 01
subsystem: dispatch
tags: [pydantic, lambda, dispatch-pipeline, runtime, python3.14]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Pydantic dispatch models (LambdaResource, DispatchPayload)
  - phase: 02-app-core-logic
    provides: LambdaConfig with runtime field and default value
  - phase: 06-fix-lambda-function-name-pipeline
    provides: function_name wiring pattern (identical approach reused for runtime)
provides:
  - runtime wired through full dispatch pipeline (LambdaConfig -> LambdaResource -> trigger -> parse_payload)
  - All defaults unified to python3.14 (schema, action.yml, Dockerfile)
affects: [07-02, 07-03]

# Tech tracking
tech-stack:
  added: []
  patterns: [config-to-dispatch-field-mapping-for-runtime]

key-files:
  created: []
  modified:
    - backend/src/ferry_backend/config/schema.py
    - utils/src/ferry_utils/models/dispatch.py
    - backend/src/ferry_backend/dispatch/trigger.py
    - action/src/ferry_action/parse_payload.py
    - action/build/action.yml
    - action/Dockerfile
    - tests/test_backend/test_config_schema.py
    - tests/test_utils/test_dispatch_models.py
    - tests/test_backend/test_dispatch_trigger.py
    - tests/test_action/test_parse_payload.py

key-decisions:
  - "runtime added as required str (not Optional) on LambdaResource -- backend resolves defaults before constructing dispatch model (same pattern as function_name)"
  - "Unified all defaults to python3.14: LambdaConfig, action.yml input, Dockerfile ARG"

patterns-established:
  - "Config-to-dispatch field wiring: Phase 6 established the pattern for function_name, Phase 7 confirms it as the standard approach for adding new fields"

requirements-completed: []

# Metrics
duration: 3min
completed: 2026-02-27
---

# Phase 7 Plan 1: Runtime Pipeline Wiring Summary

**Wired runtime end-to-end through Lambda dispatch pipeline and unified all defaults to python3.14, eliminating python3.10/3.12 inconsistency**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-27T20:31:43Z
- **Completed:** 2026-02-27T20:35:24Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Added `runtime: str` as required field on `LambdaResource` dispatch model
- Wired `runtime` from `LambdaConfig` through `_build_resource` to `parse_payload` GHA matrix
- Removed hardcoded `"python3.12"` from parse_payload.py -- now reads from dispatch model
- Unified all defaults to python3.14 (schema.py, action.yml, Dockerfile)
- All 249 tests passing including 3 new test cases for runtime flow

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire runtime through source files and update defaults to python3.14** - `d8ba60a` (feat)
2. **Task 2: Update all tests for runtime field addition and new default** - `fda9b79` (test)

**Plan metadata:** (pending) (docs: complete plan)

## Files Created/Modified
- `backend/src/ferry_backend/config/schema.py` - Changed LambdaConfig.runtime default from python3.10 to python3.14
- `utils/src/ferry_utils/models/dispatch.py` - Added `runtime: str` field to LambdaResource
- `backend/src/ferry_backend/dispatch/trigger.py` - Pass `runtime=lam.runtime` in _build_resource lambda branch
- `action/src/ferry_action/parse_payload.py` - Read `r.runtime` from dispatch model, updated docstrings
- `action/build/action.yml` - Changed runtime input default from python3.12 to python3.14
- `action/Dockerfile` - Changed ARG PYTHON_VERSION default from 3.12 to 3.14
- `tests/test_backend/test_config_schema.py` - Updated default runtime assertion to python3.14
- `tests/test_utils/test_dispatch_models.py` - Added runtime to all LambdaResource constructions, added missing-runtime and custom-runtime tests
- `tests/test_backend/test_dispatch_trigger.py` - Added runtime assertions and override test
- `tests/test_action/test_parse_payload.py` - Added runtime to all lambda resource dicts, updated matrix assertion

## Decisions Made
- `runtime` is `str` (not Optional) on LambdaResource because the backend resolves the default from LambdaConfig before constructing the dispatch model (identical rationale to function_name in Phase 6)
- All three default sites (LambdaConfig, action.yml, Dockerfile) unified to python3.14 -- single source of truth is LambdaConfig, other two are fallbacks for direct usage

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Runtime flows end-to-end from ferry.yaml to GHA matrix, closing the default inconsistency
- Phase 7 plans 02 and 03 can proceed with remaining tech debt items
- All 249 tests passing, no regressions

---
*Phase: 07-tech-debt-cleanup*
*Completed: 2026-02-27*
