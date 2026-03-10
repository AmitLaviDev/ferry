# Roadmap: v1.4 Unified Workflow

**Milestone:** v1.4 Unified Workflow
**Phases:** 22-24 (3 phases)
**Requirements:** 14 (WF-01..WF-06, BE-01..BE-02, ACT-01..ACT-02, DOC-01..DOC-02, VAL-01..VAL-02)
**Granularity:** Standard
**Started:** 2026-03-10

## Milestone Goal

Consolidate three per-type workflow files (`ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`) into a single `ferry.yml` so users maintain one workflow file regardless of how many resource types they use.

## Phases

- [ ] **Phase 22: Backend and Action Code Changes** - Backend dispatches to `ferry.yml`; setup action exposes `resource_type` output
- [ ] **Phase 23: Unified Workflow Template and Docs** - Create `ferry.yml` template with conditional jobs per type; update documentation
- [ ] **Phase 24: Test Repo Migration and E2E Validation** - Migrate test repo to unified workflow; prove all 3 resource types deploy via single file

## Phase Details

### Phase 22: Backend and Action Code Changes
**Goal**: The backend dispatches all resource types to `ferry.yml` and the setup action exposes `resource_type` as a workflow output for conditional job routing
**Depends on**: Nothing (first phase of v1.4)
**Requirements**: BE-01, BE-02, ACT-01, ACT-02
**Success Criteria** (what must be TRUE):
  1. `constants.py` has a single `WORKFLOW_FILENAME = "ferry.yml"` constant and `RESOURCE_TYPE_WORKFLOW_MAP` is removed
  2. `trigger.py` uses the new constant for all dispatch calls regardless of resource type
  3. `setup/action.yml` exposes `resource_type` as an output alongside the existing `matrix` output
  4. `parse_payload.py` calls `set_output("resource_type", ...)` to populate the new output
  5. All existing tests pass with updated assertions (old workflow filenames replaced atomically)
**Plans:** 1 plan
Plans:
- [ ] 22-01-PLAN.md -- Unify dispatch to ferry.yml and add resource_type output

### Phase 23: Unified Workflow Template and Docs
**Goal**: A complete `ferry.yml` workflow template exists that routes each dispatch to the correct deploy job, and documentation guides users through setup and migration
**Depends on**: Phase 22 (template references `resource_type` output from setup action)
**Requirements**: WF-01, WF-02, WF-03, WF-04, WF-05, WF-06, DOC-01, DOC-02
**Success Criteria** (what must be TRUE):
  1. `ferry.yml` template contains a shared `setup` job and three conditional deploy jobs (lambda, step-function, api-gateway) with job-level `if` guards
  2. Lambda deploy job uses matrix strategy for parallel per-resource builds
  3. Step Functions and API Gateway deploy jobs each use matrix strategy with `fail-fast: false` (per CONTEXT.md override)
  4. Workflow uses `run-name` that displays the resource type in the GHA Actions UI
  5. No workflow-level concurrency group exists (only job-level concurrency keyed by type)
  6. Docs include the unified `ferry.yml` template and a migration guide with deploy ordering (user repo first, backend second)
**Plans:** 1 plan
Plans:
- [ ] 23-01-PLAN.md -- Add unified ferry.yml template to setup.md and remove per-type workflow sections from type pages

### Phase 24: Test Repo Migration and E2E Validation
**Goal**: The test repo runs on the unified `ferry.yml` and all three resource types deploy successfully via Ferry dispatch
**Depends on**: Phase 22, Phase 23
**Requirements**: VAL-01, VAL-02
**Success Criteria** (what must be TRUE):
  1. `AmitLaviDev/ferry-test-app` has a single `.github/workflows/ferry.yml` file
  2. The three old workflow files (`ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`) are deleted from the test repo
  3. A push changing a Lambda source triggers Ferry dispatch, the lambda deploy job runs, and the Lambda is updated
  4. A push changing a Step Function definition triggers Ferry dispatch, the step-function deploy job runs, and the state machine is updated
  5. A push changing an API Gateway spec triggers Ferry dispatch, the api-gateway deploy job runs, and the REST API is updated
**Plans**: TBD

## Coverage

| Requirement | Phase | Category |
|-------------|-------|----------|
| BE-01 | Phase 22 | Backend |
| BE-02 | Phase 22 | Backend |
| ACT-01 | Phase 22 | Action |
| ACT-02 | Phase 22 | Action |
| WF-01 | Phase 23 | Workflow Template |
| WF-02 | Phase 23 | Workflow Template |
| WF-03 | Phase 23 | Workflow Template |
| WF-04 | Phase 23 | Workflow Template |
| WF-05 | Phase 23 | Workflow Template |
| WF-06 | Phase 23 | Workflow Template |
| DOC-01 | Phase 23 | Documentation |
| DOC-02 | Phase 23 | Documentation |
| VAL-01 | Phase 24 | Validation |
| VAL-02 | Phase 24 | Validation |

**Mapped: 14/14**

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 22. Backend and Action Code Changes | 1/1 | Complete | 2026-03-10 |
| 23. Unified Workflow Template and Docs | 0/1 | Planned | - |
| 24. Test Repo Migration and E2E Validation | 0/? | Not started | - |

## Key Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Workflow-level concurrency group cancels parallel dispatches | Do NOT add workflow-level concurrency; use job-level groups keyed by type name |
| Backend deployed before `ferry.yml` exists in user repo | Follow strict migration order: user repo first, then backend deploy |
| Empty matrix crash when `if` guard is missing | Job-level `if` gates matrix evaluation; never put routing logic at step level only |
| Old test assertions break after constant rename | Update all test assertions atomically in same commit as constant change |

---
*Roadmap created: 2026-03-10*
