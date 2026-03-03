---
phase: 14-self-deploy-manual-setup
verified: 2026-03-03T08:30:00Z
status: human_needed
score: 8/8 must-haves verified
re_verification: false
human_verification:
  - test: "Push to main triggers the self-deploy workflow and it succeeds end-to-end"
    expected: "Test job passes, Docker image builds and pushes to ECR, Lambda updates to new image SHA"
    why_human: "Cannot trigger or observe a GitHub Actions workflow run from local verification. Requires AWS_DEPLOY_ROLE_ARN secret to be set and first deploy triggered."
  - test: "GitHub App registered and receiving webhooks"
    expected: "Webhook deliveries appear in GitHub App Advanced tab, Lambda logs show incoming requests"
    why_human: "GitHub App registration is a manual external service step. Cannot verify from codebase alone."
  - test: "Secrets Manager values populated and Lambda resolves them at cold start"
    expected: "Lambda starts without errors, webhook signature validation works with real GitHub payloads"
    why_human: "SM population requires AWS CLI execution. Real cold-start behavior can only be observed in a deployed Lambda."
  - test: "Curl the Function URL returns a JSON response"
    expected: "curl returns any JSON body (error or success), proving the real Ferry image is running"
    why_human: "Requires deployed Lambda with real Docker image, not the placeholder image."
---

# Phase 14: Self-Deploy + Manual Setup Verification Report

**Phase Goal:** Ferry can deploy itself on every push to main, the GitHub App is registered and receiving webhooks, and anyone can reproduce the full setup from the runbook

**Verified:** 2026-03-03T08:30:00Z
**Status:** human_needed
**Re-verification:** No -- initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                              | Status     | Evidence                                                                                            |
|----|----------------------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------|
| 1  | `docker build` from repo root produces a container with ferry-backend installed                    | VERIFIED   | Dockerfile exists, multi-stage build, CMD wires to `ferry_backend.webhook.handler.handler`          |
| 2  | `settings.py` resolves Secrets Manager values when `FERRY_*_SECRET` env vars are present          | VERIFIED   | `resolve_secrets` model_validator calls `get_secret_value`; 4 tests pass including `@mock_aws`     |
| 3  | `settings.py` uses plain `FERRY_*` env vars when `FERRY_*_SECRET` vars are absent (local dev)     | VERIFIED   | `TestLocalDevMode` class covers this; no SM client created when secret names are empty              |
| 4  | Docker build context excludes `.git`, `.venv`, `iac`, `tests`, `docs`, `.planning`, `action`      | VERIFIED   | `.dockerignore` contains all required exclusions                                                    |
| 5  | Push to main triggers the self-deploy workflow                                                     | VERIFIED   | `on: push: branches: [main]` confirmed via YAML parse                                              |
| 6  | Test job runs pytest before build/deploy proceeds                                                  | VERIFIED   | `test` job with `uv run pytest`; `deploy` job has `needs: test`                                    |
| 7  | Deploy job authenticates via OIDC, builds Docker image, pushes to ECR, and updates Lambda          | VERIFIED   | `configure-aws-credentials@v6`, `amazon-ecr-login@v2`, `build-push-action@v6`, `update-function-code` + `wait function-updated-v2` all present |
| 8  | Setup runbook documents GitHub App registration, SM population, and E2E verification steps        | VERIFIED   | `docs/setup-runbook.md` (230 lines): all 6 steps + troubleshooting section present                |

**Score:** 8/8 truths verified (automated checks)

---

### Required Artifacts

