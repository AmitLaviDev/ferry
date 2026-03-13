# Roadmap: Ferry

## Milestones

- v1.0 MVP -- Phases 1-10 (shipped 2026-02-28)
- v1.1 Deploy to Staging -- Phases 11-14 (shipped 2026-03-03)
- v1.2 End-to-End Validation -- Phases 15-17 (shipped 2026-03-08)
- v1.3 Full-Chain E2E -- Phases 18-21 (shipped 2026-03-10)
- v1.4 Unified Workflow -- Phases 22-24 (shipped 2026-03-10)
- v1.5 Batched Dispatch -- Phases 25-28 (shipped 2026-03-11)
- v2.0 PR Integration -- Phases 29-35 (in progress)

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

- [x] Phase 11: Bootstrap + Global Resources (2/2 plans) -- completed 2026-02-28
- [x] Phase 12: Shared IAM + Secrets (1/1 plan) -- completed 2026-03-01
- [x] Phase 12.1: IaC Directory Restructure (1/1 plan) -- completed 2026-03-02
- [x] Phase 13: Backend Core (1/1 plan) -- completed 2026-03-02
- [x] Phase 14: Self-Deploy + Manual Setup (3/3 plans) -- completed 2026-03-03

Full details: [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)

</details>

<details>
<summary>v1.2 End-to-End Validation (Phases 15-17) -- SHIPPED 2026-03-08</summary>

- [x] Phase 15: Deploy Ferry Infrastructure (3/3 plans) -- completed 2026-03-04
- [x] Phase 16: Provision Test Environment (3/3 plans) -- completed 2026-03-07
- [x] Phase 17: End-to-End Loop Validation (3/3 plans) -- completed 2026-03-08

Full details: [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)

</details>

<details>
<summary>v1.3 Full-Chain E2E (Phases 18-21) -- SHIPPED 2026-03-10</summary>

- [x] Phase 18: Tech Debt Cleanup (2/2 plans) -- completed 2026-03-08
- [x] Phase 19: Test Infrastructure for SF + APGW (1/1 plan) -- completed 2026-03-08
- [x] Phase 20: Test Repo Updates (1/1 plan) -- completed 2026-03-09
- [x] Phase 21: Full-Chain E2E Validation (3/3 plans) -- completed 2026-03-10

Full details: [milestones/v1.3-ROADMAP.md](milestones/v1.3-ROADMAP.md)

</details>

<details>
<summary>v1.4 Unified Workflow (Phases 22-24) -- SHIPPED 2026-03-10</summary>

- [x] Phase 22: Backend and Action Code Changes (1/1 plan) -- completed 2026-03-10
- [x] Phase 23: Unified Workflow Template and Docs (1/1 plan) -- completed 2026-03-10
- [x] Phase 24: Test Repo Migration and E2E Validation (1/1 plan) -- completed 2026-03-10

Full details: [iac/test-env/.planning/milestones/v1.4-ROADMAP.md](../iac/test-env/.planning/milestones/v1.4-ROADMAP.md)

</details>

<details>
<summary>v1.5 Batched Dispatch (Phases 25-28) -- SHIPPED 2026-03-11</summary>

- [x] Phase 25: Shared Models and Schema (1/1 plan) -- completed 2026-03-11
- [x] Phase 26: Backend Batched Dispatch (1/1 plan) -- completed 2026-03-11
- [x] Phase 27: Action Parsing and Workflow Template (1/1 plan) -- completed 2026-03-11
- [x] Phase 28: E2E Validation (1/1 plan) -- completed 2026-03-11

Full details: [milestones/v1.5-ROADMAP.md](milestones/v1.5-ROADMAP.md)

</details>

### v2.0 PR Integration (Phases 29-35)

**Milestone Goal:** Add PR-triggered deployments with a plan/apply model -- preview what will deploy on PR open/update, deploy on merge or explicit `/ferry apply` comment, with user-defined environment mapping and GitHub Environment support.

