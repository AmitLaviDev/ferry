# Roadmap: Ferry

## Milestones

- v1.0 MVP -- Phases 1-10 (shipped 2026-02-28)
- v1.1 Deploy to Staging -- Phases 11-14 (shipped 2026-03-03)
- v1.2 End-to-End Validation -- Phases 15-17 (shipped 2026-03-08)
- **v1.3 Full-Chain E2E** -- Phases 18-21 (in progress)

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

### v1.3 Full-Chain E2E

**Milestone Goal:** Prove Step Functions and API Gateway deploy paths end-to-end with an integrated chain (API Gateway → Step Function → Lambda), and clean up v1.2 tech debt.

- [ ] **Phase 18: Tech Debt Cleanup** -- Fix 5 pending items from v1.2 (debug logging, IAM verify, doc fix, Docker warning, error mapping)
- [ ] **Phase 19: Test Infrastructure for SF + APGW** -- Terraform for state machine, REST API, SF execution role, APGW-to-SF permissions, deploy role policies
- [ ] **Phase 20: Test Repo Updates** -- ASL definition (invokes test Lambda), OpenAPI spec (triggers SF), ferry.yaml entries, GHA workflow files
- [ ] **Phase 21: Full-Chain E2E Validation** -- Push changes, verify all dispatches fire, all deploys succeed, invoke APGW → SF → Lambda chain, prove repeatability

## Phase Details

### Phase 18: Tech Debt Cleanup
**Goal**: Clean up all pending tech debt items carried forward from v1.2 so the codebase is clean before extending the test environment
**Depends on**: Nothing (standalone cleanup)
**Requirements**: TD-01, TD-02, TD-03, TD-04, TD-05
**Success Criteria** (what must be TRUE):
  1. No debug logging statements remain in deploy.py
  2. Self-deploy IAM policy includes `lambda:GetFunctionConfiguration`
  3. Workflow template docs show `name:` field on deploy jobs
  4. Docker credential warning is suppressed in build.py
  5. deploy.py error mapping distinguishes caller vs target role permission failures
  6. All tests pass, no lint errors

### Phase 19: Test Infrastructure for SF + APGW
**Goal**: AWS resources exist for Step Functions and API Gateway testing -- state machine, REST API, execution roles, and deploy permissions -- all managed via Terraform in test-env
**Depends on**: Phase 18 (clean codebase), existing test-env IaC from v1.2
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06
**Success Criteria** (what must be TRUE):
  1. Standard Step Functions state machine exists with a placeholder definition
  2. REST API exists with a `test` stage
  3. SF execution role has `lambda:InvokeFunction` permission on the test Lambda
  4. API Gateway has IAM integration permission to call `states:StartExecution` on the test state machine
  5. `ferry-test-deploy` role has Step Functions deploy permissions (UpdateStateMachine, DescribeStateMachine, TagResource, ListTagsForResource)
  6. `ferry-test-deploy` role has API Gateway deploy permissions (PutRestApi, CreateDeployment, GetRestApi, TagResource, GetTags)
  7. `terraform plan` shows no pending changes after apply

**Manual Steps:**
- Run `terraform apply` in test-env after adding the new resources

### Phase 20: Test Repo Updates
**Goal**: Test repo (ferry-test-app) contains all files needed to exercise SF and APGW deploy paths -- ASL definition that invokes the test Lambda, OpenAPI spec that triggers the SF, updated ferry.yaml, and dispatch workflow files
**Depends on**: Phase 19 (AWS resources must exist to reference their IDs/ARNs)
**Requirements**: REPO-01, REPO-02, REPO-03, REPO-04, REPO-05
**Success Criteria** (what must be TRUE):
  1. `workflows/hello-chain/definition.asl.json` contains a Task state invoking the test Lambda with `${ACCOUNT_ID}` and `${AWS_REGION}` placeholders
  2. `api/hello-chain/openapi.yaml` defines a POST endpoint with `x-amazon-apigateway-integration` calling `states:StartExecution` on the test state machine
  3. `ferry.yaml` has `step_functions` and `api_gateways` sections pointing to the new resources
  4. `.github/workflows/ferry-step_functions.yml` exists (matching hardcoded dispatch name)
  5. `.github/workflows/ferry-api_gateways.yml` exists (matching hardcoded dispatch name)

**Manual Steps:**
- Push changes to test repo on GitHub
- Install/verify Ferry GitHub App is still active on test repo

### Phase 21: Full-Chain E2E Validation
**Goal**: The full integrated chain works -- API Gateway → Step Function → Lambda -- deployed via Ferry, and all three resource types can be independently changed and deployed
**Depends on**: Phase 20 (test repo fully configured)
**Requirements**: E2E-01, E2E-02, E2E-03, E2E-04, E2E-05, E2E-06, E2E-07
**Success Criteria** (what must be TRUE):
  1. Pushing a change to the SF definition triggers Ferry → detects step_functions change → dispatches `ferry-step_functions.yml` → deploys state machine
  2. Pushing a change to the APGW spec triggers Ferry → detects api_gateways change → dispatches `ferry-api_gateways.yml` → deploys REST API
  3. Invoking the API Gateway POST endpoint triggers the Step Function, which invokes the Lambda, and the execution completes successfully
  4. A no-op push (no definition/spec changes) correctly skips SF and APGW deploys via content-hash detection
  5. A push changing files across all three resource types triggers 3 separate dispatches (lambdas, step_functions, api_gateways) and all deploy successfully

**Iterative Bug Fix Cycle:**
- Each step of the loop (webhook receipt, change detection, dispatch, build/deploy) is a potential failure point
- When a step fails: diagnose from CloudWatch logs / GHA workflow logs, fix the bug, push the fix (self-deploys), retry
- Similar to v1.2 Phase 17 -- expect bugs and iterate

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
| 18. Tech Debt Cleanup | v1.3 | 0/? | Pending | -- |
| 19. Test Infrastructure for SF + APGW | v1.3 | 0/? | Pending | -- |
| 20. Test Repo Updates | v1.3 | 0/? | Pending | -- |
| 21. Full-Chain E2E Validation | v1.3 | 0/? | Pending | -- |
