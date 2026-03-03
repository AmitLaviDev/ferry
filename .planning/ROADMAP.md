# Roadmap: Ferry

## Milestones

- ✅ **v1.0 MVP** — Phases 1-10 (shipped 2026-02-28)
- **v1.1 Deploy to Staging** — Phases 11-14 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-10) — SHIPPED 2026-02-28</summary>

- [x] Phase 1: Foundation and Shared Contract (3/3 plans) — completed 2026-02-22
- [x] Phase 2: App Core Logic (3/3 plans) — completed 2026-02-24
- [x] Phase 3: Build and Lambda Deploy (3/3 plans) — completed 2026-02-26
- [x] Phase 4: Extended Resource Types (3/3 plans) — completed 2026-02-26
- [x] ~~Phase 5: Integration and Error Reporting~~ — Superseded
- [x] Phase 6: Fix Lambda function_name Pipeline (1/1 plan) — completed 2026-02-27
- [x] Phase 7: Tech Debt Cleanup (3/3 plans) — completed 2026-02-27
- [x] Phase 8: Error Surfacing and Failure Reporting (2/2 plans) — completed 2026-02-28
- [x] Phase 9: Tech Debt Cleanup Round 2 (1/1 plan) — completed 2026-02-28
- [x] Phase 10: Docs and Dead Code Cleanup (1/1 plan) — completed 2026-02-28

Full details: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)

</details>

### v1.1 Deploy to Staging

**Milestone Goal:** Stand up Ferry's AWS infrastructure from scratch — Terraform IaC, Lambda backend, self-deploy pipeline — so we can test end-to-end and inform future milestones.

- [x] **Phase 11: Bootstrap + Global Resources** — S3 state backend, ECR repo, placeholder image (completed 2026-02-28)
- [x] **Phase 12: Shared IAM + Secrets** — Lambda execution role, OIDC provider, GHA deploy role, Secrets Manager (completed 2026-03-01)
- [x] **Phase 13: Backend Core** — Lambda + Function URL + DynamoDB dedup table + CloudWatch logs (completed 2026-03-02)
- [ ] **Phase 14: Self-Deploy + Manual Setup** — Dockerfile, GHA workflow, GitHub App registration, setup runbook

## Phase Details

### Phase 11: Bootstrap + Global Resources
**Goal**: Terraform state management and container registry exist so all subsequent IaC projects can initialize and the Lambda has an image to reference
**Depends on**: Nothing (first phase of v1.1)
**Requirements**: BOOT-01, BOOT-02, BOOT-03
**Success Criteria** (what must be TRUE):
  1. `terraform init` in any subsequent project succeeds against the S3 backend with DynamoDB locking
  2. `docker push` to the `ferry/backend` ECR repo succeeds and the lifecycle policy retains only the last 10 images
  3. A placeholder container image exists in ECR that can be referenced by a Lambda resource
**Plans**: 2 plans

**Manual Steps:**
- Have AWS account credentials configured locally before starting
- Run `scripts/bootstrap.sh` which handles: S3 bucket creation with state migration, ECR repository creation, and placeholder image build+push

Plans:
- [ ] 11-01-PLAN.md — S3 state backend + ECR repository + placeholder image TF projects
- [ ] 11-02-PLAN.md — Idempotent bootstrap script

### Phase 12: Shared IAM + Secrets
**Goal**: IAM roles and secrets infrastructure exist so the Lambda can assume its execution role and the GHA workflow can authenticate via OIDC
**Depends on**: Phase 11 (needs S3 backend for remote state)
**Requirements**: IAM-01, IAM-02, IAM-03, IAM-04
**Success Criteria** (what must be TRUE):
  1. Lambda execution role exists with least-privilege policies for DynamoDB, Secrets Manager, and CloudWatch Logs — verifiable via `aws iam simulate-principal-policy`
  2. OIDC identity provider for GitHub Actions is registered in the AWS account
  3. GHA deploy role can be assumed from a GitHub Actions workflow in the ferry repo and has ECR push + Lambda update permissions
  4. Secrets Manager contains secret containers for GitHub App credentials (app ID, private key, webhook secret) — values empty, structure exists
**Plans**: 1 plan

**Manual Steps:**
- Run `terraform apply` for the OIDC project first, then the shared project
- No secret values populated yet (that happens in Phase 14 after GitHub App registration)

Plans:
- [ ] 12-01-PLAN.md — OIDC provider (global) + shared IAM roles, policies, and Secrets Manager containers (staging)

### Phase 12.1: IaC directory restructure and state migration (INSERTED)

**Goal:** Reorganize IaC directory layout to match ConvergeBio/iac-tf conventions and migrate all Terraform remote state to new S3 keys — no new resources, pure restructure
**Depends on:** Phase 12
**Plans:** 1/1 plans complete

