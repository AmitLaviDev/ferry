---
phase: 02-app-core-logic
verified: 2026-02-24T16:30:00Z
status: passed
score: 4/4 success criteria verified
re_verification: false
---

# Phase 2: App Core Logic Verification Report

**Phase Goal:** When a developer pushes code, Ferry App reads the repo configuration, identifies which serverless resources changed, triggers the correct dispatches, and shows affected resources on the PR before merge
**Verified:** 2026-02-24T16:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from Phase Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Ferry App reads and validates ferry.yaml from user's repo at exact pushed commit SHA; invalid ferry.yaml produces clear error, not silent failure | VERIFIED | `fetch_ferry_config` calls Contents API with `ref=sha`; `ConfigError` raised on 404 and other HTTP errors; `validate_config` wraps `ValidationError` in `ConfigError`; 6 loader + 13 schema tests all pass |
| 2 | A push changing files under a Lambda's source_dir triggers dispatch; unchanged resources are not dispatched | VERIFIED | `match_resources` uses trailing-slash-normalized `startswith` prefix matching; integration test `test_handler_default_branch_push_triggers_dispatch` verifies exactly 1 dispatch for 1 matching lambda, 0 for no match |
| 3 | A push affecting multiple resource types triggers exactly one dispatch per resource type, each with versioned payload containing resource list, trigger SHA, deployment tag, and PR number | VERIFIED | `trigger_dispatches` groups by `resource_type` and fires one POST per group; `DispatchPayload` has `resource_type`, `resources`, `trigger_sha`, `deployment_tag`, `pr_number`; `test_trigger_dispatches_multiple_types` verifies 2 dispatches for lambda+step_function |
| 4 | A PR shows a GitHub Check Run listing which resources will be affected by merge, before the developer merges | VERIFIED | `create_check_run` posts "Ferry: Deployment Plan" Check Run with Terraform-plan-like markdown; `test_handler_pr_branch_push_creates_check_run` verifies check run is posted, dispatch is not; check run name and content assertions pass |

**Score: 4/4 success criteria verified**

---

## Required Artifacts

### Plan 01 Artifacts (CONF-01, CONF-02)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/src/ferry_backend/config/__init__.py` | Package init | VERIFIED | File exists, empty as expected |
| `backend/src/ferry_backend/config/loader.py` | `fetch_ferry_config`, `parse_config` | VERIFIED | Both functions present and substantive; 46 lines; Contents API call at `ref=sha`, base64 decode, ConfigError on 404/500 |
| `backend/src/ferry_backend/config/schema.py` | `FerryConfig`, `LambdaConfig`, `StepFunctionConfig`, `ApiGatewayConfig`, `validate_config` | VERIFIED | All 5 exports present; frozen models with `extra="forbid"`; `model_validator` for `function_name` default; `validate_config` wraps `ValidationError` in `ConfigError` |
| `tests/test_backend/test_config_loader.py` | 6 loader tests | VERIFIED | 6 tests covering 200/404/500 and valid/invalid/empty YAML; all pass |
| `tests/test_backend/test_config_schema.py` | 13 schema tests | VERIFIED | 13 tests covering all models and `validate_config`; all pass |

### Plan 02 Artifacts (DETECT-01)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/src/ferry_backend/detect/__init__.py` | Package init | VERIFIED | File exists, empty |
| `backend/src/ferry_backend/detect/changes.py` | `get_changed_files`, `match_resources`, `detect_config_changes`, `AffectedResource`, `merge_affected` | VERIFIED | All 5 exports present; 232 lines; frozen dataclass for `AffectedResource`; trailing-slash normalization; model_dump comparison for config diffing |
| `tests/test_backend/test_changes.py` | 17 change detection tests | VERIFIED | 17 tests (11 source-matching + 6 config-diff); all pass |

### Plan 03 Artifacts (DETECT-02, ORCH-01, ORCH-02)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/src/ferry_backend/dispatch/__init__.py` | Package init | VERIFIED | File exists, empty |
| `backend/src/ferry_backend/dispatch/trigger.py` | `trigger_dispatches`, `build_deployment_tag` | VERIFIED | Both present; grouping by `resource_type`; `DispatchPayload.model_dump_json()` serialized as `inputs.payload`; 65535-byte size check; 171 lines |
| `backend/src/ferry_backend/checks/__init__.py` | Package init | VERIFIED | File exists, empty |
| `backend/src/ferry_backend/checks/runs.py` | `create_check_run`, `format_deployment_plan`, `find_open_prs` | VERIFIED | All 3 present; Terraform-plan-like formatting with `~`/`+` indicators; Check Run name "Ferry: Deployment Plan"; `find_open_prs` filters by `state=="open"` |
| `backend/src/ferry_backend/webhook/handler.py` | Full Phase 2 pipeline | VERIFIED | Handler wires all modules: auth -> config -> detect -> dispatch/check_run; merge-base comparison for PR branches; 233 lines, no stub code |
| `tests/test_backend/test_dispatch_trigger.py` | 8 dispatch tests | VERIFIED | 8 tests covering tag formats, single/multi-type dispatch, payload format, workflow file naming, field mapping; all pass |
| `tests/test_backend/test_check_runs.py` | 10 check run tests | VERIFIED | 10 tests covering modified/new formatting, multi-type grouping, error/empty/affected check runs, open PR filtering; all pass |
| `tests/test_backend/test_handler_phase2.py` | 7 integration tests | VERIFIED | 7 integration tests covering full handler pipeline end-to-end with mocked GitHub API and DynamoDB; all pass |

