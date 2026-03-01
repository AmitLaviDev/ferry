---
phase: 12-shared-iam-secrets
plan: 01
subsystem: infra
tags: [terraform, iam, oidc, secrets-manager, aws, github-actions]

# Dependency graph
requires:
  - phase: 11-bootstrap-global-resources
    provides: S3 state bucket, ECR repository, bootstrap patterns
provides:
  - GitHub Actions OIDC identity provider (global)
  - Lambda execution role with DynamoDB, Secrets Manager, CloudWatch Logs policies
  - GHA self-deploy role with OIDC trust scoped to ferry repo
  - GHA dispatch role with OIDC trust scoped to org
  - Secrets Manager containers for GitHub App credentials
  - Role ARNs and secret ARNs exported for downstream consumption
affects: [13-lambda-deploy, 14-gha-workflow]

# Tech tracking
tech-stack:
  added: [aws_iam_openid_connect_provider, aws_iam_role, aws_iam_policy, aws_iam_role_policy_attachment, aws_secretsmanager_secret, terraform_remote_state]
  patterns: [OIDC federation trust policies, least-privilege IAM per role, Secrets Manager empty containers, remote_state cross-project references]

key-files:
  created:
    - iac/global/aws/oidc/main.tf
    - iac/global/aws/oidc/providers.tf
    - iac/global/aws/oidc/variables.tf
    - iac/global/aws/oidc/outputs.tf
    - iac/staging/aws/shared/providers.tf
    - iac/staging/aws/shared/data.tf
    - iac/staging/aws/shared/iam.tf
    - iac/staging/aws/shared/oidc.tf
    - iac/staging/aws/shared/secrets.tf
    - iac/staging/aws/shared/variables.tf
    - iac/staging/aws/shared/outputs.tf
  modified: []

key-decisions:
  - "kebab-case IAM naming (ferry-lambda-execution, ferry-gha-self-deploy) for consistency with project naming conventions"
  - "Direct policy attachments over locals map pattern -- cleaner at this scale (9 attachments)"
  - "No secret versions created -- empty containers populated via CLI in Phase 14"
  - "gha_ecr_auth policy shared between both GHA roles via separate attachment resources"

patterns-established:
  - "OIDC trust policy: StringLike on sub claim with repo scope for self-deploy, org scope for dispatch"
  - "Remote state references: terraform_remote_state.oidc for cross-project OIDC provider ARN"
  - "Permission policy split: one data.aws_iam_policy_document per concern, one aws_iam_policy per document"
  - "Staging TF projects: iac/staging/aws/<project>/ with state key matching directory path"

requirements-completed: [IAM-01, IAM-02, IAM-03, IAM-04]

# Metrics
duration: 3min
completed: 2026-03-01
---

# Phase 12 Plan 01: Shared IAM + Secrets Summary

**OIDC provider, 3 IAM roles (Lambda execution + 2 GHA deploy) with 8 least-privilege policies, and 3 Secrets Manager containers for GitHub App credentials**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-01T11:13:03Z
- **Completed:** 2026-03-01T11:15:37Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- GitHub Actions OIDC identity provider ready for account-wide use (no thumbprint required)
- Lambda execution role with least-privilege DynamoDB, Secrets Manager, and CloudWatch Logs access
- Two GHA deploy roles with OIDC trust -- self-deploy scoped to ferry repo, dispatch scoped to org
- Three Secrets Manager containers (app-id, private-key, webhook-secret) ready for CLI population
- All role ARNs and secret ARNs exported for Phase 13 and Phase 14 consumption

## Task Commits

Each task was committed atomically:

1. **Task 1: Create OIDC provider Terraform project** - `095c252` (feat)
2. **Task 2: Create shared IAM roles, policies, and Secrets Manager project** - `578a488` (feat)

## Files Created/Modified
- `iac/global/aws/oidc/providers.tf` - S3 backend with global/aws/oidc state key
- `iac/global/aws/oidc/main.tf` - GitHub Actions OIDC identity provider (no thumbprint_list)
- `iac/global/aws/oidc/variables.tf` - Region variable
- `iac/global/aws/oidc/outputs.tf` - oidc_provider_arn and oidc_provider_url exports
- `iac/staging/aws/shared/providers.tf` - S3 backend with staging/aws/shared state key
- `iac/staging/aws/shared/data.tf` - Data sources, remote_state.oidc, 9 IAM policy documents
- `iac/staging/aws/shared/iam.tf` - 3 roles, 8 policies, 9 role-policy attachments
- `iac/staging/aws/shared/oidc.tf` - 2 OIDC assume-role trust policy documents
- `iac/staging/aws/shared/secrets.tf` - 3 Secrets Manager containers via for_each
- `iac/staging/aws/shared/variables.tf` - Region, github_org, github_repo variables
- `iac/staging/aws/shared/outputs.tf` - Role ARNs, role name, and secret ARN map exports

## Decisions Made
- **kebab-case naming:** Consistent with `ferry-*` naming used throughout the project (S3 bucket, DynamoDB table prefix, Lambda function names)
- **Direct policy attachments:** Over locals map pattern -- only 9 attachments, direct is more readable at this scale
- **No secret versions:** Empty containers per plan -- forces explicit CLI population in Phase 14
- **Shared gha_ecr_auth policy:** Single policy attached to both GHA roles via separate attachment resources (distinct TF resource names)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- OIDC provider must be `terraform apply`-ed first (global/oidc), then shared project (staging/shared)
- Phase 13 can reference `lambda_execution_role_arn` via remote_state for Lambda function
- Phase 14 can reference `gha_self_deploy_role_arn` for GHA workflow OIDC configuration
- Secret values must be populated via CLI in Phase 14 before Lambda can start

## Self-Check: PASSED

All 11 created files verified present. Both task commits (095c252, 578a488) verified in git log.

---
*Phase: 12-shared-iam-secrets*
*Completed: 2026-03-01*
