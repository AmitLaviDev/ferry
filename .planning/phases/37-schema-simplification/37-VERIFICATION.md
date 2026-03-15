---
phase: 37-schema-simplification
verified: 2026-03-15T07:30:00Z
status: passed
score: 13/13 must-haves verified
re_verification: false
---

# Phase 37: Schema Simplification Verification Report

**Phase Goal:** `name` in ferry.yaml IS the AWS resource name -- no separate `function_name` / `state_machine_name` fields
**Verified:** 2026-03-15T07:30:00Z
**Status:** PASSED
**Re-verification:** No -- initial verification

---

## Goal Achievement

### Observable Truths

Truths are drawn from the ROADMAP.md Success Criteria plus the must_haves in the two PLAN files.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `LambdaConfig.name` is the sole name field (no `function_name` field) | VERIFIED | `schema.py` line 25: only `name: str`; `function_name` removed; mode="before" backward-compat validator present |
| 2 | `StepFunctionConfig.name` is the sole name field (no `state_machine_name` field) | VERIFIED | `schema.py` line 50: only `name: str`; `state_machine_name` removed; mode="before" backward-compat validator present |
| 3 | `ApiGatewayConfig` is unchanged (`rest_api_id`, `stage_name` remain) | VERIFIED | `schema.py` lines 70-80: `rest_api_id` and `stage_name` intact, no changes |
| 4 | Old ferry.yaml with `function_name` or `state_machine_name` still parses (backward compat) | VERIFIED | `test_lambda_config_function_name_alias`, `test_lambda_config_function_name_without_name`, `test_step_function_config_state_machine_name_alias`, `test_step_function_config_state_machine_name_without_name` all pass |
| 5 | `LambdaResource` dispatch model has no `function_name` field | VERIFIED | `dispatch.py` lines 15-28: fields are `resource_type`, `name`, `source`, `ecr`, `runtime` only |
| 6 | `StepFunctionResource` dispatch model has no `state_machine_name` field | VERIFIED | `dispatch.py` lines 30-42: fields are `resource_type`, `name`, `source`, `definition_file` only |
| 7 | `trigger.py` builds resources using only `.name` | VERIFIED | `trigger.py` lines 79-84, 87-93: `LambdaResource(name=name, ...)` and `StepFunctionResource(name=name, ...)` with no `function_name`/`state_machine_name` |
| 8 | `parse_payload` matrix entries use `name` only (no `function_name`/`state_machine_name` keys) | VERIFIED | `parse_payload.py` v1 builders (lines 48-76) and `_parse_v2()` (lines 175-207): only `"name": r.name`; assertions in `test_parse_payload.py` confirm `"function_name"` and `"state_machine_name"` not in matrix entries |
| 9 | `deploy.py` reads `INPUT_RESOURCE_NAME` as the Lambda function name (no `INPUT_FUNCTION_NAME`) | VERIFIED | `deploy.py` line 161-162: `resource_name = os.environ["INPUT_RESOURCE_NAME"]`; `function_name = resource_name`; no `INPUT_FUNCTION_NAME` anywhere |
| 10 | `deploy_stepfunctions.py` reads `INPUT_RESOURCE_NAME` as the state machine name (no `INPUT_STATE_MACHINE_NAME`) | VERIFIED | `deploy_stepfunctions.py` line 111-112: `resource_name = os.environ["INPUT_RESOURCE_NAME"]`; `state_machine_name = resource_name`; no `INPUT_STATE_MACHINE_NAME` anywhere |
| 11 | Composite `action/deploy/action.yml` has no `function-name` input or `INPUT_FUNCTION_NAME` env var | VERIFIED | `action.yml` inputs: `resource-name`, `image-uri`, `image-digest`, `deployment-tag`, `trigger-sha`, `aws-role-arn`, `aws-region`, `github-token`; env block has `INPUT_RESOURCE_NAME` only |
| 12 | Composite `action/deploy-stepfunctions/action.yml` has no `state-machine-name` input or `INPUT_STATE_MACHINE_NAME` env var | VERIFIED | `action.yml` inputs: `resource-name`, `definition-file`, `source-dir`, `trigger-sha`, `deployment-tag`, `aws-role-arn`, `aws-region`, `github-token`; env block has `INPUT_RESOURCE_NAME` only |
| 13 | `docs/setup.md` workflow template and ferry.yaml example use `matrix.name` (no `matrix.function_name`/`matrix.state_machine_name`) | VERIFIED | All deploy jobs use `matrix.name` (lines 125, 131, 142, 153, 163, 169, 179, 189, 195, 205); Migration section mentions schema simplification explicitly |

