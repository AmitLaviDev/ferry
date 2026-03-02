---
phase: 13-backend-core
verified: 2026-03-02T09:29:18Z
status: human_needed
score: 4/5 must-haves verified
human_verification:
  - test: "Run terraform apply and curl the Function URL"
    expected: "curl <function-url> returns any HTTP response (even an error), proving the Lambda is live and the Function URL is publicly accessible"
    why_human: "terraform apply has not been run — this is a manual step documented in the phase plan. No automated check can confirm a live deployed Lambda without AWS credentials and an applied stack."
---

# Phase 13: Backend Core Verification Report

**Phase Goal:** Ferry Lambda is deployed and accessible via a public Function URL, with DynamoDB dedup table and structured logging, ready to receive webhooks
**Verified:** 2026-03-02T09:29:18Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Ferry Lambda is deployed as arm64 container image with publicly accessible Function URL (auth=NONE) | VERIFIED | `main.tf` L53: `architectures = ["arm64"]`; L85: `authorization_type = "NONE"` on `aws_lambda_function_url.backend` |
| 2 | DynamoDB dedup table exists with PAY_PER_REQUEST billing and TTL on `expires_at` | VERIFIED | `main.tf` L18–42: `billing_mode = "PAY_PER_REQUEST"`, `hash_key = "pk"`, `range_key = "sk"`, TTL block `attribute_name = "expires_at"` enabled=true; `expires_at` correctly absent from `attribute` blocks |
| 3 | CloudWatch log group exists with 30-day retention and Lambda writes logs to it | VERIFIED | `main.tf` L5–12: `/aws/lambda/ferry-backend`, `retention_in_days = 30`; Lambda `depends_on = [aws_cloudwatch_log_group.backend]` at L68 ensures ordering |
| 4 | Lambda env vars reference Secrets Manager secret names and DynamoDB table name via Terraform (not hardcoded) | VERIFIED | `main.tf` L59–64: `FERRY_APP_ID_SECRET`, `FERRY_PRIVATE_KEY_SECRET`, `FERRY_WEBHOOK_SECRET_SECRET` use deterministic secret names; `FERRY_TABLE_NAME = aws_dynamodb_table.dedup.name` (Terraform reference, not hardcoded). Note: ROADMAP says "ARNs" but PLAN/CONTEXT explicitly decided to use secret names (not ARNs) — the implementation matches the design decision. |
| 5 | `curl <function-url>` returns a response proving the Lambda is live | NEEDS HUMAN | `terraform apply` is a documented manual step. The Terraform config is complete and valid, but the stack has not been applied. |

