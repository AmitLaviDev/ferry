---
phase: 07-tech-debt-cleanup
plan: 02
subsystem: docs
tags: [documentation, workflow, github-actions, ferry-yaml, oidc]

# Dependency graph
requires:
  - phase: 01-foundation-and-shared-contract
    provides: "RESOURCE_TYPE_WORKFLOW_MAP constants defining workflow file naming"
  - phase: 03-build-and-lambda-deploy
    provides: "Composite action YAML files (build, deploy, setup) defining real input names"
  - phase: 04-extended-resource-types
    provides: "Step Functions and API Gateway deploy actions"
provides:
  - "User-facing workflow documentation in docs/ directory"
  - "Annotated copy-paste-ready workflow YAML files for all 3 resource types"
  - "Setup guide covering ferry.yaml, OIDC, naming convention, dispatch flow"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Documentation per resource type with annotated YAML examples"

key-files:
  created:
    - docs/setup.md
    - docs/lambdas.md
    - docs/step-functions.md
    - docs/api-gateways.md
  modified: []

key-decisions:
  - "All workflow YAML examples use real action paths (./action/build, ./action/deploy, etc.) and real input names from composite action files"
  - "Runtime documented as python3.14 default (matching Dockerfile ARG and plan 01 target) with override instructions"

patterns-established:
  - "Documentation structure: shared setup.md + one file per resource type"

requirements-completed: []

# Metrics
duration: 3min
completed: 2026-02-27
---

# Phase 7 Plan 02: Workflow Documentation Summary

**User-facing docs with annotated workflow YAML files for lambdas, step functions, and API gateways plus shared setup guide covering ferry.yaml, OIDC, and dispatch flow**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-27T20:32:10Z
- **Completed:** 2026-02-27T20:35:00Z
- **Tasks:** 2
- **Files created:** 4

## Accomplishments
- Created shared setup guide covering installation, ferry.yaml structure, workflow naming convention, OIDC authentication, and dispatch flow
- Created three per-resource-type workflow guides with annotated copy-paste-ready YAML examples that use real action paths and real input names
- Documented the Magic Dockerfile (requirements.txt, system packages, private repo deps) and runtime override mechanism

## Task Commits

Each task was committed atomically:

1. **Task 1: Create shared setup guide (docs/setup.md)** - `91c141d` (docs)
2. **Task 2: Create per-resource-type workflow guides** - `a9e3899` (docs)

## Files Created/Modified
- `docs/setup.md` - Shared setup guide: installation, ferry.yaml structure, naming convention, OIDC auth, dispatch flow
- `docs/lambdas.md` - Lambda workflow guide with annotated ferry-lambdas.yml example, field reference, runtime override, Magic Dockerfile
- `docs/step-functions.md` - Step Functions workflow guide with annotated ferry-step_functions.yml example, variable substitution, content-hash skip
- `docs/api-gateways.md` - API Gateway workflow guide with annotated ferry-api_gateways.yml example, spec format notes, content-hash skip

## Decisions Made
- All workflow YAML examples reference real action input names read directly from composite action YAML files (resource-name, source-dir, ecr-repo, etc.) -- no invented input names
- Documented runtime as python3.14 default to match Dockerfile ARG and the target canonical default from Plan 01, with instructions for per-Lambda and workflow-level override
- Used `${{ secrets.AWS_ROLE_ARN }}` placeholder in workflow examples (convention for user-supplied secrets)
- Included `fail-fast: false` in all matrix strategies so one resource failure does not block others

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Documentation is ready for users once Plan 01 (runtime wiring) and Plan 03 (SUMMARY frontmatter) complete the phase
- If the canonical runtime default changes from python3.14 in Plan 01, the docs examples will need updating to match

## Self-Check: PASSED

- All 4 docs files exist: setup.md, lambdas.md, step-functions.md, api-gateways.md
- Commit 91c141d found (Task 1)
- Commit a9e3899 found (Task 2)

---
*Phase: 07-tech-debt-cleanup*
*Completed: 2026-02-27*
