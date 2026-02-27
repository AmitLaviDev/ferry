---
phase: 03-build-and-lambda-deploy
plan: 03
subsystem: action
tags: [lambda, deploy, ecr, alias, versioning, digest-skip, moto, tdd]

requires:
  - phase: 03-build-and-lambda-deploy
    provides: "Composite action scaffold (action.yml files, gha.py helpers) from plan 01"
provides:
  - "deploy.py: Lambda deployment with version/alias management and digest-based skip"
  - "Full deploy sequence: update_function_code -> wait -> publish_version -> update/create alias"
  - "Digest-based skip logic: matching sha256 digest skips deployment entirely"
  - "GHA outputs (skipped, lambda-version) and per-resource job summary"
affects: [04-extended-resource-types, 05-integration-error-reporting]

tech-stack:
  added: []
  patterns: [digest-based-skip, lambda-version-alias-management, moto-fixture-based-mock]

key-files:
  created:
    - action/src/ferry_action/deploy.py
    - tests/test_action/test_deploy.py
  modified: []

key-decisions:
  - "Fixture-based mock_aws instead of per-test decorator (avoids fixture-outside-mock-context issue)"
  - "Digest normalization strips URI prefix before comparison (handles both raw sha256: and full URI@sha256: formats)"
  - "Alias fallback: try update_alias first, catch ResourceNotFoundException, fall back to create_alias"

patterns-established:
  - "Lambda deploy pattern: update_function_code -> waiter -> publish_version -> update/create alias"
  - "moto fixture pattern: aws_env -> moto_aws (context manager) -> lambda_client/lambda_function"

requirements-completed: [DEPLOY-04, DEPLOY-05]

duration: 3min
completed: 2026-02-26
---

# Phase 3 Plan 03: Lambda Deploy Summary

**Lambda deployment module with version/alias management, digest-based skip, and per-resource GHA job summaries**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-26T08:06:26Z
- **Completed:** 2026-02-26T08:10:00Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Lambda deploy module with full sequence: update code, wait for readiness, publish immutable version, update/create alias
- Digest-based skip: when pushed image digest matches currently deployed digest, deployment is skipped entirely
- GHA outputs (skipped flag, lambda-version) written to GITHUB_OUTPUT for downstream steps
- Per-resource job summary markdown table with function name, image URI, version, alias, status, and deployment tag
- User-friendly error hints for AccessDeniedException, ResourceNotFoundException, and waiter timeout
- 14 moto-based tests covering all code paths (pure functions, AWS operations, main orchestration)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for deploy module** - `c901338` (test)
2. **Task 1 GREEN: Implement deploy.py** - `9f6762c` (feat)

## Files Created/Modified
- `action/src/ferry_action/deploy.py` - Lambda deployment: update code, wait, publish version, update/create alias, digest skip
- `tests/test_action/test_deploy.py` - 14 moto-based tests: should_skip_deploy, get_current_image_digest, deploy_lambda, main()

## Decisions Made
- **Fixture-based mock_aws:** Used a `moto_aws` fixture (context manager) instead of `@mock_aws` decorator on individual tests to ensure fixtures (IAM role, Lambda function) run inside the mock context.
- **Digest normalization:** `should_skip_deploy` normalizes both digests by stripping URI prefix before comparison, handling both `sha256:...` and `repo@sha256:...` formats.
- **Alias create/update fallback:** `deploy_lambda` attempts `update_alias` first; on `ResourceNotFoundException` it falls back to `create_alias`. This handles both first-deploy and subsequent-deploy cases.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed moto mock_aws scope for test fixtures**
- **Found during:** Task 1 GREEN phase (running tests)
- **Issue:** `@mock_aws` decorator on test methods did not wrap fixture setup, causing real AWS API calls from fixture code (IAM create_role, Lambda create_function) to fail with `InvalidClientTokenId`
- **Fix:** Replaced per-test `@mock_aws` decorators with a `moto_aws` pytest fixture using `with mock_aws():` context manager, ensuring all fixtures and tests run inside the mock
- **Files modified:** `tests/test_action/test_deploy.py`
- **Verification:** All 14 tests pass, no real AWS calls made
- **Committed in:** `9f6762c` (part of GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test infrastructure fix only. No scope creep.

## Issues Encountered
None beyond the mock_aws scope issue documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Lambda deploy pipeline complete: build (plan 02) produces ECR image, deploy (plan 03) updates Lambda
- Phase 3 fully delivers the build-and-deploy pipeline for Lambda resources
- Ready for Phase 4 (Step Functions, API Gateway) which will follow similar deploy patterns
- Ready for Phase 5 (E2E integration) which will test the full webhook -> dispatch -> build -> deploy flow

## Self-Check: PASSED

- FOUND: action/src/ferry_action/deploy.py (238 lines, min 80)
- FOUND: tests/test_action/test_deploy.py (366 lines, min 80)
- FOUND: 03-03-SUMMARY.md
- FOUND: c901338 (RED commit)
- FOUND: 9f6762c (GREEN commit)
- All 14 tests pass
- All 175 tests pass (full suite)
- Ruff lint: all checks passed

---
*Phase: 03-build-and-lambda-deploy*
*Completed: 2026-02-26*
