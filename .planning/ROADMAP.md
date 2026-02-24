# Roadmap: Ferry

## Overview

Ferry delivers serverless AWS deployment automation through two components: a thin backend (Ferry App) that detects changes and orchestrates dispatches, and a GitHub Action (Ferry Action) that builds and deploys in the user's runner. The roadmap establishes the shared contract first, then builds the App and Action as independent vertical slices, extends to all resource types, and closes with end-to-end integration and error reporting.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation and Shared Contract** - Monorepo structure, shared Pydantic models, webhook receiver, GitHub App auth
- [x] **Phase 2: App Core Logic** - ferry.yaml parsing, change detection, dispatch triggering, PR status checks (completed 2026-02-24)
- [ ] **Phase 3: Build and Lambda Deploy** - Composite action, Magic Dockerfile, ECR push, Lambda deployment, OIDC auth
- [ ] **Phase 4: Extended Resource Types** - Step Functions and API Gateway deployment
- [ ] **Phase 5: Integration and Error Reporting** - End-to-end flow, error surfacing in PR status and workflow logs

## Phase Details

### Phase 1: Foundation and Shared Contract
**Goal**: Both components (App and Action) can be developed independently against a shared, validated data contract, with the webhook receiver accepting and deduplicating GitHub events
**Depends on**: Nothing (first phase)
**Requirements**: WHOOK-01, WHOOK-02, AUTH-01, ACT-02
**Success Criteria** (what must be TRUE):
  1. A GitHub push webhook sent to the Ferry App endpoint is validated (HMAC-SHA256) and returns 200, while a tampered request is rejected with 401
  2. Sending the same webhook delivery twice results in exactly one processing — the duplicate returns 200 but is not processed again
  3. Ferry App can generate a valid GitHub App JWT and exchange it for a scoped installation token that successfully calls the GitHub API
  4. The monorepo contains three packages (ferry-app, ferry-action, ferry-shared) managed by uv workspace, with shared Pydantic models importable by both app and action
**Plans**: 3 plans

Plans:
- [ ] 01-01-PLAN.md — Monorepo scaffolding + shared Pydantic data contract + backend settings
- [ ] 01-02-PLAN.md — Webhook signature validation + DynamoDB dedup + handler (TDD)
- [ ] 01-03-PLAN.md — GitHub App JWT generation + installation token exchange (TDD)

### Phase 2: App Core Logic
**Goal**: When a developer pushes code, Ferry App reads the repo configuration, identifies which serverless resources changed, triggers the correct dispatches, and shows affected resources on the PR before merge
**Depends on**: Phase 1
**Requirements**: CONF-01, CONF-02, DETECT-01, DETECT-02, ORCH-01, ORCH-02
**Success Criteria** (what must be TRUE):
  1. Ferry App reads and validates ferry.yaml from the user's repo at the exact pushed commit SHA — an invalid ferry.yaml produces a clear error, not a silent failure
  2. A push that changes files under a Lambda's source directory triggers a workflow_dispatch with that Lambda in the resource list, while unchanged resources are not dispatched
  3. A push affecting multiple resource types (e.g., 2 Lambdas and 1 Step Function) triggers exactly 2 dispatches — one per resource type — each with a versioned payload containing resource list, trigger SHA, deployment tag, and PR number
  4. A PR shows a GitHub Check Run listing which resources will be affected by merge, before the developer merges
**Plans**: 3 plans

Plans:
- [ ] 02-01-PLAN.md — Config loading (GitHub Contents API fetch + YAML parse) and Pydantic v2 schema validation (TDD)
- [ ] 02-02-PLAN.md — Change detection via Compare API + source_dir prefix matching + config diffing (TDD)
- [ ] 02-03-PLAN.md — Dispatch triggering + Check Run creation + handler pipeline wiring

### Phase 3: Build and Lambda Deploy
**Goal**: The Ferry Action receives a dispatch, authenticates to AWS via OIDC, builds Lambda containers with the Magic Dockerfile, pushes to ECR, and deploys Lambda functions with version and alias management
**Depends on**: Phase 1
**Requirements**: AUTH-02, BUILD-01, BUILD-02, BUILD-03, BUILD-04, BUILD-05, DEPLOY-01, DEPLOY-04, DEPLOY-05, ACT-01
**Success Criteria** (what must be TRUE):
  1. A workflow_dispatch triggers the Ferry Action, which authenticates to AWS using OIDC with a user-provided role ARN — no stored AWS credentials needed
  2. The Magic Dockerfile builds any Lambda function from just main.py + requirements.txt, supports configurable Python runtime versions, handles optional system-requirements.txt and system-config.sh without failing, and supports private GitHub repo dependencies via build secrets
  3. Built images are pushed to the correct pre-existing ECR repo with deployment tags (git SHA, PR number), and Lambda functions are updated, versioned, and aliased — with the action waiting for LastUpdateStatus: Successful before publishing
  4. When the built image digest matches the currently deployed image, deployment is skipped entirely
  5. The Ferry Action is a composite GitHub Action with Python scripts for build/deploy logic, not inline bash
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD
- [ ] 03-03: TBD

### Phase 4: Extended Resource Types
**Goal**: Ferry Action deploys Step Functions and API Gateways using the same dispatch and auth foundation as Lambda
**Depends on**: Phase 3
**Requirements**: DEPLOY-02, DEPLOY-03
**Success Criteria** (what must be TRUE):
  1. A dispatch for Step Functions updates the state machine definition with correct variable substitution for account ID and region, without corrupting JSONPath expressions or other non-variable content
  2. A dispatch for API Gateways uploads the OpenAPI spec via put-rest-api and creates a deployment to push changes to the target stage
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

### Phase 5: Integration and Error Reporting
**Goal**: The full Ferry pipeline works end-to-end (push to deploy) with build and deploy failures clearly surfaced to the developer in PR status checks and workflow logs
**Depends on**: Phase 2, Phase 4
**Requirements**: WHOOK-03
**Success Criteria** (what must be TRUE):
  1. A push that changes a Lambda source directory results in the Lambda being built, pushed to ECR, and deployed — the full pipeline from webhook to running code with no manual intervention
  2. A build failure (e.g., bad requirements.txt) surfaces as a failed GitHub Check Run on the PR and a clear error message in the GHA workflow log — the developer does not need to check CloudWatch
  3. A deploy failure (e.g., invalid Lambda handler) surfaces the same way — failed Check Run plus clear workflow log output
**Plans**: TBD

Plans:
- [ ] 05-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5
Note: Phases 2 and 3 depend only on Phase 1 and could be developed in parallel.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation and Shared Contract | 0/3 | Planned | - |
| 2. App Core Logic | 0/? | Complete    | 2026-02-24 |
| 3. Build and Lambda Deploy | 0/? | Not started | - |
| 4. Extended Resource Types | 0/? | Not started | - |
| 5. Integration and Error Reporting | 0/? | Not started | - |
