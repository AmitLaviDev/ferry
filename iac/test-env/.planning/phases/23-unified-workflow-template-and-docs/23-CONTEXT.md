# Phase 23 Context: Unified Workflow Template and Docs

## Decisions

### 1. Matrix strategy for ALL resource types
- Lambda, Step Functions, and API Gateway deploy jobs all use `strategy.matrix` with `fail-fast: false`
- No special-casing for SF/APGW — same pattern as Lambda
- Rationale: no conflict risk between parallel deploys of same type; consistent structure across all jobs
- Prior "sequential loop" requirement is overridden — matrix for all

### 2. One workflow-level `env:` block
- `AWS_ROLE_ARN` (from secrets) and `AWS_REGION` set once at the workflow level
- All jobs inherit — no repetition per step or per job
- Users configure these values in one place only

### 3. Unified template lives in `setup.md` only
- Full `ferry.yml` template shown in `setup.md` — single source of truth
- Type-specific pages (`lambdas.md`, `step-functions.md`, `api-gateways.md`) have their workflow template sections REMOVED
- Type pages keep: ferry.yaml config, field reference, and type-specific details (Magic Dockerfile, variable substitution, Terraform lifecycle, content-hash skip detection, spec format)
- No workflow snippets duplicated in type pages

### 4. Migration guide is a section in `setup.md`
- Not a separate page — short section within `setup.md`
- Content: deploy ordering (add `ferry.yml` to user repo first, then deploy backend update)
- Minimal scope — only one test repo, no external users yet

## Code Context

### Files to create
- `docs/` does NOT get a workflow file — the template is shown inline in `setup.md` as a code block for users to copy

### Files to modify
- `docs/setup.md` — Add unified `ferry.yml` template section; replace per-type workflow naming section (lines 54-66); add migration guide section
- `docs/lambdas.md` — Remove "Workflow File" section (lines 28-107); keep everything else
- `docs/step-functions.md` — Remove "Workflow File" section (lines 26-87); keep everything else
- `docs/api-gateways.md` — Remove "Workflow File" section (lines 28-90); keep everything else

### Workflow template structure (for reference)
```yaml
# ferry.yml structure:
# - workflow-level env: AWS_ROLE_ARN, AWS_REGION
# - run-name: shows resource type
# - setup job: parse payload → matrix + resource_type outputs
# - deploy-lambda job: if resource_type == 'lambda', matrix strategy
# - deploy-step-function job: if resource_type == 'step_function', matrix strategy
# - deploy-api-gateway job: if resource_type == 'api_gateway', matrix strategy
```

### Dependencies on Phase 22
- Setup action must expose `resource_type` output (ACT-01)
- Setup action must expose `matrix` output (ACT-02, existing)
- Backend must dispatch to `ferry.yml` filename (BE-01, BE-02)

## Deferred Ideas
None captured during discussion.

---
*Created: 2026-03-10*
