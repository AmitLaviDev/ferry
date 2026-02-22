---
phase: 01-foundation-and-shared-contract
plan: 01
subsystem: infra
tags: [uv-workspace, pydantic, monorepo, data-contract, structlog, pydantic-settings]

# Dependency graph
requires:
  - phase: none
    provides: "First plan in project - no prior dependencies"
provides:
  - "Three-package uv workspace (ferry-utils, ferry-backend, ferry-action)"
  - "Shared Pydantic data contract: DispatchPayload with discriminated union resource types"
  - "Webhook event models: PushEvent, WebhookHeaders, Repository, Pusher"
  - "Error type hierarchy: FerryError, WebhookValidationError, DuplicateDeliveryError, GitHubAuthError, ConfigError"
  - "Constants: ResourceType enum, SCHEMA_VERSION, RESOURCE_TYPE_WORKFLOW_MAP"
  - "Backend settings: pydantic-settings with FERRY_* env prefix"
  - "Structured JSON logging: structlog configured for Lambda CloudWatch output"
  - "Test infrastructure: conftest.py with moto DynamoDB fixture"
affects: [01-02, 01-03, 02-foundation, 03-build-deploy]

# Tech tracking
tech-stack:
  added: [pydantic, pydantic-settings, PyYAML, httpx, PyJWT, boto3, structlog, tenacity, moto, pytest, pytest-httpx, pytest-cov, ruff, mypy, pre-commit, boto3-stubs, hatchling]
  patterns: [uv-workspace, src-layout, pydantic-discriminated-union, frozen-models, pydantic-settings-env-prefix, structlog-json-lambda]

key-files:
  created:
    - pyproject.toml
    - utils/pyproject.toml
    - utils/src/ferry_utils/__init__.py
    - utils/src/ferry_utils/constants.py
    - utils/src/ferry_utils/errors.py
    - utils/src/ferry_utils/models/__init__.py
    - utils/src/ferry_utils/models/dispatch.py
    - utils/src/ferry_utils/models/webhook.py
    - backend/pyproject.toml
    - backend/src/ferry_backend/__init__.py
    - backend/src/ferry_backend/settings.py
    - backend/src/ferry_backend/logging.py
    - action/pyproject.toml
    - action/src/ferry_action/__init__.py
    - tests/conftest.py
    - tests/test_utils/test_dispatch_models.py
    - tests/test_utils/test_webhook_models.py
  modified: []

key-decisions:
  - "Used --all-packages flag for uv sync to ensure workspace members are installed (not just root deps)"
  - "Pydantic discriminated union uses X | Y | Z syntax per ruff UP007 (Python 3.14)"
  - "All models frozen via ConfigDict(frozen=True) for immutability"
  - "Mixed resource types allowed at model layer; application logic enforces single-type-per-payload"
  - "structlog make_filtering_bound_logger with numeric level conversion for flexible log level control"

patterns-established:
  - "uv workspace with src layout: utils/src/ferry_utils/, backend/src/ferry_backend/, action/src/ferry_action/"
  - "Pydantic frozen models with ConfigDict for all shared data types"
  - "Re-export pattern: models/__init__.py re-exports all models, package __init__.py re-exports key types"
  - "pydantic-settings with FERRY_ env prefix for backend configuration"
  - "structlog JSON output via PrintLoggerFactory for Lambda CloudWatch compatibility"
  - "moto mock_aws fixture in conftest.py for DynamoDB testing"

requirements-completed: [ACT-02]

# Metrics
duration: 4min
completed: 2026-02-22
---

# Phase 1 Plan 1: Foundation and Shared Contract Summary

**uv workspace monorepo with three packages, shared Pydantic dispatch payload contract (discriminated union for Lambda/StepFunction/ApiGateway), webhook event models, backend settings, and structured logging**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-22T19:39:06Z
- **Completed:** 2026-02-22T19:43:18Z
- **Tasks:** 3
- **Files modified:** 24

