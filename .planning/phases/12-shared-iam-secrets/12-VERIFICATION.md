---
phase: 12-shared-iam-secrets
verified: 2026-03-01T12:00:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
---

# Phase 12: Shared IAM + Secrets Verification Report

**Phase Goal:** IAM roles and secrets infrastructure exist so the Lambda can assume its execution role and the GHA workflow can authenticate via OIDC
**Verified:** 2026-03-01
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | OIDC identity provider for GitHub Actions is defined as an account-wide Terraform resource | VERIFIED | `iac/global/aws/oidc/main.tf` contains `aws_iam_openid_connect_provider.github` with `url = "https://token.actions.githubusercontent.com"` and `client_id_list = ["sts.amazonaws.com"]`; no `thumbprint_list` (correct for provider v6.0+) |
| 2 | Lambda execution role has least-privilege policies for DynamoDB, Secrets Manager, and CloudWatch Logs | VERIFIED | `iam.tf` defines `aws_iam_role.lambda_execution`; 3 policies (`ferry-lambda-dynamodb`, `ferry-lambda-secrets`, `ferry-lambda-logs`) each backed by scoped `data.aws_iam_policy_document` blocks in `data.tf`; 3 `aws_iam_role_policy_attachment` resources wired to the role |
| 3 | Two separate GHA deploy roles exist (self-deploy and dispatch) with OIDC trust policies scoped to the ferry repo/org | VERIFIED | `iam.tf` defines `aws_iam_role.gha_self_deploy` and `aws_iam_role.gha_dispatch`; `oidc.tf` supplies their trust policies: self-deploy scoped to `repo:${var.github_org}/${var.github_repo}:*`, dispatch scoped to `repo:${var.github_org}/*:*` |
| 4 | Three Secrets Manager containers exist for GitHub App credentials (app-id, private-key, webhook-secret) with no secret versions | VERIFIED | `secrets.tf` uses `for_each` on `local.github_app_secrets` (3 entries) creating `ferry/github-app/{app-id,private-key,webhook-secret}`; zero `aws_secretsmanager_secret_version` resources |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `iac/global/aws/oidc/main.tf` | GitHub Actions OIDC identity provider resource | VERIFIED | Contains `aws_iam_openid_connect_provider "github"` with correct URL and audience; no thumbprint_list |
| `iac/global/aws/oidc/outputs.tf` | OIDC provider ARN output for downstream remote_state | VERIFIED | Exports `oidc_provider_arn` (value = `aws_iam_openid_connect_provider.github.arn`) and `oidc_provider_url` |
| `iac/global/aws/oidc/providers.tf` | S3 backend with correct state key, AWS provider v6 | VERIFIED | Backend key = `global/aws/oidc/terraform.tfstate`; `required_version = "~> 1.12.0"`; provider `~> 6.0`; correct default_tags |
| `iac/global/aws/oidc/variables.tf` | Region variable | VERIFIED | Single `region` variable with `default = "us-east-1"` |
| `iac/staging/aws/shared/iam.tf` | Lambda execution role, GHA self-deploy role, GHA dispatch role, 8 policies, 9 attachments | VERIFIED | 3 `aws_iam_role` resources, 8 `aws_iam_policy` resources, 9 `aws_iam_role_policy_attachment` resources; all reference policy documents via `data.aws_iam_policy_document.*` |
| `iac/staging/aws/shared/data.tf` | IAM policy documents and data sources | VERIFIED | `aws_caller_identity.current`, `aws_region.current`, `terraform_remote_state.oidc`, plus 9 `aws_iam_policy_document` blocks (lambda_assume_role, lambda_dynamodb, lambda_secrets, lambda_logs, gha_ecr_auth, gha_self_deploy_ecr, gha_self_deploy_lambda, gha_dispatch_ecr, gha_dispatch_lambda) |
| `iac/staging/aws/shared/oidc.tf` | OIDC assume-role trust policy documents for GHA roles | VERIFIED | `gha_self_deploy_assume_role` and `gha_dispatch_assume_role` both use `sts:AssumeRoleWithWebIdentity`, federated principal from `terraform_remote_state.oidc.outputs.oidc_provider_arn`, StringEquals on aud, StringLike on sub |
| `iac/staging/aws/shared/secrets.tf` | Secrets Manager containers with for_each, no secret versions | VERIFIED | `for_each` on 3-entry local map; names `ferry/github-app/${each.key}`; no `aws_secretsmanager_secret_version` resource |
| `iac/staging/aws/shared/outputs.tf` | Role ARNs and secret ARNs for downstream phases | VERIFIED | Exports `lambda_execution_role_arn`, `lambda_execution_role_name`, `gha_self_deploy_role_arn`, `gha_dispatch_role_arn`, `github_app_secret_arns` (map via for expression) |
| `iac/staging/aws/shared/providers.tf` | S3 backend with staging state key, AWS provider | VERIFIED | Backend key = `staging/aws/shared/terraform.tfstate`; same provider config as global |
| `iac/staging/aws/shared/variables.tf` | Region, github_org, github_repo variables | VERIFIED | All 3 variables present with expected defaults (`us-east-1`, `get-ferry`, `ferry`) |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `iac/staging/aws/shared/data.tf` | `iac/global/aws/oidc/outputs.tf` | `terraform_remote_state "oidc"` | WIRED | `data.tf` line 9-17: `terraform_remote_state "oidc"` with `key = "global/aws/oidc/terraform.tfstate"` — exact key matches `iac/global/aws/oidc/providers.tf` backend key |
| `iac/staging/aws/shared/iam.tf` | `iac/staging/aws/shared/data.tf` | `data.aws_iam_policy_document.*` references | WIRED | All 3 role `assume_role_policy` fields and all 8 policy `policy` fields reference `data.aws_iam_policy_document.*` — 11 references verified |
| `iac/staging/aws/shared/oidc.tf` | `iac/staging/aws/shared/data.tf` | `data.terraform_remote_state.oidc` in trust policies | WIRED | Both trust policy documents (lines 13 and 38) reference `data.terraform_remote_state.oidc.outputs.oidc_provider_arn` as the federated principal |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| IAM-01 | 12-01-PLAN.md | Lambda execution role with least-privilege policies (DynamoDB, Secrets Manager, CloudWatch Logs) | SATISFIED | `aws_iam_role.lambda_execution` in `iam.tf`; scoped policy documents in `data.tf`; 3 attachments confirmed |
| IAM-02 | 12-01-PLAN.md | OIDC identity provider for GitHub Actions in Ferry AWS account | SATISFIED | `aws_iam_openid_connect_provider.github` in `iac/global/aws/oidc/main.tf` |
| IAM-03 | 12-01-PLAN.md | GHA deploy role with ECR push + Lambda update permissions, scoped to ferry repo | SATISFIED | `aws_iam_role.gha_self_deploy` scoped to `repo:get-ferry/ferry:*`; `aws_iam_role.gha_dispatch` scoped to `repo:get-ferry/*:*`; ECR push and Lambda update policies attached to both |
| IAM-04 | 12-01-PLAN.md | Secrets Manager secret containers for GitHub App credentials (app ID, private key, webhook secret) | SATISFIED | 3 `aws_secretsmanager_secret` resources via `for_each` in `secrets.tf`; paths `ferry/github-app/{app-id,private-key,webhook-secret}`; no versions |

