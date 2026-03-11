---
phase: 25-shared-models-and-schema
plan: 01
subsystem: api
tags: [pydantic, dispatch, schema, batched-dispatch]

# Dependency graph
requires: []
provides:
  - "BatchedDispatchPayload v2 model in ferry-utils"
  - "BATCHED_SCHEMA_VERSION constant (v=2)"
  - "Full test coverage for batched dispatch model"
affects: [26-backend-batch-builder, 27-action-batch-receiver]

# Tech tracking
tech-stack:
  added: []
  patterns: [typed-per-type-lists, literal-version-discriminator]

key-files:
  created: []
  modified:
    - utils/src/ferry_utils/constants.py
    - utils/src/ferry_utils/models/dispatch.py
    - utils/src/ferry_utils/models/__init__.py
    - utils/src/ferry_utils/__init__.py
    - tests/test_utils/test_dispatch_models.py

key-decisions:
  - "v: Literal[2] enforces version at type level for discriminated union parsing"
  - "Typed per-type lists (lambdas, step_functions, api_gateways) instead of flat discriminated union"

patterns-established:
  - "Version literal for payload discrimination: Literal[N] on v field"
  - "Additive model evolution: new model alongside existing, no modifications to v1"

requirements-completed: [DISP-02]

# Metrics
duration: 2min
completed: 2026-03-11
---

# Phase 25 Plan 01: Shared Models and Schema Summary

**BatchedDispatchPayload v2 Pydantic model with typed per-type resource lists, Literal[2] version enforcement, and full round-trip serialization tests**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-11T06:47:26Z
- **Completed:** 2026-03-11T06:49:52Z
- **Tasks:** 4
- **Files modified:** 5

## Accomplishments
- Added BATCHED_SCHEMA_VERSION = 2 constant alongside existing SCHEMA_VERSION = 1
- Created BatchedDispatchPayload model with typed per-type resource lists (lambdas, step_functions, api_gateways)
- Exported model and constant from ferry_utils top-level package
- 9 new tests covering round-trip serialization, version enforcement, immutability, and v1 backward compatibility guard

## Task Commits

Each task was committed atomically:

1. **Task 1: Add BATCHED_SCHEMA_VERSION constant** - `bfc6338` (feat)
2. **Task 2: Add BatchedDispatchPayload model** - `3b56ab6` (feat)
3. **Task 3: Update re-exports** - `f014c86` (feat)
4. **Task 4: Add BatchedDispatchPayload tests** - `178edec` (test)

## Files Created/Modified
- `utils/src/ferry_utils/constants.py` - Added BATCHED_SCHEMA_VERSION = 2
- `utils/src/ferry_utils/models/dispatch.py` - Added BatchedDispatchPayload class with v: Literal[2]
- `utils/src/ferry_utils/models/__init__.py` - Re-export BatchedDispatchPayload
- `utils/src/ferry_utils/__init__.py` - Re-export BatchedDispatchPayload and BATCHED_SCHEMA_VERSION
- `tests/test_utils/test_dispatch_models.py` - 9 new tests in TestBatchedDispatchPayload class

## Decisions Made
None - followed plan as specified.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- BatchedDispatchPayload is ready for consumption by phase 26 (backend batch builder) and phase 27 (action batch receiver)
- Model is importable from ferry_utils top-level: `from ferry_utils import BatchedDispatchPayload`
- All 28 tests pass (19 existing + 9 new), ruff lint clean

## Self-Check: PASSED

All 5 modified files exist. All 4 task commits verified (bfc6338, 3b56ab6, f014c86, 178edec).

---
*Phase: 25-shared-models-and-schema*
*Completed: 2026-03-11*
