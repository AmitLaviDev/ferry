---
phase: 04-extended-resource-types
verified: 2026-02-26T19:30:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
---

# Phase 4: Extended Resource Types Verification Report

**Phase Goal:** Ferry Action deploys Step Functions and API Gateways using the same dispatch and auth foundation as Lambda
**Verified:** 2026-02-26T19:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A dispatch for Step Functions updates the state machine definition with correct variable substitution for account ID and region, without corrupting JSONPath expressions or other non-variable content | VERIFIED | `envsubst.py` uses `_ENVSUBST_PATTERN = re.compile(r"\$\{(ACCOUNT_ID\|AWS_REGION)\}")` — strict regex only matches the two known variables. Dollar-dot JSONPath expressions (`$.path`) are structurally immune. `deploy_stepfunctions.py` calls `envsubst()` then `update_state_machine(publish=True)`. Test `test_envsubst_applied` in `test_deploy_stepfunctions.py` confirms substituted values appear in `describe_state_machine` output. |
| 2 | A dispatch for API Gateways uploads the OpenAPI spec via put-rest-api and creates a deployment to push changes to the target stage | VERIFIED | `deploy_apigw.py` calls `put_rest_api(mode="overwrite", body=bytes)` then `create_deployment(stageName=...)`. Tests `test_uploads_spec_via_put_rest_api`, `test_creates_deployment`, and `test_deploys_json_spec`/`test_deploys_yaml_spec` in `test_deploy_apigw.py` confirm the full pipeline. |

**Score:** 2/2 success criteria verified

### Must-Have Truths (from Plan frontmatter — all 3 plans)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | envsubst replaces ${ACCOUNT_ID} and ${AWS_REGION} without corrupting JSONPath expressions or other dollar-prefixed content | VERIFIED | `_ENVSUBST_PATTERN` only matches `${ACCOUNT_ID}` and `${AWS_REGION}` by name. 18 passing unit tests in `test_envsubst.py`. |
| 2 | StepFunctionConfig requires state_machine_name and definition_file fields | VERIFIED | Both fields present in `schema.py` as required (no default). Tests `test_step_function_config_missing_state_machine_name` and `test_step_function_config_missing_definition_file` confirm validation failure when absent. |
| 3 | ApiGatewayConfig requires rest_api_id, stage_name, and spec_file fields | VERIFIED | All three fields in `schema.py` as required. Three separate missing-field tests confirm validation failure. |
| 4 | StepFunctionResource and ApiGatewayResource dispatch models carry type-specific deploy fields from config | VERIFIED | `dispatch.py` has `state_machine_name: str` and `definition_file: str` on `StepFunctionResource`; `rest_api_id: str`, `stage_name: str`, `spec_file: str` on `ApiGatewayResource`. |
| 5 | parse_payload builds correct matrix entries for step_function and api_gateway resource types | VERIFIED | `_MATRIX_BUILDERS` dict dispatches to `_build_step_function_matrix` and `_build_api_gateway_matrix`. Tests `test_step_function_matrix` and `test_api_gateway_matrix` confirm correct fields and absence of Lambda-specific fields (ecr, runtime). |
| 6 | Step Functions deploy reads definition file from source_dir, performs envsubst, and calls update_state_machine with publish=True | VERIFIED | `deploy_stepfunctions.py` lines 140-149 read definition, apply envsubst, compute hash, check skip, then call `update_state_machine(..., publish=True, ...)` at line 85. |
| 7 | API Gateway deploy reads OpenAPI spec (JSON or YAML), performs envsubst, strips problematic fields, calls put_rest_api + create_deployment | VERIFIED | `deploy_apigw.py` handles both `{.yaml,.yml}` (yaml.safe_load) and JSON (json.loads) at lines 197-200. Strips via `_STRIP_FIELDS = frozenset({"host", "schemes", "basePath", "servers"})`. Calls `put_rest_api` + `create_deployment`. |