No orphaned requirements — all 4 Phase 12 requirements are declared in the plan and have verified implementations.

---

### Anti-Patterns Found

The only grep match for the anti-pattern scan was in Terraform provider binaries (`.terraform/` directory — binary files). No anti-patterns in source `.tf` files.

The `secrets.tf` MANUAL STEP comment is informational, not a placeholder — it documents required human action for Phase 14 and is intentional per design.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

---

### Human Verification Required

None required for this phase. All artifacts are Terraform configuration files — correctness is verifiable through static analysis of resource declarations, references, and wiring. Actual AWS resource creation requires `terraform apply` but that is an operational step, not a code verification concern.

---

### Commits Verified

Both commits documented in SUMMARY.md are present in git log:

- `095c252` — feat(12-01): add GitHub Actions OIDC identity provider TF project
- `578a488` — feat(12-01): add shared IAM roles, policies, and Secrets Manager project

---

## Summary

Phase 12 fully achieves its goal. All 4 observable truths are verified, all 11 artifacts exist and are substantive (no stubs, no placeholders), and all 3 key links are correctly wired. The remote_state chain is intact: `iac/global/aws/oidc/` exports `oidc_provider_arn`, and `iac/staging/aws/shared/` consumes it via `terraform_remote_state.oidc` in both `data.tf` (the remote_state block) and `oidc.tf` (the OIDC trust policy documents). Requirements IAM-01 through IAM-04 are all satisfied. The implementation follows the plan exactly with no deviations.

---

_Verified: 2026-03-01_
_Verifier: Claude (gsd-verifier)_
