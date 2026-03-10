# Plan 21-01 Summary: Deploy Paths Verification

**Status:** Complete
**Date:** 2026-03-10

## Results

### Task 1: Lambda Echo Handler Deploy
- **Push:** `5e7062b` — modified `lambdas/hello-world/main.py` to echo input payload
- **Webhook:** `changes_detected` (1 affected, lambdas), `dispatch_triggered` → `ferry-lambdas.yml` (204)
- **GHA Run:** [22904805153](https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22904805153) — all jobs succeeded
- **Direct invoke result:** `{"source": "ferry-e2e-test", "message": "hello from ferry"}` (version 3)
- **Dispatch isolation:** Only lambdas dispatched (correct)

### Task 2: Step Functions Deploy
- **Push:** `c77f095` — updated SF definition Comment field
- **Webhook:** `changes_detected` (1 affected, step_functions), `dispatch_triggered` → `ferry-step_functions.yml` (204)
- **GHA Run:** [22904896315](https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22904896315) — all jobs succeeded
- **State machine updated:** Definition contains new Comment "Ferry E2E chain test — updated for Phase 21 validation"
- **Content-hash tag:** `3f4d73efd8798dccb0ca43f326a2901af9983d7223cc15d83565c13eb55bd21f`
- **Dispatch isolation:** Only step_functions dispatched (correct)

### Task 3: API Gateway Deploy
- **Push:** `589fbcf` — added description and updated version in OpenAPI spec
- **Webhook:** `changes_detected` (1 affected, api_gateways), `dispatch_triggered` → `ferry-api_gateways.yml` (204)
- **GHA Run:** [22904964545](https://github.com/AmitLaviDev/ferry-test-app/actions/runs/22904964545) — all jobs succeeded
- **REST API updated:** Description = "Ferry E2E chain test — updated for Phase 21 validation"
- **Content-hash tag:** `aba976ae2d288d65acba2e2f533e1d833f50404e3cd419edcdb3aacd6d84b581`
- **Dispatch isolation:** Only api_gateways dispatched (correct)

## Bugs Found
None — all three deploy paths worked on first attempt.

## Notes
- Non-blocking: `pr_lookup_failed` (403) on all pushes — GitHub App likely missing `pulls:read` permission. Does not affect deploy path.
- All pushes to default branch (main), all dispatches single-type as expected.
