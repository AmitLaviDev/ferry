# Requirements: Ferry v2.0 PR Integration

**Defined:** 2026-03-12
**Core Value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.

## v2.0 Requirements

Requirements for PR Integration milestone. Each maps to roadmap phases.

### Plan Preview

- [ ] **PLAN-01**: Ferry posts a sticky PR comment showing which resources would be deployed when a PR is opened
- [ ] **PLAN-02**: Ferry updates the sticky PR comment when new commits are pushed to the PR
- [ ] **PLAN-03**: Plan comment shows the target environment name (if environments configured)
- [ ] **PLAN-04**: Ferry creates a Check Run on the PR reflecting plan status (success/failure)
- [ ] **PLAN-05**: User can comment `/ferry plan` on a PR to manually trigger a plan preview

### Deploy Triggers

- [ ] **DEPLOY-01**: Ferry auto-deploys affected resources when a PR merges to a mapped branch
- [ ] **DEPLOY-02**: User can trigger deploy from a PR by commenting `/ferry apply`
- [ ] **DEPLOY-03**: `/ferry apply` deploys to the environment mapped to the PR's target branch
- [ ] **DEPLOY-04**: Ferry ignores `/ferry apply` comments on issues (non-PR)

### Environment Mapping

- [ ] **ENV-01**: User can define environments in ferry.yaml with branch-to-environment mapping
- [ ] **ENV-02**: Ferry resolves the correct environment name based on the branch being deployed to
- [ ] **ENV-03**: When no environment matches (or no environments configured), Ferry deploys without an environment (v1.x behavior)

### GitHub Environments

- [ ] **GHENV-01**: Workflow deploy jobs use `environment:` with the resolved environment name
- [ ] **GHENV-02**: GHA natively injects environment-level secrets and vars into deploy jobs

### Payload & Compatibility

- [ ] **COMPAT-01**: Dispatch payload v3 includes `mode`, `environment`, `head_ref`, and `base_ref` fields
- [ ] **COMPAT-02**: Setup action outputs `mode` and `environment` for workflow consumption
- [ ] **COMPAT-03**: Users must update to v2.0 workflow template (breaking change from v1.x template)

## Future Requirements

### v3+ Deferred

- **ENVADV-01**: `/ferry apply <env>` comment to override target environment
- **ENVADV-02**: Per-environment resource overrides in ferry.yaml (environment-specific aliases, stage names)
- **ENVADV-03**: Branch glob patterns for environment mapping (e.g., `release/*` -> staging)
- **PERM-01**: Permission check on `/ferry apply` commenter (verify write access)
- **PLAN-06**: Build dry-run in plan mode (verify container build succeeds without pushing)
- **PLAN-07**: Diff preview showing what changed in each resource

## Out of Scope

| Feature | Reason |
|---------|--------|
| Ephemeral preview environments | Ferry deploys to user's AWS; creating/destroying Lambdas per PR is massive scope |
| Fork PR support | Security concerns (fork PRs can't access secrets); defer with proven security model |
| Manual approval UI | GitHub Environments protection rules handle this natively |
| Concurrency/locking for mid-PR deploys | Adds significant complexity; defer to v3 |
| Per-environment resource overrides | Start simple; branch=env mapping is sufficient for v2.0 |
| Branch glob patterns | Exact-match string is sufficient for v2.0 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PLAN-01 | Phase 30 | Pending |
| PLAN-02 | Phase 30 | Pending |
| PLAN-03 | Phase 30 | Pending |
| PLAN-04 | Phase 30 | Pending |
| PLAN-05 | Phase 31 | Pending |
| DEPLOY-01 | Phase 32 | Pending |
| DEPLOY-02 | Phase 31 | Pending |
| DEPLOY-03 | Phase 31 | Pending |
| DEPLOY-04 | Phase 31 | Pending |
| ENV-01 | Phase 29 | Pending |
| ENV-02 | Phase 32 | Pending |
| ENV-03 | Phase 32 | Pending |
| GHENV-01 | Phase 34 | Pending |
| GHENV-02 | Phase 34 | Pending |
| COMPAT-01 | Phase 29 | Pending |
| COMPAT-02 | Phase 33 | Pending |
| COMPAT-03 | Phase 34 | Pending |

**Coverage:**
- v2.0 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0

---
*Requirements defined: 2026-03-12*
*Last updated: 2026-03-12 after roadmap creation*
