# Phase 32 Context: Push Path Environment Resolution

**Phase Goal:** Merging a PR to a mapped branch automatically deploys affected resources to the correct environment.
**Requirements:** DEPLOY-01, ENV-02, ENV-03
**Created:** 2026-03-13

## Decisions

### 1. Environment-gated push dispatch (replaces default-branch gating)

**Decision:** Push dispatch is driven entirely by environment mapping. The old "is default branch?" gate is removed.

New push handler logic:
1. Extract branch from push `ref`
2. Ignore branch deletions (`deleted: true`) and tag pushes (`refs/tags/...`)
3. Call `resolve_environment(config, branch)`
4. No match → silent, done (no Check Run, no dispatch, nothing)
5. Match + `auto_deploy: true` → create Check Run (with environment name) + trigger dispatch
6. Match + `auto_deploy: false` → silent, done

**Key implications:**
- Non-default branches with environment mappings (e.g., `develop` → staging) now trigger dispatch
- Branches without environment mappings are completely silent — no noise on feature branch pushes
- No environments configured at all → pushes do nothing (breaking change from v1.x, acceptable since no external users)

**Rationale:** Clean 1:1 model — if you define a branch mapping, pushes to it auto-deploy. If you don't, Ferry ignores it. No special-casing for default branch.

### 2. No environments = no push deploys

**Decision:** If ferry.yaml has no `environments:` section, pushes produce zero Ferry activity.

- This deliberately breaks v1.x behavior (default branch pushes used to always dispatch)
- Acceptable because Ferry has no external users — only the test repo
- ENV-03 in REQUIREMENTS.md must be updated: "no environments configured" now means "no push deploys" instead of "deploy without environment name"

**Rationale:** Environments are the opt-in mechanism for push deploys. Cleaner than maintaining a fallback "default branch always deploys" path.

### 3. `auto_deploy: false` = silent on push

**Decision:** When an environment has `auto_deploy: false`, pushes to that branch are completely silent — no dispatch, no Check Run, no comment on the merged PR.

- The deploy window for `auto_deploy: false` environments is while the PR is open, via `/ferry apply`
- Once the PR merges and closes, posting comments on it is noise nobody sees
- No "deploy was skipped" notification

**Rationale:** By the time the push event fires, the PR is already merged and closed. Comments on closed PRs are invisible noise.

### 4. Direct pushes, force-pushes, and edge cases

**Decision:** Ferry treats all push events the same — it doesn't care how commits arrived on the branch.

| Push type | Behavior |
|-----------|----------|
| PR merge push | Resolve environment → dispatch if `auto_deploy: true` |
| Direct push (no PR) | Same as above |
| Force-push | Same as above |
| Branch deletion (`deleted: true`) | Silently ignored |
| Tag push (`refs/tags/...`) | Silently ignored (no branch match) |

**Rationale:** Ferry deploys what's at HEAD. The mechanism that put commits there is irrelevant.

## Prior Decisions (locked from phases 29/30/31)

- `resolve_environment(config, branch)` matches branch to `EnvironmentMapping` — returns first match or `None`
- `trigger_dispatches()` already accepts `mode`, `environment`, `head_ref`, `base_ref` params
- `BatchedDispatchPayload` v2 already has all environment fields
- `EnvironmentMapping` schema: `name`, `branch`, `auto_deploy` (default `True`)
- Non-sticky plan comments (phase 31 decision) — each invocation creates a new comment
- Check Run: `success` when resources detected, `neutral` when no changes

## Code Context

### What needs to change

**`handler.py` push handler** — The main change. Replace default-branch gating with environment-based gating:
- Add early returns for branch deletions and tag pushes
- Call `resolve_environment(config, branch)` after loading config
- Check `auto_deploy` flag
- Pass environment fields to `trigger_dispatches()`
- Pass environment name to Check Run

**`handler.py` imports** — Add `resolve_environment` from `checks.plan`

### What stays the same

- `resolve_environment()` in `checks/plan.py` — already works, no changes
- `trigger_dispatches()` in `dispatch/trigger.py` — already accepts environment params
- `BatchedDispatchPayload` in dispatch models — already has fields
- `EnvironmentMapping` in config schema — already has `auto_deploy` field
- Change detection logic — unchanged
- Dedup logic — unchanged

### Tests to add

- Push to mapped branch with `auto_deploy: true` → dispatch with environment name
- Push to mapped branch with `auto_deploy: false` → no dispatch, no Check Run
- Push to unmapped branch → silent (no dispatch, no Check Run)
- Push with no environments configured → silent
- Branch deletion event → ignored
- Tag push event → ignored
- Check Run includes environment name when dispatching

## REQUIREMENTS.md Updates

- **ENV-03**: Change from "deploy without environment (v1.x behavior)" to "no push deploys when no environments configured"

## Deferred Ideas

None captured during this discussion.

---
*Context created: 2026-03-13*
