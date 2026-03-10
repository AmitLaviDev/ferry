# Ferry v1.3 Full-Chain E2E Validation Report

**Date:** 2026-03-10
**Status:** PASSED

## Infrastructure Verified

| Component | Status | Evidence |
|-----------|--------|----------|
| Ferry Lambda | Active | `arn:aws:lambda:us-east-1:050068574410:function:ferry-backend` |
| Ferry Function URL | Active | `https://6dtb47ahdfi4hywuclwhwl7x5q0wizqz.lambda-url.us-east-1.on.aws/` |
| DynamoDB dedup table | Active | `ferry-webhook-dedup` |
| GitHub App | Installed | Installed on `AmitLaviDev/ferry-test-app` |
| Test Lambda | Active | `ferry-test-hello-world` (image-based, `live` alias) |
| Test State Machine | Active | `ferry-test-sf` (STANDARD, `ferry-test-sf-execution` role) |
| Test REST API | Active | ID `v1h1ch5rqk`, stage `test`, REGIONAL |
| Test Deploy Role | Active | `ferry-test-deploy` (OIDC trust for `AmitLaviDev/ferry-test-app`) |

## Individual Deploy Path Results

### Lambda Echo Deploy
- **Push:** `5e7062b` — modified handler to echo input payload
- **Webhook received:** Yes
- **Changes detected:** 1 affected (lambdas)
- **Dispatch triggered:** Yes → `ferry-lambdas.yml` (204)
- **GHA Run:** [22904805153](https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22904805153) — success
- **Deploy completed:** Yes (version 3 published, `live` alias updated)
- **Direct invoke result:** `{"source": "ferry-e2e-test", "message": "hello from ferry"}`

### Step Functions Deploy
- **Push:** `c77f095` — updated SF definition Comment field
- **Webhook received:** Yes
- **Changes detected:** 1 affected (step_functions)
- **Dispatch triggered:** Yes → `ferry-step_functions.yml` (204)
- **GHA Run:** [22904896315](https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22904896315) — success
- **Deploy completed:** Yes (definition updated, version published)
- **State machine updated:** Comment = "Ferry E2E chain test — updated for Phase 21 validation"
- **Content-hash tag:** `3f4d73efd8798dccb0ca43f326a2901af9983d7223cc15d83565c13eb55bd21f`

### API Gateway Deploy
- **Push:** `589fbcf` — added description, updated version to 1.1
- **Webhook received:** Yes
- **Changes detected:** 1 affected (api_gateways)
- **Dispatch triggered:** Yes → `ferry-api_gateways.yml` (204)
- **GHA Run:** [22904964545](https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22904964545) — success
- **Deploy completed:** Yes (spec uploaded, deployment created)
- **REST API updated:** Description = "Ferry E2E chain test — updated for Phase 21 validation"
- **Content-hash tag:** `aba976ae2d288d65acba2e2f533e1d833f50404e3cd419edcdb3aacd6d84b581`

## Chain Invocation (APGW → SF → Lambda)

- **APGW POST /execute:** Status 200 (latency 121ms, integration 84ms)
- **Request body:** `{"source":"ferry-e2e-test","timestamp":"2026-03-10T13:35:00Z"}`
- **SF Execution ARN:** `arn:aws:states:us-east-1:050068574410:execution:ferry-test-sf:704d6f59-23a3-4590-9845-83dfd3f4c689`
- **SF Execution Status:** SUCCEEDED
- **SF Output (Lambda response):** `{"source": "ferry-e2e-test", "message": "hello from ferry"}`
- **Execution history:** `LambdaFunctionSucceeded` event confirms Lambda output
- **Data trace verified:** `source` field flowed through all 3 layers (APGW → SF → Lambda → SF output)

## Skip Detection

### Dispatch-Level Skip (Non-Resource File Change)
- **Push:** `e58ba0a` — README.md change only
- **Webhook received:** Yes
- **Changes detected:** `affected_count: 0`
- **Dispatches triggered:** 0
- **GHA runs:** No new runs
- **Result:** PASS — correct skip

### Deploy-Level Skip (Content Hash Unchanged)
- **Push:** `de320cf` — added `workflows/hello-chain/README.md` (in source_dir, not the definition file)
- **Dispatch triggered:** Yes → `ferry-step_functions.yml`
- **GHA Run:** [22905097241](https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22905097241) — completed
- **Deploy skipped:** Yes — "Skipping deploy for hello-chain -- definition unchanged"
- **Result:** PASS — content hash match detected

## Multi-Type Dispatch

- **Push:** `d6ad1b3` — single commit changing Lambda + SF + APGW files
- **Changes detected:** `affected_count: 3`
- **Dispatches triggered:** 3 — lambdas (204), step_functions (204), api_gateways (204)
- **GHA Runs:**
  - Lambdas: [22905172832](https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22905172832) — success
  - Step Functions: [22905173618](https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22905173618) — success
  - API Gateways: [22905174256](https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22905174256) — success
- **Lambda verified:** `{"source": "multi-type-test", "message": "hello from ferry", "version": "multi-type-test"}` (version 4)
- **SF verified:** Comment = "Ferry E2E chain — multi-type push test"
- **APGW verified:** Spec version updated to 1.2
- **Result:** PASS — all 3 types deployed from single push

## Bugs Found and Fixed

No bugs encountered — all deploy paths and chain invocation worked on first attempt.

Note: `pr_lookup_failed` (403) appears on all pushes — GitHub App likely missing `pulls:read` permission. Non-blocking for push deploys, will be relevant for v2.0 PR integration.

## v1.3 Summary

**What v1.3 proved:**
- All 3 resource types (Lambda, Step Functions, API Gateway) deploy via Ferry dispatch
- Full integrated chain works: APGW → SF → Lambda with data flowing through all layers
- Content-hash skip detection works at two levels:
  - Dispatch level: changes outside resource source dirs → no dispatch
  - Deploy level: changes in source dir but definition unchanged → deploy skipped
- Multi-type dispatch works: single push triggers parallel deploys for all affected resource types
- Independent deploy paths: each type can be changed and deployed independently
- 0 bugs in Phase 21 (5 bugs were found and fixed in Phase 20 during initial SF/APGW debugging)

**What v1.3 did NOT prove (future work):**
- PR event handling (Check Runs, PR comments for SF/APGW) — v2.0
- Unified workflow file (single `ferry.yml`) — v1.4
- Multi-tenant / cross-org installations — v2+
- Private repo dependencies for Lambda builds
- Rollback scenarios
- `pulls:read` permission for PR lookup on push events

## Resource Links

- Ferry Lambda CloudWatch: `/aws/lambda/ferry-backend`
- Ferry Function URL: `https://6dtb47ahdfi4hywuclwhwl7x5q0wizqz.lambda-url.us-east-1.on.aws/`
- Test repo: https://github.com/AmitLaviDev/ferry-test-app
- Test Lambda: `arn:aws:lambda:us-east-1:050068574410:function:ferry-test-hello-world`
- Test SF: `arn:aws:states:us-east-1:050068574410:stateMachine:ferry-test-sf`
- Test APGW: `https://v1h1ch5rqk.execute-api.us-east-1.amazonaws.com/test`
- GHA workflow runs: https://github.com/AmitLaviDev/ferry-test-app/actions
