# Phase 16: Provision Test Environment - Context

**Gathered:** 2026-03-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Create a test repo (`AmitLaviDev/ferry-test-app`) with a hello-world Lambda, ferry.yaml, and GHA dispatch workflow, plus supporting AWS resources (ECR repo, OIDC role, Lambda function), so Phase 17 can exercise the full Ferry push-to-deploy loop.

</domain>

<decisions>
## Implementation Decisions

### Test repo setup
- Repo: `AmitLaviDev/ferry-test-app` (same GitHub user as Ferry)
- Private repository
- Kept long-term for regression testing future Ferry changes (not disposable)

### Hello-world Lambda design
- Bare minimum: single `main.py` with handler returning `{"message": "hello"}` + empty `requirements.txt`
- Python 3.12 runtime (latest stable Lambda runtime)
- Source directory: `lambdas/hello-world/` (nested under lambdas/ folder)
- Lambda function pre-created in AWS with placeholder image before Phase 17 (matches real workflow where user's IaC creates the function)

### AWS provisioning approach
- Same AWS account as Ferry (simplest for validation)
- Terraform project in the ferry repo at `iac/test-env/` — reproducible, matches conventions
- Reuse existing GitHub OIDC provider from Phase 12 — just add a new IAM role with trust policy scoped to `AmitLaviDev/ferry-test-app`
- Naming convention: `ferry-test-` prefix for all resources (e.g. `ferry-test/hello-world` for ECR, `ferry-test-deploy-role` for IAM, `ferry-test-hello-world` for Lambda)

### Test coverage scope
- Happy path only — one Lambda, one ferry.yaml entry, one workflow
- Minimal GHA workflow template — just `workflow_dispatch` trigger + `ferry-action` call with required inputs
- Smoke test included: invoke the pre-created Lambda after provisioning to confirm it responds before Phase 17
- Example README in test repo documenting ferry.yaml, workflow setup, and how to set up a new repo with Ferry (doubles as future user-facing docs)

### Claude's Discretion
- Exact Terraform module structure within `iac/test-env/`
- IAM policy specifics for the test deploy role (ECR push + Lambda update, scoped appropriately)
- Placeholder image strategy for the pre-created Lambda
- ferry.yaml exact field values (function_name, ecr_repo, etc.)
- GHA workflow exact structure and input mapping

</decisions>

<specifics>
## Specific Ideas

- Test repo doubles as a reference example for future Ferry users — README should document how to onboard a repo with Ferry
- `lambdas/hello-world/` directory layout is more realistic than top-level, matching how real repos would organize multiple Lambda functions
- Pre-creating the Lambda function matches Ferry's design philosophy: "IaC owns infrastructure, Ferry owns code deployment"

</specifics>

<deferred>
## Deferred Ideas

- Multi-resource testing (two Lambdas in ferry.yaml) — defer to v1.3 extended E2E
- Edge case scenarios (no-change pushes, subdirectory variations) — defer to v1.3
- Production-like GHA workflow (concurrency controls, environment protection) — defer to when real users need it

</deferred>

---

*Phase: 16-provision-test-environment*
*Context gathered: 2026-03-05*
