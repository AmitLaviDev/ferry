# Ferry

## What This Is

Ferry is a hosted GitHub App that automates deploying serverless AWS resources (Lambda functions, Step Functions, API Gateways). It follows the Digger Cloud model: a thin backend receives GitHub webhooks, detects which resources changed, and triggers GitHub Actions workflows. The actual build and deploy logic runs in the user's GHA runners via a reusable Ferry Action. Users install the Ferry GitHub App, add a `ferry.yaml` to their repo, and Ferry handles change detection, container builds, and deployments.

"Serverless deploys serverless" — Ferry's backend is 1-2 Lambdas. The heavy lifting runs in users' GHA runners.

## Core Value

When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed — with full visibility on the PR before merge.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Receive and validate GitHub webhooks (push events, HMAC-SHA256 signature)
- [ ] Deduplicate webhook deliveries (DynamoDB conditional write)
- [ ] Read ferry.yaml from user's repo via GitHub API (App JWT auth)
- [ ] Detect changed resources by comparing commit diff against ferry.yaml path mappings
- [ ] Trigger one workflow_dispatch per resource type for changed resources
- [ ] Post PR status checks via GitHub Checks API (preview of what will deploy)
- [ ] Build Lambda containers using magic Dockerfile pattern, push to ECR
- [ ] Deploy Lambda functions (update code, publish version, point alias)
- [ ] Deploy Step Functions (update state machine definition with envsubst)
- [ ] Deploy API Gateways (update OpenAPI spec, create deployment)
- [ ] Handle AWS authentication via OIDC (user passes role ARN, Ferry Action does the exchange)

### Out of Scope

- Web dashboard — no UI beyond GitHub PR status
- AI discovery — no automatic resource detection, ferry.yaml is explicit
- SageMaker model deployment — different workflow, not serverless
- Multi-account AWS — single target account per workflow run
- Environment/branch mapping — v2 feature
- RBAC / permissions — relies on GitHub App installation permissions
- SQS / complex event processing — keep backend thin
- Rollback capability — user re-deploys previous commit manually
- ECR repo creation — user's IaC creates ECR repos, Ferry pushes to them

## Context

### Reference Implementation

Two existing repos at ConvergeBio demonstrate the full pattern Ferry must replicate:

**pipelines-hub** (code + CI):
- Repo structure: `{pipeline}/lambdas/{FunctionName}/` with `main.py` + `requirements.txt`
- Change detection: `tj-actions/changed-files` with merge-base comparison
- Build: "Magic Dockerfile" that works for ANY Lambda (optional `system-requirements.txt`, `system-config.sh`)
- Deploy Lambdas: `int128/deploy-lambda-action` (digest-based skip, version/alias management)
- Deploy Step Functions: `aws stepfunctions update-state-machine` with envsubst
- Deploy API Gateway: `aws apigateway put-rest-api` + `create-deployment`
- Auth: OIDC → management account → role-chain to target account
- Deployment tags: `pr-{number}` from main, `{branch}-{commit}` from manual dispatch

**iac-tf** (infrastructure):
- Terraform creates Lambda/StepFunction/APIGateway with placeholder images
- Uses `lifecycle { ignore_changes = [image_uri] }` — IaC owns infrastructure, Ferry owns code deployment
- Three connection points per resource: code directory ↔ IaC resource/module ↔ ECR repo name

### The Magic Dockerfile (Key Differentiator)

A single generic Dockerfile that builds ANY Lambda function:
- Requires only `main.py` + `requirements.txt`
- Optional `system-requirements.txt` for OS packages (glob trick: `COPY system-requirements.tx[t]`)
- Optional `system-config.sh` for post-install scripts
- Supports private GitHub repos via build secrets (`org_repos_token`)
- No per-function Dockerfile needed — this is Ferry's core UX win

### Architecture

**Ferry App (Hosted Backend):**
```
GitHub push event → Ferry Lambda (webhook validation, dedup)
  → Read ferry.yaml from repo (GitHub API, App JWT)
  → Compare commit diff against path mappings
  → Trigger workflow_dispatch per resource type (only changed resources)
  → Post PR status check (shows what will deploy)
```
Multi-tenant: single Lambda handles all GitHub App installations, identified by installation ID. Backend = 1-2 Lambdas + DynamoDB.

**Ferry Action (GHA Runner):**
```
workflow_dispatch → User's workflow calls ferry-action
  → Ferry Action authenticates to AWS (OIDC, user-provided role ARN)
  → Builds containers (magic Dockerfile) → pushes to ECR
  → Deploys: Lambda / Step Function / API Gateway
  → Reports result
```
Runs entirely in user's GHA runner. Zero Ferry infrastructure for execution.

**Dispatch Model:**
One `workflow_dispatch` per resource type. A push changing 3 Lambdas and 1 Step Function sends 2 dispatches:
1. Lambdas dispatch (payload lists the 3 changed Lambda resources)
2. Step Functions dispatch (payload lists the 1 changed Step Function)

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
| GitHub App + Action (not action-only) | PR previews + smart triggering justify the backend complexity | — Pending |
| Hosted SaaS (not self-hosted) | Lower friction for users — install and go | — Pending |
| One dispatch per resource type | Clean separation — each type has different build/deploy steps | — Pending |
| No defaults in ferry.yaml | Explicit > magical — what you see is what you get | — Pending |
| Magic Dockerfile as core pattern | One Dockerfile for all Lambdas — key differentiator and UX win | — Pending |
| OIDC auth (Digger model) | No stored AWS credentials — user passes role ARN, action does OIDC exchange | — Pending |
| Pre-existing ECR repos | IaC owns infrastructure, Ferry owns code deployment — clean separation | — Pending |
| No rollbacks in v1 | Keep scope tight — user re-deploys previous commit | — Pending |

---
*Last updated: 2026-02-21 after initialization*