---

## Key Link Verification

### Plan 01 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `config/loader.py` | `GitHubClient.get` | Contents API call with `ref=sha` | WIRED | Line 35: `client.get(f"/repos/{repo}/contents/ferry.yaml", params={"ref": sha})` |
| `config/loader.py` | `ferry_utils.errors.ConfigError` | Raises on 404 or malformed YAML | WIRED | Lines 39, 43, 65: three `raise ConfigError(...)` calls |
| `config/schema.py` | `pydantic.BaseModel` | `model_validate` for typed config | WIRED | Line 81: `return FerryConfig.model_validate(raw)` |

### Plan 02 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `detect/changes.py` | `GitHubClient.get` | Compare API call | WIRED | Line 67: `client.get(f"/repos/{repo}/compare/{base}...{head}")` |
| `detect/changes.py` | `config/schema.py` (`FerryConfig`) | Type annotation in `match_resources` and `detect_config_changes` | WIRED | Lines 15, 85, 160-161: `FerryConfig` used as type parameter in both functions |
| `detect/changes.py` | `config/loader.py` (`fetch_ferry_config`) | Caller responsibility (handler.py calls both) | WIRED (via handler) | Plan correctly states "The function receives pre-parsed FerryConfig objects. The caller (handler.py) is responsible for fetching." Handler.py lines 141, 174 call `fetch_ferry_config`; handler.py line 169 calls `match_resources` with validated config |

### Plan 03 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `dispatch/trigger.py` | `GitHubClient.post` | `workflow_dispatch` API call | WIRED | Line 155-158: `client.post(f"/repos/{repo}/actions/workflows/{workflow_file}/dispatches", ...)` |
| `dispatch/trigger.py` | `DispatchPayload.model_dump_json` | Builds and serializes payload | WIRED | Lines 130-143: `DispatchPayload(...)` then `payload.model_dump_json()` |
| `checks/runs.py` | `GitHubClient.post` | Checks API call | WIRED | Line 127: `client.post(f"/repos/{repo}/check-runs", json=body)` |
| `webhook/handler.py` | `config/loader.py` | `fetch_ferry_config` call | WIRED | Lines 19, 141, 174: imported and called twice |
| `webhook/handler.py` | `detect/changes.py` | `get_changed_files` + `match_resources` call | WIRED | Lines 21-26: imported; lines 166-169: called |
| `webhook/handler.py` | `dispatch/trigger.py` | `trigger_dispatches` call (default branch only) | WIRED | Lines 27-30: imported; lines 195-200: called under `if is_default_branch and affected` |
| `webhook/handler.py` | `checks/runs.py` | `create_check_run` call (PR branches) | WIRED | Line 18: imported; lines 149, 209: called — once in config error path, once in PR branch path |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CONF-01 | 02-01 | Ferry App reads and validates ferry.yaml from user's repo at pushed commit SHA via GitHub Contents API | SATISFIED | `fetch_ferry_config` calls `/repos/{repo}/contents/ferry.yaml?ref={sha}`; `validate_config` wraps `ValidationError` in `ConfigError`; 6 loader + 13 schema tests pass |
| CONF-02 | 02-01 | ferry.yaml supports lambdas, step_functions, and api_gateways as top-level resource types with type-specific fields | SATISFIED | `FerryConfig` model has `lambdas`, `step_functions`, `api_gateways` sections; `LambdaConfig` requires name/source_dir/ecr_repo; step_function and api_gateway require name/source_dir only |
| DETECT-01 | 02-02 | Ferry App compares commit diff (via GitHub Compare API) against ferry.yaml path mappings to identify changed resources | SATISFIED | `get_changed_files` calls Compare API; `match_resources` does trailing-slash-normalized prefix matching; 17 change detection tests pass |
| DETECT-02 | 02-03 | Ferry App posts a GitHub Check Run on PRs showing which resources will be affected before merge | SATISFIED | `create_check_run` posts "Ferry: Deployment Plan" Check Run; `format_deployment_plan` produces Terraform-plan-like markdown; always posted for PR pushes even with no changes; 7 handler integration tests verify end-to-end |
| ORCH-01 | 02-03 | Ferry App triggers one workflow_dispatch per affected resource type with a versioned payload contract | SATISFIED | `trigger_dispatches` groups by `resource_type` and fires one POST per group; `test_trigger_dispatches_multiple_types` verifies exactly 2 dispatches for lambda+step_function |
| ORCH-02 | 02-03 | Dispatch payload includes resource type, resource list, trigger SHA, deployment tag, and PR number | SATISFIED | `DispatchPayload` model has `resource_type`, `resources`, `trigger_sha`, `deployment_tag`, `pr_number`; `v` field for schema versioning; `test_trigger_dispatches_payload_format` verifies structure |

