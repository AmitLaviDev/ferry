# Phase 36 Context: PR Comment UX Polish

**Phase Goal:** Improve PR comment readability and deploy visibility -- table format with resource details, sticky deploy comment with per-resource status, fixed footer text.
**Requirements:** UX feedback from Phase 35 E2E validation
**Created:** 2026-03-14

## Decisions

### 1. Plan comment: table format with resource details

Current plan comment is a simple bullet list:
```
- **hello-world** _(modified)_
```

New format: a markdown table with type-specific details pulled from `FerryConfig`:

| Resource | Type | Details |
|----------|------|---------|
| hello-world | Lambda | `ferry-test-hello-world` / `ferry-test/hello-world` |
| hello-chain | Step Function | `ferry-test-sf` |
| hello-chain | API Gateway | `v1h1ch5rqk` / stage `test` |

**Detail strings by type:**
- Lambda: `{function_name}` / `{ecr_repo}`
- Step Function: `{state_machine_name}`
- API Gateway: `{rest_api_id}` / stage `{stage_name}`

**Implementation:** Pass `FerryConfig` to `format_plan_comment`. Add a `_resource_detail` helper that looks up config by name+type and returns the detail string.

### 2. Footer text: mention /ferry apply

Current: "_These resources will be deployed to **staging** when this PR is merged._"
Problem: misleading -- `/ferry apply` also deploys.

New: "_Deploy with `/ferry apply` or merge to auto-deploy to **staging**._"
Variant for `auto_deploy: false`: "_Deploy with `/ferry apply`. Manual deployment to **production** after merge._"
Variant for no environment: "_Deploy with `/ferry apply` or merge._"

### 3. Sticky deploy comment (one per PR)

Current: Each `/ferry apply` creates a new comment with `<!-- ferry:apply:{sha} -->`. The `workflow_run` handler finds it by SHA.

New: Single deploy comment per PR with marker `<!-- ferry:deploy:{pr_number} -->`. Each `/ferry apply` upserts (find-or-update) this comment. Embedded `<!-- ferry:sha:{sha} -->` for workflow_run correlation.

**Apply comment format (initial):**
```
<!-- ferry:deploy:42 -->
<!-- ferry:sha:abc123def456789 -->
## 🚢 Ferry: Deploying → **staging** at `abc123d`

| Resource | Type | Status |
|----------|------|--------|
| hello-world | Lambda | ⏳ |
| hello-chain | Step Function | ⏳ |
| hello-chain | API Gateway | ⏳ |
```

**Apply comment format (after workflow_run):**
```
<!-- ferry:deploy:42 -->
<!-- ferry:sha:abc123def456789 -->
## 🚢 Ferry: Deployed → **staging** at `abc123d`

| Resource | Type | Status |
|----------|------|--------|
| hello-world | Lambda | ✅ |
| hello-chain | Step Function | ✅ |
| hello-chain | API Gateway | ✅ |

✅ `success` — [View run](https://github.com/...)
```

**Race protection:** `workflow_run` handler extracts `trigger_sha` from dispatch payload AND from `<!-- ferry:sha:{sha} -->` in the comment. Only updates if they match. If a new `/ferry apply` overwrote the comment with a different SHA, the old workflow_run completion is silently skipped.

### 4. Reaction emoji: rocket stays (GitHub limitation)

GitHub's reaction API only supports: `+1`, `-1`, `laugh`, `confused`, `heart`, `hooray`, `rocket`, `eyes`. There is no boat/ship emoji reaction. The boat emoji (🚢) is already used in comment headers. Keeping `rocket` for the reaction.

**Deferred:** If we want to remove the reaction entirely and rely only on comment headers, that can be a future change.

### 5. Per-resource status: workflow-level (not per-job)

When `workflow_run` completes, all resource rows get the same status based on overall workflow conclusion:
- `success` → ✅ for all rows
- `failure` → ❌ for all rows
- `cancelled` → ⚠️ for all rows

**Deferred:** True per-job status (fetching individual job conclusions and mapping them to resources) requires changing GHA job display names to include resource type. This is a future improvement.

### 6. Merge deploy: post deploy comment on merged PR

Currently push-triggered deploys (from merge) have no PR comment visibility. With the sticky deploy marker, the push handler can:
1. Find the merged PR via `find_merged_pr()`
2. Create/update the deploy comment on it

This gives merge deploys the same visibility as `/ferry apply` deploys.

### 7. format_apply_comment needs config + affected (not just count)

To show the resource table, `format_apply_comment` needs the list of affected resources (for the table rows). It already receives `affected`, but now also needs config for detail strings.

### 8. find_deploy_comment replaces find_apply_comment

New function `find_deploy_comment(client, repo, pr_number)` searches for `<!-- ferry:deploy:{pr_number} -->`. Simpler than the SHA-based search since it's keyed on PR number (always known).

`find_apply_comment` is removed (dead code after this change).

## Prior Decisions (locked from phases 29-35)

- Non-sticky plan comments -- each PR event creates a new comment (kept)
- Environment-gated push dispatch (phase 32)
- Action outputs mode and environment (phase 33)
- SHA-specific apply markers -- REPLACED by PR-level deploy markers in this phase
- Rocket reaction before processing (kept, see decision #4)
- Fresh head SHA fetched from GET /pulls/{number} for /ferry apply (kept)

## Code Context

### Files to modify

- `backend/src/ferry_backend/checks/plan.py` -- all formatter changes, new helpers, remove old apply functions
- `backend/src/ferry_backend/webhook/handler.py` -- pass config to formatters, use upsert for deploy comments, push handler deploy comment
- `backend/src/ferry_backend/checks/runs.py` -- add `update_pr_comment` helper
- `tests/test_backend/test_plan.py` -- update all formatter tests
- `tests/test_backend/test_handler_pr.py` -- update plan comment assertions
- `tests/test_backend/test_handler_comment.py` -- update apply comment assertions
- `tests/test_backend/test_handler_workflow.py` -- update workflow_run assertions

### Key interfaces

- `format_plan_comment(affected, config, environment)` -- new signature with config
- `format_apply_comment(affected, config, environment, head_sha)` -- new signature with config
- `format_apply_status_update(original_body, conclusion, run_url)` -- signature unchanged, new body format
- `find_deploy_comment(client, repo, pr_number)` -- replaces find_apply_comment
- `upsert_deploy_comment(client, repo, pr_number, body)` -- find-or-create, returns comment dict

---
*Context created: 2026-03-14*
