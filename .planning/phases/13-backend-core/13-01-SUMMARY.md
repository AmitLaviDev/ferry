---
phase: 13-backend-core
plan: 01
subsystem: infra
tags: [terraform, lambda, function-url, dynamodb, cloudwatch, arm64, container-image]

# Dependency graph
requires:
  - phase: 12-shared-iam-secrets
    provides: Lambda execution IAM role ARN, Secrets Manager containers
  - phase: 12.1-iac-directory-restructure-and-state-migration
    provides: New directory layout and S3 state key convention
  - phase: 11-bootstrap-global-resources
    provides: ECR repository URL via remote state
provides:
  - Lambda function (ferry-backend) with arm64 container image and Function URL
  - DynamoDB dedup table (ferry-webhook-dedup) with TTL
  - CloudWatch log group with 30-day retention
  - Function URL, table name/ARN, log group name, Lambda name as Terraform outputs
affects: [14-github-app-registration, ferry-action-deploy]

# Tech tracking
tech-stack:
  added: [aws_lambda_function, aws_lambda_function_url, aws_dynamodb_table, aws_cloudwatch_log_group]
  patterns: [lifecycle ignore_changes on image_uri for CI/CD-owned deploys, terraform_remote_state cross-project wiring, explicit log group before Lambda]

key-files:
  created:
    - iac/aws/staging/us-east-1/ferry_backend/providers.tf
    - iac/aws/staging/us-east-1/ferry_backend/data.tf
    - iac/aws/staging/us-east-1/ferry_backend/main.tf
    - iac/aws/staging/us-east-1/ferry_backend/variables.tf
    - iac/aws/staging/us-east-1/ferry_backend/outputs.tf
    - iac/aws/staging/us-east-1/ferry_backend/README.md
  modified: []

key-decisions:
  - "Hardcoded secret names (ferry/github-app/*) -- deterministic from secrets.tf for_each keys, avoids unnecessary shared project output"
  - "FERRY_INSTALLATION_ID as TF variable with placeholder '0' -- deferred to Phase 14 for real value after GitHub App registration"
  - "All 4 resources in main.tf -- tightly coupled, splitting into separate files is over-engineering at this scale"

patterns-established:
  - "Regional TF projects: iac/aws/staging/us-east-1/<project>/ with state key matching directory path"
  - "Lambda env vars reference secret NAMES (not ARNs, not values) -- app resolves at cold start"
  - "lifecycle { ignore_changes = [image_uri] } on Lambda -- TF owns infra, GHA owns deployed code"

requirements-completed: [INFRA-01, INFRA-02, INFRA-03, INFRA-04]

# Metrics
duration: 2min
completed: 2026-03-02
---

# Phase 13 Plan 01: Backend Core Summary

**Ferry backend Lambda (arm64 container image with Function URL), DynamoDB dedup table (PAY_PER_REQUEST with TTL), and CloudWatch log group (30-day retention) via Terraform**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-02T09:24:05Z
- **Completed:** 2026-03-02T09:26:10Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Lambda function ferry-backend deployed as arm64 container image with public Function URL (auth=NONE)
- DynamoDB table ferry-webhook-dedup with pk/sk keys, PAY_PER_REQUEST billing, TTL on expires_at
- CloudWatch log group /aws/lambda/ferry-backend with 30-day retention created before Lambda
- Environment variables wire Secrets Manager secret names and DynamoDB table name from Terraform resources
- All pre-commit hooks pass: terraform fmt, terraform validate, tflint, trivy security scan

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ferry_backend Terraform project** - `1c5991d` (feat)
2. **Task 2: Validate Terraform configuration** - `d1a48e7` (chore)

## Files Created/Modified
- `iac/aws/staging/us-east-1/ferry_backend/providers.tf` - S3 backend config + AWS provider with default_tags
- `iac/aws/staging/us-east-1/ferry_backend/data.tf` - Remote state references for shared IAM and ECR projects
- `iac/aws/staging/us-east-1/ferry_backend/main.tf` - Lambda, Function URL, DynamoDB table, CloudWatch log group
- `iac/aws/staging/us-east-1/ferry_backend/variables.tf` - Input variables for region, log_level, installation_id
- `iac/aws/staging/us-east-1/ferry_backend/outputs.tf` - Function URL, table name/ARN, log group name, Lambda name outputs
- `iac/aws/staging/us-east-1/ferry_backend/README.md` - Auto-generated terraform-docs

## Decisions Made
- **Hardcoded secret names:** `ferry/github-app/app-id`, `ferry/github-app/private-key`, `ferry/github-app/webhook-secret` are deterministic from the `for_each` keys in `secrets.tf` -- adding a new output to the shared project just to avoid hardcoding three strings is over-engineering
- **FERRY_INSTALLATION_ID as TF variable:** Placeholder value `"0"` -- the real value is only known after GitHub App registration in Phase 14
- **All resources in main.tf:** Four tightly coupled resources in one file -- Lambda references DynamoDB table name, depends on log group

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. User must run Phase 12.1 migration script and `terraform apply` when ready.

## Next Phase Readiness
- Phase 12.1 migration script must have been run before `terraform init` (remote state references use new keys)
- After `terraform apply`: Lambda is live at Function URL, ready to receive webhooks once secrets are populated in Phase 14
- Phase 14 will populate Secrets Manager values and update settings.py to resolve secrets at cold start

## Self-Check: PASSED

All 6 created files verified present. Both task commits (1c5991d, d1a48e7) verified in git log.

---
*Phase: 13-backend-core*
*Completed: 2026-03-02*
