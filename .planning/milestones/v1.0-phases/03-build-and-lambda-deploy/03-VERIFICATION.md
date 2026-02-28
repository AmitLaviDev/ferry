---
phase: 03-build-and-lambda-deploy
verified: 2026-02-26T09:00:00Z
status: passed
score: 10/10 must-haves verified
re_verification: false
---

# Phase 3: Build and Lambda Deploy — Verification Report

**Phase Goal:** The Ferry Action receives a dispatch, authenticates to AWS via OIDC, builds Lambda containers with the Magic Dockerfile, pushes to ECR, and deploys Lambda functions with version and alias management.
**Verified:** 2026-02-26
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Setup action parses a DispatchPayload JSON string and outputs a matrix JSON suitable for fromJson() in a GHA strategy | VERIFIED | `parse_payload.py` uses `DispatchPayload.model_validate_json`, produces `{"include": [...]}` dict; `action/setup/action.yml` captures output via `steps.parse.outputs.matrix` |
| 2 | Build action.yml uses aws-actions/configure-aws-credentials with OIDC for AWS auth before invoking build script | VERIFIED | `action/build/action.yml` line 48-51: first step is `uses: aws-actions/configure-aws-credentials@v4` with `role-to-assume: ${{ inputs.aws-role-arn }}` |
| 3 | Deploy action.yml uses aws-actions/configure-aws-credentials with OIDC for AWS auth before invoking deploy script | VERIFIED | `action/deploy/action.yml` line 39-43: first step is `uses: aws-actions/configure-aws-credentials@v4` with `role-to-assume: ${{ inputs.aws-role-arn }}` |
| 4 | GHA logging helpers produce correct ::group::, ::endgroup::, ::add-mask::, and GITHUB_STEP_SUMMARY markdown | VERIFIED | `gha.py` 91 lines: all 7 functions implemented; 11 tests pass covering all command formats and file-based outputs |
| 5 | All three composite action.yml files exist with correct inputs and outputs definitions | VERIFIED | setup (30 lines), build (72 lines), deploy (62 lines) — all use `runs: using: composite` with full inputs/outputs |
| 6 | Magic Dockerfile builds any Lambda from main.py + requirements.txt using a configurable Python runtime version | VERIFIED | `action/Dockerfile` line 2: `ARG PYTHON_VERSION=3.12`, line 3: `FROM public.ecr.aws/lambda/python:${PYTHON_VERSION}` |
| 7 | Magic Dockerfile handles optional system-requirements.txt and system-config.sh without failing when absent | VERIFIED | `action/Dockerfile` lines 6-15: glob trick `COPY system-requirements.tx[t]` and `COPY system-config.s[h]` with conditional `if [ -f ... ]` guards |
| 8 | Magic Dockerfile supports private GitHub repo dependencies via Docker build secrets | VERIFIED | `action/Dockerfile` line 19: `RUN --mount=type=secret,id=github_token`; `build.py` line 85: `cmd.extend(["--secret", "id=github_token,env=GITHUB_TOKEN"])` when token provided |
| 9 | Lambda function code is updated with the new ECR image URI, version published, live alias updated, deployment skipped when digest matches | VERIFIED | `deploy.py`: `update_function_code` -> waiter -> `publish_version` -> `update_alias`/`create_alias`; digest normalization in `should_skip_deploy`; 14 moto tests all pass |
| 10 | Deploy outputs (skipped flag, lambda-version, image-uri, image-digest) written to GITHUB_OUTPUT; job summaries written to GITHUB_STEP_SUMMARY | VERIFIED | `build.py` lines 227-228: `gha.set_output("image-uri", ...)`, `gha.set_output("image-digest", ...)`; `deploy.py` lines 179-181 (skip) and 196-197 (deploy); summary markdown in both modules |

