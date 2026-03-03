---
phase: 14-self-deploy-manual-setup
plan: 01
subsystem: infra
tags: [docker, uv, secrets-manager, boto3, pydantic-settings, lambda]

# Dependency graph
requires:
  - phase: 13-backend-core
    provides: Lambda function, Secrets Manager containers, DynamoDB table
provides:
  - Multi-stage Dockerfile for ferry-backend Lambda container image
  - Secrets Manager resolution in settings.py at cold start
  - .dockerignore for efficient Docker build context
affects: [14-02-self-deploy-workflow, 14-03-setup-runbook]

# Tech tracking
tech-stack:
  added: [public.ecr.aws/lambda/python:3.14, ghcr.io/astral-sh/uv:0.10]
  patterns: [uv-export-workspace-docker, secrets-manager-model-validator]

key-files:
  created:
    - Dockerfile
    - .dockerignore
    - tests/test_settings.py
  modified:
    - backend/src/ferry_backend/settings.py

key-decisions:
  - "Hardcoded region_name='us-east-1' in SM boto3 client for explicit behavior"
  - "Two-stage uv export pattern: --no-emit-workspace for cached deps layer, full export for workspace members"

patterns-established:
  - "uv workspace Docker pattern: export third-party deps separately from workspace members for layer caching"
  - "SM resolution via pydantic model_validator(mode='after') with object.__setattr__ for frozen model bypass"

requirements-completed: [DEPLOY-01, DEPLOY-03]

# Metrics
duration: 3min
completed: 2026-03-03
---

# Phase 14 Plan 01: Backend Dockerfile + Secrets Manager Resolution Summary

**Multi-stage Docker build with uv workspace pattern and pydantic model_validator for Secrets Manager cold-start resolution**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-03T07:57:38Z
- **Completed:** 2026-03-03T08:00:51Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Multi-stage Dockerfile builds ferry-utils + ferry-backend from repo root with optimal layer caching
- settings.py resolves Secrets Manager values when FERRY_*_SECRET env vars present (Lambda deployment)
- Local dev continues working with plain FERRY_* env vars (no SM dependency)
- .dockerignore reduces build context by excluding .git, .venv, iac, tests, docs, etc.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create backend Dockerfile and .dockerignore** - `a0ecc65` (feat)
2. **Task 2: Add Secrets Manager resolution to settings.py with tests** - `dcb1b96` (feat)

## Files Created/Modified
- `Dockerfile` - Multi-stage Docker build for ferry-backend Lambda container
- `.dockerignore` - Build context exclusions for efficient Docker builds
- `backend/src/ferry_backend/settings.py` - Added SM resolution model_validator and _SECRET fields
- `tests/test_settings.py` - Tests for local dev, SM resolution, and mixed modes

## Decisions Made
- Hardcoded `region_name="us-east-1"` in the SM boto3 client call rather than relying on AWS_DEFAULT_REGION env var -- matches handler.py pattern and prevents failures if env var missing
- Used `uv export` two-stage pattern from official uv docs: first export excludes workspace members (cached layer), second includes them after source copy

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added region_name to boto3 secretsmanager client**
- **Found during:** Task 2 (Secrets Manager resolution)
- **Issue:** `boto3.client("secretsmanager")` without region_name fails when AWS_DEFAULT_REGION is not set (test environment)
- **Fix:** Added `region_name="us-east-1"` to match handler.py pattern
- **Files modified:** backend/src/ferry_backend/settings.py
- **Verification:** All 4 tests pass
- **Committed in:** dcb1b96 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential for correctness. No scope creep.

## Issues Encountered
- Ruff pre-commit hook auto-removed unused `pytest` import from test file -- resolved by re-staging and committing

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Dockerfile ready for self-deploy GHA workflow (Plan 02)
- settings.py SM resolution ready for Lambda deployment
- Docker build verified through builder stage locally

## Self-Check: PASSED

All files verified present, all commits verified in git log.

---
*Phase: 14-self-deploy-manual-setup*
*Completed: 2026-03-03*
