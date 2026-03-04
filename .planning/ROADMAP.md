# Roadmap: Ferry

## Milestones

- v1.0 MVP -- Phases 1-10 (shipped 2026-02-28)
- v1.1 Deploy to Staging -- Phases 11-14 (shipped 2026-03-03)
- **v1.2 End-to-End Validation** -- Phases 15-17 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-10) -- SHIPPED 2026-02-28</summary>

- [x] Phase 1: Foundation and Shared Contract (3/3 plans) -- completed 2026-02-22
- [x] Phase 2: App Core Logic (3/3 plans) -- completed 2026-02-24
- [x] Phase 3: Build and Lambda Deploy (3/3 plans) -- completed 2026-02-26
- [x] Phase 4: Extended Resource Types (3/3 plans) -- completed 2026-02-26
- [x] ~~Phase 5: Integration and Error Reporting~~ -- Superseded
- [x] Phase 6: Fix Lambda function_name Pipeline (1/1 plan) -- completed 2026-02-27
- [x] Phase 7: Tech Debt Cleanup (3/3 plans) -- completed 2026-02-27
- [x] Phase 8: Error Surfacing and Failure Reporting (2/2 plans) -- completed 2026-02-28
- [x] Phase 9: Tech Debt Cleanup Round 2 (1/1 plan) -- completed 2026-02-28
- [x] Phase 10: Docs and Dead Code Cleanup (1/1 plan) -- completed 2026-02-28

Full details: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)

</details>

<details>
<summary>v1.1 Deploy to Staging (Phases 11-14) -- SHIPPED 2026-03-03</summary>

- [x] **Phase 11: Bootstrap + Global Resources** -- S3 state backend, ECR repo, placeholder image (completed 2026-02-28)
- [x] **Phase 12: Shared IAM + Secrets** -- Lambda execution role, OIDC provider, GHA deploy role, Secrets Manager (completed 2026-03-01)
- [x] **Phase 12.1: IaC Directory Restructure** -- Layout migration and state key updates (completed 2026-03-02)
- [x] **Phase 13: Backend Core** -- Lambda + Function URL + DynamoDB dedup table + CloudWatch logs (completed 2026-03-02)
- [x] **Phase 14: Self-Deploy + Manual Setup** -- Dockerfile, GHA workflow, GitHub App registration, setup runbook (completed 2026-03-03)

</details>

### v1.2 End-to-End Validation

**Milestone Goal:** Deploy Ferry infrastructure, prove the full push-to-deploy loop works end-to-end with a real test repo, and fix all bugs found.

- [x] **Phase 15: Deploy Ferry Infrastructure** -- Apply all Terraform modules, register GitHub App, verify Lambda is live and self-deploy works (completed 2026-03-04)
- [ ] **Phase 16: Provision Test Environment** -- Create test repo with ferry.yaml + hello-world Lambda + GHA workflow, set up ECR + OIDC for test repo
- [ ] **Phase 17: End-to-End Loop Validation** -- Push to test repo, verify full loop works, fix bugs, prove repeatability

## Phase Details

<details>
<summary>v1.0 Phase Details (Phases 1-10)</summary>

See [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)

</details>

<details>
<summary>v1.1 Phase Details (Phases 11-14)</summary>

### Phase 11: Bootstrap + Global Resources
**Goal**: Terraform state management and container registry exist so all subsequent IaC projects can initialize and the Lambda has an image to reference
**Depends on**: Nothing (first phase of v1.1)
**Requirements**: BOOT-01, BOOT-02, BOOT-03
**Success Criteria** (what must be TRUE):
  1. `terraform init` in any subsequent project succeeds against the S3 backend with DynamoDB locking
  2. `docker push` to the `ferry/backend` ECR repo succeeds and the lifecycle policy retains only the last 10 images
  3. A placeholder container image exists in ECR that can be referenced by a Lambda resource
**Plans**: 2 plans

Plans:
- [x] 11-01-PLAN.md -- S3 state backend + ECR repository + placeholder image TF projects
- [x] 11-02-PLAN.md -- Idempotent bootstrap script

### Phase 12: Shared IAM + Secrets
**Goal**: IAM roles and secrets infrastructure exist so the Lambda can assume its execution role and the GHA workflow can authenticate via OIDC
**Depends on**: Phase 11 (needs S3 backend for remote state)
**Requirements**: IAM-01, IAM-02, IAM-03, IAM-04
**Success Criteria** (what must be TRUE):
  1. Lambda execution role exists with least-privilege policies for DynamoDB, Secrets Manager, and CloudWatch Logs
  2. OIDC identity provider for GitHub Actions is registered in the AWS account
  3. GHA deploy role can be assumed from a GitHub Actions workflow in the ferry repo and has ECR push + Lambda update permissions
  4. Secrets Manager contains secret containers for GitHub App credentials (app ID, private key, webhook secret)
**Plans**: 1 plan