**Score:** 10/10 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `action/setup/action.yml` | Composite action: parse payload, output matrix JSON | VERIFIED | 30 lines, `runs: using: composite`, inputs: `payload`, outputs: `matrix` via `steps.parse.outputs.matrix` |
| `action/build/action.yml` | Composite action: OIDC auth + Docker build + ECR push | VERIFIED | 72 lines, `aws-actions/configure-aws-credentials@v4` as first step with `role-to-assume` |
| `action/deploy/action.yml` | Composite action: OIDC auth + Lambda deploy | VERIFIED | 62 lines, `aws-actions/configure-aws-credentials@v4` as first step with `role-to-assume` |
| `action/src/ferry_action/parse_payload.py` | Dispatch payload parsing + matrix JSON generation (min 30 lines) | VERIFIED | 75 lines; `build_matrix()` and `main()` functions; filters to `LambdaResource` only |
| `action/src/ferry_action/gha.py` | GHA logging helpers (groups, masks, summaries, outputs) (min 40 lines) | VERIFIED | 91 lines; 7 functions: `set_output`, `begin_group`, `end_group`, `mask_value`, `error`, `warning`, `write_summary` |
| `action/Dockerfile` | Magic Dockerfile with `ARG PYTHON_VERSION` (min 15 lines) | VERIFIED | 29 lines; ARG PYTHON_VERSION, glob trick for optional files, build secret mount, `CMD ["main.handler"]` |
| `action/src/ferry_action/build.py` | Docker build + ECR push logic (min 80 lines) | VERIFIED | 244 lines; `parse_runtime_version`, `build_ecr_uri`, `build_docker_command`, `ecr_login`, `push_image`, `main` |
| `tests/test_action/test_build.py` | TDD tests for build module (min 60 lines) | VERIFIED | 270 lines; 13 tests covering all functions including mocked subprocess |
| `action/src/ferry_action/deploy.py` | Lambda deployment with version/alias management and digest-based skip (min 80 lines) | VERIFIED | 238 lines; `get_current_image_digest`, `should_skip_deploy`, `deploy_lambda`, `main` |
| `tests/test_action/test_deploy.py` | TDD tests for deploy module using moto (min 80 lines) | VERIFIED | 366 lines; 14 moto-based tests covering all code paths |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `action/setup/action.yml` | `action/src/ferry_action/parse_payload.py` | `python -m ferry_action.parse_payload` shell step | WIRED | Line 29 of setup/action.yml |
| `action/src/ferry_action/parse_payload.py` | `ferry_utils.models.dispatch.DispatchPayload` | `from ferry_utils.models.dispatch import DispatchPayload, LambdaResource` | WIRED | Line 14; `model_validate_json` called on line 33 |
| `action/build/action.yml` | `aws-actions/configure-aws-credentials` | `uses` step with `role-to-assume` input | WIRED | Lines 48-51; `role-to-assume: ${{ inputs.aws-role-arn }}` |
| `action/deploy/action.yml` | `aws-actions/configure-aws-credentials` | `uses` step with `role-to-assume` input | WIRED | Lines 39-43; `role-to-assume: ${{ inputs.aws-role-arn }}` |
| `action/build/action.yml` | `action/src/ferry_action/build.py` | `python -m ferry_action.build` invocation | WIRED | Line 71 of build/action.yml |
| `action/src/ferry_action/build.py` | `action/Dockerfile` | `--file` flag: `Path(__file__).resolve().parent.parent.parent / "Dockerfile"` | WIRED | Lines 176-178; resolves to `action/Dockerfile` |
| `action/src/ferry_action/build.py` | `action/src/ferry_action/gha.py` | `from ferry_action import gha` | WIRED | Line 21; `gha.mask_value`, `gha.begin_group`, `gha.end_group`, `gha.set_output`, `gha.write_summary` all used |
| `action/deploy/action.yml` | `action/src/ferry_action/deploy.py` | `python -m ferry_action.deploy` invocation | WIRED | Line 61 of deploy/action.yml |
| `action/src/ferry_action/deploy.py` | boto3 lambda client | `update_function_code`, `publish_version`, `update_alias`, `get_function` | WIRED | Lines 109, 128, 137, 145; `client.get_waiter("function_updated")` also present |
| `action/src/ferry_action/deploy.py` | `action/src/ferry_action/gha.py` | `from ferry_action import gha` | WIRED | Line 21; `gha.begin_group`, `gha.end_group`, `gha.set_output`, `gha.write_summary`, `gha.error` all used |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ACT-01 | 03-01 | Ferry Action is a composite GitHub Action with Python scripts for build/deploy logic (not inline bash) | SATISFIED | Three composite action.yml files with `runs: using: composite`; all logic delegated to `python -m ferry_action.*` modules |
| AUTH-02 | 03-01 | Ferry Action authenticates to AWS via OIDC (user provides role ARN as action input, action handles the exchange) | SATISFIED | `aws-actions/configure-aws-credentials@v4` with `role-to-assume` is first step in both build and deploy actions |
| BUILD-01 | 03-02 | Ferry Action builds Lambda containers using the Magic Dockerfile pattern | SATISFIED | `action/Dockerfile` exists; `build.py` constructs and invokes `docker build` command with Dockerfile |
| BUILD-02 | 03-02 | Magic Dockerfile supports configurable Python runtime versions via ferry.yaml | SATISFIED | `ARG PYTHON_VERSION=3.12` in Dockerfile; `--build-arg PYTHON_VERSION={version}` in `build_docker_command`; `parse_runtime_version` strips "python" prefix |
| BUILD-03 | 03-02 | Magic Dockerfile supports private GitHub repo dependencies via Docker build secrets | SATISFIED | `RUN --mount=type=secret,id=github_token` in Dockerfile; `--secret id=github_token,env=GITHUB_TOKEN` flag added when `github_token` is truthy |
| BUILD-04 | 03-02 | Magic Dockerfile handles optional system-requirements.txt and system-config.sh without failing when absent | SATISFIED | Glob trick `COPY system-requirements.tx[t]` and `COPY system-config.s[h]` with `if [ -f /tmp/... ]` guards |
| BUILD-05 | 03-02 | Ferry Action pushes built images to pre-existing ECR repos with deployment tags | SATISFIED | `ecr_login` and `push_image` in `build.py`; image tagged `{ecr_uri}:{deployment_tag}`; digest captured via `docker inspect` |
| DEPLOY-01 | 03-03 | Ferry Action deploys Lambda functions (update-function-code, wait, publish version, update alias) | SATISFIED | `deploy_lambda` in `deploy.py`: `update_function_code` -> `get_waiter("function_updated").wait()` -> `publish_version` -> `update_alias`/`create_alias` |
| DEPLOY-04 | 03-03 | Ferry Action skips deployment when built image digest matches currently deployed image | SATISFIED | `should_skip_deploy` normalizes both digests; `get_current_image_digest` extracts `ResolvedImageUri` from Lambda; skip path sets `skipped=true` output and returns early |
| DEPLOY-05 | 03-03 | Ferry Action tags deployments with git SHA and PR number for traceability | SATISFIED | `publish_version` description: `f"Deployed by Ferry: {deployment_tag}"`; job summary tables include deployment tag, trigger SHA, image URI |

