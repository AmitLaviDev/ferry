# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-10)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** v1.4 Unified Workflow

## Current Position

Milestone: v1.4 Unified Workflow
Phase: 22 - Backend and Action Code Changes (not started)
Plan: --
Status: Roadmap created, ready for phase planning
Last activity: 2026-03-10 -- v1.4 roadmap created (phases 22-24)

```
v1.4 Progress: [..........] 0/3 phases
```

## Shipped Milestones

| Version | Name | Phases | Shipped |
|---------|------|--------|---------|
| v1.0 | MVP | 1-10 | 2026-02-28 |
| v1.1 | Deploy to Staging | 11-14 | 2026-03-03 |
| v1.2 | End-to-End Validation | 15-17 | 2026-03-08 |
| v1.3 | Full-Chain E2E | 18-21 | 2026-03-10 |

## Performance Metrics

**Velocity (v1.0):**
- Total plans completed: 20
- Average duration: 4min
- Total execution time: 1.27 hours

**v1.1:** 5 phases, 8 plans (2026-02-28 to 2026-03-03)
**v1.2:** 3 phases, 9 plans (2026-03-03 to 2026-03-08)
**v1.3:** 4 phases, 7 plans (2026-03-08 to 2026-03-10)

## Accumulated Context

### Key Decisions (v1.4)
- Lambdas use matrix strategy (parallel), SF and APGW use sequential loop (no matrix)
- Backend keeps per-type dispatch model, just changes target filename to ferry.yml
- Deploy order: user repo gets ferry.yml first, then backend switches dispatch target
- No backward compatibility period needed (single test repo)
- `resource_type` string comparison for routing (not boolean outputs) -- simpler, sufficient for v1.4

### v1.4 Roadmap
- Phase 22: Backend and Action Code Changes (BE-01, BE-02, ACT-01, ACT-02)
- Phase 23: Unified Workflow Template and Docs (WF-01..WF-06, DOC-01, DOC-02)
- Phase 24: Test Repo Migration and E2E Validation (VAL-01, VAL-02)
- Detailed roadmap: iac/test-env/.planning/ROADMAP.md

## Blockers/Concerns

- None for v1.4 (all technical questions resolved via research)
- Carry-forward: Python 3.14 arm64 Lambda base image availability (fallback: Python 3.13)
- Carry-forward: `pr_lookup_failed` (403) on push events -- relevant for v2.0, not v1.4

## Session Continuity

Last session: 2026-03-10
Stopped at: v1.4 roadmap created. Ready for phase planning.
Next step: `/gsd:plan-phase 22` (Backend and Action Code Changes)
No pending manual follow-ups.
