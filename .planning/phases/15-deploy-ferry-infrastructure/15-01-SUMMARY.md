---
phase: 15-deploy-ferry-infrastructure
plan: 01
status: complete
started: 2026-03-03
completed: 2026-03-03
---

## Summary

Applied all five Terraform projects in dependency order. All AWS resources created: S3 state bucket, ECR repo with placeholder image, OIDC provider, IAM roles, Secrets Manager containers, Lambda with Function URL, DynamoDB dedup table.

## Tasks Completed

| # | Task | Status |
|---|------|--------|
| 1 | Apply Terraform projects (bootstrap + 3 manual) | Done |
| 2 | Verify all resources exist | Done |

## Key Outcomes

- S3 state bucket `ferry-global-terraform-state` holding state for all projects
- ECR repo `lambda-ferry-backend` with placeholder image
- OIDC identity provider registered for GitHub Actions
- IAM roles: `ferry-lambda-execution`, `ferry-gha-self-deploy`, `ferry-gha-dispatch`
- Secrets Manager containers for GitHub App credentials
- Lambda `ferry-backend` deployed with public Function URL
- DynamoDB table `ferry-webhook-dedup` with TTL

## Self-Check: PASSED
