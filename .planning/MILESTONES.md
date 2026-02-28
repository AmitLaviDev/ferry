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

**What's next:** v1.1 — environment management, multi-account support, or reliability features

---

