# Phase 34 Context: Workflow Template and GitHub Environments

**Phase Goal:** Users have a working ferry.yml template that surfaces environment secrets and enforces mode guards on deploy jobs.
**Requirements:** GHENV-01, GHENV-02, COMPAT-03
**Created:** 2026-03-13

## Decisions

### 1. Run name includes environment when present

The workflow `run-name` appends the environment with an arrow when present, omits it when not.

With environment:
```
Ferry Deploy: lambda,step_function → staging
```

Without environment (empty string):
```
Ferry Deploy: lambda,step_function
```

**Rationale:** Environment is the first thing you want to see in the Actions tab — "where is this deploying?" The arrow notation is compact and scannable.

### 2. Single template for all cases

One `ferry.yml` template that works with and without environments configured. No separate "basic" vs "full" templates.

- Deploy jobs always have `environment: ${{ needs.setup.outputs.environment }}`
- Empty environment string means GHA runs the job without Environment injection (no crash, no error)
- `mode == 'deploy'` guard layered into each deploy job's `if:` alongside existing boolean type gates

**Rationale:** Empty environment string is a no-op in GHA — the job runs normally without Environment-level secrets. One template means zero user decision and one thing to maintain.

### 3. Minimal documentation — just a webhook event checklist

No step-by-step guide or walkthrough. Ferry has no external users — the docs are a reference for the developer (us).

Documentation updates:
- Updated workflow template in `docs/setup.md`
- Short note listing which GitHub App webhook events to enable: `pull_request`, `issue_comment`, `workflow_run`
- Brief mention that GitHub Environments must be created in the repo settings to use environment-level secrets

**Rationale:** We're the only operator. A checklist is sufficient.

## Prior Decisions (locked from phases 29-33)

- Setup action outputs `mode` and `environment` (phase 33 — shipped)
- `mode` is always `"deploy"` in dispatched workflows — plan mode never dispatches (phase 30)
- Mode guard is defensive/future-proof — currently only `"deploy"` flows through
- `ParseResult` has `mode: str` and `environment: str` fields (phase 33)
- `BatchedDispatchPayload` and `DispatchPayload` both carry `mode` and `environment` (phases 29/33)
- Environment resolved from branch mapping by backend before dispatch (phase 32)
- `resolve_environment(config, branch)` returns first match or `None` (phase 29)
- Non-sticky plan comments — each invocation creates a new comment (phase 31)
- No environments configured = no push deploys (phase 32 breaking change, acceptable)

## Code Context

### Files to modify

| File | Change |
|------|--------|
| `docs/setup.md` | Update workflow template: add `mode`/`environment` to setup outputs, add `environment:` key to deploy jobs, add mode guard to deploy job `if:` conditions, update `run-name` with environment, add webhook events checklist |

### What stays the same (no code changes)

- `action/setup/action.yml` — already outputs `mode` and `environment` (phase 33)
- `action/src/ferry_action/parse_payload.py` — already parses and outputs mode/environment (phase 33)
- `utils/src/ferry_utils/models/dispatch.py` — already has fields on both payload models (phases 29/33)
- Backend handlers — already resolve and dispatch with environment (phases 30-32)

### Template changes (for downstream agents)

Setup job outputs to add:
```yaml
mode: ${{ steps.parse.outputs.mode }}
environment: ${{ steps.parse.outputs.environment }}
```

Deploy job `if:` condition pattern (example for lambda):
```yaml
if: needs.setup.outputs.has_lambdas == 'true' && needs.setup.outputs.mode == 'deploy'
```

Deploy job `environment:` key:
```yaml
environment: ${{ needs.setup.outputs.environment }}
```

Run name expression (conditional arrow + environment):
```yaml
run-name: "Ferry Deploy: ${{ <resource_types_expr> }}${{ <environment_expr> != '' && format(' → {0}', <environment_expr>) || '' }}"
```

### Webhook events to document

| Event | Purpose | Required for |
|-------|---------|-------------|
| `pull_request` | Plan comment on PR open/sync | Phase 30 |
| `issue_comment` | `/ferry plan` and `/ferry apply` commands | Phase 31 |
| `workflow_run` | Update apply comment with deploy status | Phase 31 |

## Deferred Ideas

None captured during this discussion.

---
*Context created: 2026-03-13*