All 6 Phase 2 requirements satisfied. No orphaned requirements found.

---

## Test Results

| Test Suite | Tests | Result |
|------------|-------|--------|
| `test_config_loader.py` | 6 | 6/6 PASS |
| `test_config_schema.py` | 13 | 13/13 PASS |
| `test_changes.py` | 17 | 17/17 PASS |
| `test_dispatch_trigger.py` | 8 | 8/8 PASS |
| `test_check_runs.py` | 10 | 10/10 PASS |
| `test_handler_phase2.py` | 7 | 7/7 PASS |
| **Full backend suite** | **100** | **100/100 PASS** |

No regressions in Phase 1 tests (Phase 1 handler tests updated for Phase 2 compatibility — documented deviation in 02-03-SUMMARY.md).

---

## Anti-Patterns Found

None. All files scanned:
- No TODO/FIXME/HACK/PLACEHOLDER comments in implementation files
- `return []` instances on lines 65 (detect/changes.py) and 115 (dispatch/trigger.py) are **legitimate**, not stubs: initial push returns empty file list by design; no-affected-resources returns empty dispatch results by design
- Zero ruff lint errors across all Phase 2 files

---

## Lint

```
uv run ruff check backend/src/ferry_backend/config/ backend/src/ferry_backend/detect/ \
  backend/src/ferry_backend/dispatch/ backend/src/ferry_backend/checks/ \
  backend/src/ferry_backend/webhook/handler.py tests/test_backend/

All checks passed!
```

---

## Human Verification Required

The following behaviors are correct in code and tests but can only be fully confirmed by a live GitHub App installation:

### 1. Check Run Visual Appearance

**Test:** Install Ferry App on a test repo, push to a PR branch with a changed source file. Open the PR on GitHub.
**Expected:** A "Ferry: Deployment Plan" Check Run appears in the Checks tab. It lists affected resources with `~` for modified and `+` for new, grouped by type, with a footer "Ferry will deploy these resources when this PR is merged."
**Why human:** Visual rendering of GitHub Check Run output markdown cannot be verified programmatically.

### 2. workflow_dispatch Actually Triggers

**Test:** Merge a PR to default branch with a real Ferry App installation and a `ferry-lambdas.yml` workflow file in the target repo.
**Expected:** The `ferry-lambdas.yml` workflow is triggered exactly once, with the correct JSON payload in the `inputs.payload` field.
**Why human:** Requires a live GitHub App installation and real workflow file; cannot be fully mocked.

### 3. Merge-Base Comparison Accuracy

**Test:** Open a PR from a feature branch, push two commits (each touching different lambda files). Observe the Check Run after each push.
**Expected:** Each Check Run shows ALL files changed since the branch diverged from `main` (not just incremental changes since the last push).
**Why human:** Requires observing two consecutive Check Runs in a live PR to confirm cumulative diff behavior.

---

## Commit Verification

All commits referenced in summaries confirmed in git log:

| Commit | Description |
|--------|-------------|
| `5c8dd39` | test(02-01): RED phase — config loader tests |
| `c868491` | feat(02-01): GREEN phase — config loader implementation |
| `41f7a0e` | test(02-01): RED phase — config schema tests |
| `ccee018` | feat(02-01): GREEN phase — config schema implementation |
| `fe90781` | feat(02-02): Compare API fetch, source_dir matching, merge dedup |
| `c53a4c7` | feat(02-02): ferry.yaml config diff detection |
| `d7e2e0c` | feat(02-03): dispatch triggering and Check Run creation modules |
| `29f3c31` | feat(02-03): wire complete Phase 2 pipeline into webhook handler |

---

_Verified: 2026-02-24T16:30:00Z_
_Verifier: Claude (gsd-verifier)_
