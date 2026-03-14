---
phase: 35-e2e-validation
plan: 01
status: complete
started: 2026-03-14
completed: 2026-03-14
---

# Phase 35 Summary: E2E Validation

## Results

All 5 success criteria validated end-to-end:

| SC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| SC#1 | Plan preview comment | PASS | Comment lists 3 resources + "→ staging", `/ferry plan` retrigger works |
| SC#2 | /ferry apply deploy | PASS | Dispatch against PR branch, all 3 deploy jobs succeeded |
| SC#3 | Merge auto-deploy | PASS | Auto-deploy with `→ staging`, Lambda shows "v2.0 merged" |
| SC#4 | Environment secrets | PASS | Deploys succeeded with env-scoped `AWS_ROLE_ARN` only |
| SC#5 | Negative test | PASS | Unmapped branch push = zero Ferry activity |

## Workflow Runs

- `/ferry apply` deploy: run 23087241682 (v2-e2e-validation branch, success)
- Merge auto-deploy: run 23087319281 (main branch, success)
- Previous `/ferry apply` (before dispatch ref fix): run 23086985507 (main branch — deployed old code)

## Resource Verification

- **Lambda** (`ferry-test-hello-world`): `"hello from ferry v2.0 merged"` confirmed via invoke
- **Step Function** (`ferry-test-sf`): `"Ferry v2.0 E2E validation"` in definition Comment
- **API Gateway** (`v1h1ch5rqk`): `"Ferry v2.0 E2E validation"` in description

## Bugs Found and Fixed

1. **`issues:write` missing from token** — installation token didn't request issues:write, causing 403 on PR comments. Fixed in `auth/tokens.py`.
2. **`pull_requests:write` needed** — GitHub requires pull_requests:write to comment on PRs via Issues API, even with issues:write. Fixed in `auth/tokens.py` and GitHub App permissions.
3. **Dispatch ref was always `main`** — `/ferry apply` dispatched against default branch instead of PR head branch, so `actions/checkout@v4` got main's code, not the PR's. Fixed in `handler.py` to use `head_branch` as dispatch ref.
4. **`pr_comment_posted` logged on 403** — no status check before logging success. Fixed in `checks/runs.py`.
5. **Test mock missing `head.ref`** — PR mock data didn't include `head.ref` field needed by the dispatch ref fix. Fixed in `test_handler_comment.py`.

## GitHub App Permission Changes

- Added: `Pull requests: Read and write` (required for PR comments)
- Added: `Issues: Read and write` (required for PR comments via Issues API)
- Events subscribed: Push, Pull request, Issue comment, Workflow run

## UX Issues Identified (deferred to Phase 36)

1. Reaction emoji: rocket → should be boat
2. Plan comment format: plain list → table with resource details (function name, ECR, etc.)
3. Plan comment footer "will be deployed when merged" is misleading (can also `/ferry apply`)
4. Deploy comment is vague ("3 resource(s)") — should list resources explicitly
5. Deploy comment should be sticky and updated per-resource as jobs complete
6. ECR image tags on merge: tagged as `main-{hash}`, should preserve branch context
