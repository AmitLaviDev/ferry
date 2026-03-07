---
phase: 17-end-to-end-loop-validation
plan: 01
subsystem: api
tags: [github-api, error-handling, httpx, structlog]

# Dependency graph
requires:
  - phase: 08-error-surfacing
    provides: "Check runs and PR comment functions"
provides:
  - "Graceful 403/error handling in find_open_prs and find_merged_pr"
  - "Tests covering non-200 response paths for PR lookup"
affects: [17-02, 17-03]

# Tech tracking
tech-stack:
  added: []
  patterns: ["status_code guard before resp.json() on read-only GitHub API calls"]

key-files:
  created: []
  modified:
    - backend/src/ferry_backend/checks/runs.py
    - tests/test_backend/test_check_runs.py

key-decisions:
  - "Return safe defaults on any non-200 (not just 403) to cover rate limits, 500s, etc."
  - "Log warning with structlog but do not raise -- caller decides behavior on empty result"

patterns-established:
  - "Status code guard pattern: check resp.status_code != 200 before .json() on GitHub read endpoints"

requirements-completed: [E2E-08]

# Metrics
duration: 1min
completed: 2026-03-07
---

# Phase 17 Plan 01: Fix 403 Bug Summary

**Graceful non-200 handling in find_open_prs and find_merged_pr with status_code guard and structlog warning**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-07T18:33:20Z
- **Completed:** 2026-03-07T18:34:28Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Fixed known bug where find_open_prs crashes on 403 (dict has no "state" key in list comprehension)
- Fixed same pattern in find_merged_pr (dict iteration fails on error response body)
- Added 4 new tests covering 403, 500, and 200 regression paths
- Full test suite (280 tests) passes

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix 403 handling in find_open_prs and find_merged_pr** - `bbee950` (fix)
2. **Task 2: Add tests for 403 handling in PR lookup functions** - `58d1157` (test)

## Files Created/Modified
- `backend/src/ferry_backend/checks/runs.py` - Added status_code guard in find_open_prs and find_merged_pr
- `tests/test_backend/test_check_runs.py` - Added TestFindOpenPrs403 class with 4 tests

## Decisions Made
- Guard on any non-200 status (not just 403) to also cover rate limits (429) and server errors (500)
- Do not raise exceptions -- return safe defaults ([] or None) and let caller handle gracefully

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The 403 bug blocker is resolved, E2E validation loop (plans 02-03) can proceed
- No blockers remaining for this fix

## Self-Check: PASSED

All files and commits verified.

---
*Phase: 17-end-to-end-loop-validation*
*Completed: 2026-03-07*