**Score:** 13/13 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/src/ferry_backend/config/schema.py` | LambdaConfig and StepFunctionConfig without function_name/state_machine_name, with backward-compat validators | VERIFIED | Both classes cleaned; `handle_deprecated_function_name` and `handle_deprecated_state_machine_name` mode="before" validators present |
| `utils/src/ferry_utils/models/dispatch.py` | LambdaResource without function_name, StepFunctionResource without state_machine_name | VERIFIED | Both models simplified to 5 and 4 fields respectively |
| `backend/src/ferry_backend/dispatch/trigger.py` | Resource builder using .name only | VERIFIED | `_build_resource()` constructs all resource types using `name=name` only |
| `action/src/ferry_action/parse_payload.py` | Matrix builders without function_name/state_machine_name keys | VERIFIED | v1 and v2 builders emit `"name": r.name` only |
| `action/src/ferry_action/deploy.py` | Lambda deploy using INPUT_RESOURCE_NAME as function name | VERIFIED | `function_name = resource_name` pattern; INPUT_FUNCTION_NAME gone |
| `action/src/ferry_action/deploy_stepfunctions.py` | SF deploy using INPUT_RESOURCE_NAME as state machine name | VERIFIED | `state_machine_name = resource_name` pattern; INPUT_STATE_MACHINE_NAME gone |
| `action/deploy/action.yml` | Composite action without function-name input | VERIFIED | function-name input absent; INPUT_RESOURCE_NAME serves the role |
| `action/deploy-stepfunctions/action.yml` | Composite action without state-machine-name input | VERIFIED | state-machine-name input absent; INPUT_RESOURCE_NAME serves the role |
| `docs/setup.md` | Updated workflow template and ferry.yaml docs | VERIFIED | ferry.yaml example shows name as AWS resource name; workflow uses matrix.name throughout |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `schema.py` | `trigger.py` | `_build_resource` reads `config.lambdas[].name` | VERIFIED | `trigger.py` line 79: `if lam.name == name` confirms lookup via `.name` |
| `dispatch.py` (LambdaResource) | `trigger.py` | `LambdaResource(name=name, ...)` -- no function_name arg | VERIFIED | `trigger.py` line 80-85: constructor passes only `name`, `source`, `ecr`, `runtime` |
| `parse_payload.py` | `docs/setup.md` | Matrix output keys match workflow template (matrix.name) | VERIFIED | Matrix entries use key `"name"` and workflow uses `${{ matrix.name }}` throughout |
| `action/deploy/action.yml` | `deploy.py` | `INPUT_RESOURCE_NAME` env var wiring | VERIFIED | action.yml line 66: `INPUT_RESOURCE_NAME: ${{ inputs.resource-name }}`; deploy.py line 161: `os.environ["INPUT_RESOURCE_NAME"]` |
| `action/deploy-stepfunctions/action.yml` | `deploy_stepfunctions.py` | `INPUT_RESOURCE_NAME` env var wiring | VERIFIED | action.yml line 65: `INPUT_RESOURCE_NAME: ${{ inputs.resource-name }}`; deploy_stepfunctions.py line 111: `os.environ["INPUT_RESOURCE_NAME"]` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SCHEMA-01 | 37-01-PLAN.md, 37-02-PLAN.md | `name` in ferry.yaml IS the AWS resource name -- no separate `function_name` / `state_machine_name` fields | SATISFIED | All 6 ROADMAP success criteria confirmed in codebase; 442 tests pass |

**Note on SCHEMA-01 traceability:** SCHEMA-01 is defined in `37-RESEARCH.md` and referenced in `ROADMAP.md` (Phase 37). It does **not** appear in `.planning/REQUIREMENTS.md` because that file covers the v2.0 PR Integration milestone (phases 29-36). SCHEMA-01 is a v2.1 milestone requirement. This is expected -- no orphaned requirements.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

Scan results:
- Zero hits for `function_name`/`state_machine_name` as model fields in source (`backend/src/`, `utils/src/`, `action/src/`)
- Remaining references in `deploy.py` and `deploy_stepfunctions.py` are **local variables** (`function_name = resource_name`, `state_machine_name = resource_name`) -- these are correct: the local variable holds the actual AWS resource name derived from `INPUT_RESOURCE_NAME`
- Remaining references in `schema.py` are inside the backward-compat validators (handling incoming old field names) -- correct
- Zero hits for `INPUT_FUNCTION_NAME` or `INPUT_STATE_MACHINE_NAME` in composite actions or tests
- Zero hits for `function-name` or `state-machine-name` inputs in composite action YAML files

---

### Human Verification Required

#### 1. ferry-test-app E2E validation

**Test:** Push a change to `AmitLaviDev/ferry-test-app` on a branch with a ferry.yaml using `name` as the AWS resource name (no `function_name`/`state_machine_name`). Open a PR and verify `/ferry plan` shows the correct Lambda/SF name.
**Expected:** Ferry plan comment lists the resource by its `name` value (e.g., "ferry-test-hello-world") -- the name that IS the AWS resource name.
**Why human:** The SUMMARY documents this was verified by the user on PR #5 (branch schema-simplification), but programmatic verification of a live GitHub Actions run is not possible from this environment.

*Note: Per 37-02-SUMMARY.md, user already confirmed E2E validation: "/ferry plan on PR #5 shows 'ferry-test-hello-world' as Lambda name". This item is documented for completeness -- the phase author considers it complete.*

---

### Gaps Summary

No gaps. All 13 observable truths are verified by code inspection and test execution.

**Test suite:** 442 tests pass (all of `tests/` with zero failures).

**Commit verification:** All four task commits are present and accounted for:
- `f691915` -- schema and dispatch model simplification
- `bed2d1d` -- test updates and parse_payload fix
- `0af2c4f` -- deploy script and parse_payload cleanup
- `50a395c` -- composite actions, docs, and action test updates

The phase goal -- `name` IS the AWS resource name across the entire pipeline -- is fully achieved. The change propagates consistently from ferry.yaml schema parsing through dispatch payload construction, GHA matrix output, composite action inputs, and deploy script execution.

---

*Verified: 2026-03-15T07:30:00Z*
*Verifier: Claude (gsd-verifier)*
