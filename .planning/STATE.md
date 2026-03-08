# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-08)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** v1.3 Full-Chain E2E (APGW → SF → Lambda)

## Current Position

Milestone: v1.3 Full-Chain E2E
Status: Phase 18 in progress -- 18-02 complete
Last activity: 2026-03-08 -- completed 18-02 (non-code tech debt)

## Phase Overview

| Phase | Goal | Status |
|-------|------|--------|
| 18. Tech Debt Cleanup | Fix 5 pending v1.2 items | In Progress (18-02 done) |
| 19. Test Infrastructure for SF + APGW | Terraform for state machine, REST API, IAM | Pending |
| 20. Test Repo Updates | ASL definition, OpenAPI spec, ferry.yaml, workflows | Pending |
| 21. Full-Chain E2E Validation | Prove APGW → SF → Lambda chain works via Ferry | Pending |

## Performance Metrics

**Velocity (v1.0):**
- Total plans completed: 20
- Average duration: 4min
- Total execution time: 1.27 hours

**v1.1:** 5 phases, 8 plans (2026-02-28 → 2026-03-03)
**v1.2:** 3 phases, 9 plans (2026-03-03 → 2026-03-08)

## Accumulated Context

### Pending Todos (carried from v1.2 → Phase 18)

- Remove debug logging from deploy.py (raw error output)
- ~~Verify self-deploy IAM policy also has GetFunctionConfiguration (shared/data.tf)~~ DONE (18-02, needs terraform apply)
- ~~Add `name: "Ferry: deploy ${{ matrix.name }}"` to deploy job in workflow template (docs/lambdas.md)~~ DONE (18-02)
- Suppress Docker credential warning in build.py (cosmetic, low priority)
- Improve deploy.py error mapping (AccessDeniedException can mean target role lacks perms, not caller)

### Key Context for v1.3

- SF and APGW deploy code already exists and is tested (v1.0 Phase 4) -- never proven E2E
- Test repo: AmitLaviDev/ferry-test-app (from v1.2)
- Test Lambda: ferry-test-hello-world (already deployed and working)
- Deploy role: ferry-test-deploy (needs SF + APGW permissions added)
- Dispatch workflow names are hardcoded: ferry-step_functions.yml, ferry-api_gateways.yml
- Full chain: REST API → StartExecution (Standard SF) → Task state invokes Lambda

### Blockers/Concerns

- Python 3.14 arm64 Lambda base image availability on public.ecr.aws must be verified (fallback: Python 3.13 or custom base)

## Session Continuity

Last session: 2026-03-08
Stopped at: Completed 18-02-PLAN.md (non-code tech debt). IAM policy needs terraform apply.
