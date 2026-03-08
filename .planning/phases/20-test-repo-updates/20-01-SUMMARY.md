---
phase: 20-test-repo-updates
plan: 01
status: complete
duration: ~45s
tasks_completed: 2/2 auto, 1 manual pending
files_created: 4
files_modified: 1
---

# Plan 20-01 Summary: Test Repo Updates

## What was done

Created 5 files in `/Users/amit/Repos/github/ferry-test-app/` for the SF + APGW deploy paths:

1. **workflows/hello-chain/definition.asl.json** — Minimal ASL with single Task state invoking `ferry-test-hello-world` Lambda. Uses `${ACCOUNT_ID}` and `${AWS_REGION}` envsubst placeholders.

2. **api/hello-chain/openapi.yaml** — Swagger 2.0 spec with `POST /execute` endpoint. Integration type `aws` calling `states:StartExecution`, request template maps HTTP body to SF input via `$util.escapeJavaScript($input.body)`, credentials reference `ferry-test-apgw-invoke` role.

3. **ferry.yaml** — Updated with all 3 resource types: existing `lambdas` preserved, new `step_functions` (state_machine_name: ferry-test-sf) and `api_gateways` (rest_api_id: v1h1ch5rqk, stage_name: test).

4. **`.github/workflows/ferry-step_functions.yml`** — GHA workflow for SF dispatch with `AmitLaviDev/ferry/action/{setup,deploy-stepfunctions}@main` external composite action references.

5. **`.github/workflows/ferry-api_gateways.yml`** — GHA workflow for APGW dispatch with `AmitLaviDev/ferry/action/{setup,deploy-apigw}@main` external composite action references.

## Verification

- ASL: valid JSON, correct StartAt/Task/Resource/placeholders
- OpenAPI: Swagger 2.0, POST /execute, x-amazon-apigateway-integration with StartExecution
- ferry.yaml: 3 sections (lambdas, step_functions, api_gateways), validates against Pydantic schema
- Workflows: workflow_dispatch triggers, OIDC permissions (id-token+contents+checks), external action references

## Manual step remaining

```bash
cd /Users/amit/Repos/github/ferry-test-app
git add -A
git commit -m "feat: add SF + APGW resources for full-chain E2E"
git push origin main
```
