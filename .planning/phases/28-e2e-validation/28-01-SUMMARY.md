---
phase: 28-e2e-validation
plan: 01
status: completed
started: "2026-03-11T21:30:00Z"
completed: "2026-03-11T21:40:00Z"
duration: ~10min
requirements_validated: [VAL-01, VAL-02]
---

# Phase 28-01 Summary: E2E Validation

## What was validated

Proved that Ferry v1.5 batched dispatch works end-to-end: one push produces one workflow_dispatch with correct per-type job routing.

## Results

### Task 1: Self-deploy
- Ferry monorepo already pushed to main
- Self-deploy run `22975485182` completed (test + deploy green)
- Backend Lambda updated at `2026-03-11T21:33:20Z`

### Task 2: Test repo workflow update
- Replaced `ferry-test-app/.github/workflows/ferry.yml` with v1.5 template
- Key changes: `has_lambdas == 'true'` boolean gates, per-type matrices, `resource_types` in run-name
- No spurious dispatch triggered by workflow file change

### Task 3: VAL-02 — Single-type validation
- **Run ID:** `22975593340`
- **Run name:** `Ferry Deploy: lambda`
- **Result:** 1 run, 1 active Lambda deploy job, 2 skipped (SF + APGW)
- Confirms: single-type push correctly gates inactive deploy jobs via boolean flags

### Task 4: VAL-01 — Multi-type validation
- **Run ID:** `22975664942`
- **Run name:** `Ferry Deploy: lambda,step_function,api_gateway`
- **Result:** 1 run, 3 active deploy jobs (Lambda + SF + APGW), 0 skipped
- Confirms: multi-type push batches all types into a single dispatch with all jobs active

## Key observations

- Backend batched dispatch produces exactly 1 `workflow_dispatch` per push (not per-type)
- v2 payload `resource_types` field renders correctly in run-name
- Action setup step correctly parses v2 batched payload into per-type boolean flags and matrices
- SF and APGW deploys complete in ~15s; Lambda takes ~1m due to Docker build
- Check runs (`Ferry: hello-world deploy`, `Ferry: hello-chain deploy`) created successfully

## No issues found

All validation passed on first attempt. No bugs, no retries needed.
