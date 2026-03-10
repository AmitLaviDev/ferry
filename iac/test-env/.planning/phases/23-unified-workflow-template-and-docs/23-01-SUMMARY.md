---
phase: 23-unified-workflow-template-and-docs
plan: 01
status: complete
started: 2026-03-10
completed: 2026-03-10
---

# Plan 23-01 Summary: Unified Workflow Template and Docs

## What Changed

### docs/setup.md
- Replaced "Workflow File Naming Convention" section (old per-type table) with new "Workflow File" section containing the complete `ferry.yml` template
- Template includes: `run-name` with `fromJson` guard, workflow-level `env:` block (`AWS_ROLE_ARN`, `AWS_REGION`), `setup` job with `matrix` + `resource_type` outputs, three conditional deploy jobs (`deploy-lambda`, `deploy-step-function`, `deploy-api-gateway`) each with `if` guard, `strategy.matrix`, `fail-fast: false`, and job-level `concurrency` group
- No workflow-level `concurrency:` key (prevents cross-type cancellation)
- Added "Migration from Per-Type Workflows" subsection with 3-step deploy ordering
- Updated Installation step 2: references single `ferry.yml` instead of per-type files
- Updated OIDC step 4: references `AWS_ROLE_ARN` secret in `ferry.yml` template
- Updated How Dispatch Works step 3: references `ferry.yml` instead of `ferry-lambdas.yml`
- Updated Per-Resource-Type Guides intro: describes type pages as resource configuration guides (no workflow setup)

### docs/lambdas.md
- Removed "Workflow File" section (lines 28-107) including the `ferry-lambdas.yml` template
- Retained: ferry.yaml Configuration, Field Reference, Runtime Override, Magic Dockerfile

### docs/step-functions.md
- Removed "Workflow File" section (lines 26-87) including the `ferry-step_functions.yml` template
- Retained: ferry.yaml Configuration, Field Reference, Variable Substitution, Terraform Lifecycle, Content-Hash Skip Detection

### docs/api-gateways.md
- Removed "Workflow File" section (lines 28-90) including the `ferry-api_gateways.yml` template
- Retained: ferry.yaml Configuration, Field Reference, Spec Format, Terraform Lifecycle, Content-Hash Skip Detection

## Verification

- `setup.md` has exactly 1 `## Workflow File` heading: PASS
- Template contains `run-name`, `deploy-lambda`, `deploy-step-function`, `deploy-api-gateway`: PASS
- Migration guide section present: PASS
- Old "Workflow File Naming Convention" section removed: PASS
- No stale per-type filename references outside migration guide: PASS
- Type pages have no `## Workflow File` sections: PASS
- Type pages retain all non-workflow content: PASS
- Regression tests: Pre-existing moto credential issue (expired SSO token interfering with mock_aws) — affects all moto-based tests equally on clean tree; not caused by this phase

## Requirements Covered

| Req | Description | Status |
|-----|-------------|--------|
| WF-01 | ferry.yml has setup + 3 conditional deploy jobs | Done |
| WF-02 | Lambda job uses matrix strategy | Done |
| WF-03 | SF job uses matrix strategy | Done |
| WF-04 | APGW job uses matrix strategy | Done |
| WF-05 | run-name shows resource type | Done |
| WF-06 | No workflow-level concurrency; job-level groups | Done |
| DOC-01 | setup.md has template + migration guide | Done |
| DOC-02 | Type pages have workflow sections removed | Done |
