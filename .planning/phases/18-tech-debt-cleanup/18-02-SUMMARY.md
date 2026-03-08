---
phase: 18-tech-debt-cleanup
plan: 02
subsystem: iac, docs
tags: [tech-debt, iam, docs, terraform]

# Dependency graph
requires: []
provides:
  - "Self-deploy IAM policy with GetFunctionConfiguration permission"
  - "Workflow template docs with named deploy job"
affects:
  - iac/aws/staging/shared (requires terraform apply)

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - iac/aws/staging/shared/data.tf
    - docs/lambdas.md

key-decisions:
  - "IAM change requires manual terraform apply -- not executed by plan"

patterns-established: []

requirements-completed: [TD-02, TD-03]

# Metrics
duration: 1min
completed: 2026-03-08
---

# Phase 18 Plan 02: Non-Code Tech Debt (IAM Policy + Workflow Docs)

**Added lambda:GetFunctionConfiguration to self-deploy IAM policy and name field to deploy job in workflow docs.**

## Performance

- **Duration:** 1 min
- **Tasks:** 2/2
- **Files modified:** 2

## Accomplishments

- Added `lambda:GetFunctionConfiguration` to the `gha_self_deploy_lambda` IAM policy document, matching the pattern already present in test-env
- Added `name: "Ferry: deploy ${{ matrix.name }}"` to the deploy job in the workflow template documentation, making parallel matrix jobs distinguishable in the GHA UI

## Task Results

1. **Task 1: Add GetFunctionConfiguration to self-deploy IAM policy (TD-02)** -- `f2fd81e`
   - Added missing permission to `iac/aws/staging/shared/data.tf`
   - Required for `deploy.py` wait_for_update functionality
   - **Action required:** `terraform apply` in `iac/aws/staging/shared/` to propagate to AWS

2. **Task 2: Add name field to deploy job in workflow docs (TD-03)** -- `a7c0818`
   - Added `name:` field to deploy job in `docs/lambdas.md` workflow template
   - Users copying the template will now get descriptive job names in GHA UI

## Deviations from Plan

None -- plan executed exactly as written.

## Manual Follow-up Required

- Run `terraform apply` in `iac/aws/staging/shared/` to apply the IAM policy change to AWS

## Self-Check: PASSED

All verification criteria met.

---
*Phase: 18-tech-debt-cleanup*
*Completed: 2026-03-08*