Plans:
- [x] 12-01-PLAN.md -- OIDC provider (global) + shared IAM roles, policies, and Secrets Manager containers (staging)

### Phase 12.1: IaC Directory Restructure (INSERTED)
**Goal**: Reorganize IaC directory layout to match ConvergeBio/iac-tf conventions and migrate all Terraform remote state to new S3 keys
**Depends on**: Phase 12
**Plans**: 1 plan

Plans:
- [x] 12.1-01-PLAN.md -- Update TF backend keys, remote state references, and create migration script (completed 2026-03-02)

### Phase 13: Backend Core
**Goal**: Ferry Lambda is deployed and accessible via a public Function URL, with DynamoDB dedup table and structured logging, ready to receive webhooks
**Depends on**: Phase 11 (ECR placeholder image), Phase 12 (IAM role, Secrets Manager ARNs)
**Requirements**: INFRA-v1.1-01, INFRA-v1.1-02, INFRA-v1.1-03, INFRA-v1.1-04
**Success Criteria** (what must be TRUE):
  1. Ferry Lambda is deployed as an arm64 container image with a publicly accessible Function URL (auth=NONE)
  2. DynamoDB dedup table exists with PAY_PER_REQUEST billing and TTL enabled on `expires_at`
  3. CloudWatch log group exists with 30-day retention and Lambda writes logs to it
  4. Lambda environment variables reference Secrets Manager ARNs and the DynamoDB table name via Terraform outputs
  5. `curl <function-url>` returns a response (even if an error, proving the Lambda is live)
**Plans**: 1 plan

Plans:
- [x] 13-01-PLAN.md -- Lambda + Function URL + DynamoDB + CloudWatch Terraform project

### Phase 14: Self-Deploy + Manual Setup
**Goal**: Ferry can deploy itself on every push to main, the GitHub App is registered and receiving webhooks, and anyone can reproduce the full setup from the runbook
**Depends on**: Phase 13 (Lambda exists, Function URL known)
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03, SETUP-01, SETUP-02, SETUP-03
**Success Criteria** (what must be TRUE):
  1. `docker build` from repo root produces a working container with ferry-utils and ferry-backend installed
  2. Pushing to main triggers the self-deploy GHA workflow which builds, pushes to ECR, and updates the Lambda
  3. `settings.py` loads GitHub App credentials from Secrets Manager ARNs at Lambda cold start
  4. GitHub App is registered at github.com with the Function URL as webhook endpoint and can receive test webhook deliveries
  5. Setup runbook in the repo documents the complete apply order and all manual steps so a fresh setup can be reproduced
**Plans**: 3 plans

Plans:
- [x] 14-01-PLAN.md -- Backend Dockerfile + .dockerignore + settings.py Secrets Manager resolution
- [x] 14-02-PLAN.md -- Self-deploy GHA workflow (test + build + deploy)
- [x] 14-03-PLAN.md -- Setup runbook + manual setup checkpoint

</details>

### Phase 15: Deploy Ferry Infrastructure
**Goal**: All Ferry AWS infrastructure is live and operational -- Terraform applied, GitHub App registered, secrets populated, Lambda responding to HTTP requests, and self-deploy pipeline proven
**Depends on**: Phase 14 (IaC code and runbook exist from v1.1)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05
**Success Criteria** (what must be TRUE):
  1. All four Terraform projects applied successfully (bootstrap, ECR, shared IAM/secrets, backend) with `terraform plan` showing no pending changes
  2. GitHub App is registered at github.com with the Ferry Lambda Function URL as its webhook endpoint
  3. Secrets Manager contains valid GitHub App credentials (app ID, private key, webhook secret) and the Lambda can read them at cold start
  4. Sending a test webhook from the GitHub App settings page returns a 200 response from the Ferry Lambda
  5. Pushing a commit to ferry/main triggers the self-deploy workflow, which builds the Docker image, pushes to ECR, and updates the Lambda successfully
**Plans**: 3 plans

Plans:
- [x] 15-01-PLAN.md -- Terraform apply chain (bootstrap + OIDC + shared + backend) and resource verification
- [x] 15-02-PLAN.md -- GitHub App registration, secrets population, installation ID, and repo secret
- [x] 15-03-PLAN.md -- Lambda liveness verification, webhook delivery test, and self-deploy pipeline proof

**Manual Steps:**
- Follow the setup runbook from Phase 14 (`docs/setup-runbook.md`)
- Run `terraform init && terraform apply` for each IaC project in dependency order
- Register GitHub App at github.com/settings/apps with correct webhook URL and permissions
- Populate Secrets Manager values via `aws secretsmanager put-secret-value`
- Set `AWS_DEPLOY_ROLE_ARN` as a GitHub repo secret
- Trigger and verify the self-deploy pipeline by pushing to main

