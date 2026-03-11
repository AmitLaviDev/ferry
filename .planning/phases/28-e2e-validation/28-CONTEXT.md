# Phase 28 Context: E2E Validation

## Decisions

### 1. Deploy sequencing for the multi-type test
- Single commit touching all 3 resource source directories (`lambdas/hello-world/`, `workflows/hello-chain/`, `api/hello-chain/`)
- Dummy/trivial changes only (comment, version bump) — just enough to trigger detection
- Explicitly ensure fresh changes to avoid content-hash skip from prior Phase 24 test pushes
- Order: single-type push first (smoke test, validates VAL-02), then multi-type push (validates VAL-01)

### 2. Backend + action deploy ordering
- Ferry monorepo pushed to `main` first — explicit step to push and wait for self-deploy CI/CD to complete
- Redeploy backend even though it may already be current — ensures Phase 26 batched dispatch code is live
- Action code at `@main` ref picks up Phase 27 changes automatically after push
- Test repo `ferry.yml` updated to v1.5 template as its own commit+push (before any validation pushes)
- Wait for the workflow-update dispatch to complete (or be ignored) before pushing validation commits

### 3. What constitutes "validation passed"
- GHA "all jobs green" is sufficient — deploy logic is unchanged from v1.4, no need to re-verify AWS resource state
- Explicitly verify via `gh run list` that exactly 1 workflow run was triggered per push (not 2 or 3)
- Explicitly verify via `gh run view` that non-active deploy jobs show "skipped" conclusion
- Fallback path (>65KB) is NOT E2E tested — unit tested in Phase 26, skip here

## Code Context

### Repositories
- **Ferry monorepo**: `/Users/amit/Repos/github/ferry` — backend + action code (Phases 25-27 changes)
- **Test repo**: `/Users/amit/Repos/github/ferry-test-app` — E2E validation target

### Test repo current state
- Single workflow file: `.github/workflows/ferry.yml` (v1.4 template — gates on `resource_type == 'lambda'`)
- ferry.yaml with 3 resources: hello-world Lambda, hello-chain SF, hello-chain APGW
- AWS resources provisioned by `iac/test-env` Terraform

### What needs updating in test repo
- Replace `ferry.yml` with v1.5 template from `docs/setup.md`:
  - `has_lambdas == 'true'` boolean gates instead of `resource_type == 'lambda'`
  - Per-type matrices (`lambda_matrix`, `sf_matrix`, `ag_matrix`) instead of shared `matrix`
  - `run-name` uses `resource_types` (v2) with `resource_type` (v1) fallback
  - 7 setup job outputs instead of 2

### Verification commands
- Run count: `gh run list --repo AmitLaviDev/ferry-test-app --branch main --limit 5`
- Job details: `gh run view <run-id> --repo AmitLaviDev/ferry-test-app --json jobs`
- Self-deploy status: `gh run list --repo AmitLaviDev/ferry --workflow self-deploy.yml --limit 1`

### Task sequence
1. Push ferry monorepo to `main` (if not already current) — wait for self-deploy
2. Update test repo `ferry.yml` to v1.5 template — commit + push — wait for dispatch to settle
3. Single-type validation: push dummy change to 1 resource dir — verify 1 run, 1 active job, 2 skipped (VAL-02)
4. Multi-type validation: push dummy change to all 3 resource dirs in 1 commit — verify 1 run, 3 active jobs, 0 skipped (VAL-01)

## Deferred Ideas
None captured during discussion.

---
*Created: 2026-03-11*
