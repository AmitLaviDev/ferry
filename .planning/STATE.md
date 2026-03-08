# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-08)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** Planning next milestone

## Current Position

Milestone: v1.2 archived. No active milestone.
Status: Between milestones -- ready for /gsd:new-milestone
Last activity: 2026-03-08 -- v1.2 archived, PROJECT.md evolved

## Performance Metrics

**Velocity (v1.0):**
- Total plans completed: 20
- Average duration: 4min
- Total execution time: 1.27 hours

**v1.1:** 5 phases, 8 plans (2026-02-28 → 2026-03-03)
**v1.2:** 3 phases, 9 plans (2026-03-03 → 2026-03-08)

## Accumulated Context

### Pending Todos (carried from v1.2)

- Remove debug logging from deploy.py (raw error output)
- Verify self-deploy IAM policy also has GetFunctionConfiguration (shared/data.tf)
- Add `name: "Ferry: deploy ${{ matrix.name }}"` to deploy job in workflow template (docs/lambdas.md)
- Suppress Docker credential warning in build.py (cosmetic, low priority)
- Improve deploy.py error mapping (AccessDeniedException can mean target role lacks perms, not caller)

### Blockers/Concerns

- Python 3.14 arm64 Lambda base image availability on public.ecr.aws must be verified (fallback: Python 3.13 or custom base)

## Session Continuity

Last session: 2026-03-08
Stopped at: v1.2 milestone archived. Starting v1.3 via /gsd:new-milestone.
