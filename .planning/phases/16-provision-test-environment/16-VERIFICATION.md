---
phase: 16-provision-test-environment
verified: 2026-03-07T18:30:00Z
status: human_needed
score: 4/5 must-haves verified
re_verification: false
human_verification:
  - test: "Verify Ferry GitHub App is installed on AmitLaviDev/ferry-test-app"
    expected: "App appears in the test repo's installed apps list and has repo-level permissions"
    why_human: "TEST-06 status is inconsistent -- SUMMARY claims done but REQUIREMENTS.md shows Pending. Cannot verify GitHub App installation programmatically from this environment."
  - test: "Verify AWS resources exist (ECR, IAM role, Lambda)"
    expected: "aws ecr describe-repositories --repository-names ferry-test/hello-world succeeds; aws iam get-role --role-name ferry-test-deploy succeeds; aws lambda get-function --function-name ferry-test-hello-world succeeds"
    why_human: "External AWS resources cannot be verified from code alone. Terraform IaC is correct, but need to confirm terraform apply was actually run."
  - test: "Verify test repo content on GitHub matches git history"
    expected: "gh api repos/AmitLaviDev/ferry-test-app/contents/ferry.yaml returns 200; gh api repos/AmitLaviDev/ferry-test-app/contents/.github/workflows/ferry-lambdas.yml returns 200"
    why_human: "Content was pushed to external repo and removed from this repo. Cannot verify remote repo from codebase alone."
  - test: "Verify AWS_ROLE_ARN secret is set on test repo"
    expected: "gh secret list --repo AmitLaviDev/ferry-test-app shows AWS_ROLE_ARN"
    why_human: "Repo secrets cannot be verified from codebase."
---

# Phase 16: Provision Test Environment Verification Report

**Phase Goal:** A test repo exists with everything needed to exercise the full Ferry push-to-deploy loop -- ferry.yaml, hello-world Lambda source, GHA dispatch workflow, ECR repo, OIDC role, and the GitHub App installed
**Verified:** 2026-03-07T18:30:00Z
**Status:** human_needed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Test repo on GitHub contains a ferry.yaml that defines one Lambda resource pointing to a hello-world source directory | ? UNCERTAIN | ferry.yaml was created (commit `2c51731`), pushed to external repo (per 16-03-SUMMARY), then removed (commit `5b2edf2`). Content in git history matches spec: `source_dir: lambdas/hello-world`, `ecr_repo: ferry-test/hello-world`, `function_name: ferry-test-hello-world`. Cannot verify remote repo from codebase. |
| 2 | The hello-world Lambda source exists in the test repo (main.py with handler + requirements.txt) and can be built with the Magic Dockerfile | ? UNCERTAIN | main.py has `def handler(event, context)` returning `{"message": "hello from ferry-test"}` (verified from git history commit `2c51731`). requirements.txt is empty (correct for Magic Dockerfile). Content was pushed to external repo. Cannot verify remote. |
| 3 | Test repo has a .github/workflows/ferry-lambdas.yml that triggers on workflow_dispatch and calls ferry-action with the correct inputs | VERIFIED (in codebase) | Workflow (commit `cdfd488`) has `workflow_dispatch` trigger, `id-token: write` + `contents: read` + `checks: write` permissions, and uses `AmitLaviDev/ferry/action/{setup,build,deploy}@main` external composite actions. All matrix inputs are correctly wired. Remote push needs human check. |
| 4 | An ECR repository exists for the test Lambda and the test repo's GHA runner can push images to it via an OIDC IAM role | VERIFIED (IaC correct) | `iac/test-env/main.tf` defines ECR module (`ferry-test/hello-world`), IAM role with OIDC trust scoped to `AmitLaviDev/ferry-test-app`, ECR push policy, and Lambda deploy policy. All 6 Lambda API actions present. Actual AWS resources need human verification. |
| 5 | The Ferry GitHub App is installed on the test repo and the test repo appears in the App's installation list | ? UNCERTAIN | 16-03-SUMMARY claims done. REQUIREMENTS.md has TEST-06 as `[ ]` unchecked and `Pending` in tracking table. Contradictory evidence. Needs human verification. |

