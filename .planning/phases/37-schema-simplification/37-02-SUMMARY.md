---
phase: 37-schema-simplification
plan: 02
subsystem: action
tags: [gha-action, composite-action, deploy, parse-payload, schema-simplification]

# Dependency graph
requires:
  - phase: 37-schema-simplification
    plan: 01
    provides: Simplified LambdaResource/StepFunctionResource dispatch models with name = AWS resource name
provides:
  - "Action deploy scripts using INPUT_RESOURCE_NAME as function name / state machine name"
  - "Composite actions without function-name / state-machine-name inputs"
  - "Matrix output using name only (no function_name / state_machine_name keys)"
  - "Updated docs/setup.md with simplified ferry.yaml example and workflow template"
  - "ferry-test-app migrated and validated E2E with new schema"
affects: [ferry-test-app, future-phases]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "resource-name input serves as the AWS resource name across all resource types"

key-files:
  created: []
  modified:
    - action/src/ferry_action/parse_payload.py
    - action/src/ferry_action/deploy.py
    - action/src/ferry_action/deploy_stepfunctions.py
    - action/deploy/action.yml
    - action/deploy-stepfunctions/action.yml
    - docs/setup.md
    - tests/test_action/test_parse_payload.py
    - tests/test_action/test_deploy.py
    - tests/test_action/test_deploy_stepfunctions.py

key-decisions:
  - "resource-name composite action input IS the AWS resource name for all types (Lambda function name, SF state machine name)"
  - "Removed function-name and state-machine-name inputs from composite actions entirely (not deprecated, removed)"
  - "ferry-test-app validated E2E with new schema -- /ferry plan shows name as AWS resource name"

patterns-established:
  - "Single resource-name input pattern: composite actions pass one name, deploy scripts use it as the AWS resource name"

requirements-completed: [SCHEMA-01]

# Metrics
duration: 5min
completed: 2026-03-15
---

# Phase 37 Plan 02: Action Deploy and Composite Action Simplification Summary

**Propagated schema simplification through GHA action layer -- deploy scripts, composite actions, and docs all use name as AWS resource name, validated E2E via ferry-test-app**

## Performance

- **Duration:** 5 min (code changes) + E2E verification by user
- **Started:** 2026-03-14T20:50:28Z
- **Completed:** 2026-03-15T06:27:00Z
- **Tasks:** 3 (2 auto + 1 checkpoint)
- **Files modified:** 9

## Accomplishments

- Removed function_name and state_machine_name from parse_payload matrix output -- entries use name only
- deploy.py derives Lambda function name from INPUT_RESOURCE_NAME (INPUT_FUNCTION_NAME removed)
- deploy_stepfunctions.py derives state machine name from INPUT_RESOURCE_NAME (INPUT_STATE_MACHINE_NAME removed)
- Composite action.yml files no longer accept function-name or state-machine-name inputs
- docs/setup.md updated with simplified ferry.yaml example and workflow template
- All tests pass with updated assertions
- ferry-test-app validated E2E: /ferry plan on PR #5 shows "ferry-test-hello-world" as Lambda name

## Task Commits

Each task was committed atomically:

1. **Task 1: Update parse_payload matrix builders and deploy scripts** - `0af2c4f` (feat)
2. **Task 2: Update composite actions, docs, and all action tests** - `50a395c` (test)
3. **Task 3: Checkpoint -- user verified schema simplification E2E** - N/A (human verification)

## Files Created/Modified

- `action/src/ferry_action/parse_payload.py` - Removed function_name/state_machine_name from matrix entry dicts
- `action/src/ferry_action/deploy.py` - Uses INPUT_RESOURCE_NAME as Lambda function name, removed INPUT_FUNCTION_NAME
- `action/src/ferry_action/deploy_stepfunctions.py` - Uses INPUT_RESOURCE_NAME as state machine name
- `action/deploy/action.yml` - Removed function-name input and INPUT_FUNCTION_NAME env var
- `action/deploy-stepfunctions/action.yml` - Removed state-machine-name input and INPUT_STATE_MACHINE_NAME env var
- `docs/setup.md` - Simplified ferry.yaml example and workflow template (no function_name/state_machine_name)
- `tests/test_action/test_parse_payload.py` - Updated assertions for name-only matrix entries
- `tests/test_action/test_deploy.py` - Removed INPUT_FUNCTION_NAME from test env vars
- `tests/test_action/test_deploy_stepfunctions.py` - Removed INPUT_STATE_MACHINE_NAME from test env vars

## Decisions Made

- **resource-name IS the AWS name**: The composite action `resource-name` input directly maps to the AWS resource name (Lambda function name or state machine name). No translation layer needed.
- **Hard removal, not deprecation**: Removed `function-name` and `state-machine-name` inputs entirely from composite actions rather than deprecating them. Acceptable since there are no external users yet.
- **E2E validation via ferry-test-app**: User verified /ferry plan on PR #5 (branch schema-simplification) shows the simplified schema working end-to-end.

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None -- all changes were straightforward.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness

- Schema simplification is complete across the entire pipeline: ferry.yaml -> schema models -> dispatch models -> action parsing -> deploy scripts -> composite actions -> workflow template
- ferry-test-app migrated and validated E2E
- Ready for multi-tenant / other orgs (v2+) or other future work

## Self-Check: PASSED

All 9 modified files exist. Both task commits (0af2c4f, 50a395c) verified in git log.

---
*Phase: 37-schema-simplification*
*Completed: 2026-03-15*
