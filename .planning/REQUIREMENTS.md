# Requirements: Ferry

**Defined:** 2026-03-10
**Core Value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.

## v1.4 Requirements

Requirements for Unified Workflow milestone. Each maps to roadmap phases.

### Workflow Template

- [ ] **WF-01**: Single `ferry.yml` file handles all resource types (replaces `ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`)
- [ ] **WF-02**: Each dispatch triggers only the matching type's job via conditional routing (`if: needs.setup.outputs.resource_type == '<type>'`)
- [ ] **WF-03**: Lambda deploy job uses matrix strategy for parallel per-resource builds
- [ ] **WF-04**: Step Functions deploy job uses sequential loop (no matrix overhead)
- [ ] **WF-05**: API Gateway deploy job uses sequential loop (no matrix overhead)
- [ ] **WF-06**: Workflow runs display resource type in GHA UI via `run-name`

### Backend

- [ ] **BE-01**: All dispatches target `ferry.yml` regardless of resource type
- [ ] **BE-02**: Remove/replace `RESOURCE_TYPE_WORKFLOW_MAP` with single workflow filename constant

### Action

- [ ] **ACT-01**: Setup action exposes `resource_type` as a workflow output
- [ ] **ACT-02**: Setup action outputs matrix JSON (existing behavior preserved)

### Documentation

- [ ] **DOC-01**: Docs updated with unified `ferry.yml` template and setup instructions
- [ ] **DOC-02**: Migration guide documents deploy order (user repo first, backend second)

### Validation

- [ ] **VAL-01**: Test repo migrated from 3 workflow files to single `ferry.yml`
- [ ] **VAL-02**: E2E push-to-deploy works for all 3 resource types via unified workflow

## Future Requirements

### v2.0 PR Integration

- **PR-01**: On pull_request events, show what resources would be built/deployed (dry-run preview)
- **PR-02**: On merge or explicit trigger, execute actual build and deploy
- **PR-03**: Mid-way deployments to staging/preview environments from PRs
- **PR-04**: Environment/branch mapping (e.g., main -> prod, develop -> staging)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Single dispatch with all types | Overcomplicates payload structure; per-type dispatch model works well |
| Workflow-level concurrency groups | Known GHA bug with `inputs` context; not needed for v1.4 |
| Hiding skipped jobs in GHA UI | GHA limitation, no workaround available |
| Backward compatibility (old + new filenames) | Only one test repo; clean cut is sufficient |
| Multi-tenant migration tooling | v2+ concern when other orgs use Ferry |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| WF-01 | Phase 23 | Pending |
| WF-02 | Phase 23 | Pending |
| WF-03 | Phase 23 | Pending |
| WF-04 | Phase 23 | Pending |
| WF-05 | Phase 23 | Pending |
| WF-06 | Phase 23 | Pending |
| BE-01 | Phase 22 | Pending |
| BE-02 | Phase 22 | Pending |
| ACT-01 | Phase 22 | Pending |
| ACT-02 | Phase 22 | Pending |
| DOC-01 | Phase 23 | Pending |
| DOC-02 | Phase 23 | Pending |
| VAL-01 | Phase 24 | Pending |
| VAL-02 | Phase 24 | Pending |

**Coverage:**
- v1.4 requirements: 14 total
- Mapped to phases: 14
- Unmapped: 0

---
*Requirements defined: 2026-03-10*
*Last updated: 2026-03-10 after roadmap creation (phases 22-24 mapped)*
