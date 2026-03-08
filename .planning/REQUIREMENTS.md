# Requirements: v1.3 Full-Chain E2E

**Milestone Goal:** Prove Step Functions and API Gateway deploy paths end-to-end by extending the test repo with an integrated chain: API Gateway → Step Function → Lambda. Also clean up pending tech debt from v1.2.

---

## Tech Debt Cleanup

- [x] **TD-01**: Remove debug logging from deploy.py (raw error output lines)
- [x] **TD-02**: Verify self-deploy IAM policy has `lambda:GetFunctionConfiguration` (shared/data.tf)
- [x] **TD-03**: Add `name:` field to deploy job in workflow template docs (docs/lambdas.md)
- [x] **TD-04**: Suppress Docker credential warning in build.py (cosmetic)
- [x] **TD-05**: Improve deploy.py error mapping — AccessDeniedException can mean target role lacks permissions, not just caller

## Test Infrastructure (Step Functions + API Gateway)

- [x] **INFRA-01**: Step Functions state machine exists in AWS (Standard type, placeholder definition) — created via Terraform in test-env
- [x] **INFRA-02**: API Gateway REST API exists in AWS with a `test` stage — created via Terraform in test-env
- [x] **INFRA-03**: IAM execution role for the Step Function with permission to invoke the test Lambda
- [x] **INFRA-04**: API Gateway has IAM permissions to call `states:StartExecution` on the test state machine
- [x] **INFRA-05**: Deploy role (`ferry-test-deploy`) has Step Functions deploy permissions (UpdateStateMachine, DescribeStateMachine, TagResource, ListTagsForResource)
- [x] **INFRA-06**: Deploy role has API Gateway deploy permissions (PutRestApi, CreateDeployment, GetRestApi, TagResource, GetTags)

## Test Repo Updates

- [ ] **REPO-01**: ASL definition file (definition.asl.json) with a Task state that invokes the test Lambda via `${ACCOUNT_ID}` and `${AWS_REGION}` substitution
- [ ] **REPO-02**: OpenAPI spec (openapi.yaml) defining a POST endpoint with `x-amazon-apigateway-integration` that calls `states:StartExecution` on the test state machine
- [ ] **REPO-03**: ferry.yaml updated with `step_functions` and `api_gateways` sections pointing to the new resources
- [ ] **REPO-04**: GHA workflow `ferry-step_functions.yml` in test repo (matching hardcoded dispatch name)
- [ ] **REPO-05**: GHA workflow `ferry-api_gateways.yml` in test repo (matching hardcoded dispatch name)

## Full-Chain E2E Validation

- [ ] **E2E-01**: Push changing SF definition triggers Ferry webhook → detects step_functions change → dispatches `ferry-step_functions.yml`
- [ ] **E2E-02**: Step Functions deploy succeeds — state machine definition updated, version published, content-hash tag set
- [ ] **E2E-03**: Push changing APGW spec triggers Ferry webhook → detects api_gateways change → dispatches `ferry-api_gateways.yml`
- [ ] **E2E-04**: API Gateway deploy succeeds — spec uploaded, deployment created to test stage, content-hash tag set
- [ ] **E2E-05**: Invoking the API Gateway endpoint triggers the Step Function, which invokes the Lambda, proving the full chain works
- [ ] **E2E-06**: No-op push (no definition/spec changes) correctly skips SF and APGW deploys via content-hash detection
- [ ] **E2E-07**: All three resource types (Lambda + SF + APGW) can be changed and deployed in a single push (multi-type dispatch)

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TD-01..TD-05 | Phase 18 | Complete |
| INFRA-01..INFRA-06 | Phase 19 | Complete (TF written, needs apply) |
| REPO-01..REPO-05 | Phase 20 | Pending |
| E2E-01..E2E-07 | Phase 21 | Pending |

**Coverage:** 11/23 requirements complete