**Score:** 7/7 must-have truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `action/src/ferry_action/envsubst.py` | Shared envsubst + content hash helpers | VERIFIED | 74 lines; exports `envsubst`, `compute_content_hash`, `get_content_hash_tag` |
| `backend/src/ferry_backend/config/schema.py` | Updated StepFunctionConfig and ApiGatewayConfig | VERIFIED | Contains `state_machine_name`, `definition_file`, `rest_api_id`, `stage_name`, `spec_file` |
| `utils/src/ferry_utils/models/dispatch.py` | Updated dispatch resource models | VERIFIED | `StepFunctionResource` has `state_machine_name` + `definition_file`; `ApiGatewayResource` has `rest_api_id` + `stage_name` + `spec_file` |
| `action/src/ferry_action/parse_payload.py` | Extended matrix builder for all resource types | VERIFIED | `_MATRIX_BUILDERS` dispatch dict covers `lambda`, `step_function`, `api_gateway` |
| `tests/test_action/test_envsubst.py` | envsubst unit tests (min 40 lines) | VERIFIED | 131 lines, 18 tests |
| `action/src/ferry_action/deploy_stepfunctions.py` | Step Functions deploy module (min 80 lines) | VERIFIED | 211 lines; exports `deploy_step_function`, `should_skip_deploy`, `main` |
| `action/deploy-stepfunctions/action.yml` | Composite action for Step Functions | VERIFIED | Composite action; `python -m ferry_action.deploy_stepfunctions` in final step |
| `tests/test_action/test_deploy_stepfunctions.py` | Step Functions deploy tests (min 80 lines) | VERIFIED | 438 lines, 12 tests with moto |
| `action/src/ferry_action/deploy_apigw.py` | API Gateway deploy module (min 100 lines) | VERIFIED | 268 lines; exports `deploy_api_gateway`, `should_skip_deploy`, `strip_openapi_fields`, `main` |
| `action/deploy-apigw/action.yml` | Composite action for API Gateway | VERIFIED | Composite action; `python -m ferry_action.deploy_apigw` in final step |
| `tests/test_action/test_deploy_apigw.py` | API Gateway deploy tests (min 80 lines) | VERIFIED | 596 lines, 21 tests |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/src/ferry_backend/config/schema.py` | `backend/src/ferry_backend/dispatch/trigger.py` | `_build_resource` maps `sf.state_machine_name`, `sf.definition_file` | WIRED | Lines 79-80 pass `state_machine_name=sf.state_machine_name, definition_file=sf.definition_file`; lines 88-90 pass `rest_api_id`, `stage_name`, `spec_file` |
| `utils/src/ferry_utils/models/dispatch.py` | `action/src/ferry_action/parse_payload.py` | `parse_payload` reads `StepFunctionResource` and `ApiGatewayResource` into matrix | WIRED | Both models imported at lines 16-20; used via `isinstance()` guards in `_build_step_function_matrix` and `_build_api_gateway_matrix` |
| `action/src/ferry_action/deploy_stepfunctions.py` | `action/src/ferry_action/envsubst.py` | imports `envsubst`, `compute_content_hash`, `get_content_hash_tag` | WIRED | Lines 23-27; all three functions called in `main()` |
| `action/src/ferry_action/deploy_stepfunctions.py` | `action/src/ferry_action/gha.py` | imports GHA helpers for outputs, groups, summaries, errors | WIRED | Line 22; `gha.begin_group`, `gha.set_output`, `gha.write_summary`, `gha.error`, `gha.end_group` all called |
| `action/deploy-stepfunctions/action.yml` | `action/src/ferry_action/deploy_stepfunctions.py` | composite action runs `python -m ferry_action.deploy_stepfunctions` | WIRED | Line 65 of action.yml |
| `action/src/ferry_action/deploy_apigw.py` | `action/src/ferry_action/envsubst.py` | imports `envsubst`, `compute_content_hash`, `get_content_hash_tag` | WIRED | Line 27; all three functions called in `main()` |
| `action/src/ferry_action/deploy_apigw.py` | `action/src/ferry_action/gha.py` | imports GHA helpers for outputs, groups, summaries, errors | WIRED | Line 26; `gha.begin_group`, `gha.set_output`, `gha.write_summary`, `gha.error`, `gha.end_group` all called |
| `action/deploy-apigw/action.yml` | `action/src/ferry_action/deploy_apigw.py` | composite action runs `python -m ferry_action.deploy_apigw` | WIRED | Line 69 of action.yml |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DEPLOY-02 | 04-01-PLAN, 04-02-PLAN | Ferry Action deploys Step Functions (update state machine definition with variable substitution for account ID and region) | SATISFIED | `deploy_stepfunctions.py` implements full pipeline: envsubst -> content-hash skip -> `update_state_machine(publish=True)` -> tag update. 12 tests pass with moto. Both plans claim this requirement; covered by implementation in 04-02. |
| DEPLOY-03 | 04-01-PLAN, 04-03-PLAN | Ferry Action deploys API Gateways (put-rest-api with OpenAPI spec, create-deployment to push to stage) | SATISFIED | `deploy_apigw.py` implements: read spec (JSON/YAML) -> envsubst -> strip fields -> canonical JSON hash -> `put_rest_api(mode=overwrite)` -> `create_deployment` -> tag update. 21 tests pass. |

**Traceability cross-check:** REQUIREMENTS.md maps DEPLOY-02 and DEPLOY-03 to Phase 4, both marked Complete. No orphaned requirements — no other Phase 4 requirements exist in REQUIREMENTS.md.

### Anti-Patterns Found

No anti-patterns detected.

| File | Pattern Checked | Result |
|------|-----------------|--------|
| `deploy_stepfunctions.py` | TODO/FIXME, placeholder returns, stub implementations | Clean |
| `deploy_apigw.py` | TODO/FIXME, placeholder returns, stub implementations | Clean |
| `envsubst.py` | TODO/FIXME, placeholder returns | Clean |
| `action.yml` (both) | Placeholder content | Clean |

### Commit Verification

All 6 commits claimed in SUMMARYs verified in git history:

| Commit | Description |
|--------|-------------|
| `e057633` | feat(04-01): add envsubst module with content hash helpers |
| `b63a782` | feat(04-01): add SF/APIGW deploy fields to config, dispatch, trigger, and parse_payload |
| `6246220` | feat(04-02): add Step Functions deploy module with TDD tests |
| `94b32bb` | feat(04-02): add Step Functions composite action YAML |
| `f91a4f3` | feat(04-03): add API Gateway deploy module with TDD tests |
| `65a2d4b` | feat(04-03): add API Gateway composite action YAML |

### Test Suite Results

Full test suite: **237 tests, 0 failures, 0 errors**

- `tests/test_action/test_envsubst.py`: 18 tests — envsubst substitution, JSONPath safety, content hashing, dual tag format extraction
- `tests/test_action/test_deploy_stepfunctions.py`: 12 tests — skip logic, deploy operations, main() lifecycle with moto
- `tests/test_action/test_deploy_apigw.py`: 21 tests — field stripping, skip logic, deploy operations, main() with moto + manual mocks for tags
- `tests/test_backend/test_config_schema.py`: 13 tests including new SF/APIGW required field validation
- `tests/test_backend/test_dispatch_trigger.py`: 11 tests including `_build_resource` field mapping for SF/APIGW
- `tests/test_action/test_parse_payload.py`: 14 tests including SF and APIGW matrix building

### Human Verification Required

None. All phase 4 behaviors are unit-testable (moto for AWS, manual mocks for tag operations). No UI, real-time behavior, or external service dependencies that require human observation.

## Summary

Phase 4 goal fully achieved. The Ferry Action now deploys all three resource types:

1. **Step Functions** — `deploy_stepfunctions.py` reads a definition file, applies `${ACCOUNT_ID}`/`${AWS_REGION}` substitution via strict regex (safe for JSONPath), checks content-hash against the `ferry:content-hash` tag to skip unchanged definitions, calls `update_state_machine(publish=True)`, and updates the tag. The composite action at `action/deploy-stepfunctions/action.yml` wires GHA inputs to the Python module.

2. **API Gateway** — `deploy_apigw.py` reads OpenAPI specs in JSON or YAML format, applies envsubst, strips AWS-managed fields (`host`, `schemes`, `basePath`, `servers`), serializes to canonical JSON for deterministic content hashing, skips if unchanged, calls `put_rest_api(mode=overwrite, body=bytes)` + `create_deployment`, and updates the content-hash tag. The composite action at `action/deploy-apigw/action.yml` wires the inputs.

3. **Shared foundation** — Both modules use the same `envsubst.py` utilities and `gha.py` helpers as the Lambda deploy module from Phase 3. The dispatch pipeline (config schema → trigger → dispatch models → parse_payload) carries type-specific fields end-to-end so the action receives all necessary information from the GHA matrix.

Requirements DEPLOY-02 and DEPLOY-03 are both satisfied. No gaps.

---
_Verified: 2026-02-26T19:30:00Z_
_Verifier: Claude (gsd-verifier)_