**Manual Steps:**
- Run `scripts/migrate-iac-layout.sh` after code changes are committed (requires AWS credentials)
- Verify each `terraform plan` shows "No changes"
- Commit the directory restructure

Plans:
- [x] 12.1-01-PLAN.md — Update TF backend keys, remote state references, and create migration script (completed 2026-03-02)

### Phase 13: Backend Core
**Goal**: Ferry Lambda is deployed and accessible via a public Function URL, with DynamoDB dedup table and structured logging, ready to receive webhooks
**Depends on**: Phase 11 (ECR placeholder image), Phase 12 (IAM role, Secrets Manager ARNs)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04
**Success Criteria** (what must be TRUE):
  1. Ferry Lambda is deployed as an arm64 container image with a publicly accessible Function URL (auth=NONE)
  2. DynamoDB dedup table exists with PAY_PER_REQUEST billing and TTL enabled on `expires_at`
  3. CloudWatch log group exists with 30-day retention and Lambda writes logs to it
  4. Lambda environment variables reference Secrets Manager ARNs and the DynamoDB table name via Terraform outputs (not hardcoded)
  5. `curl <function-url>` returns a response (even if an error, proving the Lambda is live)
**Plans**: 1 plan

**Manual Steps:**
- Run `terraform apply` for the ferry_backend project
- Note the Function URL from `terraform output` — needed for GitHub App registration in Phase 14

Plans:
- [ ] 13-01-PLAN.md — Lambda + Function URL + DynamoDB + CloudWatch Terraform project

### Phase 14: Self-Deploy + Manual Setup
**Goal**: Ferry can deploy itself on every push to main, the GitHub App is registered and receiving webhooks, and anyone can reproduce the full setup from the runbook
**Depends on**: Phase 13 (Lambda exists, Function URL known)
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03, SETUP-01, SETUP-02, SETUP-03
**Success Criteria** (what must be TRUE):
  1. `docker build` from repo root produces a working container with ferry-utils and ferry-backend installed
  2. Pushing to main triggers the self-deploy GHA workflow which builds, pushes to ECR, and updates the Lambda — verifiable in GHA workflow run logs
  3. `settings.py` loads GitHub App credentials from Secrets Manager ARNs at Lambda cold start (not from direct env var values)
  4. GitHub App is registered at github.com with the Function URL as webhook endpoint and can receive test webhook deliveries
  5. Setup runbook in the repo documents the complete apply order and all manual steps so a fresh setup can be reproduced
**Plans**: 3 plans

**Manual Steps:**
- Register GitHub App at github.com/settings/apps using the Function URL from Phase 13
- Populate Secrets Manager values via `aws secretsmanager put-secret-value` for app ID, private key, and webhook secret
- Set `AWS_DEPLOY_ROLE_ARN` repo secret in GitHub
- Trigger first deploy by pushing to main
- Verify end-to-end: webhook delivery reaches Lambda, Lambda responds

Plans:
- [ ] 14-01-PLAN.md — Backend Dockerfile + .dockerignore + settings.py Secrets Manager resolution
- [ ] 14-02-PLAN.md — Self-deploy GHA workflow (test + build + deploy)
- [ ] 14-03-PLAN.md — Setup runbook + manual setup checkpoint

## Progress

**Execution Order:** Phases 11 through 14, sequential.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation and Shared Contract | v1.0 | 3/3 | Complete | 2026-02-22 |
| 2. App Core Logic | v1.0 | 3/3 | Complete | 2026-02-24 |
| 3. Build and Lambda Deploy | v1.0 | 3/3 | Complete | 2026-02-26 |
| 4. Extended Resource Types | v1.0 | 3/3 | Complete | 2026-02-26 |
| 5. Integration and Error Reporting | v1.0 | — | Superseded | — |
| 6. Fix Lambda function_name Pipeline | v1.0 | 1/1 | Complete | 2026-02-27 |
| 7. Tech Debt Cleanup | v1.0 | 3/3 | Complete | 2026-02-27 |
| 8. Error Surfacing and Failure Reporting | v1.0 | 2/2 | Complete | 2026-02-28 |
| 9. Tech Debt Cleanup (Round 2) | v1.0 | 1/1 | Complete | 2026-02-28 |
| 10. Docs and Dead Code Cleanup | v1.0 | 1/1 | Complete | 2026-02-28 |
| 11. Bootstrap + Global Resources | 2/2 | Complete    | 2026-02-28 | — |
| 12. Shared IAM + Secrets | 1/1 | Complete    | 2026-03-01 | — |
| 12.1. IaC Directory Restructure | 1/1 | Complete    | 2026-03-02 | — |
| 13. Backend Core | 1/1 | Complete   | 2026-03-02 | — |
| 14. Self-Deploy + Manual Setup | 1/3 | In Progress|  | — |
