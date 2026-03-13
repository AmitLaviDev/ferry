# Ferry

## What This Is

Ferry is a hosted GitHub App that automates deploying serverless AWS resources (Lambda functions, Step Functions, API Gateways). It follows the Digger Cloud model: a thin backend receives GitHub webhooks, detects which resources changed, and triggers GitHub Actions workflows. The actual build and deploy logic runs in the user's GHA runners via a reusable Ferry Action. Users install the Ferry GitHub App, add a `ferry.yaml` to their repo, and Ferry handles change detection, container builds, and deployments.

"Serverless deploys serverless" — Ferry's backend is 1 Lambda + DynamoDB. The heavy lifting runs in users' GHA runners.

## Core Value

When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed — with full visibility on the PR before merge.

## Requirements

### Validated

- ✓ Receive and validate GitHub webhooks (HMAC-SHA256 signature) — v1.0
- ✓ Deduplicate webhook deliveries (DynamoDB conditional write) — v1.0
- ✓ Read ferry.yaml from user's repo via GitHub API (App JWT auth) — v1.0
- ✓ Detect changed resources by comparing commit diff against ferry.yaml path mappings — v1.0
- ✓ Trigger one workflow_dispatch per resource type for changed resources — v1.0
- ✓ Post PR Check Runs via GitHub Checks API (preview of what will deploy) — v1.0
- ✓ Build Lambda containers using Magic Dockerfile pattern, push to ECR — v1.0
- ✓ Deploy Lambda functions (update code, publish version, point alias) — v1.0
- ✓ Deploy Step Functions (update state machine definition with envsubst) — v1.0
- ✓ Deploy API Gateways (update OpenAPI spec, create deployment) — v1.0
- ✓ Handle AWS authentication via OIDC (user passes role ARN, Ferry Action does the exchange) — v1.0
- ✓ Surface build/deploy failures in PR Check Runs and GHA workflow logs — v1.0
- ✓ Bootstrap Terraform state backend (S3 bucket) in Ferry's own AWS account — v1.1
- ✓ Create ECR repo for Ferry Lambda container — v1.1
- ✓ Set up shared IAM roles and policies for Lambda execution — v1.1
- ✓ Store GitHub App secrets in Secrets Manager — v1.1
- ✓ Deploy Ferry Lambda with Function URL — v1.1
- ✓ Deploy DynamoDB table for webhook dedup — v1.1
- ✓ Create self-deploy GHA workflow (build, push ECR, update Lambda) — v1.1
- ✓ Register GitHub App setup runbook — v1.1
- ✓ Apply Terraform IaC and deploy Ferry infrastructure to AWS — v1.2
- ✓ Register GitHub App and populate Secrets Manager credentials — v1.2
- ✓ Create test repo with ferry.yaml, hello-world Lambda, and dispatch workflow — v1.2
- ✓ Set up test infrastructure (ECR repo + OIDC role for test repo GHA) — v1.2
- ✓ Full push-to-deploy loop works: push → webhook → detect → dispatch → build → deploy — v1.2
- ✓ Fix all bugs surfaced during end-to-end testing (9 bugs found and fixed) — v1.2
- ✓ Clean up 5 tech debt items from v1.2 (error handling, IAM, docs, Docker warning, error mapping) — v1.3
- ✓ Deploy Step Functions via Ferry (definition update, version publish, content-hash skip) — v1.3
- ✓ Deploy API Gateways via Ferry (spec upload, deployment create, content-hash skip) — v1.3
- ✓ Full chain works: APGW → SF → Lambda, all deployed via Ferry dispatch — v1.3
- ✓ Two-level skip detection: dispatch-level (no affected resources) and deploy-level (content-hash unchanged) — v1.3
- ✓ Multi-type dispatch: single push triggers parallel deploys for all affected resource types — v1.3
- ✓ Unified workflow: single `ferry.yml` with conditional jobs per resource type — v1.4
- ✓ Backend dispatches all types to `ferry.yml` (single target filename) — v1.4
- ✓ Setup action exposes `resource_type` output for conditional job routing — v1.4
- ✓ Docs updated with unified template and migration guide — v1.4
- ✓ Batched dispatch: single workflow_dispatch per push with all affected types in one payload — v1.5
- ✓ Per-type boolean flags and matrices for clean GHA job routing — v1.5
- ✓ v2 payload schema with automatic >65KB fallback to per-type v1 dispatch — v1.5
- ✓ Backward-compatible v1/v2 payload parsing in setup action — v1.5

### Active

- [ ] PR change detection: On PR open/sync, detect which resources would be deployed and post preview as PR comment
- [ ] PR deploy on merge: Automatically deploy affected resources when PR merges to target branch
- [ ] Comment-triggered deploy: `/ferry apply` comment on PR triggers mid-way deploy to mapped environment
- [ ] Environment mapping: User-defined environments in ferry.yaml with branch-to-environment mapping
- [ ] GitHub Environment support: Workflow jobs use `environment: <name>` so GHA natively injects env-level secrets/vars
- [ ] Mid-way deployments: Deploy to staging/preview environments from PRs before merge via comment trigger

