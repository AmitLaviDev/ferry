---
phase: 04-extended-resource-types
plan: 03
subsystem: deploy
tags: [api-gateway, openapi, swagger, envsubst, content-hash, put-rest-api, composite-action]

# Dependency graph
requires:
  - phase: 04-extended-resource-types
    plan: 01
    provides: "envsubst module, compute_content_hash, get_content_hash_tag, ApiGatewayConfig/Resource models"
  - phase: 03-build-and-lambda-deploy
    provides: "Lambda deploy module pattern, gha.py helpers, composite action structure"
provides:
  - "deploy_apigw.py: API Gateway deploy with OpenAPI spec parsing, field stripping, content-hash skip"
  - "Composite action at action/deploy-apigw/action.yml"
affects: [05-integration-and-error-reporting]

# Tech tracking
tech-stack:
  added: [pyyaml, openapi-spec-validator]
  patterns: [OpenAPI field stripping for AWS-managed fields, canonical JSON hashing for deterministic change detection]

key-files:
  created:
    - action/src/ferry_action/deploy_apigw.py
    - action/deploy-apigw/action.yml
    - tests/test_action/test_deploy_apigw.py
  modified:
    - action/pyproject.toml
    - pyproject.toml

key-decisions:
  - "pyyaml added to ferry-action deps for YAML spec parsing; moto[apigateway] added to dev deps"
  - "Canonical JSON (sort_keys=True, compact separators) for deterministic hashing regardless of input format"
  - "Moto requires x-amazon-apigateway-integration in spec for create_deployment; tests use valid integration specs"

patterns-established:
  - "OpenAPI field stripping: shallow-copy + pop for Swagger 2.0 and OpenAPI 3.x AWS-managed fields"
  - "Content-hash skip via API Gateway tags: get_tags with flat dict format, tag_resource for updates"
  - "API Gateway deploy: put_rest_api(mode=overwrite, body=bytes) + create_deployment(stageName=...)"

requirements-completed: [DEPLOY-03]

# Metrics
duration: 5min
completed: 2026-02-26
---

# Phase 4 Plan 3: API Gateway Deploy Summary

**API Gateway deploy module with OpenAPI/Swagger spec parsing (JSON+YAML), envsubst, field stripping, canonical JSON content-hash skip, and put_rest_api + create_deployment pipeline**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-26T19:07:43Z
- **Completed:** 2026-02-26T19:13:23Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created deploy_apigw.py with full lifecycle: read spec (JSON/YAML), envsubst, strip problematic fields (host/schemes/basePath/servers), canonical JSON hash, content-hash skip via tags, put_rest_api + create_deployment, GHA summary
- 21 TDD tests covering strip_openapi_fields, should_skip_deploy, deploy_api_gateway, and main() with moto for API operations and manual mocks for tag operations
- Composite action YAML at action/deploy-apigw/action.yml matching Lambda deploy action pattern

## Task Commits

Each task was committed atomically:

1. **Task 1: API Gateway deploy module (TDD)** - `f91a4f3` (feat)
2. **Task 2: Create API Gateway composite action YAML** - `65a2d4b` (feat)

_Task 1 followed TDD: RED (ModuleNotFoundError confirmed) then GREEN (21 tests pass)_

## Files Created/Modified
- `action/src/ferry_action/deploy_apigw.py` - API Gateway deploy with spec parsing, field stripping, content-hash skip, put_rest_api + create_deployment
- `action/deploy-apigw/action.yml` - Composite action for API Gateway deployment
- `tests/test_action/test_deploy_apigw.py` - 21 tests (5 strip, 4 skip, 5 deploy, 7 main)
- `action/pyproject.toml` - Added pyyaml dependency
- `pyproject.toml` - Added moto[apigateway] to dev deps

## Decisions Made
- Added pyyaml to ferry-action dependencies for YAML spec file support; moto[apigateway] extra to dev dependencies for openapi-spec-validator
- Canonical JSON serialization (sort_keys=True, separators=(",",":")) ensures deterministic hashing regardless of original key ordering or format (JSON vs YAML)
- Moto's create_deployment requires API to have methods; test specs include x-amazon-apigateway-integration for valid moto behavior
- _tag_content_hash extracted as separate function for easy mocking in main() tests (moto does not support APIGW tag_resource/get_tags)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed openapi-spec-validator for moto API Gateway support**
- **Found during:** Task 1 (GREEN phase, first run with moto API Gateway)
- **Issue:** moto's apigateway module requires openapi-spec-validator which was not installed; tests errored with ModuleNotFoundError
- **Fix:** Added moto[apigateway] extra to dev dependencies in pyproject.toml, ran uv sync
- **Files modified:** pyproject.toml, uv.lock
- **Verification:** All moto API Gateway operations work; 21 tests pass
- **Committed in:** f91a4f3 (Task 1 commit)

**2. [Rule 1 - Bug] Updated test specs to include x-amazon-apigateway-integration**
- **Found during:** Task 1 (GREEN phase, moto create_deployment fails)
- **Issue:** moto's create_deployment requires REST API to have methods; bare specs with only paths/responses don't create methods in moto
- **Fix:** Created VALID_MOTO_SPEC constant with x-amazon-apigateway-integration, used for all tests requiring moto deployment
- **Files modified:** tests/test_action/test_deploy_apigw.py
- **Verification:** create_deployment succeeds with proper specs; all 21 tests pass
- **Committed in:** f91a4f3 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for moto compatibility. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three deploy modules complete: Lambda (phase 3), Step Functions (04-02), API Gateway (04-03)
- Phase 4 complete -- ready for Phase 5 integration and error reporting
- Full test suite: 237 tests passing

---
## Self-Check: PASSED

- All created files verified to exist on disk (deploy_apigw.py, action.yml, test_deploy_apigw.py)
- Both task commits (f91a4f3, 65a2d4b) verified in git log
- All 237 tests pass, ruff clean on all modified files

---
*Phase: 04-extended-resource-types*
*Completed: 2026-02-26*
