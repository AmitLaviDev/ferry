---
phase: 09-tech-debt-cleanup-r2
plan: 01
subsystem: infra
tags: [pyproject, dependencies, moto, pyyaml, exports]

# Dependency graph
requires:
  - phase: 07-tech-debt-cleanup
    provides: "Existing workspace package structure and dependency declarations"
provides:
  - "Correct dependency declarations across all workspace packages"
  - "Clean public exports (no unused webhook models)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Each package declares only what it imports"
    - "Public __all__ exports only what is consumed by downstream code"

key-files:
  created: []
  modified:
    - backend/pyproject.toml
    - utils/pyproject.toml
    - pyproject.toml
    - utils/src/ferry_utils/__init__.py
    - utils/src/ferry_utils/models/__init__.py

key-decisions:
  - "Removed all four webhook re-exports (PushEvent, WebhookHeaders, Pusher, Repository) from models __init__ for consistency, not just the two flagged"

patterns-established:
  - "Dependency ownership: packages declare only the deps they directly import"

requirements-completed: []

# Metrics
duration: 2min
completed: 2026-02-28
---

# Phase 09 Plan 01: Dependency & Export Cleanup Summary

**Removed phantom tenacity dep, moved PyYAML to backend, added moto stepfunctions extra, and cleaned unused webhook models from public exports**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-28T08:27:13Z
- **Completed:** 2026-02-28T08:29:02Z
- **Tasks:** 2
- **Files modified:** 5 (+ uv.lock)

## Accomplishments
- Removed phantom tenacity dependency from backend (no file imports it)
- Moved PyYAML declaration from utils to backend where `import yaml` actually lives
- Added stepfunctions to moto extras for test coverage of SF deploy module
- Cleaned PushEvent, WebhookHeaders, Pusher, Repository from public re-exports
- All 272 existing tests pass after changes

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix dependency declarations across workspace packages** - `7103e20` (fix)
2. **Task 2: Remove PushEvent and WebhookHeaders from public exports** - `2fb5f49` (refactor)

## Files Created/Modified
- `backend/pyproject.toml` - Added PyYAML, removed tenacity
- `utils/pyproject.toml` - Removed PyYAML (no longer needed here)
- `pyproject.toml` - Added stepfunctions to moto extras
- `uv.lock` - Regenerated after dependency changes
- `utils/src/ferry_utils/__init__.py` - Removed PushEvent/WebhookHeaders from exports
- `utils/src/ferry_utils/models/__init__.py` - Removed all webhook model re-exports

## Decisions Made
- Removed all four webhook re-exports (PushEvent, WebhookHeaders, Pusher, Repository) from `ferry_utils.models.__init__` for consistency, not just the two explicitly flagged in success criteria. All four are unused in production code (confirmed by research grep).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All dependency hygiene items resolved
- Package exports are clean and minimal
- Ready for any subsequent development phases

## Self-Check: PASSED

All files found, all commits verified.

---
*Phase: 09-tech-debt-cleanup-r2*
*Completed: 2026-02-28*
