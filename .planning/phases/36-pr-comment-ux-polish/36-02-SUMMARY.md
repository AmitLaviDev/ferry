---
phase: 36-pr-comment-ux-polish
plan: 02
subsystem: api
tags: [github-api, pr-comments, e2e-validation, ux]

# Dependency graph
requires:
  - phase: 36-01
    provides: "Plan comment table format, sticky deploy comment, status updates, merge deploy comment"
provides:
  - "E2E validation of all Phase 36 UX changes on real PR"
  - "Bug fix: find_merged_pr race condition with GitHub API"
affects: [37-schema-simplification]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - backend/src/ferry_backend/checks/runs.py
    - tests/test_backend/test_check_runs.py

key-decisions:
  - "Deploy comments create one per /ferry apply (not upsert) -- SHA marker ties each to its workflow_run"
  - "find_merged_pr falls back to state=closed when merged_at not yet set (GitHub API race condition)"

patterns-established: []

requirements-completed: [UX-01, UX-02, UX-03, UX-04, UX-05]

# Metrics
duration: 15min
completed: 2026-03-14
---

# Phase 36 Plan 02: E2E Validation Summary

**Full PR lifecycle validated E2E: plan comment with resource table, deploy comment with status progression, merge deploy with pr-N tag -- plus race condition bug fix in find_merged_pr**

## Performance

- **Duration:** 15 min
- **Started:** 2026-03-14T15:08:51Z
- **Completed:** 2026-03-14T15:24:23Z
- **Tasks:** 6
- **Files modified:** 2

## Accomplishments

- All 6 UX changes validated on real PR #4 in AmitLaviDev/ferry-test-app
- Fixed GitHub API race condition where merge deploy comment was silently skipped
- Full deploy lifecycle proven: plan comment -> /ferry apply -> status update -> second apply -> merge deploy
- Tag format validated: branch-sha4 for PR deploys, pr-N for merge deploys

## Task Commits

Each task was committed atomically:

1. **Tasks 1-4: Deploy + Plan + Apply + Status** -- validated on PR #3 (prior session, commits acc4b98..b670156)
2. **Task 5: Bug fix + re-validation** -- `edde601` (fix: find_merged_pr race condition)
3. **Task 6: Merge deploy** -- validated on PR #4, deploy comment posted and updated

**Plan metadata:** (pending)

## E2E Validation Results

### PR #4 (AmitLaviDev/ferry-test-app)

**Task 2 -- Plan comment table format:**
- Header: "Ferry: Deployment Plan -> **staging**"
- Summary: "1 Lambda, 1 Step Function, 1 API Gateway"
- Collapsible table with Type | Resource columns
- Footer: "Deploy with `/ferry apply` or merge to auto-deploy to **staging**."

**Task 3 -- Deploy comment with resource table:**
- Header: "Ferry: Deploying -> **staging**"
- Tag: `ux-polish-final-validation-b155`
- 3 resources with hourglass status
- Eyes reaction on /ferry apply comment

**Task 4 -- Status update after workflow completion:**
- Header changed: "Deploying" -> "Deployed" with checkmark
- All 3 resources: hourglass -> checkmark
- Run link appended at bottom

**Task 5 -- Second /ferry apply:**
- New deploy comment created with new SHA (458b5bb)
- workflow_run correctly updated the new comment (not the old one)
- SHA-based correlation works correctly across multiple deploys

**Task 6 -- Merge deploy:**
- Deploy comment posted on merged PR with tag `pr-4`
- After workflow_run: "Deploying" -> "Deployed" with checkmark
- All 3 resources show checkmark, run link present

## Files Created/Modified

- `backend/src/ferry_backend/checks/runs.py` -- find_merged_pr: fall back to state=closed when merged_at not set
- `tests/test_backend/test_check_runs.py` -- updated tests for closed-state fallback, added only-open returns None

## Decisions Made

- Deploy comments: one per /ferry apply (not upsert). Each has a SHA marker; workflow_run handler matches by SHA to update the correct comment. This preserves deploy history on the PR.
- find_merged_pr accepts state=closed as fallback for merged_at race condition. GitHub API may not propagate merged_at within seconds of merge.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] find_merged_pr race condition with GitHub API**
- **Found during:** Task 5/6 analysis (investigating why PR #3 merge deploy had no comment)
- **Issue:** GitHub commits/pulls API returns PR with state=closed but merged_at=null within seconds of merge. find_merged_pr only checked merged_at, so it returned None, silently skipping the deploy comment post.
- **Fix:** Added fallback: if no PR has merged_at set, accept first PR with state=closed.
- **Files modified:** backend/src/ferry_backend/checks/runs.py, tests/test_backend/test_check_runs.py
- **Verification:** PR #4 merge deploy comment posted successfully; 443 tests pass
- **Committed in:** edde601

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix for merge deploy visibility. Without it, merge deploys would silently skip PR comments.

## Issues Encountered

- PR #3 (from prior session) was already merged, requiring a new PR #4 for complete E2E validation
- The original plan expected sticky (upsert) deploy comments, but prior session changed to one-per-apply design -- plan's Task 5 expectations were outdated, behavior is correct per design decision

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 36 complete -- all v2.0 UX improvements validated
- v2.0 milestone ready to ship
- Phase 37 (Schema Simplification) can proceed

---
*Phase: 36-pr-comment-ux-polish*
*Completed: 2026-03-14*