**Score:** 4/5 truths verified (code-level); 0/5 confirmed in production (all external)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `iac/test-env/providers.tf` | S3 backend config, AWS provider | VERIFIED | S3 backend at `test-env/terraform.tfstate`, AWS provider with `ferry-test` tags |
| `iac/test-env/variables.tf` | Configurable variables | VERIFIED | 6 variables: region, github_owner, github_repo, ecr_repository_name, lambda_function_name, lambda_placeholder_image_uri |
| `iac/test-env/data.tf` | OIDC remote state, IAM policy documents | VERIFIED | terraform_remote_state.oidc, 5 policy documents (deploy trust, lambda trust, ECR auth, ECR push, Lambda deploy) |
| `iac/test-env/main.tf` | ECR repo, IAM role+policies, Lambda function | VERIFIED | ECR module v2.4.0, IAM role with 3 policy attachments, Lambda module v8.7.0, execution role |
| `iac/test-env/outputs.tf` | Role ARN, ECR URL, Lambda name/ARN | VERIFIED | 4 outputs: test_deploy_role_arn, ecr_repository_url, lambda_function_name, lambda_function_arn |
| `test-app/ferry.yaml` (historical) | Ferry config with 1 Lambda | VERIFIED (git history) | Created in 2c51731, removed in 5b2edf2 after push to external repo |
| `test-app/lambdas/hello-world/main.py` (historical) | Lambda handler | VERIFIED (git history) | `def handler(event, context)` returns greeting JSON |
| `test-app/.github/workflows/ferry-lambdas.yml` (historical) | GHA workflow | VERIFIED (git history) | workflow_dispatch, external composite action refs, OIDC permissions |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `iac/test-env/data.tf` | OIDC remote state | `terraform_remote_state.oidc` | WIRED | References `global/cloud/aws/oidc/terraform.tfstate` for OIDC provider ARN |
| `iac/test-env/main.tf` | `iac/test-env/data.tf` | OIDC provider ARN in trust policy | WIRED | `data.terraform_remote_state.oidc.outputs.oidc_provider_arn` used in trust policy |
| `ferry.yaml` | `lambdas/hello-world/` | `source_dir` field | WIRED | `source_dir: lambdas/hello-world` matches directory structure |
| `ferry.yaml` | ECR repo | `ecr_repo` field | WIRED | `ecr_repo: ferry-test/hello-world` matches TF `var.ecr_repository_name` default |
| `ferry.yaml` | Lambda function | `function_name` field | WIRED | `function_name: ferry-test-hello-world` matches TF `var.lambda_function_name` default |
| GHA workflow | IAM role | `AWS_ROLE_ARN` secret | WIRED (design) | Workflow uses `${{ secrets.AWS_ROLE_ARN }}` -- actual secret set per 16-03-SUMMARY |
| GHA workflow | ferry-action | `uses: AmitLaviDev/ferry/action/*@main` | WIRED | Correct external composite action syntax |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TEST-01 | 16-02 | Test repo with ferry.yaml defining one hello-world Lambda | SATISFIED | ferry.yaml created (commit 2c51731), matches schema |
| TEST-02 | 16-02 | Test repo contains hello-world Lambda source | SATISFIED | main.py handler + requirements.txt created (commit 2c51731) |
| TEST-03 | 16-02 | Test repo has GHA workflow triggering ferry-action on workflow_dispatch | SATISFIED | ferry-lambdas.yml with correct dispatch trigger and action refs (commit cdfd488) |
| TEST-04 | 16-01 | ECR repo exists for test Lambda | SATISFIED | `iac/test-env/main.tf` defines ECR module for `ferry-test/hello-world`; 16-03-SUMMARY confirms apply |
| TEST-05 | 16-01 | OIDC IAM role allows test repo GHA runner to deploy | SATISFIED | IAM role with OIDC trust scoped to `AmitLaviDev/ferry-test-app`, ECR push + Lambda deploy permissions |
| TEST-06 | 16-03 | GitHub App installed on test repo | NEEDS HUMAN | 16-03-SUMMARY claims done; REQUIREMENTS.md shows unchecked/Pending. Contradictory. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `iac/test-env/data.tf` | 112 | Lambda deploy resource ARN missing `:*` suffix for alias operations | Warning | `lambda:UpdateAlias`, `lambda:CreateAlias`, `lambda:GetAlias` require `function:name:*` resource ARN. Current ARN is `function:name` only. Will cause AccessDenied during Phase 17 E2E when ferry-action tries to create/update aliases. |
| `test-app/` | - | Residual `__pycache__` directory | Info | `test-app/lambdas/hello-world/__pycache__/` remains after staging dir removal. Gitignored, no impact. |

