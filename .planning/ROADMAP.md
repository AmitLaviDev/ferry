# Roadmap: Ferry

## Overview

Ferry delivers serverless AWS deployment automation through two components: a thin backend (Ferry App) that detects changes and orchestrates dispatches, and a GitHub Action (Ferry Action) that builds and deploys in the user's runner. The roadmap establishes the shared contract first, then builds the App and Action as independent vertical slices, extends to all resource types, and closes with end-to-end integration and error reporting.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation and Shared Contract** - Monorepo structure, shared Pydantic models, webhook receiver, GitHub App auth
- [x] **Phase 2: App Core Logic** - ferry.yaml parsing, change detection, dispatch triggering, PR status checks (completed 2026-02-24)
- [x] **Phase 3: Build and Lambda Deploy** - Composite action, Magic Dockerfile, ECR push, Lambda deployment, OIDC auth
- [x] **Phase 4: Extended Resource Types** - Step Functions and API Gateway deployment (completed 2026-02-26)
- [x] ~~**Phase 5: Integration and Error Reporting**~~ - *Superseded: E2E flows verified by Phases 1-4+6; error surfacing moved to Phase 8*
- [x] **Phase 6: Fix Lambda function_name Pipeline** - Close DEPLOY-01 integration break (function_name dropped in dispatch pipeline) (completed 2026-02-27)
- [x] **Phase 7: Tech Debt Cleanup** - Resolve inconsistent defaults, add workflow docs, fix SUMMARY frontmatter (completed 2026-02-27)
- [ ] **Phase 8: Error Surfacing and Failure Reporting** - Close WHOOK-03: surface build/deploy failures in PR status checks and workflow logs
- [ ] **Phase 9: Tech Debt Cleanup (Round 2)** - Resolve remaining low-severity tech debt from second audit

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
**Plans**: 3 plans

Plans:
- [ ] 03-01-PLAN.md — Three-action scaffolding (setup/build/deploy action.yml) + payload parsing + OIDC auth + GHA helpers
- [ ] 03-02-PLAN.md — Magic Dockerfile + Docker build + ECR push logic (TDD)
- [ ] 03-03-PLAN.md — Lambda deploy + version/alias management + digest-based skip (TDD)

### Phase 4: Extended Resource Types
**Goal**: Ferry Action deploys Step Functions and API Gateways using the same dispatch and auth foundation as Lambda
**Depends on**: Phase 3
**Requirements**: DEPLOY-02, DEPLOY-03
**Success Criteria** (what must be TRUE):
  1. A dispatch for Step Functions updates the state machine definition with correct variable substitution for account ID and region, without corrupting JSONPath expressions or other non-variable content
  2. A dispatch for API Gateways uploads the OpenAPI spec via put-rest-api and creates a deployment to push changes to the target stage
**Plans**: 3 plans

Plans:
- [x] 04-01-PLAN.md — Shared utilities (envsubst, content hash) + config/dispatch model updates for SF/APGW fields
- [x] 04-02-PLAN.md — Step Functions deploy module with envsubst, content-hash skip, version publishing (TDD)
- [x] 04-03-PLAN.md — API Gateway deploy module with spec parsing, field stripping, content-hash skip (TDD)

### Phase 5: Integration and Error Reporting *(SUPERSEDED)*
**Status:** Superseded — E2E flows verified by Phases 1-4+6. Error surfacing (WHOOK-03) moved to Phase 8.
**Original Goal**: The full Ferry pipeline works end-to-end (push to deploy) with build and deploy failures clearly surfaced
**Requirements**: WHOOK-03 → reassigned to Phase 8

### Phase 6: Fix Lambda function_name Pipeline
**Goal:** Lambda `function_name` flows correctly from `ferry.yaml` through the dispatch pipeline to the deploy action, closing the DEPLOY-01 integration break
**Depends on**: Phase 3
**Requirements**: DEPLOY-01
**Gap Closure:** Closes gaps from audit — DEPLOY-01 partial, integration (Phase 2→3), flow (Lambda E2E deploy)
**Success Criteria** (what must be TRUE):
  1. `LambdaResource` model includes `function_name` field that carries through from `LambdaConfig`
  2. `_build_resource` in `trigger.py` passes `function_name` when constructing `LambdaResource`
  3. `parse_payload.py` includes `function_name` in the GHA matrix output for Lambda resources
  4. `deploy.py` receives `INPUT_FUNCTION_NAME` env var from the matrix and deploys to the correct function
