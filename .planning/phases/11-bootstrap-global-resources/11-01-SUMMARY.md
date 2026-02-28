---
phase: 11-bootstrap-global-resources
plan: 01
subsystem: infra
tags: [terraform, s3, ecr, docker, aws, lambda]

# Dependency graph
requires: []
provides:
  - S3 state backend TF project (iac/global/aws/backend/)
  - ECR repository TF project (iac/global/aws/ecr/)
  - Placeholder Lambda handler image source (iac/global/aws/ecr/placeholder/)
affects: [11-02-bootstrap-script, 12-iam-oidc, 13-app-infrastructure, 14-deploy-pipeline]

# Tech tracking
tech-stack:
  added: [terraform ~> 1.14, aws-provider ~> 6.0]
  patterns: [s3-backend-with-use-lockfile, convergebio-file-split, separate-s3-bucket-resources]

key-files:
  created:
    - iac/global/aws/backend/providers.tf
    - iac/global/aws/backend/main.tf
    - iac/global/aws/backend/variables.tf
    - iac/global/aws/backend/outputs.tf
    - iac/global/aws/ecr/providers.tf
    - iac/global/aws/ecr/main.tf
    - iac/global/aws/ecr/variables.tf
    - iac/global/aws/ecr/outputs.tf
    - iac/global/aws/ecr/placeholder/Dockerfile
    - iac/global/aws/ecr/placeholder/app.py
  modified: []

key-decisions:
  - "No assume_role in global bootstrap projects -- ambient credentials for one-time setup"
  - "Simple provider block with default_tags (ManagedBy + Project) instead of per-resource tags"
  - "aws_caller_identity data source for account ID in ECR outputs (no hardcoded IDs)"

patterns-established:
  - "ConvergeBio file-split: providers.tf, main.tf, variables.tf, outputs.tf per TF project"
  - "S3 backend with use_lockfile = true (no DynamoDB lock table)"
  - "Separate S3 bucket resources for versioning/encryption/public-access (AWS provider v4+ pattern)"
  - "default_tags on provider for ManagedBy and Project tags"

requirements-completed: [BOOT-01, BOOT-02, BOOT-03]

# Metrics
duration: 1min
completed: 2026-02-28
---

# Phase 11 Plan 01: Terraform Projects Summary

**S3 state backend with versioning/encryption/locking and ECR repo with lifecycle policy plus placeholder Lambda image**

## Performance

- **Duration:** 1 min
- **Started:** 2026-02-28T17:36:12Z
- **Completed:** 2026-02-28T17:37:33Z
- **Tasks:** 2
- **Files modified:** 10 created, 1 deleted (.gitkeep)

## Accomplishments
- S3 state bucket TF project with versioning, KMS encryption, and public access block as separate resources
- ECR repository TF project with scan-on-push and lifecycle policy keeping last 10 images
- Placeholder Lambda handler image source (Python 3.14 base, hello-world handler returning health check JSON)
- Both projects share consistent S3 backend config pointing to ferry-terraform-state with use_lockfile

## Task Commits

Each task was committed atomically:

1. **Task 1: Create S3 state backend Terraform project** - `c6958a9` (feat)
2. **Task 2: Create ECR Terraform project and placeholder image** - `1b29874` (feat)

## Files Created/Modified
- `iac/global/aws/backend/providers.tf` - Terraform config with S3 backend, use_lockfile, AWS provider ~> 6.0
- `iac/global/aws/backend/main.tf` - S3 bucket + versioning + encryption + public access block
- `iac/global/aws/backend/variables.tf` - bucket_name (ferry-terraform-state) and region (us-east-1)
- `iac/global/aws/backend/outputs.tf` - Bucket ARN, name, and region outputs
- `iac/global/aws/ecr/providers.tf` - Terraform config with S3 backend for ECR state
- `iac/global/aws/ecr/main.tf` - ECR repo + lifecycle policy (keep last 10 images)
- `iac/global/aws/ecr/variables.tf` - repository_name (lambda-ferry-backend) and region
- `iac/global/aws/ecr/outputs.tf` - Repository URL, ARN, name, and registry ID
- `iac/global/aws/ecr/placeholder/Dockerfile` - Minimal Lambda container from public.ecr.aws/lambda/python:3.14
- `iac/global/aws/ecr/placeholder/app.py` - Hello-world handler returning JSON health check

## Decisions Made
- No assume_role in global bootstrap projects; they use ambient credentials since the assume-role target may not exist yet during initial bootstrap
- Used default_tags on the AWS provider for ManagedBy and Project tags, with only resource-specific tags (Name, Purpose) on individual resources
- Used aws_caller_identity data source for account ID in ECR outputs instead of hardcoding

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Both Terraform projects are ready for the bootstrap script (Plan 02) to apply
- S3 backend project includes bootstrap instructions as comments in providers.tf
- ECR project references the same S3 state bucket created by the backend project
- Placeholder image source is ready for docker build with --platform linux/arm64

## Self-Check: PASSED

All 10 created files verified present. Both task commits (c6958a9, 1b29874) verified in git log. No missing items.

---
*Phase: 11-bootstrap-global-resources*
*Completed: 2026-02-28*
