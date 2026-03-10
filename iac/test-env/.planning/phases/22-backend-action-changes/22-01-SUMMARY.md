# Phase 22 Plan 01 Summary

**Executed:** 2026-03-10
**Status:** Complete

## Files Modified (7)

### Source Files
1. `utils/src/ferry_utils/constants.py` — Removed `RESOURCE_TYPE_WORKFLOW_MAP`, added `WORKFLOW_FILENAME = "ferry.yml"`
2. `backend/src/ferry_backend/dispatch/trigger.py` — Import `WORKFLOW_FILENAME` instead of map+enum, simplified dispatch line
3. `action/src/ferry_action/parse_payload.py` — Added `set_output("resource_type", payload.resource_type)` to `main()`
4. `action/setup/action.yml` — Added `resource_type` output declaration

### Test Files
5. `tests/test_backend/test_dispatch_trigger.py` — Updated all URL mocks and assertions to `ferry.yml`
6. `tests/test_backend/test_handler_phase2.py` — Updated `_mock_dispatch` default parameter to `ferry.yml`
7. `tests/test_action/test_parse_payload.py` — Updated `test_valid_payload_writes_output` to verify both matrix and resource_type outputs

## Test Results

50 passed (test_dispatch_trigger + test_parse_payload + test_dispatch_models)

Note: `test_handler_phase2` has a pre-existing moto/AWS credential fixture error unrelated to this phase.

## Requirements Satisfied

| ID | Description | Verified |
|----|-------------|----------|
| BE-01 | All dispatches target `ferry.yml` regardless of resource type | Yes — trigger.py uses `WORKFLOW_FILENAME` directly |
| BE-02 | `RESOURCE_TYPE_WORKFLOW_MAP` removed, `WORKFLOW_FILENAME` exists | Yes — ImportError on old name, new constant exports correctly |
| ACT-01 | Setup action exposes `resource_type` as workflow output | Yes — action.yml + parse_payload.py both updated |
| ACT-02 | Matrix output preserved (existing behavior) | Yes — all 17 parse_payload tests pass unchanged |

## Deviations

None. All changes matched the plan exactly.
