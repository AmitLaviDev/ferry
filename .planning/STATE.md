---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: PR Integration
status: in_progress
stopped_at: Phase 35 complete -- E2E validation passed, UX polish remaining
last_updated: "2026-03-14T12:00:00Z"
last_activity: 2026-03-14 -- Phase 35 E2E validation executed
progress:
  total_phases: 8
  completed_phases: 7
  total_plans: 7
  completed_plans: 7
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-12)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** v2.0 PR Integration -- Phase 35 E2E complete, Phase 36 UX Polish remaining

## Current Position

Milestone: v2.0 PR Integration
Phase: 35 of 36 (E2E Validation) -- COMPLETE
Next: Phase 36 (PR Comment UX Polish)
Status: E2E validation passed, UX improvements identified
Last activity: 2026-03-14 -- Phase 35 E2E validation

```
v2.0 Progress: [█████████░] 88%
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

### Key Decisions (v2.0)

- Non-sticky plan comments: each PR event or /ferry plan creates a new comment (simpler, no race conditions)
- PR handler uses base branch (not before SHA) for compare -- shows full PR diff
- No dispatch for plan mode -- zero GHA runner minutes
- Check Run conclusion: `success` when resources detected, `neutral` when no changes
- Draft PRs treated same as regular PRs
- SHA-specific apply markers: `<!-- ferry:apply:{sha} -->` for targeted status updates
- Rocket reaction posted before any processing (even on closed PRs)
- Fresh head SHA always fetched from GET /pulls/{number} for /ferry apply
- v1 DispatchPayload now has mode/environment with defaults (backward compatible)
- ParseResult and GHA outputs extended with mode and environment
- /ferry apply dispatches against PR head branch (not default branch) for correct checkout
- GitHub App needs pull_requests:write to comment on PRs via Issues API

### Carry-forward Concerns

- Python 3.14 arm64 Lambda base image availability (fallback: Python 3.13)

### Phase 35 Bugs Fixed

1. Token missing issues:write and pull_requests:write for PR comments
2. Dispatch ref was always main (not PR branch) for /ferry apply
3. pr_comment_posted logged success on 403
4. Test mocks missing head.ref

## Session Continuity

Last session: 2026-03-14
Stopped at: Phase 35 complete -- E2E validation passed
Next step: Plan and execute Phase 36 (PR Comment UX Polish)
