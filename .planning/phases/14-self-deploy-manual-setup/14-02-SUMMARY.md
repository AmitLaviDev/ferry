---
phase: 14-self-deploy-manual-setup
plan: 02
subsystem: infra
tags: [github-actions, oidc, ecr, lambda, docker, ci-cd, self-deploy]

# Dependency graph
requires:
  - phase: 14-self-deploy-manual-setup
    provides: Backend Dockerfile, Secrets Manager resolution in settings.py
provides:
  - Self-deploy GHA workflow that builds, pushes, and deploys ferry-backend on push to main
affects: [14-03-setup-runbook]

# Tech tracking
tech-stack:
  added: [configure-aws-credentials@v6, amazon-ecr-login@v2, docker/build-push-action@v6, docker/setup-buildx-action@v3]
  patterns: [oidc-gha-deploy, gha-docker-cache, lambda-wait-v2]

key-files:
  created:
    - .github/workflows/self-deploy.yml
  modified: []

key-decisions:
  - "No path filtering on push trigger -- every push to main triggers deploy for simplicity"
  - "Image tagged with github.sha for traceability back to exact commit"

patterns-established:
  - "GHA OIDC deploy pattern: configure-aws-credentials with role-to-assume from repo secret"
  - "Lambda code deploy pattern: update-function-code + wait function-updated-v2 with --no-cli-pager"
  - "Docker layer caching via GHA cache backend (type=gha, mode=max)"

requirements-completed: [DEPLOY-02]

# Metrics
duration: 1min
completed: 2026-03-03
---

# Phase 14 Plan 02: Self-Deploy GHA Workflow Summary

**GHA workflow with OIDC auth, ECR push, and Lambda code update triggered on every push to main**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-03T08:03:36Z
- **Completed:** 2026-03-03T08:05:06Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Self-deploy workflow triggers on every push to main with test-then-deploy pipeline
- Test job runs pytest with Python 3.14 and uv before build proceeds
- Deploy job authenticates via OIDC, builds Docker image with Buildx caching, pushes to ECR, and updates Lambda
- Lambda update uses function-updated-v2 waiter for reliable completion confirmation

## Task Commits

Each task was committed atomically:

1. **Task 1: Create self-deploy GHA workflow** - `820d602` (feat)

## Files Created/Modified
- `.github/workflows/self-deploy.yml` - Self-deploy GHA workflow with test and deploy jobs

## Decisions Made
None - followed plan as specified.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
The `AWS_DEPLOY_ROLE_ARN` GitHub repository secret must be set to the ARN of the `ferry-gha-self-deploy` IAM role before the workflow will succeed. This is documented in the setup runbook (Plan 03).

## Next Phase Readiness
- Self-deploy workflow ready for use once AWS_DEPLOY_ROLE_ARN repo secret is configured
- Setup runbook (Plan 03) will document the manual steps for GitHub App registration, secrets population, and triggering the first deploy

## Self-Check: PASSED

All files verified present, all commits verified in git log.

---
*Phase: 14-self-deploy-manual-setup*
*Completed: 2026-03-03*