### Out of Scope

- Web dashboard — the PR is the dashboard, no frontend/auth investment
- AI discovery — no automatic resource detection, ferry.yaml is explicit
- SageMaker model deployment — different workflow, not serverless compute
- Multi-account AWS — single target account per workflow run for v1
- ~~Unified workflow (single `ferry.yml` instead of per-type workflow files) — shipped in v1.4~~
- ~~PR integration with "ferry plan" / "ferry apply" and mid-way deployments — moved to v2.0 Active~~
- Environment/branch mapping — v2.0
- RBAC / permissions — relies on GitHub App installation permissions
- SQS / complex event processing — keep backend thin, process synchronously
- Rollback capability — user re-deploys previous commit; cross-resource rollback is unsolved for serverless
- ECR repo creation — user's IaC creates ECR repos, Ferry pushes to them
- Drift detection — process problem, not a tooling problem for v1
- Local dev/testing — Ferry is a CI/CD tool, not a dev tool

## Context

### Current State

v1.5 shipped. Batched dispatch: one push produces one workflow_dispatch with all affected resource types in a single payload. Clean GHA UI with only relevant deploy jobs active.
- ~10,000 lines of Python across ~170 files + 1,290 lines of Terraform
- Tech stack: Python 3.14, uv workspace, Pydantic v2, httpx, PyJWT, boto3, moto
- Three packages: ferry-backend (backend Lambda), ferry-action (composite GHA action), ferry-shared (Pydantic models)
- 320 tests passing, 0 lint errors
- Infrastructure live: Lambda + Function URL + DynamoDB + Secrets Manager + ECR
- Self-deploy pipeline working (push to main → build → ECR → Lambda update)
- Full push-to-deploy loop proven with test repo (2 successful deploys + no-op skip)

### Architecture

**Ferry App (Hosted Backend):**
```
GitHub push event → Ferry Lambda (webhook validation, dedup)
  → Read ferry.yaml from repo (GitHub API, App JWT)
  → Compare commit diff against path mappings
  → Trigger workflow_dispatch per resource type (only changed resources)
  → Post PR Check Run (shows what will deploy)
  → Surface config errors as PR comments
```
Multi-tenant: single Lambda handles all GitHub App installations, identified by installation ID. Backend = 1 Lambda + DynamoDB.

**Ferry Action (GHA Runner):**
```
workflow_dispatch → User's workflow calls ferry-action
  → Ferry Action authenticates to AWS (OIDC, user-provided role ARN)
  → Builds containers (Magic Dockerfile) → pushes to ECR
  → Deploys: Lambda / Step Function / API Gateway
  → Reports success/failure via Check Runs
```
Runs entirely in user's GHA runner. Zero Ferry infrastructure for execution.

**Dispatch Model:**
One batched `workflow_dispatch` per push (v1.5). A push changing 3 Lambdas and 1 Step Function sends 1 dispatch containing all affected types. Deploy jobs gate on per-type boolean flags; only relevant jobs run. Falls back to per-type dispatch if payload exceeds 65KB.

### ferry.yaml Design

Grouped by resource type. Type-aware fields. No defaults block — explicit config only. File name: `ferry.yaml` in repo root.

```yaml
version: 1
lambdas:
  order-processor:
    source: services/order-processor
    iac: module.order_processor
    ecr: ferry/order-processor
  payment-handler:
    source: services/payment-handler
    iac: module.payment_handler
    ecr: ferry/payment-handler
step_functions:
  checkout-flow:
    source: workflows/checkout
    iac: module.checkout_flow
api_gateways:
  main-api:
    source: definitions/api_gateway.yaml
    iac: module.api_gateway
```

### Known Tech Debt

- `build.py` CalledProcessError exits via `raise` instead of `sys.exit(1)` — produces Python traceback in GHA logs (cosmetic)
- Webhook models (WebhookHeaders, PushEvent, Pusher, Repository) defined and tested but unused in production code
- `gha.mask_account_id()` defined but never called — `build.py` uses `gha.mask_value()` instead
- Debug logging in deploy.py (raw error output) — should be removed
- deploy.py error mapping assumes AccessDeniedException = caller lacks permission, but can also mean target role lacks permissions
- Docker credential warning in build.py (cosmetic)
- Workflow template docs missing `name:` field for cleaner GHA job names

## Constraints

