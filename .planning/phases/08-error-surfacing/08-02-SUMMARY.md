---
phase: 08-error-surfacing
plan: 02
subsystem: action
tags: [github-check-runs, httpx, error-reporting, gha-annotations, debug-mode]

# Dependency graph
requires:
  - phase: 03-build-and-lambda-deploy
    provides: build.py, deploy.py, composite action.yml files
  - phase: 04-extended-resource-types
    provides: deploy_stepfunctions.py, deploy_apigw.py
provides:
  - report.py module with report_check_run and format_error_detail
  - mask_account_id helper in gha.py
  - Check Run reporting integrated into all build/deploy modules
  - github-token input on all composite actions
affects: [08-error-surfacing]

# Tech tracking
tech-stack:
  added: [httpx (ferry-action dependency)]
  patterns: [Check Run reporter pattern, debug-mode error detail toggle, step-by-step progress output]

key-files:
  created:
    - action/src/ferry_action/report.py
    - tests/test_action/test_report.py
  modified:
    - action/src/ferry_action/gha.py
    - action/src/ferry_action/build.py
    - action/src/ferry_action/deploy.py
    - action/src/ferry_action/deploy_stepfunctions.py
    - action/src/ferry_action/deploy_apigw.py
    - action/build/action.yml
    - action/deploy/action.yml
    - action/deploy-stepfunctions/action.yml
    - action/deploy-apigw/action.yml
    - action/pyproject.toml
    - tests/test_action/test_gha.py

key-decisions:
  - "GITHUB_TOKEN read from env in report.py (not passed as parameter) for clean API surface"
  - "Check Run creation is non-critical: wrapped in try/except to never fail the build/deploy"
  - "Reuse existing github-token input in build action for dual purpose (private deps + Check Runs)"
  - "trigger-sha input added to deploy/action.yml (was missing) for Check Run attachment"

patterns-established:
  - "report_check_run pattern: call before sys.exit on failure, after success output on success"
  - "format_error_detail for GHA annotations, terse summary for Check Run body"
  - "Step-by-step progress: [1/N] prefix for build phases"

requirements-completed: [WHOOK-03]

# Metrics
duration: 6min
completed: 2026-02-28
---

# Phase 8 Plan 2: Action-Side Error Surfacing Summary

**Per-resource GitHub Check Runs via report.py module with FERRY_DEBUG traceback toggle and mask_account_id helper, integrated into all build/deploy modules**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-28T06:53:22Z
- **Completed:** 2026-02-28T07:00:01Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments
- Created report.py with report_check_run (GitHub Check Run API) and format_error_detail (FERRY_DEBUG toggle)
- Added mask_account_id to gha.py for partial AWS account ID masking in error messages
- Integrated Check Run reporting into build.py, deploy.py, deploy_stepfunctions.py, and deploy_apigw.py
- All four composite action.yml files now accept github-token input and pass GITHUB_TOKEN env
- Step-by-step progress output in build.py ([1/3], [2/3], [3/3])
- Skip events produce success Check Runs with explicit skip message

## Task Commits

Each task was committed atomically:

1. **Task 1: Check Run reporter module + gha helpers + httpx dependency** - `f0605ae` (feat)
2. **Task 2: Integrate reporting into build/deploy modules + action.yml github-token input** - `e61cd48` (feat)

## Files Created/Modified
- `action/src/ferry_action/report.py` - Check Run reporter (report_check_run, format_error_detail)
- `action/src/ferry_action/gha.py` - Added mask_account_id helper
- `action/src/ferry_action/build.py` - Check Run reporting on success/failure, step progress
- `action/src/ferry_action/deploy.py` - Check Run reporting on success/skip/failure
- `action/src/ferry_action/deploy_stepfunctions.py` - Check Run reporting on success/skip/failure
- `action/src/ferry_action/deploy_apigw.py` - Check Run reporting on success/skip/failure
- `action/build/action.yml` - Added GITHUB_TOKEN env mapping
- `action/deploy/action.yml` - Added github-token input, trigger-sha input, GITHUB_TOKEN env
- `action/deploy-stepfunctions/action.yml` - Added github-token input, GITHUB_TOKEN env
- `action/deploy-apigw/action.yml` - Added github-token input, GITHUB_TOKEN env
- `action/pyproject.toml` - Added httpx>=0.27 dependency
- `tests/test_action/test_report.py` - Tests for report_check_run and format_error_detail
- `tests/test_action/test_gha.py` - Tests for mask_account_id

## Decisions Made
- GITHUB_TOKEN read from env in report.py (not passed as parameter) for clean API surface -- modules just call report_check_run without auth plumbing
- Check Run creation wrapped in try/except: never fails the actual build/deploy (non-critical reporting)
- Reused existing github-token input in build/action.yml for dual purpose (private deps + Check Runs) instead of adding a second input
- Added trigger-sha input to deploy/action.yml which was missing -- needed for Check Run SHA attachment

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added trigger-sha input to deploy/action.yml**
- **Found during:** Task 2 (action.yml updates)
- **Issue:** deploy/action.yml did not have a trigger-sha input, but deploy.py needs INPUT_TRIGGER_SHA for Check Run reporting
- **Fix:** Added trigger-sha input (required: false, default: "") and INPUT_TRIGGER_SHA env mapping
- **Files modified:** action/deploy/action.yml
- **Verification:** deploy.py reads trigger_sha via os.environ.get("INPUT_TRIGGER_SHA", "")
- **Committed in:** e61cd48 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential for deploy.py to have trigger_sha available for Check Run creation. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Action-side error surfacing complete -- all build/deploy outcomes surface as GitHub Check Runs on PRs
- Backend-side error surfacing (08-01) handles config errors as PR comments
- Together, 08-01 and 08-02 close WHOOK-03 requirement

## Self-Check: PASSED

All created files exist. All commit hashes verified.

---
*Phase: 08-error-surfacing*
*Completed: 2026-02-28*
