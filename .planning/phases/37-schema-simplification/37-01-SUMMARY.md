---
phase: 37-schema-simplification
plan: 01
subsystem: config
tags: [pydantic, schema, ferry-yaml, dispatch, backward-compat]

# Dependency graph
requires:
  - phase: 36-pr-comment-ux-polish
    provides: v2.0 milestone complete, stable schema baseline
provides:
  - "LambdaConfig and StepFunctionConfig with name = AWS resource name"
  - "Backward-compat validators accepting old function_name/state_machine_name fields"
  - "Simplified LambdaResource and StepFunctionResource dispatch models"
  - "trigger.py using .name only for resource building"
affects: [37-02 action deploy code, ferry-test-app migration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "mode=before model_validator for backward-compat field migration"
    - "state_machine_name wins over name when both present (Pitfall 5)"

key-files:
  created: []
  modified:
    - backend/src/ferry_backend/config/schema.py
    - utils/src/ferry_utils/models/dispatch.py
    - backend/src/ferry_backend/dispatch/trigger.py
    - action/src/ferry_action/parse_payload.py
    - tests/test_backend/test_config_schema.py
    - tests/test_utils/test_dispatch_models.py
    - tests/test_backend/test_dispatch_trigger.py
    - tests/test_backend/test_changes.py
    - tests/test_action/test_parse_payload.py

key-decisions:
  - "LambdaConfig backward-compat: name wins when both present (function_name silently dropped)"
  - "StepFunctionConfig backward-compat: state_machine_name wins when both present and differ (it IS the AWS name)"
  - "Matrix output still emits function_name and state_machine_name keys for composite action compatibility (Plan 02 will clean up)"

patterns-established:
  - "mode=before validator strips deprecated fields before extra=forbid sees them"

requirements-completed: [SCHEMA-01]

# Metrics
duration: 9min
completed: 2026-03-14
---

# Phase 37 Plan 01: Schema Simplification Summary

**Eliminated function_name and state_machine_name from schema and dispatch models -- name IS the AWS resource name, with mode=before backward-compat validators**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-14T20:36:48Z
- **Completed:** 2026-03-14T20:45:56Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- Removed function_name from LambdaConfig and LambdaResource; name is now the AWS Lambda function name
- Removed state_machine_name from StepFunctionConfig and StepFunctionResource; name is now the AWS state machine name
- Added mode="before" backward-compat validators that silently accept old field names during migration
- Updated trigger.py to build dispatch resources using .name only
- All 444 tests pass with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Simplify schema models and dispatch payload models** - `f691915` (feat)
2. **Task 2: Update all backend and utils tests** - `bed2d1d` (test)

## Files Created/Modified

- `backend/src/ferry_backend/config/schema.py` - Removed function_name/state_machine_name fields, added backward-compat validators
- `utils/src/ferry_utils/models/dispatch.py` - Removed function_name from LambdaResource, state_machine_name from StepFunctionResource
- `backend/src/ferry_backend/dispatch/trigger.py` - Updated _build_resource to use .name only
- `action/src/ferry_action/parse_payload.py` - Changed matrix output to use r.name instead of r.function_name/r.state_machine_name
- `tests/test_backend/test_config_schema.py` - Updated tests, added backward-compat alias tests
- `tests/test_utils/test_dispatch_models.py` - Removed all function_name/state_machine_name from constructors and assertions
- `tests/test_backend/test_dispatch_trigger.py` - Updated config names and assertions
- `tests/test_backend/test_changes.py` - Updated StepFunctionConfig constructors
- `tests/test_action/test_parse_payload.py` - Updated test fixtures and assertions for simplified models

## Decisions Made

- **LambdaConfig backward-compat**: When both `name` and `function_name` present, `name` wins and `function_name` is silently dropped (the user explicitly chose `name`, so honor it)
- **StepFunctionConfig backward-compat**: When both `name` and `state_machine_name` present and differ, `state_machine_name` wins (it IS the AWS resource name, per research Pitfall 5)
- **Matrix output keys preserved**: The GHA matrix dict still emits `function_name` and `state_machine_name` keys (set to `r.name`) for composite action compatibility -- Plan 02 will update the composite actions to use `name` directly

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed action parse_payload.py to use .name**
- **Found during:** Task 2 (running full test suite)
- **Issue:** `parse_payload.py` referenced `.function_name` and `.state_machine_name` on dispatch model objects, which no longer exist after Task 1 changes
- **Fix:** Changed `r.function_name` to `r.name` and `r.state_machine_name` to `r.name` in both v1 and v2 matrix builders. Kept the matrix dict keys as `"function_name"` and `"state_machine_name"` for composite action compatibility.
- **Files modified:** `action/src/ferry_action/parse_payload.py`, `tests/test_action/test_parse_payload.py`
- **Verification:** All 444 tests pass
- **Committed in:** `bed2d1d` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (blocking issue)
**Impact on plan:** Necessary fix for correctness -- the action code is a consumer of the shared dispatch models. No scope creep; Plan 02 will do the full composite action cleanup.

## Issues Encountered

None - all changes were straightforward.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Backend and utils are fully simplified -- name IS the AWS resource name
- Action parse_payload.py bridges the gap by outputting `function_name=name` and `state_machine_name=name` in matrix dicts
- Plan 02 will update composite actions (deploy.py, deploy_stepfunctions.py), action.yml, docs, and ferry-test-app

---
## Self-Check: PASSED

All 9 modified files exist. Both task commits (f691915, bed2d1d) verified in git log.

---
*Phase: 37-schema-simplification*
*Completed: 2026-03-14*
