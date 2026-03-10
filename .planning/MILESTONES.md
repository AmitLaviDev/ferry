# Project Milestones: Ferry

## v1.0 MVP (Shipped: 2026-02-28)

**Delivered:** Serverless AWS deployment automation — a GitHub App backend detects changes and dispatches workflows, while a composite GitHub Action builds containers and deploys Lambda, Step Functions, and API Gateway resources.

**Phases completed:** 1-10 (20 plans total)

**Key accomplishments:**
- Three-package uv workspace with shared Pydantic data contract between App and Action
- Webhook pipeline: HMAC-SHA256 validation, DynamoDB dedup, GitHub App JWT auth
- Smart change detection via Compare API with type-based workflow_dispatch and PR Check Runs
- Magic Dockerfile builds any Lambda from main.py + requirements.txt, with ECR push and digest-based deploy skip
- Step Functions and API Gateway deployment with envsubst and content-hash skip
- Structured error surfacing: PR comments for config errors, Check Run reporting for build/deploy failures

**Stats:**
- 167 files created/modified
- 9,092 lines of Python
- 9 phases, 20 plans
- 7 days from start to ship (2026-02-21 → 2026-02-28)
- 272 tests passing

**Git range:** `feat(01-01)` → `feat(10-01)`

---

## v1.1 Deploy to Staging (Shipped: 2026-03-03)

**Delivered:** Terraform IaC, Dockerfile, GHA self-deploy workflow, GitHub App registration runbook -- everything needed to deploy Ferry to AWS and keep it updated.

**Phases completed:** 11-14 (8 plans total)

**Key accomplishments:**
- S3 state backend + ECR repository with lifecycle policy and placeholder image
- Shared IAM: Lambda execution role, OIDC provider, GHA deploy role, Secrets Manager containers
- IaC directory restructure to match ConvergeBio/iac-tf conventions
- Backend Lambda + Function URL + DynamoDB dedup table + CloudWatch logs
- Backend Dockerfile + self-deploy GHA workflow (push to main → build → ECR → Lambda update)
- Setup runbook documenting complete apply order and manual steps

**Stats:**
- 5 phases, 8 plans
- 4 days (2026-02-28 → 2026-03-03)

---

## v1.2 End-to-End Validation (Shipped: 2026-03-08)

**Delivered:** Deployed Ferry to AWS, proved the full push-to-deploy loop works end-to-end with a real test repo, fixed 9 bugs discovered during validation.

**Phases completed:** 15-17 (9 plans total)

**Key accomplishments:**
- Deployed all Ferry infrastructure to AWS (Lambda, DynamoDB, Function URL, IAM, Secrets Manager)
- Registered GitHub App and verified webhook delivery
- Created test environment (ECR repo, OIDC role, hello-world Lambda, test repo with ferry.yaml)
- Proved full push-to-deploy loop: push → webhook → detect → dispatch → build → deploy
- Found and fixed 9 bugs during E2E iteration (ECR permissions, PEP 668, Dockerfile bundling, etc.)
- Proved repeatability (2 successful deploys + correct no-op skip)

**Stats:**
- 3 phases, 9 plans
- 40 commits, 49 files changed (3,479 insertions, 214 deletions)
- 5 days (2026-03-03 → 2026-03-08)
- Codebase: 9,384 LOC Python + 1,290 LOC Terraform

---

## v1.3 Full-Chain E2E (Shipped: 2026-03-10)

**Delivered:** Full three-type deployment chain (APGW -> SF -> Lambda) proven end-to-end via Ferry dispatch, plus tech debt cleanup from v1.2.

**Phases completed:** 18-21 (7 plans total)

**Key accomplishments:**
- Cleaned up 5 tech debt items from v1.2
- Deployed Step Functions and API Gateway infrastructure for test environment
- Updated test repo with SF and APGW resources in ferry.yaml
- Proved full chain: push triggers dispatch for all 3 resource types, each deploys successfully
- Fixed 5 bugs discovered during chain validation

**Stats:**
- 4 phases, 7 plans
- 2 days (2026-03-08 → 2026-03-10)

---

## v1.4 Unified Workflow (Shipped: 2026-03-10)

**Delivered:** Single `ferry.yml` replaces three per-type workflow files. Backend dispatches all types to `ferry.yml`, setup action exposes `resource_type` for conditional job routing.

**Phases completed:** 22-24 (3 plans total)

**Key accomplishments:**
- Backend dispatch changed to target `ferry.yml` for all resource types
- Setup action exposes `resource_type` output for conditional job routing
- Unified `ferry.yml` template with conditional deploy jobs per type
- Test repo migrated from 3 workflow files to single `ferry.yml`
- All 3 resource types validated E2E through unified dispatch

**Stats:**
- 3 phases, 3 plans
- 1 day (2026-03-10)

---

## v1.5 Batched Dispatch (Active)

**Goal:** Single dispatch per push deploys all affected resource types in one workflow run (instead of one dispatch per type with skipped-job clutter in GHA UI).

**Phases:** 25-28 (4 phases)

**Target features:**
- Batch all affected resource types into a single workflow_dispatch payload (schema v2)
- Setup action outputs per-type boolean flags and matrices
- Workflow template gates deploy jobs on boolean flags with per-type matrix references
- Backward-compatible payload parsing (v1 and v2)
- Clean GHA UI: 1 workflow run per push, no skipped-job noise for multi-type pushes
