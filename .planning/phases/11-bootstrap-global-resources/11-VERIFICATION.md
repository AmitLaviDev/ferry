---
phase: 11-bootstrap-global-resources
verified: 2026-02-28T18:00:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
human_verification:
  - test: "Run scripts/bootstrap.sh against a real AWS account"
    expected: "S3 bucket ferry-terraform-state created, ECR repo lambda-ferry-backend created, placeholder image pushed with tag 'placeholder' — all in a single command with no errors"
    why_human: "Requires live AWS credentials and account; cannot verify actual AWS resource creation programmatically from codebase alone"
---

# Phase 11: Bootstrap + Global Resources Verification Report

**Phase Goal:** Terraform state management and container registry exist so all subsequent IaC projects can initialize and the Lambda has an image to reference
**Verified:** 2026-02-28T18:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | S3 state bucket TF project defines bucket with versioning, encryption, and public access block | VERIFIED | `iac/global/aws/backend/main.tf` has `aws_s3_bucket`, `aws_s3_bucket_versioning` (Enabled), `aws_s3_bucket_server_side_encryption_configuration` (aws:kms + bucket_key_enabled), and `aws_s3_bucket_public_access_block` (all four booleans = true) as separate resources |
| 2 | ECR repository TF project defines repo with lifecycle policy keeping last 10 images | VERIFIED | `iac/global/aws/ecr/main.tf` has `aws_ecr_repository` with scan_on_push and `aws_ecr_lifecycle_policy` with countNumber = 10, tagStatus = "any" |
| 3 | Placeholder Dockerfile builds a minimal Lambda handler image for arm64 | VERIFIED | `iac/global/aws/ecr/placeholder/Dockerfile` uses `public.ecr.aws/lambda/python:3.14` base, copies `app.py`, sets `CMD ["app.handler"]`; bootstrap script builds with `--platform linux/arm64` |
| 4 | All TF projects use S3 backend with use_lockfile | VERIFIED | Both `iac/global/aws/backend/providers.tf` and `iac/global/aws/ecr/providers.tf` have `backend "s3"` block with `use_lockfile = true` and `bucket = "ferry-terraform-state"` |
| 5 | Running bootstrap.sh orchestrates the full sequence: S3 bucket creation, state migration, ECR apply, placeholder image build and push | VERIFIED | `scripts/bootstrap.sh` (255 lines) implements `step_backend`, `step_ecr`, `step_placeholder` functions in correct order, called from `main()` |
| 6 | Bootstrap script is idempotent — re-running skips already-completed steps | VERIFIED | `step_backend` checks via `aws s3api head-bucket`; `step_ecr` via `aws ecr describe-repositories`; `step_placeholder` via `aws ecr describe-images`; each returns early if resource exists |
| 7 | Placeholder image is built for arm64 architecture to match Lambda target | VERIFIED | `docker build --platform linux/arm64` present in `scripts/bootstrap.sh` line 222–225 |

**Score:** 7/7 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `iac/global/aws/backend/main.tf` | S3 bucket + versioning + encryption + public access block | VERIFIED | 36 lines; all four separate resources present |
| `iac/global/aws/backend/providers.tf` | Terraform config with S3 backend and use_lockfile | VERIFIED | `use_lockfile = true`, bucket = "ferry-terraform-state", key = "global/aws/backend/terraform.tfstate" |
| `iac/global/aws/backend/variables.tf` | bucket_name + region variables | VERIFIED | Both variables with defaults ("ferry-terraform-state", "us-east-1") |
| `iac/global/aws/backend/outputs.tf` | bucket_arn, bucket_name, bucket_region outputs | VERIFIED | Three outputs pointing to correct resource attributes |
| `iac/global/aws/ecr/main.tf` | ECR repository + lifecycle policy | VERIFIED | `aws_ecr_repository.backend` + `aws_ecr_lifecycle_policy.backend` with countNumber = 10 |
| `iac/global/aws/ecr/providers.tf` | Terraform config with S3 backend | VERIFIED | `backend "s3"` block with use_lockfile, key = "global/aws/ecr/terraform.tfstate" |
| `iac/global/aws/ecr/variables.tf` | repository_name + region variables | VERIFIED | repository_name defaults to "lambda-ferry-backend" |
| `iac/global/aws/ecr/outputs.tf` | repository_url, arn, name, registry_id | VERIFIED | Four outputs; registry_id uses `data.aws_caller_identity.current.account_id` (no hardcoded ID) |
| `iac/global/aws/ecr/placeholder/Dockerfile` | Minimal Lambda container image | VERIFIED | FROM public.ecr.aws/lambda/python:3.14, COPY app.py, CMD ["app.handler"] |
| `iac/global/aws/ecr/placeholder/app.py` | Hello-world Lambda handler | VERIFIED | `def handler(event, context)` returns statusCode 200 with JSON body |
| `scripts/bootstrap.sh` | Idempotent bootstrap orchestration script (min 80 lines) | VERIFIED | 255 lines, executable, bash -n passes |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `iac/global/aws/backend/providers.tf` | S3 bucket ferry-terraform-state | backend s3 block references bucket name | WIRED | `bucket = "ferry-terraform-state"` confirmed at line 7 |
| `iac/global/aws/ecr/providers.tf` | S3 bucket ferry-terraform-state | backend s3 block references same state bucket | WIRED | `bucket = "ferry-terraform-state"` confirmed at line 5 |
| `iac/global/aws/ecr/placeholder/Dockerfile` | `iac/global/aws/ecr/placeholder/app.py` | COPY app.py into Lambda task root | WIRED | `COPY app.py ${LAMBDA_TASK_ROOT}` at line 3 |
| `scripts/bootstrap.sh` | `iac/global/aws/backend/` | terraform init/apply/migrate-state commands | WIRED | `BACKEND_DIR="$REPO_ROOT/iac/global/aws/backend"` used in all step_backend terraform calls |
| `scripts/bootstrap.sh` | `iac/global/aws/ecr/` | terraform init/apply commands | WIRED | `ECR_DIR="$REPO_ROOT/iac/global/aws/ecr"` used in step_ecr terraform calls |
| `scripts/bootstrap.sh` | `iac/global/aws/ecr/placeholder/` | docker build with --platform linux/arm64 | WIRED | `docker build --platform linux/arm64 ... "$ECR_DIR/placeholder"` at line 222–225 |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Notes |
|-------------|-------------|-------------|--------|-------|
| BOOT-01 | 11-01, 11-02 | Terraform state stored in S3 with locking in Ferry's AWS account | SATISFIED | Implementation uses `use_lockfile = true` (S3 native locking). REQUIREMENTS.md wording says "DynamoDB locking" — this is a stale requirement text. CONTEXT.md and RESEARCH.md explicitly decided against DynamoDB in favor of Terraform 1.14 native S3 locking (zero extra infrastructure). The requirement intent (state locking) is fully satisfied. |
| BOOT-02 | 11-01 | ECR repository exists with lifecycle policy (keep last 10 images) | SATISFIED | ECR repo named `lambda-ferry-backend` (not `ferry/backend` as REQUIREMENTS.md says). CONTEXT.md explicitly decided on `lambda-ferry-{name}` naming pattern. Lifecycle policy keeping last 10 images is correctly implemented. |
| BOOT-03 | 11-01, 11-02 | Placeholder container image pushed to ECR to unblock Lambda creation | SATISFIED | Placeholder Dockerfile + app.py exist; bootstrap.sh builds and pushes with `--platform linux/arm64` and tag "placeholder". Actual push requires running bootstrap.sh against real AWS. |