### Phase 16: Provision Test Environment
**Goal**: A test repo exists with everything needed to exercise the full Ferry push-to-deploy loop -- ferry.yaml, hello-world Lambda source, GHA dispatch workflow, ECR repo, OIDC role, and the GitHub App installed
**Depends on**: Phase 15 (Ferry infrastructure must be live to install the App)
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06
**Success Criteria** (what must be TRUE):
  1. Test repo on GitHub contains a `ferry.yaml` that defines one Lambda resource pointing to a hello-world source directory
  2. The hello-world Lambda source exists in the test repo (main.py with a handler that returns a greeting + requirements.txt) and can be built with the Magic Dockerfile
  3. Test repo has a `.github/workflows/ferry-deploy.yml` that triggers on `workflow_dispatch` and calls ferry-action with the correct inputs
  4. An ECR repository exists for the test Lambda and the test repo's GHA runner can push images to it via an OIDC IAM role
  5. The Ferry GitHub App is installed on the test repo and the test repo appears in the App's installation list

**Manual Steps:**
- Create a new GitHub repo (or use an existing test org repo)
- Create ECR repo for the test Lambda in AWS
- Create OIDC IAM role allowing the test repo's GHA runners to push ECR + deploy Lambdas
- Create the hello-world Lambda function in AWS (so there is something to deploy to)
- Install the Ferry GitHub App on the test repo
- Set required repo secrets (AWS role ARN) on the test repo

### Phase 17: End-to-End Loop Validation
**Goal**: The full push-to-deploy loop works reliably -- a push to the test repo triggers Ferry, which detects changes, dispatches a workflow, builds the container, deploys the Lambda, and the deployed Lambda executes correctly -- and this is repeatable
**Depends on**: Phase 16 (test environment fully provisioned)
**Requirements**: E2E-01, E2E-02, E2E-03, E2E-04, E2E-05, E2E-06, E2E-07, E2E-08, E2E-09
**Success Criteria** (what must be TRUE):
  1. Pushing a code change to the test repo triggers the Ferry Lambda via webhook, which detects the changed Lambda resource and dispatches a `workflow_dispatch` event to the test repo
  2. The dispatched GHA workflow runs ferry-action, which builds the hello-world container via the Magic Dockerfile and pushes it to ECR
  3. ferry-action deploys the test Lambda (updates function code, publishes a version, points the alias) and the deployment completes without errors
  4. Invoking the deployed test Lambda returns the expected hello-world response, proving the built container works in production
  5. A second push with a code change also triggers a successful deploy, proving the loop is repeatable and not dependent on first-run conditions

**Iterative Bug Fix Cycle:**
- Each step of the loop (webhook receipt, change detection, dispatch, build, push, deploy) is a potential failure point
- When a step fails: diagnose from CloudWatch logs / GHA workflow logs, fix the bug in ferry code, push the fix (which self-deploys), retry
- E2E-08 (all blocking bugs fixed) is satisfied when criteria 1-4 pass without manual intervention
- Known bug to watch for: `find_open_prs` in checks/runs.py crashes on 403 response

## Progress

**Execution Order:** Phases 15 through 17, sequential.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation and Shared Contract | v1.0 | 3/3 | Complete | 2026-02-22 |
| 2. App Core Logic | v1.0 | 3/3 | Complete | 2026-02-24 |
| 3. Build and Lambda Deploy | v1.0 | 3/3 | Complete | 2026-02-26 |
| 4. Extended Resource Types | v1.0 | 3/3 | Complete | 2026-02-26 |
| 5. Integration and Error Reporting | v1.0 | -- | Superseded | -- |
| 6. Fix Lambda function_name Pipeline | v1.0 | 1/1 | Complete | 2026-02-27 |
| 7. Tech Debt Cleanup | v1.0 | 3/3 | Complete | 2026-02-27 |
| 8. Error Surfacing and Failure Reporting | v1.0 | 2/2 | Complete | 2026-02-28 |
| 9. Tech Debt Cleanup (Round 2) | v1.0 | 1/1 | Complete | 2026-02-28 |
| 10. Docs and Dead Code Cleanup | v1.0 | 1/1 | Complete | 2026-02-28 |
| 11. Bootstrap + Global Resources | v1.1 | 2/2 | Complete | 2026-02-28 |
| 12. Shared IAM + Secrets | v1.1 | 1/1 | Complete | 2026-03-01 |
| 12.1. IaC Directory Restructure | v1.1 | 1/1 | Complete | 2026-03-02 |
| 13. Backend Core | v1.1 | 1/1 | Complete | 2026-03-02 |
| 14. Self-Deploy + Manual Setup | v1.1 | 3/3 | Complete | 2026-03-03 |
| 15. Deploy Ferry Infrastructure | v1.2 | 3/3 | Complete | 2026-03-04 |
| 16. Provision Test Environment | v1.2 | 0/TBD | Not started | -- |
| 17. End-to-End Loop Validation | v1.2 | 0/TBD | Not started | -- |