## Accomplishments
- Three-package uv workspace (ferry-utils, ferry-backend, ferry-action) fully installed and cross-importable
- Shared Pydantic data contract with DispatchPayload discriminated union, webhook event models, constants, and error types
- Backend pydantic-settings configuration loading FERRY_* env vars with validation
- Structured JSON logging configured for Lambda CloudWatch output
- 25 model validation tests all passing, zero lint errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold uv workspace with three packages** - `5bc28e4` (feat)
2. **Task 2: Create shared Pydantic data contract models** - `b7f8110` (feat)
3. **Task 3: Create backend settings and structured logging** - `c6656f3` (feat)
4. **Lint fixes** - `5930a9e` (fix)

## Files Created/Modified
- `pyproject.toml` - Workspace root with uv workspace config, dev deps, ruff/mypy/pytest tool config
- `utils/pyproject.toml` - ferry-utils package with pydantic, PyYAML dependencies
- `utils/src/ferry_utils/__init__.py` - Package init with re-exports of key types
- `utils/src/ferry_utils/constants.py` - ResourceType StrEnum, SCHEMA_VERSION, RESOURCE_TYPE_WORKFLOW_MAP
- `utils/src/ferry_utils/errors.py` - FerryError hierarchy (5 error types)
- `utils/src/ferry_utils/models/__init__.py` - Re-exports all models for convenient imports
- `utils/src/ferry_utils/models/dispatch.py` - DispatchPayload with discriminated union resource types
- `utils/src/ferry_utils/models/webhook.py` - PushEvent, WebhookHeaders, Repository, Pusher models
- `backend/pyproject.toml` - ferry-backend package with httpx, pydantic-settings, PyJWT, boto3, structlog
- `backend/src/ferry_backend/__init__.py` - Package init
- `backend/src/ferry_backend/settings.py` - Settings class loading FERRY_* env vars
- `backend/src/ferry_backend/logging.py` - structlog JSON configuration for Lambda
- `backend/src/ferry_backend/webhook/__init__.py` - Webhook subpackage stub
- `backend/src/ferry_backend/auth/__init__.py` - Auth subpackage stub
- `backend/src/ferry_backend/github/__init__.py` - GitHub client subpackage stub
- `action/pyproject.toml` - ferry-action package with ferry-utils workspace dependency
- `action/src/ferry_action/__init__.py` - Package init
- `tests/conftest.py` - Shared DynamoDB table fixture with moto mock_aws
- `tests/test_utils/test_dispatch_models.py` - 15 dispatch model validation tests
- `tests/test_utils/test_webhook_models.py` - 10 webhook model validation tests
- `uv.lock` - Generated lockfile for entire workspace

## Decisions Made
- Used `uv sync --all-packages` to install workspace members (standard `uv sync` only installs root deps)
- All Pydantic models use `ConfigDict(frozen=True)` for immutability
- Mixed resource types allowed at the model layer -- application logic will enforce single-type-per-payload in the dispatch pipeline
- structlog uses `make_filtering_bound_logger` with numeric level conversion for flexible log level control
- Private key validator strips whitespace to handle PEM formatting issues from environment variables

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff lint errors in models and tests**
- **Found during:** Overall verification (post-Task 3)
- **Issue:** Import sorting (I001) and Union type annotation style (UP007) did not match ruff rules
- **Fix:** Ran `ruff check . --fix` to auto-sort imports and convert `Union[X, Y, Z]` to `X | Y | Z`
- **Files modified:** `utils/src/ferry_utils/models/__init__.py`, `utils/src/ferry_utils/models/dispatch.py`, `tests/test_utils/test_webhook_models.py`
- **Verification:** `ruff check .` passes, all 25 tests still pass
- **Committed in:** `5930a9e`

---

**Total deviations:** 1 auto-fixed (1 lint fix)
**Impact on plan:** Trivial formatting fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Workspace structure and shared contract ready for Plans 01-02 (webhook handler + dedup) and 01-03 (GitHub App auth)
- Backend subpackage stubs (webhook/, auth/, github/) ready for implementation
- Test infrastructure (conftest.py with DynamoDB fixture) ready for integration tests
- Shared models importable from both backend and action packages

## Self-Check: PASSED

All 20 created files verified present. All 4 commits (5bc28e4, b7f8110, c6656f3, 5930a9e) verified in git log.

---
*Phase: 01-foundation-and-shared-contract*
*Completed: 2026-02-22*
