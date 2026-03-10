---
phase: 24-test-repo-migration-e2e
plan: 01
status: complete
completed: 2026-03-10
---

# Summary: Test Repo Migration and E2E Validation

## What was done

1. **Created unified `ferry.yml`** in `AmitLaviDev/ferry-test-app` (commit `d45ae62`)
   - Full template from docs/setup.md: setup job + 3 conditional deploy jobs
   - `run-name` displays resource type in GHA Actions UI

2. **Deployed Ferry backend with Phase 22 code**
   - Pushed 10 commits (including Phase 22's `WORKFLOW_FILENAME = "ferry.yml"`) to ferry repo main
   - Self-deploy CI/CD built and deployed new image (run `22923541074`, completed in ~80s)
   - Backend Lambda `ferry-backend` now dispatches to `ferry.yml`

3. **Deleted old per-type workflow files** (commit `eec8cb2`)
   - Removed: `ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`
   - Only `ferry.yml` remains in `.github/workflows/`

4. **E2E: Lambda deploy** (GHA run `22923620397`)
   - Changed `lambdas/hello-world/main.py` version string
   - Ferry dispatched to `ferry.yml` with `resource_type=lambda`
   - `deploy-lambda` job ran and succeeded (56s)
   - `deploy-step-function` and `deploy-api-gateway` were **skipped**

5. **E2E: Step Functions deploy** (GHA run `22923683219`)
   - Changed `workflows/hello-chain/definition.json` comment
   - Ferry dispatched to `ferry.yml` with `resource_type=step_function`
   - `deploy-step-function` job ran and succeeded (14s)
   - `deploy-lambda` and `deploy-api-gateway` were **skipped**

6. **E2E: API Gateway deploy** (GHA run `22923718417`)
   - Changed `api/hello-chain/openapi.yaml` description
   - Ferry dispatched to `ferry.yml` with `resource_type=api_gateway`
   - `deploy-api-gateway` job ran and succeeded (18s)
   - `deploy-lambda` and `deploy-step-function` were **skipped**

## Requirements Satisfied

- **VAL-01**: Test repo migrated to unified workflow — single `ferry.yml`, old files deleted
- **VAL-02**: All 3 resource types deploy successfully via unified workflow with correct job routing

## Deviations

- Backend was not previously deployed with Phase 22 code (commits hadn't been pushed). Resolved by pushing to main, which triggered the self-deploy workflow.
- No deviations from the planned workflow template or migration steps.
