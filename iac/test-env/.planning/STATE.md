# Project State

## Project Reference

See: .planning/PROJECT.md (in main ferry repo)
See: .planning/ROADMAP.md (this directory)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** v2.0 PR Integration

## Current Position

Milestone: v2.0 PR Integration
Phase: 32 Push Path Environment Resolution -- COMPLETE
Status: Phase 32 plan 01 executed
Last activity: 2026-03-13 -- Environment-gated push dispatch implemented

```
v2.0 Progress: [######----] 4/7 phases (29 done, 30 done, 31 done, 32 done)
```

## Shipped Milestones

| Version | Name | Phases | Shipped |
|---------|------|--------|---------|
| v1.0 | MVP | 1-10 | 2026-02-28 |
| v1.1 | Deploy to Staging | 11-14 | 2026-03-03 |
| v1.2 | End-to-End Validation | 15-17 | 2026-03-08 |
| v1.3 | Full-Chain E2E | 18-21 | 2026-03-10 |
| v1.4 | Unified Workflow | 22-24 | 2026-03-10 |
| v1.5 | Batched Dispatch | 25-28 | 2026-03-11 |

## Performance Metrics

**Velocity (v1.0):**
- Total plans completed: 20
- Average duration: 4min
- Total execution time: 1.27 hours

**v1.1:** 5 phases, 8 plans (2026-02-28 to 2026-03-03)
**v1.2:** 3 phases, 9 plans (2026-03-03 to 2026-03-08)
**v1.3:** 4 phases, 7 plans (2026-03-08 to 2026-03-10)
**v1.4:** 3 phases, 3 plans (2026-03-10)
**v1.5:** 4 phases, 4 plans (2026-03-11)
**v2.0 (in progress):** Phase 32 plan 01 -- 8min, 2 tasks, 4 files

## Accumulated Context

### Key Decisions (v2.0)
- Push dispatch driven entirely by resolve_environment() -- is_default_branch gate removed
- No environments configured = no push deploys (breaking change from v1.x, acceptable)
- auto_deploy: false = completely silent on push (no dispatch, no check run, no comment)
- Branch deletions and tag pushes return before auth step (zero API calls)
- All push compare bases use before_sha (incremental), not default_branch
- ENV-03 updated: "no Ferry activity" instead of "v1.x behavior"

### Blockers/Concerns
- None for current phase
- Carry-forward: `pr_lookup_failed` (403) on push events -- relevant for E2E validation

## Session Continuity

Last session: 2026-03-13
Stopped at: Completed 32-01-PLAN.md (Push Path Environment Resolution)
Next step: Phase 33 (Action v3 Parsing and Outputs) or continue with remaining v2.0 phases.