- **Language**: Python — both backend Lambda and GHA action logic
- **Backend infra**: Lambda + DynamoDB only. No SQS, no queues. Process synchronously.
- **Hosting model**: Hosted SaaS — we run the backend, users install the GitHub App
- **Code quality**: Fully typed (Pydantic models, typed signatures), Pythonic idioms, Ruff linting + formatting, pytest + moto testing
- **Tooling**: uv workspace, pre-commit hooks, Python 3.14
- **AWS auth**: OIDC federation (Digger/OpenTaco model) — user passes role ARN, Ferry Action handles the exchange
- **ECR**: Pre-existing repos only — created by user's IaC, Ferry pushes to them
- **Explicit config**: No convention-based derivation. ferry.yaml is the source of truth.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| GitHub App + Action (not action-only) | PR previews + smart triggering justify the backend complexity | ✓ Good — enables Check Run previews and type-based dispatch |
| Hosted SaaS (not self-hosted) | Lower friction for users — install and go | ✓ Good — 1 Lambda + DynamoDB, minimal infra |
| One dispatch per resource type | Clean separation — each type has different build/deploy steps | ✓ Good — clean matrix per type, independent deploy scripts |
| No defaults in ferry.yaml | Explicit > magical — what you see is what you get | ✓ Good — function_name defaults to key name at parse time |
| Magic Dockerfile as core pattern | One Dockerfile for all Lambdas — key differentiator and UX win | ✓ Good — supports private deps, system packages, multi-runtime |
| OIDC auth (Digger model) | No stored AWS credentials — user passes role ARN, action does OIDC exchange | ✓ Good — clean separation, works in GHA runners |
| Pre-existing ECR repos | IaC owns infrastructure, Ferry owns code deployment — clean separation | ✓ Good — no resource creation in deploy path |
| No rollbacks in v1 | Keep scope tight — user re-deploys previous commit | ✓ Good — kept scope focused |
| Composite action (not Docker action) | Ferry needs host Docker daemon for builds; Docker-in-Docker is fragile | ✓ Good — direct access to Docker, clean Python scripts |
| Config errors as PR comments (not Check Runs) | PR comments persist across pushes; Check Runs are per-commit | ✓ Good — errors visible without navigating checks tab |
| Digest-based deploy skip | Skip Lambda/SF/APGW deploy when content unchanged | ✓ Good — saves deploy time and avoids unnecessary versions |
| Envsubst for Step Functions | Safe regex: only ${ACCOUNT_ID} and ${AWS_REGION}, preserves JSONPath | ✓ Good — avoids corrupting state machine definitions |
| Ferry repo public | GHA can't reference composite actions from private repos | ✓ Good — required for cross-repo action references |
| importlib.resources for bundled files | `__file__` unreliable in installed packages | ✓ Good — correct Python pattern for package data |
| ECR repo policy with Lambda service principal | Lambda pulls images via its own service principal, not execution role | ✓ Good — required for container image Lambdas |

## Future Design Notes

### v1.4: Unified workflow file (SHIPPED)
Consolidated three per-type workflow files into single `ferry.yml`. Backend dispatches all types to `ferry.yml`, setup action exposes `resource_type`, conditional jobs route by type. Used Option B (minimal backend change — one dispatch per type, same filename).

### v1.5: Batched dispatch
Currently each resource type triggers a separate `workflow_dispatch` to `ferry.yml`, resulting in 3 workflow runs (with 2 skipped jobs each) when a push touches all 3 types. Batch all affected types into a single dispatch so the user sees 1 clean workflow run with only the relevant deploy jobs active. Touches: backend dispatch logic (batch types into single payload), setup action (output multiple matrices), workflow template (remove `if` guards or make multi-type aware), payload schema.

### v2.0: PR integration — "ferry plan" / "ferry apply"
Currently Ferry only handles `push` events on the default branch. v2.0 adds `pull_request` event handling with a plan/apply model:
- **ferry plan**: On `pull_request` (opened, synchronize, reopened), run dry-run change detection and build preview. Post results as PR comment or Check Run showing what resources would be deployed.
- **ferry apply**: On merge to target branch (or explicit comment trigger like `/ferry apply`), execute the actual build and deploy.
- **Mid-way deployments**: Deploy to staging/preview environments from PRs before merge. Requires environment mapping in ferry.yaml (e.g., `main` → prod, `develop` → staging).
- Touches: webhook handler (new event types), dispatch model (plan vs apply mode), ferry.yaml schema (environment config), action scripts (dry-run mode), PR comment formatting.

## Current Milestone: v2.0 PR Integration

**Goal:** Add PR-triggered deployments with a plan/apply model — preview what will deploy on PR open/update, deploy on merge or explicit `/ferry apply` comment, with user-defined environment mapping and GitHub Environment support.

**Target features:**
- ferry plan: detect changed resources on PR and post preview as PR comment
- ferry apply: auto-deploy on merge + `/ferry apply` comment trigger for mid-way deploys
- Environment mapping: user-defined environments in ferry.yaml (branch → environment)
- GitHub Environment support: workflow jobs use `environment:` for native secrets/vars injection
- Mid-way deployments: deploy to staging/preview from PRs before merge

### Future: Selective Deploy Flags (post-v2.0 milestone)
`/ferry apply` gains resource-type and resource-level flags so developers can deploy a subset of the plan. Examples:
- `/ferry apply --lambdas` — deploy only Lambda resources from the plan
- `/ferry apply --lambda order-processor` — deploy a single named resource
- Applies to any combination of types and names. Useful when a plan shows changes across multiple types but the developer wants incremental rollout.

---
*Last updated: 2026-03-13 after phase 31 discussion*
