---
phase: 06-fix-lambda-function-name-pipeline
plan: 01
subsystem: dispatch
tags: [pydantic, lambda, dispatch-pipeline, function-name, gha-matrix]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Pydantic dispatch models (LambdaResource, DispatchPayload)
  - phase: 02-app-core-logic
    provides: LambdaConfig with function_name field and model_validator default
  - phase: 03-build-and-lambda-deploy
    provides: deploy.py Lambda deployment with INPUT_FUNCTION_NAME consumption
provides:
  - function_name wired through full dispatch pipeline (LambdaResource -> trigger -> parse_payload -> deploy)
  - DEPLOY-01 integration break closed
affects: [07-tech-debt-cleanup]

# Tech tracking
tech-stack:
  added: []
  patterns: [required-field-addition-to-frozen-pydantic-model, config-to-dispatch-field-mapping]

key-files:
  created: []
  modified:
    - utils/src/ferry_utils/models/dispatch.py
    - backend/src/ferry_backend/dispatch/trigger.py
    - action/src/ferry_action/parse_payload.py
    - action/src/ferry_action/deploy.py
    - tests/test_utils/test_dispatch_models.py
    - tests/test_backend/test_dispatch_trigger.py
    - tests/test_action/test_parse_payload.py
    - tests/test_action/test_deploy.py

key-decisions:
  - "function_name added as required str field on LambdaResource (not Optional) -- backend resolves defaults before constructing the model"
  - "deploy.py uses os.environ.get with explicit fail-fast instead of KeyError for INPUT_FUNCTION_NAME -- clearer error message"

patterns-established:
  - "Required field addition pattern: add field to model, update constructor in _build_resource, surface in matrix builder, update all test construction sites"

requirements-completed: [DEPLOY-01]

# Metrics
duration: 4min
completed: 2026-02-27
---

# Phase 6 Plan 1: Fix Lambda function_name Pipeline Summary

**Wired function_name through the full Lambda dispatch pipeline: LambdaResource model -> _build_resource -> parse_payload GHA matrix -> deploy.py, closing the DEPLOY-01 integration break**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-27T12:39:42Z
- **Completed:** 2026-02-27T12:44:34Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Added `function_name: str` as required field on `LambdaResource` dispatch model
- Wired `function_name` from `LambdaConfig` through `_build_resource`, `parse_payload` matrix, to `deploy.py`
- Improved `ResourceNotFoundException` error message with ferry.yaml guidance
- Added fail-fast check for missing/empty `INPUT_FUNCTION_NAME` in deploy.py
- All 246 tests passing including 9 new test cases for function_name flow

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire function_name through source files** - `a391898` (feat)
2. **Task 2: Update all test files for function_name** - `c609a4a` (test)

**Plan metadata:** (pending) (docs: complete plan)

## Files Created/Modified
- `utils/src/ferry_utils/models/dispatch.py` - Added `function_name: str` field to LambdaResource
- `backend/src/ferry_backend/dispatch/trigger.py` - Pass `function_name=lam.function_name` in _build_resource lambda branch
- `action/src/ferry_action/parse_payload.py` - Include `function_name` in _build_lambda_matrix output dict
- `action/src/ferry_action/deploy.py` - Fail-fast for missing INPUT_FUNCTION_NAME, improved ResourceNotFoundException message
- `tests/test_utils/test_dispatch_models.py` - Updated all LambdaResource constructions, added override and missing-field tests
- `tests/test_backend/test_dispatch_trigger.py` - Added explicit function_name flow tests, override case test
- `tests/test_action/test_parse_payload.py` - Updated all lambda resource dicts, added matrix function_name tests
- `tests/test_action/test_deploy.py` - Added missing/empty INPUT_FUNCTION_NAME tests, ResourceNotFoundException message test

## Decisions Made
- `function_name` is `str` (not Optional) on LambdaResource because the backend resolves the default before constructing the dispatch model
- `deploy.py` uses `os.environ.get("INPUT_FUNCTION_NAME", "")` with explicit check instead of bare `os.environ["INPUT_FUNCTION_NAME"]` to provide a clear error message instead of a raw KeyError

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- DEPLOY-01 integration break is closed: function_name flows end-to-end from ferry.yaml to deploy.py
- Phase 7 (tech debt cleanup) can now proceed with runtime wiring through the same pipeline path
- All 246 tests passing, no regressions

---
*Phase: 06-fix-lambda-function-name-pipeline*
*Completed: 2026-02-27*
