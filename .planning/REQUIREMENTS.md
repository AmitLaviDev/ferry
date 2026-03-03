# Requirements: Ferry

**Defined:** 2026-03-03
**Core Value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.

## v1.2 Requirements

Requirements for End-to-End Validation milestone. Each maps to roadmap phases.

### Infrastructure Deployment

- [ ] **INFRA-01**: All Terraform modules applied successfully (bootstrap S3, ECR, shared IAM/secrets, backend Lambda+DDB)
- [ ] **INFRA-02**: GitHub App registered with webhook URL pointing to Ferry Lambda Function URL
- [ ] **INFRA-03**: Secrets Manager populated with GitHub App private key, app ID, and webhook secret
- [ ] **INFRA-04**: Ferry Lambda responds to HTTP requests and validates webhook signatures
- [ ] **INFRA-05**: Self-deploy pipeline succeeds (push to ferry/main -> Docker build -> ECR push -> Lambda update)

### Test Environment

- [ ] **TEST-01**: Test repo created with ferry.yaml defining one hello-world Lambda resource
- [ ] **TEST-02**: Test repo contains hello-world Lambda source (main.py + requirements.txt)
- [ ] **TEST-03**: Test repo has GHA workflow that triggers ferry-action on workflow_dispatch
- [ ] **TEST-04**: ECR repo exists for test Lambda container images
- [ ] **TEST-05**: OIDC IAM role allows test repo GHA runner to deploy Lambdas + push ECR
- [ ] **TEST-06**: GitHub App installed on test repo

### End-to-End Validation

- [ ] **E2E-01**: Push to test repo triggers Ferry Lambda via webhook
- [ ] **E2E-02**: Ferry detects changed Lambda resource from ferry.yaml
- [ ] **E2E-03**: Ferry dispatches workflow_dispatch with correct payload
- [ ] **E2E-04**: GHA workflow runs and ferry-action builds container via Magic Dockerfile
- [ ] **E2E-05**: Built container pushed to ECR successfully
- [ ] **E2E-06**: Test Lambda deployed (function updated, version published, alias pointed)
- [ ] **E2E-07**: Deployed test Lambda executes correctly
- [ ] **E2E-08**: All bugs blocking the push-to-deploy loop are fixed
- [ ] **E2E-09**: Second push also triggers successful deploy (repeatable)

## v1.1 Requirements (Completed)

<details>
<summary>v1.1 Deploy to Staging -- all 17 requirements complete</summary>

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

- [x] **INFRA-v1.1-01**: Ferry Lambda deployed as arm64 container image with Function URL (auth=NONE)
- [x] **INFRA-v1.1-02**: DynamoDB dedup table with PAY_PER_REQUEST billing and TTL on expires_at
- [x] **INFRA-v1.1-03**: CloudWatch log group with 30-day retention
- [x] **INFRA-v1.1-04**: Lambda env vars reference Secrets Manager ARNs and DynamoDB table name via Terraform

### Deployment Pipeline

- [x] **DEPLOY-01**: Backend Dockerfile builds ferry-utils + ferry-backend from repo root context
- [x] **DEPLOY-02**: Self-deploy GHA workflow builds, pushes to ECR, and updates Lambda on push to main
- [x] **DEPLOY-03**: settings.py modified to load secrets from Secrets Manager at cold start

### Manual Setup

- [x] **SETUP-01**: GitHub App registered with Function URL as webhook endpoint
- [x] **SETUP-02**: Secrets Manager values populated via CLI after GitHub App registration
- [x] **SETUP-03**: Setup runbook documented in repo (apply order + manual steps)

</details>

## Future Requirements

### PR Integration (v2)

- **PR-01**: Ferry receives pull_request webhooks and detects changes
- **PR-02**: Ferry posts deploy preview as PR Check Run before merge
- **PR-03**: PR merge triggers production deploy

### Multi-Tenant (v2)

- **MT-01**: Multiple GitHub orgs can install and use Ferry
- **MT-02**: Installation-scoped config and credential management

### Extended E2E (v1.3)

- **EXT-01**: Step Functions end-to-end deploy tested with real state machine
- **EXT-02**: API Gateway end-to-end deploy tested with real API

### Monitoring (v2)

- **MON-01**: CloudWatch alarms on 5xx rate and p99 latency
- **MON-02**: X-Ray active tracing on Lambda
- **MON-03**: Reserved concurrency for blast radius control
- **MON-04**: CloudWatch dashboard (invocations, errors, duration, DynamoDB capacity)

## Out of Scope

| Feature | Reason |
|---------|--------|
| PR event handling | v2 feature -- focus on push-to-deploy loop first |
| Multi-tenant / other orgs | v2 -- prove single-tenant works first |
| Step Functions / API Gateway e2e | v1.3 -- Lambda loop is the priority |
| Environment/branch mapping | v2 -- single environment for now |
| Dashboard or UI | PR is the dashboard |
| Rollback capability | User re-deploys previous commit |
| Production environment | Staging only for this milestone |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 15 | Pending |
| INFRA-02 | Phase 15 | Pending |
| INFRA-03 | Phase 15 | Pending |
| INFRA-04 | Phase 15 | Pending |
| INFRA-05 | Phase 15 | Pending |
| TEST-01 | Phase 16 | Pending |
| TEST-02 | Phase 16 | Pending |
| TEST-03 | Phase 16 | Pending |
| TEST-04 | Phase 16 | Pending |
| TEST-05 | Phase 16 | Pending |
| TEST-06 | Phase 16 | Pending |
| E2E-01 | Phase 17 | Pending |
| E2E-02 | Phase 17 | Pending |
| E2E-03 | Phase 17 | Pending |
| E2E-04 | Phase 17 | Pending |
| E2E-05 | Phase 17 | Pending |
| E2E-06 | Phase 17 | Pending |
| E2E-07 | Phase 17 | Pending |
| E2E-08 | Phase 17 | Pending |
| E2E-09 | Phase 17 | Pending |

**Coverage:**
- v1.2 requirements: 20 total
- Mapped to phases: 20/20
- Unmapped: 0

---
*Requirements defined: 2026-03-03*
*Last updated: 2026-03-03 after roadmap creation*
