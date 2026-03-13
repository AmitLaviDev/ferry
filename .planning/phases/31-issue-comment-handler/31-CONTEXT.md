# Phase 31 Context: Issue Comment Handler (/ferry plan + /ferry apply)

**Phase Goal:** Developers can interact with Ferry via PR comments -- `/ferry plan` re-triggers plan preview, `/ferry apply` triggers deploy.
**Requirements:** PLAN-05, DEPLOY-02, DEPLOY-03, DEPLOY-04
**Created:** 2026-03-13

## Decisions

### 1. Command parsing strictness

**Decision:** Case-insensitive, whitespace-tolerant, entire-comment-body match. Trailing text after the command is silently ignored.

- `/ferry plan` and `/ferry apply` must be the entire comment body (not embedded in prose)
- Leading/trailing whitespace and extra spaces between words are tolerated
- Case-insensitive: `/Ferry Apply`, `/FERRY PLAN` all accepted
- Trailing arguments (e.g., `/ferry apply staging`) are accepted but ignored -- the environment is always resolved from the PR's target branch
- Forward-compatible: when SELFDEP-01/02/03 land, the parser starts reading flags instead of ignoring them

**Rationale:** Strict "whole comment" matching avoids false positives from casual mentions. Whitespace/case tolerance avoids user frustration. Ignoring trailing text is forward-compatible with future flag support.

### 2. `/ferry apply` acknowledgment UX

**Decision:** Reaction emoji + new apply comment per invocation, updated with final status via `workflow_run` webhook.

#### Reaction emoji
- Both `/ferry plan` and `/ferry apply` get a :ship: reaction emoji on the triggering comment as immediate acknowledgment ("Ferry saw this")
- Reaction is added even when no resources are affected

#### Plan comments (one per invocation)
- **NOT sticky.** Each plan invocation (push sync OR `/ferry plan`) creates a **new** comment
- This is a **change from phase 30** which used `<!-- ferry:plan -->` to find-and-update a single sticky comment
- Phase 30's `find_plan_comment` / `upsert_plan_comment` sticky logic must be replaced with simple `post` calls
- "No changes" case: post a new "no changes" comment (not silent)

#### Apply comments (one per invocation, with status updates)
- Each `/ferry apply` creates a new comment with a unique marker: `<!-- ferry:apply:{sha} -->`
- Initial content: "Deploy triggered for N resources to **{env}**..."
- Updated with final status (success/failure) when `workflow_run` webhook arrives
- Correlation: `workflow_run` payload contains trigger SHA in workflow inputs, matched to apply comment marker

#### `workflow_run` webhook handling
- New event type to handle in `handler.py`: `workflow_run` with `action: "completed"`
- Extracts conclusion (`success`/`failure`/`cancelled`) and trigger SHA from workflow inputs
- Finds the apply comment by marker `<!-- ferry:apply:{sha} -->` and updates it with final status
- **Manual step required:** GitHub App webhook subscriptions must have `workflow_run` enabled

### 3. `/ferry apply` with no affected resources

**Decision:** Refuse to dispatch. Post a comment saying no resources affected.

- `/ferry apply` runs fresh change detection (same logic as plan), not reading from a previous plan comment
- If zero resources found, Ferry does NOT dispatch -- posts a comment like "No Ferry-managed resources affected -- nothing to deploy"
- Reaction emoji still added to the triggering comment
- Plan and apply are data-independent: plan comments are purely informational, apply always runs its own detection

### 4. Closed/merged PR handling

**Decision:** Post a comment saying "PR is not open -- `/ferry apply` requires an open PR."

- Check `payload["issue"]["state"]` -- if not `open`, refuse and post explanatory comment
- Reaction emoji still added
- Same behavior for `/ferry plan` on closed PRs

## Prior Decisions (locked from phases 29/30)

- `resolve_environment()` maps PR base branch to environment via `ferry.yaml` `environments[].branch`
- `trigger_dispatches()` handles batched v2 dispatch with mode/environment fields
- v3 payload model has `mode`, `environment`, `head_ref`, `base_ref` fields
- Guard `issue_comment` on issues vs PRs: check `payload["issue"]["pull_request"]` exists
- Deploy uses current PR head SHA fetched fresh from GitHub API, not stale reference
- No permission checks on `/ferry apply` commenter (PERM-01 deferred to v3+)
- Check Run: reuse existing `create_check_run()` -- conclusion `success` when resources detected, `neutral` when no changes

## Code Context

### Existing assets to reuse
- `backend/src/ferry_backend/checks/plan.py` -- `resolve_environment()`, `format_plan_comment()`, `format_no_changes_comment()` (reuse formatting, remove sticky upsert logic)
- `backend/src/ferry_backend/checks/runs.py` -- `create_check_run()`, `post_pr_comment()`
- `backend/src/ferry_backend/webhook/handler.py` -- Add `issue_comment` and `workflow_run` routing alongside existing `push` and `pull_request` paths
- `backend/src/ferry_backend/webhook/dedup.py` -- Dual-key dedup for new event types
- `backend/src/ferry_backend/dispatch/trigger.py` -- `trigger_dispatches()` for `/ferry apply` dispatch
- `backend/src/ferry_backend/github/client.py` -- `get()`, `post()`, `patch()` for API calls + new reaction endpoint

### Phase 30 code to modify
- `plan.py`: Remove `find_plan_comment()` and `upsert_plan_comment()` (sticky logic). Replace with direct `post_pr_comment()` calls. Keep `format_plan_comment()`, `format_no_changes_comment()`, `resolve_environment()`
- `handler.py` `_handle_pull_request()`: Change from upsert to post for plan comments

### New GitHub API calls needed
- `POST /repos/{owner}/{repo}/issues/comments/{comment_id}/reactions` -- Add :ship: reaction to triggering comment
- `GET /repos/{owner}/{repo}/issues/{pr_number}/comments` -- Find apply comment by `<!-- ferry:apply:{sha} -->` marker (for `workflow_run` status update)
- `PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}` -- Update apply comment with final status

### New handler functions needed
- `_handle_issue_comment(payload, repo)` -- Parse command, guard PR-only, route to plan or apply
- `_handle_workflow_run(payload, repo)` -- Match completed workflow to apply comment, update status

## Deferred Ideas

- **Selective deploy flags** (v3+ milestone): `/ferry apply --lambdas`, `/ferry apply --lambda order-processor` -- deploy subset of planned resources. Tracked as SELFDEP-01/02/03 in REQUIREMENTS.md.

---
*Context created: 2026-03-13*
