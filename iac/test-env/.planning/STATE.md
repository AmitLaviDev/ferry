# Project State

## Project Reference

See: .planning/PROJECT.md (in main ferry repo)
See: .planning/ROADMAP.md (this directory)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** Next milestone planning

## Current Position

Milestone: v1.4 Unified Workflow -- COMPLETE
Phase: All phases complete (22, 23, 24)
Status: Milestone shipped
Last activity: 2026-03-10 -- Phase 24 executed, all 3 resource types validated E2E

```
v1.4 Progress: [##########] 3/3 phases (22 done, 23 done, 24 done)
```

## Shipped Milestones

| Version | Name | Phases | Shipped |
|---------|------|--------|---------|
| v1.0 | MVP | 1-10 | 2026-02-28 |
| v1.1 | Deploy to Staging | 11-14 | 2026-03-03 |
| v1.2 | End-to-End Validation | 15-17 | 2026-03-08 |
| v1.3 | Full-Chain E2E | 18-21 | 2026-03-10 |
| v1.4 | Unified Workflow | 22-24 | 2026-03-10 |

## Performance Metrics

**Velocity (v1.0):**
- Total plans completed: 20
- Average duration: 4min
- Total execution time: 1.27 hours

**v1.1:** 5 phases, 8 plans (2026-02-28 to 2026-03-03)
**v1.2:** 3 phases, 9 plans (2026-03-03 to 2026-03-08)
**v1.3:** 4 phases, 7 plans (2026-03-08 to 2026-03-10)
**v1.4:** 3 phases, 3 plans (2026-03-10)

## Accumulated Context

### Key Decisions (v1.4)
- Lambdas use matrix strategy (parallel), SF and APGW use sequential loop (no matrix)
- Backend keeps per-type dispatch model, just changes target filename to ferry.yml
- Deploy order: user repo gets ferry.yml first, then backend switches dispatch target
- No backward compatibility period needed (single test repo)
- `resource_type` string comparison for routing (not boolean outputs) -- simpler, sufficient for v1.4

### Research Findings
- All GHA behavioral questions resolved with HIGH confidence (parallel dispatches, skipped jobs, concurrency groups, run-name)
- No new libraries or dependencies needed
- 4 small code edits + 1 new workflow template + doc updates
- Critical pitfalls documented: concurrency groups, migration order, empty matrix, indistinguishable run names, atomic test updates

### Blockers/Concerns
- None for v1.4 (all technical questions resolved via research)
- Carry-forward: `pr_lookup_failed` (403) on push events -- relevant for v2.0, not v1.4

## Session Continuity

Last session: 2026-03-10
Stopped at: v1.4 milestone complete. All phases shipped.
Next step: Plan next milestone (v2.0 PR Integration or other priority).
