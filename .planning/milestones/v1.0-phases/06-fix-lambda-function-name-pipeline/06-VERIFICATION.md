---
phase: 06-fix-lambda-function-name-pipeline
verified: 2026-02-27T15:00:00Z
status: passed
score: 6/6 must-haves verified
---

# Phase 6: Fix Lambda function_name Pipeline Verification Report

**Phase Goal:** Lambda `function_name` flows correctly from `ferry.yaml` through the dispatch pipeline to the deploy action, closing the DEPLOY-01 integration break
**Verified:** 2026-02-27T15:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `LambdaResource` model includes `function_name` as a required `str` field | VERIFIED | `dispatch.py` line 24: `function_name: str` with no default — Pydantic validation rejects construction without it |
| 2 | `_build_resource` in `trigger.py` passes `function_name` when constructing `LambdaResource` | VERIFIED | `trigger.py` lines 72-77: `LambdaResource(..., function_name=lam.function_name)` |
| 3 | GHA matrix output includes `function_name` for Lambda resources | VERIFIED | `parse_payload.py` line 37: `"function_name": r.function_name` in `_build_lambda_matrix` dict |
| 4 | `deploy.py` improved `ResourceNotFoundException` error message includes `function_name` and ferry.yaml guidance | VERIFIED | `deploy.py` lines 225-228: `f"Lambda function '{function_name}' not found. Check ferry.yaml function_name or verify the Lambda exists in the target account."` |
| 5 | All existing tests pass after `function_name` is added as a required field | VERIFIED | Full suite: 246 passed in 3.29s, zero failures |
| 6 | At least one test verifies `function_name` differs from `name` (explicit override case) | VERIFIED | 4 test files each have override case: `test_dispatch_models.py::test_lambda_resource_function_name_differs_from_name`, `test_dispatch_trigger.py::test_build_resource_lambda_explicit_function_name` + `test_trigger_dispatches_includes_explicit_function_name`, `test_parse_payload.py::test_lambda_matrix_explicit_function_name_override` |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `utils/src/ferry_utils/models/dispatch.py` | `LambdaResource` with `function_name: str` field | VERIFIED | Line 24: required field present, no Optional, no default |
| `backend/src/ferry_backend/dispatch/trigger.py` | `_build_resource` passes `function_name` for lambda type | VERIFIED | Lines 72-77: `function_name=lam.function_name` in `LambdaResource` constructor |
| `action/src/ferry_action/parse_payload.py` | `function_name` in Lambda matrix output | VERIFIED | Line 37: `"function_name": r.function_name` in `_build_lambda_matrix` |
| `action/src/ferry_action/deploy.py` | Fail-fast for missing `INPUT_FUNCTION_NAME`, improved error message | VERIFIED | Lines 165-171: `.get` with explicit empty-check; lines 225-228: ferry.yaml guidance in error |
| `tests/test_utils/test_dispatch_models.py` | All `LambdaResource` constructions include `function_name`; override test exists | VERIFIED | `test_lambda_resource_function_name_differs_from_name` tests `name="order"` vs `function_name="order-processor-prod"` |
| `tests/test_backend/test_dispatch_trigger.py` | Override test; payload JSON includes `function_name` | VERIFIED | `test_trigger_dispatches_includes_explicit_function_name` asserts `resource["function_name"] == "order-processor-prod"` |
| `tests/test_action/test_parse_payload.py` | All lambda dicts include `function_name`; matrix override test | VERIFIED | `_make_payload` helper includes `function_name`; `test_lambda_matrix_explicit_function_name_override` asserts distinct values |
| `tests/test_action/test_deploy.py` | Missing/empty `INPUT_FUNCTION_NAME` tests; `ResourceNotFoundException` message test | VERIFIED | `test_missing_function_name_exits`, `test_empty_function_name_exits`, `test_resource_not_found_error_message` all present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/src/ferry_backend/dispatch/trigger.py` | `utils/src/ferry_utils/models/dispatch.py` | `LambdaResource` constructor with `function_name` kwarg | WIRED | `trigger.py` line 76: `function_name=lam.function_name` |
| `action/src/ferry_action/parse_payload.py` | `utils/src/ferry_utils/models/dispatch.py` | `r.function_name` access on `LambdaResource` instance | WIRED | `parse_payload.py` line 37: `"function_name": r.function_name` |
| `action/src/ferry_action/deploy.py` | `action/deploy/action.yml` | `INPUT_FUNCTION_NAME` env var from GHA matrix | WIRED | `action.yml` line 57: `INPUT_FUNCTION_NAME: ${{ inputs.function-name }}`; `deploy.py` line 165: `os.environ.get("INPUT_FUNCTION_NAME", "")` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DEPLOY-01 | `06-01-PLAN.md` | Ferry Action deploys Lambda functions (update-function-code, wait for LastUpdateStatus: Successful, publish version, update alias) — specifically the `function_name` data-plumbing break that prevented targeting the correct function | SATISFIED | `function_name` flows from `LambdaConfig` (backend) through `LambdaResource` dispatch model, `parse_payload` GHA matrix, and into `deploy.py` which targets the correct AWS Lambda via `INPUT_FUNCTION_NAME` |

**Orphaned requirements check:** REQUIREMENTS.md Traceability table maps DEPLOY-01 to Phase 6 only — no additional Phase 6 requirements exist. Coverage is complete.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `action/src/ferry_action/parse_payload.py` | 101-106 | `build_matrix` docstring lists lambda fields as "name, source, ecr, trigger_sha, deployment_tag, runtime" — omits `function_name` | Info | Documentation only; the field is correctly emitted at line 37. No functional impact. |

### Human Verification Required

None. All success criteria are verifiable programmatically:

- Field presence in model: grep confirmed
- Constructor argument passing: code inspection confirmed
- Matrix dict key: code inspection confirmed
- Error message text: test `test_resource_not_found_error_message` asserts `"Check ferry.yaml function_name" in captured.out`
- Test suite: 246/246 passing

### Gaps Summary

No gaps. All 6 must-have truths verified. All 3 key links wired. DEPLOY-01 requirement satisfied. Full test suite green.

**Minor documentation note (non-blocking):** The `build_matrix` docstring at line 101 omits `function_name` from the lambda field list. This is tracked by Phase 7 (tech debt cleanup) and does not block the Phase 6 goal.

---

**Commit verification:**
- `a391898` — `feat(06-01): wire function_name through Lambda dispatch pipeline` — confirmed in `git log`, touches all 4 source files
- `c609a4a` — `test(06-01): update all tests for function_name and add override cases` — confirmed in `git log`

---

_Verified: 2026-02-27T15:00:00Z_
_Verifier: Claude (gsd-verifier)_
