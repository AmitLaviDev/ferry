# Requirements: Ferry

**Defined:** 2026-03-10
**Core Value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.

## v1.5 Requirements

Requirements for Batched Dispatch milestone. Each maps to roadmap phases.

### Dispatch

- [ ] **DISP-01**: Backend sends a single workflow_dispatch per push containing all affected resource types in one payload
- [ ] **DISP-02**: Batched payload uses schema version field (v=2) to distinguish from v1 per-type payloads
- [ ] **DISP-03**: Backend falls back to per-type dispatch if combined payload exceeds 65,535 character limit

### Action

- [ ] **ACT-01**: Setup action outputs per-type boolean flags (has_lambdas, has_step_functions, has_api_gateways)
- [ ] **ACT-02**: Setup action outputs per-type matrix JSON (lambda_matrix, sf_matrix, ag_matrix)
- [ ] **ACT-03**: Setup action outputs resource_types string (comma-separated list of affected types) for run-name
- [ ] **ACT-04**: Setup action parses both v1 (per-type) and v2 (batched) payloads for backward compatibility during rollout

### Template

- [ ] **TMPL-01**: Deploy jobs gate on boolean flags (if: has_lambdas == 'true') instead of resource_type string comparison
- [ ] **TMPL-02**: Each deploy job references its own per-type matrix output (fromJson(needs.setup.outputs.lambda_matrix))
- [ ] **TMPL-03**: Workflow run-name dynamically displays all affected resource types

### Validation

- [ ] **VAL-01**: Multi-type push (touching all 3 types) produces 1 workflow run with all 3 deploy jobs active
- [ ] **VAL-02**: Single-type push produces 1 workflow run with 1 active deploy job and 2 skipped

## Future Requirements

### v2.0 PR Integration

- **PR-01**: On pull_request events, show what resources would be built/deployed (dry-run preview)
- **PR-02**: On merge or explicit trigger, execute actual build and deploy
- **PR-03**: Mid-way deployments to staging/preview environments from PRs
- **PR-04**: Environment/branch mapping (e.g., main -> prod, develop -> staging)

### Deferred from v1.5

- **DEF-01**: Ordered cross-type deploys (Lambda before SF before APGW) -- add in v2.0
- **DEF-02**: Aggregated status reporting (one Check Run summary for all types) -- add in v2.0

## Out of Scope

| Feature | Reason |
|---------|--------|
| Eliminating skipped-job UI noise entirely | GHA limitation -- static job model cannot hide skipped jobs |
| Ordered cross-type deploys | Types deploy independently in parallel; dependency chain is v2.0 |
| Aggregated status reporting | Each deploy job posts its own Check Run; summary job is v2.0 polish |
| Workflow-level concurrency groups | Known GHA bug with `inputs` context; job-level groups sufficient |
| Multi-tenant migration tooling | v2+ concern when other orgs use Ferry |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DISP-01 | TBD | Pending |
| DISP-02 | TBD | Pending |
| DISP-03 | TBD | Pending |
| ACT-01 | TBD | Pending |
| ACT-02 | TBD | Pending |
| ACT-03 | TBD | Pending |
| ACT-04 | TBD | Pending |
| TMPL-01 | TBD | Pending |
| TMPL-02 | TBD | Pending |
| TMPL-03 | TBD | Pending |
| VAL-01 | TBD | Pending |
| VAL-02 | TBD | Pending |

**Coverage:**
- v1.5 requirements: 12 total
- Mapped to phases: 0
- Unmapped: 12

---
*Requirements defined: 2026-03-10*
*Last updated: 2026-03-10 after initial definition*