- [x] **Phase 29: Shared Models and Schema Extension** (1/1 plan) - v3 payload model, environment mapping config, ferry.yaml schema update
- [x] **Phase 30: PR Event Handler and Plan Comment** (1/1 plan) - Backend handles pull_request events, posts plan preview comment, creates check run
- [x] **Phase 31: Issue Comment Handler (/ferry plan + /ferry apply)** (1/1 plan) - PR comment commands, deploy dispatch, workflow_run status updates
- [x] **Phase 32: Push Path Environment Resolution** (1/1 plan) - Existing push handler gains environment awareness for auto-deploy on merge
- [ ] **Phase 33: Action v3 Parsing and Outputs** - Setup action parses v3 payload, outputs mode and environment with backward compatibility
- [x] **Phase 34: Workflow Template and GitHub Environments** (1/1 plan) - Updated ferry.yml template with environment: key, mode guard, and docs
- [ ] **Phase 35: E2E Validation** - Full PR lifecycle proven in test repo: plan comment, /ferry apply, merge deploy, environment secrets

## Phase Details

### Phase 29: Shared Models and Schema Extension
**Goal**: Both backend and action can work with v3 dispatch payloads and environment-aware ferry.yaml configs
**Depends on**: Phase 28 (v1.5 complete)
**Requirements**: COMPAT-01, ENV-01
**Success Criteria** (what must be TRUE):
  1. `ferry.yaml` with an `environments:` section parses into a valid `FerryConfig` with `EnvironmentMapping` entries
  2. `BatchedDispatchPayload` v3 includes `mode`, `environment`, `head_ref`, and `base_ref` fields with safe defaults
  3. A v2 payload (from v1.5) still parses successfully with `mode="deploy"` and `environment=""` defaults
  4. All existing tests continue to pass (no regressions from additive model changes)
**Plans**: 29-01 (models + tests)

### Phase 30: PR Event Handler and Plan Comment
**Goal**: Developers see which resources would be deployed as a sticky PR comment every time a PR is opened or updated
**Depends on**: Phase 29
**Requirements**: PLAN-01, PLAN-02, PLAN-03, PLAN-04
**Success Criteria** (what must be TRUE):
  1. Opening a PR that changes resource source files produces a sticky comment listing affected resources
  2. Pushing new commits to the same PR updates the existing comment in-place (no duplicate comments)
  3. When environments are configured, the plan comment shows the target environment name
  4. A Check Run appears on the PR reflecting plan status (success if resources detected, or neutral if no changes)
  5. No workflow_dispatch is triggered for plan mode (zero GHA runner minutes burned)
**Plans**: 1 plan
Plans:
- [x] 30-01-PLAN.md -- PR event handler, plan comment, check run, dedup extension

### Phase 31: Issue Comment Handler (/ferry plan + /ferry apply)
**Goal**: Developers can interact with Ferry via PR comments -- `/ferry plan` re-triggers plan preview, `/ferry apply` triggers deploy
**Depends on**: Phase 29, Phase 30 (reuses plan comment logic)
**Requirements**: PLAN-05, DEPLOY-02, DEPLOY-03, DEPLOY-04
**Success Criteria** (what must be TRUE):
  1. Commenting `/ferry plan` on a PR re-triggers the plan preview (posts a new comment with fresh change detection)
  2. Commenting `/ferry apply` on a PR triggers a workflow_dispatch with `mode="deploy"` and the correct environment
  3. The deploy uses the current PR head SHA (fetched fresh from the API), not a stale reference
  4. Commenting `/ferry apply` or `/ferry plan` on a regular issue (not a PR) is silently ignored -- no dispatch, no error
  5. The dispatch payload carries the resolved environment name based on the PR's target branch
**Plans**: 1 plan
Plans:
- [x] 31-01-PLAN.md -- Command parser, issue_comment handler, workflow_run handler, dedup, tests

### Phase 32: Push Path Environment Resolution
**Goal**: Merging a PR to a mapped branch automatically deploys affected resources to the correct environment
**Depends on**: Phase 29
**Requirements**: DEPLOY-01, ENV-02, ENV-03
**Success Criteria** (what must be TRUE):
  1. Merging a PR to a branch with an environment mapping triggers deploy with the correct environment name in the payload
  2. Ferry resolves the environment by matching the push ref against `ferry.yaml` environment branch mappings
  3. When no environment matches (or no environments configured), pushes produce no Ferry activity (breaking change from v1.x, per CONTEXT.md decision)
