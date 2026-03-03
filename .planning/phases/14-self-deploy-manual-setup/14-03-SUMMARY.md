---
phase: 14-self-deploy-manual-setup
plan: 03
subsystem: infra
tags: [runbook, github-app, secrets-manager, setup, documentation]

# Dependency graph
requires:
  - phase: 14-self-deploy-manual-setup
    provides: Backend Dockerfile, self-deploy GHA workflow, Secrets Manager resolution
provides:
  - Complete setup runbook for Phase 14 manual steps (GitHub App, secrets, deploy, verification)
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [setup-runbook-with-verification]

key-files:
  created:
    - docs/setup-runbook.md
  modified: []

key-decisions:
  - "Option A (CLI) and Option B (Terraform) for installation ID update -- recommended Option B for persistence"
  - "Runbook scoped to Phase 14 manual steps only, not Phases 11-13 apply order"
  - "Troubleshooting section added for common failure modes (OIDC, secrets, webhook)"

patterns-established:
  - "Runbook pattern: prerequisites, step-by-step, verification, troubleshooting sections"

requirements-completed: [SETUP-01, SETUP-02, SETUP-03]

# Metrics
duration: 2min
completed: 2026-03-03
---

# Phase 14 Plan 03: Setup Runbook Summary

**Phase 14 setup runbook covering GitHub App registration, Secrets Manager population, OIDC repo secret, installation ID update, first deploy trigger, and end-to-end verification**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-03T08:07:32Z
- **Completed:** 2026-03-03T08:09:20Z
- **Tasks:** 1 (+ 1 non-blocking checkpoint deferred to user)
- **Files modified:** 1

## Accomplishments
- Setup runbook with 6 ordered steps covering all Phase 14 manual actions
- GitHub App registration instructions with exact permissions table (Contents:Read, PRs:R&W, Checks:R&W, Actions:Write)
- Secrets Manager population with all three secrets (app-id, private-key, webhook-secret) plus verification commands
- Two options for installation ID update: quick CLI fix and permanent Terraform approach
- End-to-end verification steps: curl Function URL, webhook redeliver test, CloudWatch log tailing
- Troubleshooting section for common failure modes (OIDC trust, missing secrets, webhook signature)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create setup runbook** - `042f553` (docs)

Task 2 (Execute manual setup steps) is a non-blocking human-verify checkpoint -- deferred to user execution.

## Files Created/Modified
- `docs/setup-runbook.md` - Complete Phase 14 setup runbook (230 lines)

## Decisions Made
- Provided both CLI (Option A) and Terraform (Option B) approaches for installation ID update, recommending Option B for persistence across applies
- Added troubleshooting section beyond plan requirements -- common failure modes save debugging time
- Included secret verification commands (get-secret-value queries) after population step

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
The setup runbook (`docs/setup-runbook.md`) documents all manual steps. The user must follow the runbook to:
1. Register the GitHub App with correct permissions and webhook URL
2. Populate Secrets Manager values via AWS CLI
3. Set `AWS_DEPLOY_ROLE_ARN` GitHub repo secret
4. Update the installation ID in the Lambda configuration
5. Trigger the first deploy by pushing to main
6. Verify end-to-end (curl, webhook, CloudWatch)

## Next Phase Readiness
- All Phase 14 code artifacts are committed and ready (Dockerfile, settings.py, GHA workflow, runbook)
- Manual setup steps documented in runbook, awaiting user execution
- Once manual steps are complete, Ferry will self-deploy on every push to main

## Self-Check: PASSED

All files verified present, all commits verified in git log.

---
*Phase: 14-self-deploy-manual-setup*
*Completed: 2026-03-03*
