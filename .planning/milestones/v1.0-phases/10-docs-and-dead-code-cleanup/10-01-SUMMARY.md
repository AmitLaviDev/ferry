---
phase: 10-docs-and-dead-code-cleanup
plan: 01
subsystem: docs
tags: [workflow-docs, github-actions, error-handling, dead-code]

# Dependency graph
requires:
  - phase: 08-error-surfacing
    provides: Check Run reporting (report.py) requiring checks:write permission and github-token/trigger-sha inputs
provides:
  - Updated workflow docs reflecting Phase 8 Check Run inputs and permissions
  - Clean error hierarchy without unused exception classes
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - docs/lambdas.md
    - docs/step-functions.md
    - docs/api-gateways.md
    - utils/src/ferry_utils/errors.py

key-decisions:
  - "Inline comments per permission line instead of block comment above permissions block"
  - "Deploy github-token uses github.token (auto-granted) not secrets.GH_PAT (private deps)"

patterns-established: []

requirements-completed: []

# Metrics
duration: 2min
completed: 2026-02-28
---

# Phase 10 Plan 01: Workflow Doc Gaps and Dead Code Cleanup Summary

**Backfilled checks:write permission and deploy inputs (trigger-sha, github-token) across all three workflow docs; removed unused BuildError and DeployError classes from error hierarchy**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-28T09:53:23Z
- **Completed:** 2026-02-28T09:55:16Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- All three workflow docs (lambdas, step-functions, api-gateways) now include checks:write permission with inline comments
- Lambda deploy step includes trigger-sha and github-token; SF and APIGW deploy steps include github-token
- Removed dead BuildError and DeployError classes that were never imported or used anywhere in the codebase
- All 272 existing tests continue to pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Update workflow doc permissions and deploy inputs** - `70c41e8` (docs)
2. **Task 2: Remove unused BuildError and DeployError classes** - `a1c5fe0` (fix)

## Files Created/Modified
- `docs/lambdas.md` - Added checks:write permission, trigger-sha and github-token to deploy step
- `docs/step-functions.md` - Added checks:write permission, github-token to deploy step
- `docs/api-gateways.md` - Added checks:write permission, github-token to deploy step
- `utils/src/ferry_utils/errors.py` - Removed unused BuildError and DeployError classes

## Decisions Made
- Inline comments per permission line instead of block comment above the permissions block (per plan)
- Deploy step github-token uses `${{ github.token }}` (auto-granted) not `${{ secrets.GH_PAT }}` (which is for private repo deps in build step)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- This is the final phase (Phase 10). All workflow docs are now accurate and dead code is removed.
- Project is at v1.0 milestone completion.

## Self-Check: PASSED

All 4 modified files verified present on disk. Both task commits (70c41e8, a1c5fe0) verified in git log.

---
*Phase: 10-docs-and-dead-code-cleanup*
*Completed: 2026-02-28*