**Plans**: 1 plan

Plans:
- [x] 06-01-PLAN.md — Wire function_name through dispatch pipeline (model + trigger + matrix + deploy error handling + tests)

### Phase 7: Tech Debt Cleanup
**Goal:** Resolve low-severity tech debt items identified by the milestone audit
**Depends on**: Phase 6
**Requirements**: None (tech debt)
**Gap Closure:** Closes tech debt items from audit
**Success Criteria** (what must be TRUE):
  1. Runtime default is consistent — `LambdaConfig.runtime` and `parse_payload.py` use the same default value
  2. User-facing documentation exists for workflow file naming convention (`ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`)
  3. SUMMARY.md files include `requirements-completed` frontmatter field for 3-source cross-reference
**Plans**: 3 plans

Plans:
- [ ] 07-01-PLAN.md — Wire runtime end-to-end through dispatch pipeline, unify defaults to python3.14
- [ ] 07-02-PLAN.md — Create user-facing workflow documentation (docs/ directory with 4 guides)
- [ ] 07-03-PLAN.md — Fix SUMMARY frontmatter mismatch + codebase sweep for stale references

### Phase 8: Error Surfacing and Failure Reporting
**Goal:** Build and deploy failures are clearly surfaced to developers in PR status checks and GHA workflow logs — no silent failures, no need to check CloudWatch
**Depends on**: Phase 2, Phase 6
**Requirements**: WHOOK-03
**Gap Closure:** Closes WHOOK-03 gap from audit (Phase 5 never executed)
**Success Criteria** (what must be TRUE):
  1. Auth failures (bad JWT, expired token, invalid installation) in the backend handler produce a structured error response and log — not an unstructured Lambda 500
  2. Invalid ferry.yaml on the default branch after merge produces a clear error in logs — not a silent HTTP 200
  3. A build failure (e.g., bad requirements.txt) surfaces as a failed GitHub Check Run on the PR and a clear error message in the GHA workflow log
  4. A deploy failure (e.g., invalid Lambda handler) surfaces the same way — failed Check Run plus clear workflow log output
**Plans**: TBD

Plans:
- [ ] 08-01: TBD

### Phase 9: Tech Debt Cleanup (Round 2)
**Goal:** Resolve remaining low-severity tech debt items identified by the second milestone audit
**Depends on**: Phase 8
**Requirements**: None (tech debt)
**Gap Closure:** Closes tech debt items from second audit
**Success Criteria** (what must be TRUE):
  1. `build_matrix` docstring in parse_payload.py includes `function_name` in the lambda field list
  2. `PushEvent` and `WebhookHeaders` are either consumed in production code or removed from exports
  3. `tenacity>=8.3` phantom dependency removed from backend/pyproject.toml
  4. `PyYAML>=6.0.1` dependency moved from utils to backend pyproject.toml (where YAML parsing actually happens)
  5. `moto` extras include `stepfunctions` in root pyproject.toml
**Plans**: TBD

Plans:
- [ ] 09-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5(superseded) → 6 → 7 → 8 → 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation and Shared Contract | 3/3 | Complete | 2026-02-22 |
| 2. App Core Logic | 3/3 | Complete | 2026-02-24 |
| 3. Build and Lambda Deploy | 3/3 | Complete | 2026-02-26 |
| 4. Extended Resource Types | 3/3 | Complete | 2026-02-26 |
| 5. Integration and Error Reporting | — | Superseded | — |
| 6. Fix Lambda function_name Pipeline | 1/1 | Complete | 2026-02-27 |
| 7. Tech Debt Cleanup | 3/3 | Complete | 2026-02-27 |
| 8. Error Surfacing and Failure Reporting | 0/? | Not started | - |
| 9. Tech Debt Cleanup (Round 2) | 0/? | Not started | - |
