---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: PR Integration
status: unknown
stopped_at: Completed 37-02-PLAN.md (Action deploy, composite actions, docs, E2E validation) -- v2.1 milestone complete
last_updated: "2026-03-15T07:50:02.370Z"
last_activity: 2026-03-15 -- Phase 37 Plan 02 executed, v2.1 shipped
progress:
  total_phases: 8
  completed_phases: 6
  total_plans: 9
  completed_plans: 7
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-12)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** v2.1 Schema Simplification -- COMPLETE

## Current Position

Milestone: v2.1 Schema Simplification -- COMPLETE
Phase: 37 (Schema Simplification) -- COMPLETE
Plan 01: COMPLETE (schema models, dispatch models, trigger builder, tests)
Plan 02: COMPLETE (action deploy code, composite actions, docs, E2E validation)
Last activity: 2026-03-15 -- Phase 37 Plan 02 executed, v2.1 shipped

```
v2.1 Progress: [##########] 2/2 plans
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
| v2.0 | PR Integration | 29-36 | 2026-03-14 |
| v2.1 | Schema Simplification | 37 | 2026-03-15 |

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
- Deploy comments: each /ferry apply creates a NEW comment (not upsert), SHA marker for workflow_run correlation
- Eyes reaction (not rocket) posted before any processing (even on closed PRs)
- Fresh head SHA always fetched from GET /pulls/{number} for /ferry apply
- v1 DispatchPayload now has mode/environment with defaults (backward compatible)
- ParseResult and GHA outputs extended with mode and environment
- /ferry apply dispatches against PR head branch (not default branch) for correct checkout
- GitHub App needs pull_requests:write to comment on PRs via Issues API

### Key Decisions (Phase 36 UX)

- Plan comment: summary counts + collapsible `<details>` table (scales to many resources)
- Table column order: Type | Resource (Type first)
- No Details column -- removed function_name/ecr_repo/etc display (schema simplification deferred to Phase 37)
- Deploy comment: Type | Resource | Status table with per-resource status emoji, Tag bullet with {branch}-{sha4}
- Merge push handler creates deploy comment on merged PR with tag pr-{N}
- workflow_run handler correlates via commits->PR API (not dispatch inputs, which return null for GitHub App dispatches)
- Dedup key for workflow_run includes action (requested vs completed are distinct events)
- find_merged_pr falls back to state=closed when merged_at not yet propagated (GitHub API race condition)

### Key Decisions (v2.1 Schema Simplification)

- LambdaConfig.name IS the AWS function name -- no separate function_name field
- StepFunctionConfig.name IS the AWS state machine name -- no separate state_machine_name field
- mode="before" backward-compat validators silently strip deprecated fields before extra="forbid" sees them
- StepFunctionConfig: when name and state_machine_name both present and differ, state_machine_name wins (it is the AWS name)
- Composite action resource-name input IS the AWS resource name -- function-name and state-machine-name inputs removed
- Hard removal (not deprecation) of old inputs -- acceptable since no external users yet

### Post-v2.1 Bugfix: Merge commit PR number race condition

- GitHub API /commits/{sha}/pulls returns empty when push webhook fires ~4s after merge (indexing lag)
- Fix: parse "Merge pull request #N" from head_commit.message in push payload as fallback
- Also fixed deploy comment to post on merged PR even when pr_number came from message fallback (not API lookup)

### Carry-forward Concerns

- Python 3.14 arm64 Lambda base image availability (fallback: Python 3.13)

### Phase 35 Bugs Fixed

1. Token missing issues:write and pull_requests:write for PR comments
2. Dispatch ref was always main (not PR branch) for /ferry apply
3. pr_comment_posted logged success on 403
4. Test mocks missing head.ref

### Phase 36 Bugs Fixed (during E2E)

1. workflow_run dedup: "requested" and "completed" shared same event key (missing action)
2. workflow_run inputs null: GitHub API returns null inputs for App-dispatched runs; switched to commits->PR API
3. Deploy comment was upsert per-PR: changed to new comment per /ferry apply, workflow_run updates by SHA marker
4. Rocket reaction changed to eyes
5. find_merged_pr race condition: GitHub API returns closed PR without merged_at within seconds of merge

## Session Continuity

Last session: 2026-03-15
Stopped at: Completed 37-02-PLAN.md (Action deploy, composite actions, docs, E2E validation) -- v2.1 milestone complete

### What to do next

1. **Multi-tenant / other orgs** (v2+)
2. Define next milestone and phases