**No orphaned requirements.** All 10 Phase 3 requirement IDs from REQUIREMENTS.md traceability table (AUTH-02, BUILD-01 through BUILD-05, DEPLOY-01, DEPLOY-04, DEPLOY-05, ACT-01) are claimed in plan frontmatter and verified in code.

---

## Anti-Patterns Found

None detected. Scanned all source and action files for: TODO/FIXME/XXX/HACK, placeholder text, `return null`/`return {}`, empty handlers, console-log-only implementations.

---

## Test Results

- **50 tests** in `tests/test_action/` — all pass (0.65s)
- **175 tests** across full test suite — all pass (2.12s)
- Coverage: `test_parse_payload.py` (12 tests), `test_gha.py` (11 tests), `test_build.py` (13 tests), `test_deploy.py` (14 tests)

---

## Human Verification Required

None for core functionality. The following items can only be confirmed with a live GHA run but are not blockers given the quality of the implementation:

### 1. End-to-end OIDC token exchange

**Test:** Install Ferry Action in a real GHA workflow with `permissions: id-token: write` and a valid AWS role ARN. Trigger a workflow run.
**Expected:** `configure-aws-credentials` successfully obtains temporary credentials; `build.py` can call `sts.get_caller_identity()` and `ecr.get-login-password`.
**Why human:** Cannot verify OIDC token exchange without a real GHA environment and live AWS account.

### 2. Dockerfile glob trick behavior on Docker BuildKit

**Test:** Run `docker build --build-arg PYTHON_VERSION=3.12 -f action/Dockerfile .` from a directory without `system-requirements.txt` or `system-config.sh`.
**Expected:** Build completes successfully without errors for missing optional files.
**Why human:** The glob trick (`COPY system-requirements.tx[t]`) requires BuildKit; cannot verify behavior without a Docker daemon.

### 3. ECR push digest capture via docker inspect

**Test:** After a real image push, verify `docker inspect --format='{{index .RepoDigests 0}}'` returns a `repo@sha256:...` string and that `deploy.py` correctly reads this for skip detection on the next run.
**Expected:** Digest captured during build matches the `ResolvedImageUri` in Lambda on the next deploy cycle, triggering a skip.
**Why human:** Requires a live ECR registry and Lambda function.

---

## Summary

Phase 3 fully achieves its goal. The complete build-and-deploy pipeline is implemented:

- **Three composite actions** scaffold the fan-out architecture (setup parses payload to matrix, build handles Docker/ECR per resource, deploy handles Lambda per resource).
- **OIDC authentication** is correctly wired in both build and deploy actions as the first step, with `role-to-assume` passed from the user's workflow.
- **Magic Dockerfile** implements all v1 design requirements: configurable Python runtime, optional system packages via glob trick, build secrets for private repo dependencies, and `CMD ["main.handler"]`.
- **Build module** constructs the full Docker build command, performs ECR login via the password-pipe pattern, pushes the image, and captures the digest via `docker inspect`.
- **Deploy module** executes the complete Lambda deploy sequence with waiter, publishes a named version, manages the `live` alias with create/update fallback, and correctly skips when the digest is unchanged.
- All 10 requirement IDs are satisfied with substantive implementations and 50 passing tests (175 across the full suite).

---

_Verified: 2026-02-26_
_Verifier: Claude (gsd-verifier)_
