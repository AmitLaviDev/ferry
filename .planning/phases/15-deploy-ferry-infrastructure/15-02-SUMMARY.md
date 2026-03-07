---
phase: 15-deploy-ferry-infrastructure
plan: 02
status: complete
started: 2026-03-03
completed: 2026-03-03
---

## Summary

Registered Ferry GitHub App, populated Secrets Manager with real credentials, set Installation ID via Terraform, configured AWS_DEPLOY_ROLE_ARN repo secret.

## Tasks Completed

| # | Task | Status |
|---|------|--------|
| 1 | Register GitHub App with Lambda Function URL as webhook endpoint | Done |
| 2 | Populate Secrets Manager (App ID, private key, webhook secret) | Done |
| 3 | Set Installation ID in terraform.tfvars and re-apply | Done |
| 4 | Set AWS_DEPLOY_ROLE_ARN repo secret | Done |

## Key Outcomes

- GitHub App registered with correct permissions (Contents:Read, PRs:R&W, Checks:R&W, Actions:Write)
- App subscribed to Push events
- App installed on ferry repo
- All three Secrets Manager values populated
- Lambda has FERRY_INSTALLATION_ID set
- GHA repo secret configured for OIDC deployment

## Self-Check: PASSED
