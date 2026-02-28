---
phase: 04-extended-resource-types
plan: 02
subsystem: deploy
tags: [step-functions, envsubst, content-hash, moto, composite-action]

# Dependency graph
requires:
  - phase: 04-extended-resource-types
    provides: "envsubst module, compute_content_hash, get_content_hash_tag from plan 04-01"
  - phase: 03-build-and-lambda-deploy
    provides: "Lambda deploy module pattern, gha.py helpers, composite action pattern"
provides:
  - "deploy_stepfunctions.py module with should_skip_deploy, deploy_step_function, main"
  - "Composite action at action/deploy-stepfunctions/action.yml"
  - "Content-hash skip logic for Step Functions deployments"
affects: [05-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [content-hash tag skip for Step Functions, envsubst in state machine definitions, STS account_id resolution for ARN construction]

key-files:
  created:
    - action/src/ferry_action/deploy_stepfunctions.py
    - action/deploy-stepfunctions/action.yml
    - tests/test_action/test_deploy_stepfunctions.py
  modified: []

key-decisions:
  - "ARN constructed from STS GetCallerIdentity account_id + AWS_REGION env var + state_machine_name"
  - "update_state_machine called with publish=True and versionDescription for traceability"
  - "Content-hash skip reads ferry:content-hash tag via list_tags_for_resource before deploying"

patterns-established:
  - "Step Functions deploy pattern: read definition, envsubst, content-hash check, update_state_machine, tag update"
  - "Dual boto3 client pattern in main(): STS for account_id, SFN for state machine operations"

requirements-completed: [DEPLOY-02]

# Metrics
duration: 3min
completed: 2026-02-26
---

# Phase 4 Plan 2: Step Functions Deploy Module Summary

**Step Functions deploy module with envsubst variable substitution, content-hash skip logic, versioned publishing, and GHA composite action**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-26T19:07:41Z
- **Completed:** 2026-02-26T19:11:07Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created deploy_stepfunctions.py with full SF deploy lifecycle: read definition, envsubst, content-hash skip, update_state_machine with publish=True, tag update
- 12 moto-based tests covering skip logic (hash match/differ/missing), deploy operations (update, version, tag, result dict), and main() (skip, deploy, envsubst, summary, error hints)
- Composite action YAML maps GHA inputs to INPUT_* env vars, follows same pattern as Lambda deploy action

## Task Commits

Each task was committed atomically:

1. **Task 1: Step Functions deploy module (TDD)** - `6246220` (feat)
2. **Task 2: Create Step Functions composite action YAML** - `94b32bb` (feat)

_Task 1 followed TDD: RED (ModuleNotFoundError confirmed) then GREEN (12 tests pass)_

## Files Created/Modified
- `action/src/ferry_action/deploy_stepfunctions.py` - Step Functions deploy with should_skip_deploy, deploy_step_function, main
- `tests/test_action/test_deploy_stepfunctions.py` - 12 moto-based tests for full deploy lifecycle
- `action/deploy-stepfunctions/action.yml` - Composite action for Step Functions deployment

## Decisions Made
- ARN constructed from STS GetCallerIdentity account_id + AWS_REGION env var + state_machine_name (same pattern as plan describes)
- update_state_machine called with publish=True and versionDescription for deployment traceability
- Content-hash skip logic reads ferry:content-hash tag via list_tags_for_resource, uses get_content_hash_tag helper from envsubst module
- Error hints cover StateMachineDoesNotExist, AccessDeniedException, InvalidDefinition (same pattern as Lambda deploy)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Step Functions deploy module complete, ready for integration testing in Phase 5
- API Gateway deploy module (Plan 04-03) can follow the same pattern established here
- Pre-existing test_deploy_apigw.py from plan 04-01 exists but awaits plan 04-03 implementation

---
## Self-Check: PASSED

- All created files verified to exist on disk
- Both task commits (6246220, 94b32bb) verified in git log
- All 216 tests pass (excluding pre-existing test_deploy_apigw.py from future plan 04-03), ruff clean

---
*Phase: 04-extended-resource-types*
*Completed: 2026-02-26*