| Artifact                                          | Expected                                              | Status      | Details                                                                           |
|---------------------------------------------------|-------------------------------------------------------|-------------|-----------------------------------------------------------------------------------|
| `Dockerfile`                                      | Multi-stage Docker build for ferry-backend            | VERIFIED    | 43 lines, two stages, CMD `ferry_backend.webhook.handler.handler`                |
| `.dockerignore`                                   | Build context exclusions                              | VERIFIED    | 19 entries including `.git/`, `.venv/`, `iac/`, `tests/`, `docs/`, `action/`    |
| `backend/src/ferry_backend/settings.py`           | SM resolution at cold start                           | VERIFIED    | `resolve_secrets` model_validator, `boto3.client("secretsmanager")`, `get_secret_value` |
| `tests/test_settings.py`                          | Tests for SM resolution and local dev fallback        | VERIFIED    | 4 tests, all pass: local dev, whitespace strip, all-SM, mixed mode               |
| `.github/workflows/self-deploy.yml`               | Self-deploy GHA workflow                              | VERIFIED    | Valid YAML, triggers on push to main, test + deploy jobs, OIDC, ECR, Lambda update |
| `docs/setup-runbook.md`                           | Complete setup runbook for Phase 14 manual steps      | VERIFIED    | 230 lines, 6 steps + troubleshooting, `put-secret-value` commands, `github.com/settings/apps` |

---

### Key Link Verification

| From                                    | To                                     | Via                             | Status   | Details                                                      |
|-----------------------------------------|----------------------------------------|---------------------------------|----------|--------------------------------------------------------------|
| `Dockerfile`                            | `backend/src/ferry_backend/webhook/handler.py` | CMD handler path        | VERIFIED | `CMD ["ferry_backend.webhook.handler.handler"]` matches `def handler` at line 51 |
| `backend/src/ferry_backend/settings.py` | Secrets Manager                        | `boto3 get_secret_value`        | VERIFIED | Line 77-79: `client = boto3.client("secretsmanager", ...)`, `get_secret_value(SecretId=secret_name)` |
| `Dockerfile`                            | `pyproject.toml`                       | `uv export --package ferry-backend` | VERIFIED | Line 21: `uv export --frozen --no-emit-workspace --no-dev --package ferry-backend` |
| `.github/workflows/self-deploy.yml`     | `Dockerfile`                           | `docker/build-push-action context: .` | VERIFIED | `uses: docker/build-push-action@v6` with `context: .`      |
| `.github/workflows/self-deploy.yml`     | AWS Lambda                             | `aws lambda update-function-code` | VERIFIED | Lines 64-69: `update-function-code` + `wait function-updated-v2` |
| `.github/workflows/self-deploy.yml`     | ECR                                    | `aws-actions/amazon-ecr-login`  | VERIFIED | `uses: aws-actions/amazon-ecr-login@v2`, registry used for image tag |
| `docs/setup-runbook.md`                 | GitHub App settings                    | Registration instructions       | VERIFIED | Direct link `https://github.com/settings/apps/new` + 11-step instructions |
| `docs/setup-runbook.md`                 | Secrets Manager                        | CLI population commands         | VERIFIED | Three `aws secretsmanager put-secret-value` commands with correct secret IDs |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                          | Status       | Evidence                                                          |
|-------------|-------------|----------------------------------------------------------------------|--------------|-------------------------------------------------------------------|
| DEPLOY-01   | 14-01       | Backend Dockerfile builds ferry-utils + ferry-backend from repo root | SATISFIED    | `Dockerfile` verified: two-stage build, uv export workspace pattern, CMD wires to handler |
| DEPLOY-02   | 14-02       | Self-deploy GHA workflow builds, pushes to ECR, and updates Lambda on push to main | SATISFIED | `self-deploy.yml`: push trigger, test + deploy jobs, OIDC, ECR push, Lambda update + wait |
| DEPLOY-03   | 14-01       | settings.py modified to load secrets from Secrets Manager at cold start | SATISFIED | `settings.py`: `resolve_secrets` model_validator, boto3 SM client, `get_secret_value` |
| SETUP-01    | 14-03       | GitHub App registered with Function URL as webhook endpoint          | NEEDS HUMAN  | Runbook documents step-by-step instructions; actual registration is a manual external step |
| SETUP-02    | 14-03       | Secrets Manager values populated via CLI after GitHub App registration | NEEDS HUMAN | Runbook has exact `put-secret-value` commands; actual population is a manual step |
| SETUP-03    | 14-03       | Setup runbook documented in repo (apply order + manual steps)        | SATISFIED    | `docs/setup-runbook.md` (230 lines): prerequisites, 6 ordered steps, troubleshooting |

