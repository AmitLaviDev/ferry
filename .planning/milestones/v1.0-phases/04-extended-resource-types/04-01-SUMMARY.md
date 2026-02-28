---
phase: 04-extended-resource-types
plan: 01
subsystem: deploy
tags: [envsubst, sha256, step-functions, api-gateway, pydantic, dispatch]

# Dependency graph
requires:
  - phase: 03-build-and-lambda-deploy
    provides: "Lambda deploy module, parse_payload, trigger._build_resource patterns"
  - phase: 02-app-core
    provides: "Config schema models, dispatch trigger pipeline"
provides:
  - "envsubst module for ${ACCOUNT_ID} and ${AWS_REGION} variable substitution"
  - "compute_content_hash for SHA-256 change detection"
  - "get_content_hash_tag for both SF list and APIGW dict tag formats"
  - "StepFunctionConfig with state_machine_name and definition_file"
  - "ApiGatewayConfig with rest_api_id, stage_name, and spec_file"
  - "StepFunctionResource and ApiGatewayResource dispatch models with deploy fields"
  - "parse_payload handles lambda, step_function, and api_gateway resource types"
affects: [04-02-PLAN, 04-03-PLAN]

# Tech tracking
tech-stack:
  added: [hashlib, re]
  patterns: [envsubst regex substitution, content-hash tag extraction, type-dispatched matrix builders]

key-files:
  created:
    - action/src/ferry_action/envsubst.py
    - tests/test_action/test_envsubst.py
  modified:
    - backend/src/ferry_backend/config/schema.py
    - utils/src/ferry_utils/models/dispatch.py
    - backend/src/ferry_backend/dispatch/trigger.py
    - action/src/ferry_action/parse_payload.py
    - tests/test_backend/test_config_schema.py
    - tests/test_backend/test_dispatch_trigger.py
    - tests/test_action/test_parse_payload.py
    - tests/test_backend/test_changes.py
    - tests/test_utils/test_dispatch_models.py

key-decisions:
  - "Strict regex pattern for envsubst: only matches ${ACCOUNT_ID} and ${AWS_REGION}, safe for JSONPath"
  - "get_content_hash_tag handles both SF list-of-dicts and APIGW flat-dict tag formats"
  - "_MATRIX_BUILDERS dispatch dict pattern for type-based matrix construction in parse_payload"

patterns-established:
  - "envsubst via strict regex: _ENVSUBST_PATTERN.sub with lambda lookup from fixed dict"
  - "Content-hash tag extraction: isinstance check for dict vs list tag format"
  - "Matrix builder dispatch: dict mapping resource_type to builder function"

requirements-completed: [DEPLOY-02, DEPLOY-03]

# Metrics
duration: 6min
completed: 2026-02-26
---

# Phase 4 Plan 1: Shared Utilities and Deploy Field Pipeline Summary

**envsubst module with SHA-256 content hashing, plus end-to-end SF/APIGW deploy field pipeline from config schema through dispatch models to GHA matrix**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-26T18:58:33Z
- **Completed:** 2026-02-26T19:04:50Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- Created envsubst module with strict regex substitution for ${ACCOUNT_ID} and ${AWS_REGION}, safe for JSONPath expressions
- Added content hash utilities (SHA-256 compute + dual-format tag extraction for SF/APIGW)
- Extended config schema, dispatch models, trigger, and parse_payload to carry SF/APIGW deploy-specific fields end-to-end
- All 204 tests pass, ruff clean on all modified files

## Task Commits

Each task was committed atomically:

1. **Task 1: Create envsubst module with content hash helpers (TDD)** - `e057633` (feat)
2. **Task 2: Update config schema, dispatch models, trigger, and parse_payload** - `b63a782` (feat)

_Task 1 followed TDD: RED (import error confirmed) then GREEN (18 tests pass)_

## Files Created/Modified
- `action/src/ferry_action/envsubst.py` - Shared envsubst, compute_content_hash, get_content_hash_tag
- `tests/test_action/test_envsubst.py` - 18 tests covering substitution, hashing, tag extraction
- `backend/src/ferry_backend/config/schema.py` - StepFunctionConfig + ApiGatewayConfig new required fields
- `utils/src/ferry_utils/models/dispatch.py` - StepFunctionResource + ApiGatewayResource deploy fields
- `backend/src/ferry_backend/dispatch/trigger.py` - _build_resource maps new config fields to dispatch models
- `action/src/ferry_action/parse_payload.py` - Type-dispatched matrix builders for all resource types
- `tests/test_backend/test_config_schema.py` - New field validation tests for SF/APIGW configs
- `tests/test_backend/test_dispatch_trigger.py` - _build_resource field mapping tests for SF/APIGW
- `tests/test_action/test_parse_payload.py` - SF and APIGW matrix building tests
- `tests/test_backend/test_changes.py` - Updated SF fixtures with new required fields
- `tests/test_utils/test_dispatch_models.py` - Updated SF/APIGW resource and payload tests

## Decisions Made
- Strict regex pattern `\$\{(ACCOUNT_ID|AWS_REGION)\}` for envsubst -- only matches known variables, inherently safe for JSONPath (`$.path`) since those use dollar-dot not dollar-brace
- get_content_hash_tag uses isinstance(tags, dict) check to differentiate SF list format from APIGW dict format
- parse_payload uses a _MATRIX_BUILDERS dispatch dict mapping resource_type to builder functions for clean extensibility

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated existing tests that construct SF/APIGW models without new required fields**
- **Found during:** Task 2 (model field updates)
- **Issue:** test_changes.py, test_dispatch_models.py contained StepFunctionConfig/ApiGatewayConfig/StepFunctionResource/ApiGatewayResource constructions without new required fields, causing ValidationError
- **Fix:** Added state_machine_name, definition_file to SF fixtures; rest_api_id, stage_name, spec_file to APIGW fixtures across 3 additional test files
- **Files modified:** tests/test_backend/test_changes.py, tests/test_utils/test_dispatch_models.py
- **Verification:** Full test suite (204 tests) passes
- **Committed in:** b63a782 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary fix for test compatibility with new required fields. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- envsubst module ready for Plans 02 (Step Functions deploy) and 03 (API Gateway deploy)
- Config schema, dispatch models, trigger, and parse_payload all carry type-specific fields end-to-end
- Both deploy modules can now read their required fields from the GHA matrix

---
## Self-Check: PASSED

- All created files verified to exist on disk
- Both task commits (e057633, b63a782) verified in git log
- All 204 tests pass, ruff clean on all modified files

---
*Phase: 04-extended-resource-types*
*Completed: 2026-02-26*
