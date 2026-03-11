---
phase: 27-action-parsing-and-workflow-template
plan: 01
subsystem: action
tags: [parse-payload, v2-dispatch, boolean-flags, per-type-matrix, workflow-template, tdd]

# Dependency graph
requires:
  - "BatchedDispatchPayload v2 model with computed resource_types from phase 25+27"
  - "Batched dispatch path in trigger.py from phase 26"
provides:
  - "parse_payload() with v1/v2 dispatch routing"
  - "ParseResult dataclass with per-type outputs"
  - "Setup action with 7 per-type outputs"
  - "Updated ferry.yml template with boolean gates and per-type matrices"
affects: [28-e2e-validation]

# Tech tracking
tech-stack:
  added: []
  patterns: [version-routed-parser, computed-field-for-serialization, boolean-flag-gating]

key-files:
  created: []
  modified:
    - utils/src/ferry_utils/models/dispatch.py
    - tests/test_utils/test_dispatch_models.py
    - action/src/ferry_action/parse_payload.py
    - tests/test_action/test_parse_payload.py
    - action/setup/action.yml
    - docs/setup.md

key-decisions:
  - "Version routing via raw JSON v field before model validation"
  - "ParseResult is a frozen dataclass (not Pydantic) to keep action layer lightweight"
  - "build_matrix() preserved unchanged for backward compat with existing tests"
  - "run-name uses resource_types (v2) || resource_type (v1) || 'dispatched' fallback chain"

patterns-established:
  - "Boolean flag gating for GHA job conditionals (has_lambdas == 'true')"
  - "Per-type matrices instead of shared matrix for multi-type fan-out"
  - "Concurrency groups per resource name instead of per type"

requirements-completed: [ACT-01, ACT-02, ACT-03, ACT-04, TMPL-01, TMPL-02, TMPL-03]

# Metrics
duration: 5min
completed: 2026-03-11
---

# Phase 27 Plan 01: Action Parsing and Workflow Template Summary

**Implemented v1/v2 payload parsing with per-type boolean flags and matrices, updated setup action outputs and ferry.yml workflow template for batched dispatch**

## Performance

- **Duration:** 5 min
- **Completed:** 2026-03-11
- **Tasks:** 4
- **Files modified:** 6

## Accomplishments

- Added `resource_types` computed field to `BatchedDispatchPayload` -- automatically included in `model_dump_json()` for GHA `run-name` consumption
- Implemented `parse_payload()` function routing v1 and v2 payloads to separate parsers
- Created `ParseResult` frozen dataclass with 7 fields: lambda_matrix, sf_matrix, ag_matrix, has_lambdas, has_step_functions, has_api_gateways, resource_types
- Updated `main()` to write 7 outputs to GITHUB_OUTPUT (replacing old matrix + resource_type)
- Updated `action/setup/action.yml` with 7 per-type outputs
- Replaced ferry.yml template in docs with boolean-flag gating, per-type matrices, and resource_types run-name
- Updated dispatch documentation to describe batched (single event) model
- 16 new tests for v2 parsing + v1 backward compat + main() output validation
- 5 new tests for computed resource_types field on BatchedDispatchPayload
- All 320 tests pass, ruff clean

## Task Commits

Each task was committed atomically:

1. **Task 1: Add resource_types computed field** - `b7f509b` (feat)
2. **Task 2: Write failing tests for v2 parsing (RED)** - `803bf16` (test)
3. **Task 3: Implement parse_payload v1/v2 (GREEN)** - `bfdaffd` (feat)
4. **Task 4: Update action.yml and docs template** - `b922e54` (feat)

## Files Created/Modified

- `utils/src/ferry_utils/models/dispatch.py` - computed_field resource_types on BatchedDispatchPayload
- `tests/test_utils/test_dispatch_models.py` - 5 new tests for computed field (25 total)
- `action/src/ferry_action/parse_payload.py` - ParseResult, parse_payload(), _parse_v1(), _parse_v2(), updated main()
- `tests/test_action/test_parse_payload.py` - 16 new/updated tests (30 total)
- `action/setup/action.yml` - 7 per-type outputs replacing matrix + resource_type
- `docs/setup.md` - Updated ferry.yml template, dispatch docs, migration section

## Decisions Made

- Version routing via raw JSON `v` field before model validation
- ParseResult is a frozen dataclass (not Pydantic) to keep action layer lightweight
- build_matrix() preserved unchanged for backward compat with existing tests
- run-name uses `resource_types` (v2) || `resource_type` (v1) || `'dispatched'` fallback chain

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness

- parse_payload() handles both v1 (per-type) and v2 (batched) dispatch payloads
- Setup action outputs per-type boolean flags and matrices for workflow routing
- ferry.yml template uses boolean gates and per-type matrices
- Phase 28 (E2E validation) can verify the full batched dispatch chain end-to-end

## Self-Check: PASSED

All 6 modified files exist. All 4 task commits verified (b7f509b, 803bf16, bfdaffd, b922e54).

---
*Phase: 27-action-parsing-and-workflow-template*
*Completed: 2026-03-11*