**Notes on SETUP-01 and SETUP-02:** These requirements describe manual operational tasks (GitHub App registration and Secrets Manager population). The plan correctly scoped them as non-blocking human checkpoint steps. The *documentation* artifact for these steps (SETUP-03) is fully satisfied. Whether the manual steps have been *executed* cannot be verified from the codebase and requires human confirmation.

---

### Anti-Patterns Found

| File                       | Line | Pattern              | Severity | Impact                                                                     |
|----------------------------|------|----------------------|----------|----------------------------------------------------------------------------|
| `docs/setup-runbook.md`    | 129  | "placeholder (`0`)"  | Info     | Expected documentation text explaining that `installation_id=0` is a Terraform default that must be replaced. Not a code stub. |
| `docs/setup-runbook.md`    | 191  | "placeholder image"  | Info     | Expected documentation text explaining ECR placeholder replaced by real image on first deploy. Not a code stub. |

No blocker or warning-level anti-patterns found.

---

### Human Verification Required

#### 1. Self-Deploy Workflow Succeeds End-to-End

**Test:** Push a commit to `main` (or re-run the most recent push workflow) and observe the GitHub Actions run at `https://github.com/<owner>/ferry/actions/workflows/self-deploy.yml`
**Expected:** Test job passes, deploy job authenticates via OIDC, Docker image builds and pushes to ECR tagged with the commit SHA, Lambda updates and the `wait function-updated-v2` waiter completes successfully
**Why human:** Cannot trigger or observe a GHA workflow run from local verification. Requires `AWS_DEPLOY_ROLE_ARN` secret to be set and AWS infrastructure from Phases 11-13 to be deployed.

#### 2. GitHub App Registered and Receiving Webhooks (SETUP-01)

**Test:** After GitHub App registration, push a commit to the ferry repo and check the GitHub App's Advanced tab for a webhook delivery with HTTP 200
**Expected:** Webhook delivery appears showing the Function URL received a `push` event and responded with 200
**Why human:** GitHub App registration is an external service action. The App's existence and webhook delivery cannot be verified from the codebase.

#### 3. Secrets Manager Values Populated and Resolved at Cold Start (SETUP-02)

**Test:** After running the `put-secret-value` commands from the runbook, invoke the Lambda and check CloudWatch logs: `aws logs tail /aws/lambda/ferry-backend --since 5m`
**Expected:** No `botocore.exceptions.ClientError` errors in logs; Lambda processes webhooks with valid HMAC signature validation
**Why human:** SM population requires executing AWS CLI commands. Cold-start resolution can only be observed in a deployed Lambda.

#### 4. Function URL Returns Real Ferry Response

**Test:** `curl -s "$(terraform -chdir=iac/aws/staging/us-east-1/ferry_backend output -raw lambda_function_url)" | jq .`
**Expected:** Any JSON response (even an error body) proving the real Ferry Docker image is running, not the ECR placeholder image
**Why human:** Requires deployed Lambda with the image built by the self-deploy workflow.

---

### Gaps Summary

No automated gaps found. All code artifacts exist, are substantive, and are correctly wired:

- `Dockerfile` -- complete multi-stage build with correct handler CMD
- `.dockerignore` -- all required exclusions present
- `settings.py` -- SM resolution implemented and tested (4/4 tests pass)
- `self-deploy.yml` -- valid YAML, correct trigger, both jobs wired, all actions present
- `docs/setup-runbook.md` -- complete 230-line document with all required sections

The only unverifiable items are the manual operational steps (SETUP-01, SETUP-02) and the live workflow execution (DEPLOY-02 runtime behavior). These require human execution per the plan's design -- Plan 03 Task 2 was explicitly marked as a non-blocking human-verify checkpoint.

---

_Verified: 2026-03-03T08:30:00Z_
_Verifier: Claude (gsd-verifier)_