**Score:** 4/5 automated truths verified. 1 requires human confirmation after `terraform apply`.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `iac/aws/staging/us-east-1/ferry_backend/providers.tf` | S3 backend config + AWS provider with default_tags | VERIFIED | S3 backend key `aws/staging/us-east-1/ferry_backend/terraform.tfstate`, required_version `~> 1.12.0`, AWS provider `~> 6.0`, default_tags ManagedBy+Project, "No assume_role" comment |
| `iac/aws/staging/us-east-1/ferry_backend/data.tf` | Remote state refs for shared IAM and ECR | VERIFIED | `terraform_remote_state.shared` (key: `aws/staging/shared/terraform.tfstate`) and `terraform_remote_state.ecr` (key: `global/cloud/aws/ecr/terraform.tfstate`) |
| `iac/aws/staging/us-east-1/ferry_backend/main.tf` | Lambda, Function URL, DynamoDB, CloudWatch | VERIFIED | 4 resources: `aws_cloudwatch_log_group.backend`, `aws_dynamodb_table.dedup`, `aws_lambda_function.backend`, `aws_lambda_function_url.backend` |
| `iac/aws/staging/us-east-1/ferry_backend/variables.tf` | region, log_level, installation_id variables | VERIFIED | 3 variables with correct defaults (us-east-1, INFO, "0") and descriptions |
| `iac/aws/staging/us-east-1/ferry_backend/outputs.tf` | function_url, table name/ARN, log group, Lambda name | VERIFIED | 5 outputs: `function_url`, `dynamodb_table_name`, `dynamodb_table_arn`, `log_group_name`, `lambda_function_name` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `main.tf` | `data.tf` (shared remote state) | `data.terraform_remote_state.shared.outputs.lambda_execution_role_arn` | WIRED | `main.tf` L50: `role = data.terraform_remote_state.shared.outputs.lambda_execution_role_arn` |
| `main.tf` | `data.tf` (ecr remote state) | `data.terraform_remote_state.ecr.outputs.repository_url` | WIRED | `main.tf` L52: `image_uri = "${data.terraform_remote_state.ecr.outputs.repository_url}:latest"` |
| `main.tf` | `aws_dynamodb_table.dedup` | `FERRY_TABLE_NAME` env var references DynamoDB resource | WIRED | `main.tf` L62: `FERRY_TABLE_NAME = aws_dynamodb_table.dedup.name` |
| `main.tf` | `aws_cloudwatch_log_group.backend` | `depends_on` for log group creation ordering | WIRED | `main.tf` L68: `depends_on = [aws_cloudwatch_log_group.backend]` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INFRA-01 | 13-01-PLAN.md | Ferry Lambda deployed as arm64 container image with Function URL (auth=NONE) | SATISFIED | `main.tf`: `architectures = ["arm64"]`, `package_type = "Image"`, `aws_lambda_function_url` with `authorization_type = "NONE"` |
| INFRA-02 | 13-01-PLAN.md | DynamoDB dedup table with PAY_PER_REQUEST billing and TTL on expires_at | SATISFIED | `main.tf`: `billing_mode = "PAY_PER_REQUEST"`, TTL block with `attribute_name = "expires_at"`, `enabled = true`; only pk/sk as attribute blocks |
| INFRA-03 | 13-01-PLAN.md | CloudWatch log group with 30-day retention | SATISFIED | `main.tf`: `aws_cloudwatch_log_group.backend`, `name = "/aws/lambda/ferry-backend"`, `retention_in_days = 30` |
| INFRA-04 | 13-01-PLAN.md | Lambda env vars reference Secrets Manager ARNs and DynamoDB table name via Terraform | SATISFIED | `main.tf`: secret names set via deterministic string literals (design decision: names, not ARNs); `FERRY_TABLE_NAME = aws_dynamodb_table.dedup.name` (Terraform reference) |

No orphaned requirements. All four INFRA-0x IDs claimed by 13-01-PLAN.md are accounted for in REQUIREMENTS.md and mapped to Phase 13.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `variables.tf` | 14 | `description = "...placeholder until App registration in Phase 14"` | Info | Expected and documented — `FERRY_INSTALLATION_ID` has value `"0"` until Phase 14 GitHub App registration. Not a blocker. |

No other TODOs, FIXMEs, empty implementations, or stub patterns found across any of the 5 Terraform files.

### Human Verification Required

#### 1. Lambda Live Check

**Test:** After running `terraform apply` in `iac/aws/staging/us-east-1/ferry_backend/`, retrieve the Function URL with `terraform output function_url`, then run `curl -s -o /dev/null -w "%{http_code}" <function-url>`.

**Expected:** Any HTTP response code (200, 403, 500, etc.) confirms the Lambda is live and the Function URL is publicly reachable. A 403 or payload error from the app code is acceptable — it proves the Lambda invoked.

**Why human:** `terraform apply` is a documented manual step requiring AWS credentials and the Phase 12.1 state migration to have been run first. No automated check can confirm a deployed Lambda from the Terraform source alone.

### Additional Notes

**terraform fmt:** Passes with exit 0 — no formatting diffs.

**Git commits:** Both task commits verified in git history:
- `1c5991d` — feat(13-01): create ferry_backend Terraform project
- `d1a48e7` — chore(13-01): validate Terraform and add auto-generated docs

**INFRA-04 wording discrepancy:** REQUIREMENTS.md says "Secrets Manager ARNs" but PLAN.md, CONTEXT.md, and the RESEARCH.md discretion decision explicitly specify "secret names (not ARNs, not a prefix)." The implementation uses names (`ferry/github-app/app-id`, etc.), which is the correct design. The REQUIREMENTS.md wording is slightly imprecise — it should read "secret names." This is a documentation discrepancy, not an implementation gap.

**lifecycle ignore_changes:** `lifecycle { ignore_changes = [image_uri] }` correctly set on the Lambda — Terraform owns infrastructure, GHA owns deployed container code.

**Dependency chain:** Remote state references use the new key convention from Phase 12.1 (`aws/staging/shared/terraform.tfstate` and `global/cloud/aws/ecr/terraform.tfstate`), consistent with the directory restructure.

---

*Verified: 2026-03-02T09:29:18Z*
*Verifier: Claude (gsd-verifier)*
