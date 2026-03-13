---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: PR Integration
status: phase_complete
stopped_at: Phase 31 complete -- issue comment handler and deploy dispatch
last_updated: "2026-03-13T00:00:00.000Z"
last_activity: 2026-03-13 -- Phase 31 executed
progress:
  total_phases: 7
  completed_phases: 3
  total_plans: 3
  completed_plans: 3
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-12)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** v2.0 PR Integration -- Phase 31 complete

## Current Position

Milestone: v2.0 PR Integration
Phase: 31 of 35 (Issue Comment Handler / /ferry apply) -- COMPLETE
Plan: 31-01 (Command parser, handlers, dedup, tests) -- DONE
Status: Phase 31 complete
Last activity: 2026-03-13 -- Phase 31 executed

```
v2.0 Progress: [████░░░░░░] 43%
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

## Accumulated Context

### Key Decisions (v1.5)

- Batched payload uses named per-type lists (lambdas, step_functions, api_gateways) not a flat discriminated union
- Boolean flags gate deploy jobs (prevents empty-matrix fromJson crash)
- Schema version v=2 distinguishes batched from legacy payloads
- v: Literal[2] enforces version at type level for discriminated union parsing
- No feature flag -- v2 batched dispatch is the only path, v1 exists solely as >65KB fallback

### Carry-forward Concerns

- Python 3.14 arm64 Lambda base image availability (fallback: Python 3.13)
- `pr_lookup_failed` (403) on push events -- relevant for v2.0
- GitHub App webhook subscriptions for `pull_request`, `issue_comment`, and `workflow_run` are manual steps

### Key Decisions (v2.0)

- Non-sticky plan comments: each PR event or /ferry plan creates a new comment (simpler, no race conditions)
- PR handler uses base branch (not before SHA) for compare -- shows full PR diff
- No dispatch for plan mode -- zero GHA runner minutes
- Check Run conclusion: `success` when resources detected, `neutral` when no changes
- Draft PRs treated same as regular PRs
- SHA-specific apply markers: `<!-- ferry:apply:{sha} -->` for targeted status updates
- Rocket reaction posted before any processing (even on closed PRs)
- Fresh head SHA always fetched from GET /pulls/{number} for /ferry apply

## Session Continuity

Last session: 2026-03-13
Stopped at: Phase 31 complete -- issue comment handler and deploy dispatch
Next step: Plan and execute phase 32 (Push Path Environment Resolution)