**Orphaned requirements:** None. All BOOT-01/02/03 are covered by plans 11-01 and 11-02.

---

### Anti-Patterns Found

| File | Pattern | Severity | Assessment |
|------|---------|----------|------------|
| `scripts/bootstrap.sh` | `PLACEHOLDER_TAG="placeholder"` and references | Info | This is correct usage — "placeholder" is the intended Docker image tag name for the bootstrap image, not a TODO marker. Not a code quality issue. |
| `iac/global/aws/ecr/placeholder/app.py` | `"""Placeholder handler -- replaced by real deploy in Phase 14."""` | Info | Intentional docstring documenting the placeholder's purpose. Not a stub anti-pattern — the handler is fully functional code. |

No blocker or warning anti-patterns found.

---

### Requirement Wording Discrepancies (Informational)

Two discrepancies exist between REQUIREMENTS.md wording and the actual implementation. Both are deliberate decisions documented in CONTEXT.md and RESEARCH.md — the requirement text was written before research phase and not updated:

1. **BOOT-01** says "DynamoDB locking" — implementation uses `use_lockfile = true`. Decision rationale: no extra infrastructure needed; Terraform 1.14 native S3 locking is fully supported and preferred. Documented in RESEARCH.md and CONTEXT.md.

2. **BOOT-02** says ECR repo named `ferry/backend` — implementation uses `lambda-ferry-backend`. Decision rationale: ECR naming pattern `lambda-ferry-{name}` was adopted in CONTEXT.md for extensibility (one repo per Lambda). The lifecycle policy (keep last 10) matches exactly.

These are not gaps. REQUIREMENTS.md should be updated to reflect the implemented decisions, but the implementation itself is correct per the design context.

---

### Human Verification Required

#### 1. Full Bootstrap Execution

**Test:** Run `scripts/bootstrap.sh` from repo root against a real AWS account with credentials configured.
**Expected:**
- Step 1 creates S3 bucket `ferry-terraform-state` with versioning, KMS encryption, public access block; then migrates local Terraform state to S3
- Step 2 creates ECR repository `lambda-ferry-backend` with lifecycle policy via `terraform apply`
- Step 3 builds and pushes placeholder image to ECR with tag `placeholder` using `--platform linux/arm64`
- Second run: all three steps display `[skip]` messages and exit cleanly
**Why human:** Requires live AWS credentials, Terraform, Docker, and a real AWS account. Cannot verify actual resource creation from codebase alone.

---

### Gaps Summary

No gaps. All 7 observable truths verified, all 11 artifacts substantive and correctly wired, all 6 key links confirmed. Bootstrap script is executable (255 lines), passes `bash -n` syntax check, and implements all required idempotency guards, the S3 backend chicken-and-egg sequence, and arm64 placeholder image build.

The phase goal is achieved: IaC source files for Terraform state management and ECR container registry exist, plus an idempotent bootstrap script that orchestrates the full setup sequence. Subsequent IaC phases (12, 13, 14) can initialize against the S3 backend once `scripts/bootstrap.sh` is run.

---

**Commits verified:** c6958a9, 1b29874 (Plan 01 tasks), 2d41267 (Plan 02 task) — all present in git log.

---

_Verified: 2026-02-28T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