**Plans**: 1 plan
Plans:
- [x] 32-01-PLAN.md -- Environment-gated push dispatch, tests, ENV-03 update

### Phase 33: Action v3 Parsing and Outputs
**Goal**: The ferry setup action exposes mode and environment as workflow outputs so downstream jobs can consume them
**Depends on**: Phase 29
**Requirements**: COMPAT-02
**Success Criteria** (what must be TRUE):
  1. Setup action outputs `mode` and `environment` when receiving a v3 payload
  2. Setup action outputs `mode="deploy"` and `environment=""` when receiving a v2 payload (backward compatibility)
  3. All existing v1.5 outputs (has_lambdas, has_step_functions, etc.) continue to work unchanged
**Plans**: 1 plan
Plans:
- [ ] 33-01-PLAN.md -- Add mode/environment to DispatchPayload, ParseResult, parsers, main(), and action.yml

### Phase 34: Workflow Template and GitHub Environments
**Goal**: Users have a working ferry.yml template that surfaces environment secrets and enforces mode guards on deploy jobs
**Depends on**: Phase 33
**Requirements**: GHENV-01, GHENV-02, COMPAT-03
**Success Criteria** (what must be TRUE):
  1. Deploy jobs in the workflow template use `environment: ${{ needs.setup.outputs.environment }}` for GHA native secret injection
  2. Deploy jobs only run when `mode == 'deploy'` (layered on top of existing boolean type gates)
  3. Empty environment string (no environments configured) results in deploy jobs running without an environment (no crash, no error)
  4. Documentation includes the updated workflow template and instructions for adding `pull_request` and `issue_comment` webhook subscriptions
**Plans**: 1 plan
Plans:
- [x] 34-01-PLAN.md -- Update docs/setup.md with v2.0 workflow template, environments section, mode guards, and webhook events

### Phase 35: E2E Validation
**Goal**: Full PR lifecycle proven end-to-end in the real test environment
**Depends on**: Phases 30, 31, 32, 33, 34 (all prior phases)
**Requirements**: (validates all v2.0 requirements)
**Success Criteria** (what must be TRUE):
  1. Opening a PR in ferry-test-app produces a plan preview comment listing affected resources and target environment
  2. Commenting `/ferry apply` on the PR triggers a deploy workflow that successfully builds and deploys to the mapped environment
  3. Merging the PR triggers auto-deploy with the correct environment name flowing through to the GHA deploy job
  4. GitHub Environment secrets are accessible in deploy jobs (verified by a test secret)
  5. Existing push-to-deploy behavior (no environments configured) still works with the v2.0 codebase
**Plans**: TBD

## Progress

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
| 16. Provision Test Environment | v1.2 | 3/3 | Complete | 2026-03-07 |
| 17. End-to-End Loop Validation | v1.2 | 3/3 | Complete | 2026-03-08 |
| 18-21. Full-Chain E2E | v1.3 | 7/7 | Complete | 2026-03-10 |
| 22-24. Unified Workflow | v1.4 | 3/3 | Complete | 2026-03-10 |
| 25-28. Batched Dispatch | v1.5 | 4/4 | Complete | 2026-03-11 |
| 29. Shared Models and Schema Extension | v2.0 | 1/1 | Complete | 2026-03-12 |
| 30. PR Event Handler and Plan Comment | v2.0 | 1/1 | Complete | 2026-03-12 |
| 31. Issue Comment Handler and Deploy Dispatch | v2.0 | 1/1 | Complete | 2026-03-13 |
| 32. Push Path Environment Resolution | v2.0 | Complete    | 2026-03-13 | 2026-03-13 |
| 33. Action v3 Parsing and Outputs | v2.0 | 0/1 | Planned | - |
| 34. Workflow Template and GitHub Environments | v2.0 | 1/1 | Complete | 2026-03-13 |
| 35. E2E Validation | v2.0 | 0/? | Not started | - |
