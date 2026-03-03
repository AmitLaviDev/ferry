# Requirements: Ferry v1.1 — Deploy to Staging

**Defined:** 2026-02-28
**Core Value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed — with full visibility on the PR before merge.

## v1.1 Requirements

Requirements for deploying Ferry to its own AWS account. Each maps to roadmap phases.

### Bootstrap

- [x] **BOOT-01**: Terraform state stored in S3 with DynamoDB locking in Ferry's AWS account
- [x] **BOOT-02**: ECR repository (`ferry/backend`) exists with lifecycle policy (keep last 10 images)
- [x] **BOOT-03**: Placeholder container image pushed to ECR to unblock Lambda creation

### Shared Infrastructure

- [x] **IAM-01**: Lambda execution role with least-privilege policies (DynamoDB, Secrets Manager, CloudWatch Logs)
- [x] **IAM-02**: OIDC identity provider for GitHub Actions in Ferry AWS account
- [x] **IAM-03**: GHA deploy role with ECR push + Lambda update permissions, scoped to ferry repo
- [x] **IAM-04**: Secrets Manager secret containers for GitHub App credentials (app ID, private key, webhook secret)

### Backend Infrastructure

- [x] **INFRA-01**: Ferry Lambda deployed as arm64 container image with Function URL (auth=NONE)
- [x] **INFRA-02**: DynamoDB dedup table with PAY_PER_REQUEST billing and TTL on expires_at
- [x] **INFRA-03**: CloudWatch log group with 30-day retention
- [x] **INFRA-04**: Lambda env vars reference Secrets Manager ARNs and DynamoDB table name via Terraform

### Deployment Pipeline

- [x] **DEPLOY-01**: Backend Dockerfile builds ferry-utils + ferry-backend from repo root context
- [ ] **DEPLOY-02**: Self-deploy GHA workflow builds, pushes to ECR, and updates Lambda on push to main
- [x] **DEPLOY-03**: settings.py modified to load secrets from Secrets Manager at cold start

### Manual Setup

- [ ] **SETUP-01**: GitHub App registered with Function URL as webhook endpoint
- [ ] **SETUP-02**: Secrets Manager values populated via CLI after GitHub App registration
- [ ] **SETUP-03**: Setup runbook documented in repo (apply order + manual steps)

## Manual Action Timeline

Manual steps mapped to when they happen relative to phases:

| When | Action | Blocks |
|------|--------|--------|
| **Before Phase 11** | Have AWS account credentials ready | Everything |
| **Phase 11** | `terraform apply` locally (bootstrap S3), then `terraform init -migrate-state` | All subsequent TF projects |
| **Phase 11** | `terraform apply` for ECR, then pull+tag+push placeholder image | Lambda creation (Phase 13) |
| **After Phase 13** | Note Function URL from `terraform output` | GitHub App registration |
| **Phase 14** | Register GitHub App at github.com using Function URL | Webhook delivery |
| **Phase 14** | `aws secretsmanager put-secret-value` for app ID, private key, webhook secret | Lambda functionality |
| **Phase 14** | Trigger first deploy (push to main) | End-to-end verification |

## v2 Requirements

Deferred operational features (not in current roadmap).

### Monitoring

- **MON-01**: CloudWatch alarms on 5xx rate and p99 latency
- **MON-02**: X-Ray active tracing on Lambda
- **MON-03**: Reserved concurrency (10-25) for blast radius control
- **MON-04**: CloudWatch dashboard (invocations, errors, duration, DynamoDB capacity)

### Production Readiness

- **PROD-01**: Production environment (`iac/teams/platform/aws/prod/`)
- **PROD-02**: Custom domain with CloudFront + ACM + Route53
- **PROD-03**: Lambda provisioned concurrency for consistent cold starts

## Out of Scope

| Feature | Reason |
|---------|--------|
| API Gateway | Function URL is free and sufficient; HMAC auth handled in app code |
| VPC configuration | Lambda accesses all services via public endpoints; VPC adds cold start + NAT cost |
| Secrets Manager Lambda Extension | Direct env var approach from TF data sources is simpler and sufficient for staging |
| DLQ | Function URL invocations are synchronous; DLQ only applies to async |
| KMS Customer Managed Keys | Default AWS encryption sufficient for staging |
| Terraform modules (terraform-aws-modules) | Raw resources preferred — only 5-6 AWS resources, modules add abstraction overhead |
| Multi-environment in this milestone | Staging only; prod environment deferred to v1.2+ |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| BOOT-01 | Phase 11 | Complete |
| BOOT-02 | Phase 11 | Complete |
| BOOT-03 | Phase 11 | Complete |
| IAM-01 | Phase 12 | Complete |
| IAM-02 | Phase 12 | Complete |
| IAM-03 | Phase 12 | Complete |
| IAM-04 | Phase 12 | Complete |
| INFRA-01 | Phase 13 | Complete |
| INFRA-02 | Phase 13 | Complete |
| INFRA-03 | Phase 13 | Complete |
| INFRA-04 | Phase 13 | Complete |
| DEPLOY-01 | Phase 14 | Complete |
| DEPLOY-02 | Phase 14 | Pending |
| DEPLOY-03 | Phase 14 | Complete |
| SETUP-01 | Phase 14 | Pending |
| SETUP-02 | Phase 14 | Pending |
| SETUP-03 | Phase 14 | Pending |

**Coverage:**
- v1.1 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0

---
*Requirements defined: 2026-02-28*
*Last updated: 2026-02-28 after roadmap creation*