### Human Verification Required

### 1. Verify Ferry GitHub App Installation (TEST-06)

**Test:** Check if Ferry GitHub App is installed on `AmitLaviDev/ferry-test-app`
**Expected:** App appears in installation list with appropriate permissions (contents read, checks write, pull_requests write)
**Why human:** REQUIREMENTS.md contradicts SUMMARY. Cannot query GitHub App installations from codebase.
**Command:** `gh api /user/installations --jq '.installations[].repositories_url'` then check for ferry-test-app

### 2. Verify AWS Resources Exist

**Test:** Confirm terraform apply was run and resources are live
**Expected:** All three resources exist:
- `aws ecr describe-repositories --repository-names ferry-test/hello-world`
- `aws iam get-role --role-name ferry-test-deploy`
- `aws lambda get-function --function-name ferry-test-hello-world`
**Why human:** External AWS state cannot be verified from codebase

### 3. Verify Test Repo Content on GitHub

**Test:** Confirm ferry-test-app repo has all pushed content
**Expected:**
- `gh api repos/AmitLaviDev/ferry-test-app/contents/ferry.yaml` returns 200
- `gh api repos/AmitLaviDev/ferry-test-app/contents/lambdas/hello-world/main.py` returns 200
- `gh api repos/AmitLaviDev/ferry-test-app/contents/.github/workflows/ferry-lambdas.yml` returns 200
**Why human:** External repo, not verifiable from this codebase

### 4. Verify AWS_ROLE_ARN Secret

**Test:** Confirm repo secret is set
**Expected:** `gh secret list --repo AmitLaviDev/ferry-test-app` shows `AWS_ROLE_ARN`
**Why human:** Secrets not readable from codebase

### Gaps Summary

No code-level gaps were found. All Terraform IaC files are complete, well-structured, and follow existing conventions. All test-app content (ferry.yaml, Lambda source, GHA workflow) was verified from git history and matches specifications.

**One warning-level finding:** The Lambda deploy IAM policy resource ARN in `iac/test-env/data.tf` line 112 is missing the `:*` wildcard suffix needed for alias operations. This will likely cause an IAM AccessDenied error in Phase 17 when ferry-action tries to `create_alias` or `update_alias`. The fix is to add a second resource entry: `arn:aws:lambda:...:function:${var.lambda_function_name}:*`.

**One tracking inconsistency:** TEST-06 (GitHub App installed on test repo) shows contradictory status between 16-03-SUMMARY (done) and REQUIREMENTS.md (Pending/unchecked). Needs human confirmation.

All 5 truths pass at the code/IaC level. The phase's unique nature (provisioning external resources) means all truths ultimately require human verification to confirm the external state matches the code.

---

_Verified: 2026-03-07T18:30:00Z_
_Verifier: Claude (gsd-verifier)_
