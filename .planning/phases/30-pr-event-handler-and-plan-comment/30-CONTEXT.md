# Phase 30 Context: PR Event Handler and Plan Comment

**Phase Goal:** Developers see which resources would be deployed as a sticky PR comment every time a PR is opened or updated.
**Requirements:** PLAN-01, PLAN-02, PLAN-03, PLAN-04
**Created:** 2026-03-12

## Decisions

### 1. Zero-change behavior

**Decision:** Silent on first open; update existing sticky comment if one exists.

When a PR is opened and no Ferry-managed resources are affected, do NOT post a comment. Only the Check Run (neutral) communicates "nothing to deploy." However, if a sticky comment already exists from a previous push that did have changes, update it to reflect "no changes" — so developers know previously-queued changes are no longer pending.

**Rationale:** Avoids noisy comments on unrelated PRs, but doesn't leave stale plan comments if relevant file changes are removed from the PR.

### 2. Draft PR behavior

**Decision:** Treat draft PRs the same as regular PRs.

Post plan comment on all `opened`/`synchronize` actions regardless of draft status. No draft-state checking logic needed.

**Rationale:** Plan comments are lightweight (no dispatch, no runner cost). Developers who use drafts still want to know what will deploy. Simplest implementation.

### 3. Plan comment visual design

**Decision:** Branded header with icon, grouped resource list (no file paths), context-aware CTA footer.

#### Header format

With environment configured and PR targets a mapped branch:
```
🚢 Ferry: Deployment Plan → **staging**
```

Without environments configured (or no branch match):
```
🚢 Ferry: Deployment Plan
```

#### Resource list format

Grouped by type, resource name and status only. No changed file paths (visible in PR diff already).

```markdown
#### Lambdas
- **order-processor** _(modified)_

#### Step Functions
- **checkout-flow** _(modified)_
```

#### Footer (context-aware CTA)

With environment + `auto_deploy: true`:
```
Will auto-deploy to **staging** on merge. Comment `/ferry apply` to deploy now.
```

With environment + `auto_deploy: false`:
```
Comment `/ferry apply` to deploy to **staging**.
```

Without environments configured:
```
Will deploy on merge to default branch.
```

#### No-changes update (when sticky comment exists but changes were removed)

```
🚢 Ferry: Deployment Plan

No Ferry-managed resources affected by this PR.
```

## Prior Decisions (from research/phase 29)

These are locked and should not be re-discussed:

- **Sticky comment pattern:** `<!-- ferry:plan -->` hidden HTML marker for find-and-update
- **No dispatch for plan mode:** Backend posts comment directly, zero GHA runner minutes
- **New `plan.py` module:** Sticky comment search-and-update logic lives in `backend/src/ferry_backend/checks/plan.py` (or similar)
- **`pull_request` event actions:** Handle `opened`, `synchronize`, `reopened`
- **Dedup:** Existing DynamoDB dual-key pattern handles `pull_request` delivery IDs
- **Check Run:** Reuse existing `create_check_run()` — conclusion is `success` when resources detected, `neutral` when no changes
- **Change detection:** Reuse `get_changed_files()` + `match_resources()` with PR base/head SHAs
- **Environment resolution:** Match PR base branch against `ferry.yaml` `environments[].branch`

## Code Context

### Existing assets to reuse
- `backend/src/ferry_backend/checks/runs.py` — `create_check_run()`, `post_pr_comment()`, `format_deployment_plan()` (reference for format, but PR comment uses condensed version)
- `backend/src/ferry_backend/detect/changes.py` — `get_changed_files()`, `match_resources()`, `merge_affected()`
- `backend/src/ferry_backend/webhook/handler.py` — Add `pull_request` routing alongside existing `push` path
- `backend/src/ferry_backend/webhook/dedup.py` — Dual-key dedup works for new event types
- `backend/src/ferry_backend/github/client.py` — `get()`, `post()`, `patch()` methods for new API calls
- `backend/src/ferry_backend/config/schema.py` — `FerryConfig.environments` and `EnvironmentMapping` (added in phase 29)

### New GitHub API calls needed
- `GET /repos/{owner}/{repo}/issues/{number}/comments` — Find existing sticky comment by marker
- `PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}` — Update existing sticky comment
- `POST /repos/{owner}/{repo}/issues/{number}/comments` — Create new sticky comment (existing `post_pr_comment()` already does this)

### New module
- `backend/src/ferry_backend/checks/plan.py` — Sticky comment logic: format plan comment body, find existing comment, create-or-update

## Deferred Ideas

None captured during this discussion.

---
*Context created: 2026-03-12*
