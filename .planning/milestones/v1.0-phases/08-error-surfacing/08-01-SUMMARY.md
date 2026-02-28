---
phase: 08-error-surfacing
plan: 01
subsystem: error-handling
tags: [exception-handling, pr-comments, github-api, structlog, error-hierarchy]

# Dependency graph
requires:
  - phase: 02-app-core-logic/plan-03
    provides: create_check_run, find_open_prs, handler pipeline, GitHubClient
  - phase: 01-foundation-and-shared-contract/plan-03
    provides: GitHubClient, GitHubAuthError, FerryError hierarchy
provides:
  - Top-level exception handler for all unhandled errors in webhook handler
  - post_pr_comment function for surfacing config errors on PRs
  - find_merged_pr function for locating merged PRs on default branch pushes
  - GitHubClient.patch() method for Check Run updates
  - BuildError and DeployError types in shared error hierarchy
affects: [08-error-surfacing/plan-02]

# Tech tracking
tech-stack:
  added: []
  patterns: [structured error responses for all handler paths, PR comment for config errors instead of Check Run, merged PR lookup for default branch error surfacing]

key-files:
  created: []
  modified:
    - utils/src/ferry_utils/errors.py
    - backend/src/ferry_backend/github/client.py
    - backend/src/ferry_backend/checks/runs.py
    - backend/src/ferry_backend/webhook/handler.py
    - tests/test_backend/test_check_runs.py
    - tests/test_backend/test_handler_phase2.py

key-decisions:
  - "Config errors surface as PR comments (not Check Runs) per user decision -- applies to both PR and default branches"
  - "Default branch config errors use find_merged_pr to locate the merged PR for commenting"
  - "Auth errors return structured 500 with logging only -- not surfaced to developers (infra-visible)"
  - "Catch-all Exception returns generic 500 without leaking internal details"
  - "ConfigError handler placed after dedup (steps 8-13) so after_sha is always available"

patterns-established:
  - "Top-level try/except wrapping steps 8-13: ConfigError -> PR comment, GitHubAuthError -> structured 500, Exception -> generic 500"
  - "find_merged_pr filters by merged_at (not state) to find closed+merged PRs"
  - "post_pr_comment uses issues API endpoint (/issues/{pr_number}/comments)"

requirements-completed: [WHOOK-03]

# Metrics
duration: 4min
completed: 2026-02-28
---

# Phase 08 Plan 01: Backend Error Handling Summary

**Top-level exception handler catching auth/config/unhandled errors with structured responses, config errors surfaced as PR comments via find_merged_pr and post_pr_comment, error hierarchy extended with BuildError/DeployError**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-28T06:53:28Z
- **Completed:** 2026-02-28T06:58:10Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- No exception can escape the handler as an unstructured Lambda 500 -- all paths return structured JSON responses
- Config errors produce PR comments (not Check Runs) on both PR branches and default branches
- Default branch config errors use find_merged_pr to locate the merged PR for commenting
- Auth errors produce structured 500 responses with structlog logging (infra-visible only)
- BuildError and DeployError types added to shared error hierarchy for action-side use
- GitHubClient.patch() method added following existing get/post pattern
- 272 total tests passing with zero ruff lint errors in modified files

## Task Commits

Each task was committed atomically:

1. **Task 1: Backend error hierarchy, GitHubClient.patch(), PR comment + find merged PR** - `796c3a7` (feat)
2. **Task 2: Handler top-level exception handler + config error as PR comment** - `feff89d` (feat)

## Files Created/Modified
- `utils/src/ferry_utils/errors.py` - Added BuildError and DeployError to error hierarchy
- `backend/src/ferry_backend/github/client.py` - Added patch() method to GitHubClient
- `backend/src/ferry_backend/checks/runs.py` - Added find_merged_pr and post_pr_comment functions
- `backend/src/ferry_backend/webhook/handler.py` - Top-level exception handler, config error as PR comment
- `tests/test_backend/test_check_runs.py` - Tests for find_merged_pr and post_pr_comment
- `tests/test_backend/test_handler_phase2.py` - Tests for auth error, unhandled error, config error as PR comment

## Decisions Made
- Config errors surface as PR comments (not Check Runs) per user decision -- the "Ferry: Deployment Plan" Check Run only appears when config is valid
- Default branch config errors use find_merged_pr to locate the merged PR, with a warning log if no PR is found
- Auth errors are logged with structlog (exc_info=True for CloudWatch) but NOT surfaced to developers
- Catch-all Exception returns "internal server error" to avoid leaking internal details
- find_open_prs called first in ConfigError handler; if no open PRs, falls back to find_merged_pr

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- pytest-httpx consumes each mock response once -- the default branch config error test needed two registrations for the commits/{sha}/pulls endpoint since both find_open_prs and find_merged_pr hit the same URL. Fixed by registering the mock response twice.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Backend error handling is complete: all handler paths return structured JSON
- Plan 02 (action-side Check Run reporting) can proceed -- it will use BuildError/DeployError and the GitHubClient.patch() method added here
- The create_check_run function retains its error parameter for backward compatibility but handler.py no longer uses it for config errors

## Self-Check: PASSED

All 6 modified files verified on disk. Both task commits (796c3a7, feff89d) verified in git log.

---
*Phase: 08-error-surfacing*
*Completed: 2026-02-28*
