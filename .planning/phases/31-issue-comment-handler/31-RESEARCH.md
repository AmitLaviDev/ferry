# Phase 31: Issue Comment Handler (/ferry plan + /ferry apply) - Research

**Researched:** 2026-03-13
**Domain:** GitHub webhook handling (issue_comment, workflow_run events), GitHub Reactions API, command parsing
**Confidence:** HIGH

## Summary

Phase 31 adds two new webhook event handlers: `issue_comment` for `/ferry plan` and `/ferry apply` commands, and `workflow_run` for updating apply status comments when deploys complete. This is the command-response interface for Ferry -- developers interact via PR comments and Ferry responds with acknowledgment reactions, plan previews, and deploy status updates.

The existing codebase provides all building blocks: `trigger_dispatches()` for deploy, `format_plan_comment()` and `format_no_changes_comment()` for plan formatting, `resolve_environment()` for branch-to-environment mapping, `create_check_run()` for status, and the `GitHubClient` with `get`/`post`/`patch`. The new work is: (1) routing `issue_comment` and `workflow_run` events in the handler, (2) a command parser for `/ferry plan|apply`, (3) reaction emoji via the Reactions API, (4) removing sticky comment logic from `plan.py` (replacing with direct POST), (5) apply comment formatting with a SHA-specific marker, (6) a `workflow_run` handler that fetches dispatch inputs via REST API and updates the apply comment, and (7) dedup keys for the new event types.

A critical design consideration: the `workflow_run` webhook payload does NOT contain the `workflow_dispatch` inputs directly. The `workflow_run` object has `id`, `event`, `conclusion`, `head_sha`, but to get `trigger_sha` from the dispatch payload, we must call `GET /repos/{owner}/{repo}/actions/runs/{run_id}` and read `inputs.payload`. This is verified against the GitHub API (see Sources).

**Primary recommendation:** Extend `handler.py` with `_handle_issue_comment()` and `_handle_workflow_run()` functions. Modify `_handle_pull_request()` to use direct POST instead of upsert. Remove `find_plan_comment()` and `upsert_plan_comment()` from `plan.py`. Add apply comment formatting and `find_apply_comment()` functions. Keep command parser simple with regex.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Command parsing strictness:** Case-insensitive, whitespace-tolerant, entire-comment-body match. Trailing text after the command is silently ignored. `/ferry plan` and `/ferry apply` must be the entire comment body (not embedded in prose). Forward-compatible with future flag support (SELFDEP-01/02/03).

2. **`/ferry apply` acknowledgment UX:** Reaction emoji + new apply comment per invocation, updated with final status via `workflow_run` webhook.
   - Both `/ferry plan` and `/ferry apply` get a :ship: reaction emoji on the triggering comment as immediate acknowledgment
   - Reaction is added even when no resources are affected
   - Plan comments are NOT sticky -- each invocation creates a NEW comment (change from phase 30)
   - Phase 30's `find_plan_comment` / `upsert_plan_comment` sticky logic must be REMOVED
   - Apply comments have `<!-- ferry:apply:{sha} -->` marker, updated by `workflow_run` webhook

3. **`/ferry apply` with no affected resources:** Refuse to dispatch. Post a comment saying no resources affected.

4. **Closed/merged PR handling:** Post a comment saying "PR is not open -- `/ferry apply` requires an open PR." Same for `/ferry plan`.

5. **Prior decisions (locked from phases 29/30):**
   - `resolve_environment()` maps PR base branch to environment via `ferry.yaml` `environments[].branch`
   - `trigger_dispatches()` handles batched v2 dispatch with mode/environment fields
   - Guard `issue_comment` on issues vs PRs: check `payload["issue"]["pull_request"]` exists
   - Deploy uses current PR head SHA fetched fresh from GitHub API
   - No permission checks on `/ferry apply` commenter (PERM-01 deferred to v3+)
   - Check Run: reuse existing `create_check_run()`

6. **`workflow_run` webhook handling:**
   - New event type: `workflow_run` with `action: "completed"`
   - Extracts conclusion and trigger SHA from workflow inputs
   - Finds apply comment by marker and updates with final status
   - Manual step required: GitHub App webhook subscriptions must have `workflow_run` enabled

### Claude's Discretion

None specified -- all decisions are locked.

### Deferred Ideas (OUT OF SCOPE)

- **Selective deploy flags** (v3+ milestone): `/ferry apply --lambdas`, `/ferry apply --lambda order-processor` -- deploy subset of planned resources. Tracked as SELFDEP-01/02/03 in REQUIREMENTS.md.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PLAN-05 | User can comment `/ferry plan` on a PR to manually trigger a plan preview | `issue_comment` handler parses command, runs change detection, posts new plan comment (not sticky) |
| DEPLOY-02 | User can trigger deploy from a PR by commenting `/ferry apply` | `issue_comment` handler parses command, runs change detection, triggers `workflow_dispatch` via `trigger_dispatches()`, posts apply comment |
| DEPLOY-03 | `/ferry apply` deploys to the environment mapped to the PR's target branch | `resolve_environment()` maps PR base branch to environment; dispatch payload includes environment name |
| DEPLOY-04 | Ferry ignores `/ferry apply` comments on issues (non-PR) | Guard on `payload["issue"]["pull_request"]` existence; issues lack this field |

</phase_requirements>

## Existing Codebase Analysis

### Current Handler Flow (handler.py)

The handler currently routes two event types:
1. `push` -- full pipeline: auth -> config -> detect -> dispatch/check-run
2. `pull_request` -- auth -> config -> detect -> plan comment (sticky upsert) + check run

**Event filter (line 109):** `if event_type not in {"push", "pull_request"}` -- must be extended to include `issue_comment` and `workflow_run`.

### Functions to Reuse

| Function | Module | Reusable? | Notes |
|----------|--------|-----------|-------|
| `format_plan_comment(affected, env)` | `checks/plan.py` | YES | Returns formatted markdown body |
| `format_no_changes_comment()` | `checks/plan.py` | YES | Returns no-changes markdown body |
| `resolve_environment(config, base_branch)` | `checks/plan.py` | YES | Returns `EnvironmentMapping | None` |
| `create_check_run(client, repo, sha, affected)` | `checks/runs.py` | YES | For plan commands |
| `post_pr_comment(client, repo, pr_number, body)` | `checks/runs.py` | YES | Creates new comment |
| `get_changed_files(client, repo, base, head)` | `detect/changes.py` | YES | Compare API diff |
| `match_resources(config, changed_files)` | `detect/changes.py` | YES | File -> resource matching |
| `detect_config_changes(old, new)` | `detect/changes.py` | YES | Config diff |
| `merge_affected(source, config)` | `detect/changes.py` | YES | Merge affected lists |
| `trigger_dispatches(...)` | `dispatch/trigger.py` | YES | Fire workflow_dispatch |
| `build_deployment_tag(pr, branch, sha)` | `dispatch/trigger.py` | YES | Tag generation |
| `is_duplicate(delivery_id, payload, table, client)` | `webhook/dedup.py` | NEEDS UPDATE | Add issue_comment and workflow_run keys |

### Functions to Remove

| Function | Module | Reason |
|----------|--------|--------|
| `find_plan_comment(client, repo, pr_number)` | `checks/plan.py` | Sticky logic removed -- each plan creates new comment |
| `upsert_plan_comment(client, repo, pr_number, body)` | `checks/plan.py` | Replaced by direct `post_pr_comment()` calls |

### Code to Modify

| Location | Change |
|----------|--------|
| `handler.py` line 109 | Extend event filter: `{"push", "pull_request", "issue_comment", "workflow_run"}` |
| `handler.py` routing | Add `_handle_issue_comment()` and `_handle_workflow_run()` routes |
| `handler.py` `_handle_pull_request()` | Replace `upsert_plan_comment()` with `post_pr_comment()` |
| `handler.py` imports | Remove `find_plan_comment`, `upsert_plan_comment`; add new functions |
| `plan.py` | Remove `find_plan_comment()`, `upsert_plan_comment()`, `PLAN_MARKER` const; add apply comment formatting + `find_apply_comment()` |
| `dedup.py` `_build_event_key()` | Add `issue_comment` and `workflow_run` payload patterns |
| Tests | Update `test_handler_pr.py` for non-sticky comments; add `test_handler_comment.py`; update `test_plan.py` |

## Architecture Patterns

### issue_comment Webhook Payload Structure

When GitHub sends an `issue_comment` event (HIGH confidence -- well-established API):

```python
{
    "action": "created",  # or "edited", "deleted"
    "issue": {
        "number": 42,
        "state": "open",      # "open" or "closed"
        "pull_request": {      # ONLY present if comment is on a PR
            "url": "https://api.github.com/repos/owner/repo/pulls/42",
            "html_url": "https://github.com/owner/repo/pull/42",
            "diff_url": "https://github.com/owner/repo/pull/42.diff",
            "patch_url": "https://github.com/owner/repo/pull/42.patch",
        },
    },
    "comment": {
        "id": 123456,
        "body": "/ferry apply",
        "user": {"login": "developer", ...},
    },
    "repository": {
        "full_name": "owner/repo",
        "default_branch": "main",
    },
    "sender": {"login": "developer", ...},
}
```

Key observations:
- **PR vs issue detection:** `payload["issue"]["pull_request"]` key EXISTS for PRs, ABSENT for plain issues. The value is a dict of URLs, NOT the full PR object.
- **PR state:** `payload["issue"]["state"]` is `"open"` or `"closed"` -- use this for the closed-PR guard.
- **Comment body:** `payload["comment"]["body"]` -- the raw text to parse for commands.
- **Comment ID:** `payload["comment"]["id"]` -- needed for adding the reaction emoji.
- **PR number:** `payload["issue"]["number"]` -- same as PR number (PRs are issues).
- **Head SHA is NOT in this payload.** Must fetch via `GET /repos/{owner}/{repo}/pulls/{number}` to get current head SHA. This is correct per CONTEXT.md decision: "Deploy uses current PR head SHA fetched fresh from GitHub API, not stale reference."
- **Base branch is NOT in this payload.** Also fetched from the PR GET endpoint.

### workflow_run Webhook Payload Structure

When GitHub sends a `workflow_run` event (HIGH confidence -- verified against REST API):

```python
{
    "action": "completed",     # or "requested", "in_progress"
    "workflow_run": {
        "id": 12345678901,     # Run ID -- used to fetch inputs
        "name": "Ferry Deploy",
        "event": "workflow_dispatch",  # What triggered this run
        "conclusion": "success",       # "success", "failure", "cancelled"
        "head_sha": "abc123...",
        "head_branch": "main",
        "status": "completed",
        "html_url": "https://github.com/owner/repo/actions/runs/12345678901",
        "path": ".github/workflows/ferry.yml",
        "pull_requests": [],
        "actor": {...},
        "triggering_actor": {...},
    },
    "workflow": {
        "id": 240960323,
        "name": "Ferry Deploy",
        "path": ".github/workflows/ferry.yml",
    },
    "repository": {
        "full_name": "owner/repo",
    },
}
```

**CRITICAL LIMITATION:** The `workflow_run` webhook payload does NOT contain `inputs` from the `workflow_dispatch` trigger. To get the trigger SHA, you must:

1. Extract `run_id` from `payload["workflow_run"]["id"]`
2. Call `GET /repos/{owner}/{repo}/actions/runs/{run_id}` via REST API
3. The response includes `"inputs": {"payload": "{...JSON string...}"}`
4. Parse the JSON payload string to extract `trigger_sha`

Verified: The REST API `GET /repos/{owner}/{repo}/actions/runs/{run_id}` response includes an `inputs` field that is `null` for non-dispatch events and a `dict` for `workflow_dispatch` events. The `inputs` dict maps workflow input names to their string values.

```python
# Fetching trigger_sha from workflow run
run_id = payload["workflow_run"]["id"]
resp = client.get(f"/repos/{repo}/actions/runs/{run_id}")
run_data = resp.json()
inputs = run_data.get("inputs", {})
if inputs:
    payload_json = inputs.get("payload", "{}")
    dispatch_payload = json.loads(payload_json)
    trigger_sha = dispatch_payload.get("trigger_sha", "")
```

### GitHub Reactions API

**Endpoint:** `POST /repos/{owner}/{repo}/issues/comments/{comment_id}/reactions`

```python
# Add ship reaction to a comment
resp = client.post(
    f"/repos/{repo}/issues/comments/{comment_id}/reactions",
    json={"content": "rocket"},
)
# Returns 200 if reaction already exists, 201 if newly created
```

**IMPORTANT:** There is NO "ship" emoji in GitHub's reaction set. The allowed `content` values are:
- `+1`, `-1`, `laugh`, `confused`, `heart`, `hooray`, `rocket`, `eyes`

The CONTEXT.md says ":ship: reaction emoji" but the closest available reaction is `rocket`. Since there is no ship reaction, **use `rocket` as the acknowledgment reaction.** The ship emoji exists as a standard Unicode emoji in comments but NOT as a GitHub reaction type.

**Source:** [GitHub REST API - Reactions](https://docs.github.com/en/rest/reactions/reactions) (HIGH confidence)

### Command Parser Pattern

Based on CONTEXT.md decisions:
- Case-insensitive, whitespace-tolerant, entire-comment-body match
- Trailing text silently ignored (forward-compatible with future flags)

```python
import re

# Pattern: optional leading whitespace, /ferry, one or more spaces, command word,
# optional trailing text (ignored), optional trailing whitespace
_COMMAND_RE = re.compile(
    r"^\s*/ferry\s+(plan|apply)(?:\s+.*)?$",
    re.IGNORECASE | re.DOTALL,
)

def parse_ferry_command(body: str) -> str | None:
    """Parse a /ferry command from a comment body.

    Returns "plan" or "apply" if the comment is a valid command,
    or None if it's not a Ferry command.
    """
    match = _COMMAND_RE.match(body.strip())
    if match:
        return match.group(1).lower()
    return None
```

**Why regex over string matching:** The `re.DOTALL` flag handles multi-line bodies cleanly. The `re.IGNORECASE` flag handles case variants. The `(?:\s+.*)?$` pattern handles trailing text (future flags). A simple `strip().lower().startswith()` approach would require more manual handling of these edge cases.

**Why NOT simple split:** `body.strip().lower().split()` could work for the basic case but fails to enforce "entire comment body" -- it would match `/ferry plan` embedded in a paragraph. The regex anchors `^...$` enforce full-body match.

Test cases for the parser:
- `"/ferry plan"` -> `"plan"`
- `"  /ferry  apply  "` -> `"apply"`
- `"/Ferry Plan"` -> `"plan"`
- `"/FERRY APPLY"` -> `"apply"`
- `"/ferry apply staging"` -> `"apply"` (trailing text ignored)
- `"Please /ferry plan"` -> `None` (not at start)
- `"some text\n/ferry plan"` -> `None` (not entire body -- but wait, `re.DOTALL` + `^...$` means this would also not match because `^` without `re.MULTILINE` matches start of string only)
- `"/ferry"` -> `None` (no command)
- `"/ferry status"` -> `None` (unknown command)

### Fetching Fresh PR Head SHA

For `/ferry apply`, we need the current head SHA (not stale from a webhook):

```python
# GET /repos/{owner}/{repo}/pulls/{pull_number}
resp = client.get(f"/repos/{repo}/pulls/{pr_number}")
pr_data = resp.json()
head_sha = pr_data["head"]["sha"]
base_branch = pr_data["base"]["ref"]
state = pr_data["state"]  # "open", "closed"
```

This is also needed for `/ferry plan` because the `issue_comment` payload does NOT include the head SHA or base branch.

### Dedup Keys for New Event Types

```python
# issue_comment: unique by repo + comment ID
# (Each comment is a unique action; re-delivered comments have same delivery ID)
"EVENT#issue_comment#{repo}#{comment_id}"

# workflow_run: unique by repo + run ID
# (Each completed event for a run is unique; re-deliveries have same delivery ID)
"EVENT#workflow_run#{repo}#{run_id}"
```

**Why comment_id for issue_comment:** The delivery-level dedup (X-GitHub-Delivery header) catches retries. The event-level dedup catches re-queued events with new delivery IDs. Using `comment_id` ensures the same comment only triggers one processing cycle, even if GitHub generates multiple webhooks for the same comment creation.

**Why run_id for workflow_run:** Same logic -- one processing per completed run.

### _handle_issue_comment Flow

```
1. Filter: action != "created" -> ignore (only new comments)
2. Parse command: parse_ferry_command(comment.body) -> None -> ignore
3. Guard: issue.pull_request not present -> ignore (DEPLOY-04)
4. Add rocket reaction to comment (always, even for closed PR or no resources)
5. Guard: issue.state != "open" -> post "PR not open" comment, return
6. Fetch fresh PR data: GET /repos/{repo}/pulls/{pr_number}
   -> Extract head_sha, base_branch
7. Auth as GitHub App installation
8. Fetch + validate ferry.yaml at head_sha
9. Detect changes (same as _handle_pull_request)
10. Route by command:
    a. "plan":
       - If affected: format_plan_comment -> post_pr_comment (new comment)
       - If not affected: format_no_changes_comment -> post_pr_comment (new comment)
       - Create Check Run (same as PR handler)
    b. "apply":
       - Resolve environment from base_branch
       - If no affected resources: post "no resources" comment, return
       - Build deployment tag, trigger_dispatches
       - Post apply comment with <!-- ferry:apply:{head_sha} --> marker
       - Create Check Run
```

### _handle_workflow_run Flow

```
1. Filter: action != "completed" -> ignore
2. Filter: workflow_run.event != "workflow_dispatch" -> ignore (only dispatched runs)
3. Filter: workflow_run.path != ".github/workflows/ferry.yml" -> ignore (only Ferry runs)
4. Auth as GitHub App installation
5. Fetch run details: GET /repos/{repo}/actions/runs/{run_id}
   -> Extract inputs.payload JSON -> trigger_sha
6. Find apply comment by marker: <!-- ferry:apply:{trigger_sha} -->
   -> Paginate through recent PR comments
   -> But which PR? Need to determine PR number from context
7. Update apply comment with conclusion status
```

**Challenge: Finding the right PR for workflow_run.**

The `workflow_run` webhook payload does NOT directly identify which PR the apply comment is on. Options:

1. **Store PR number in dispatch inputs:** Modify `trigger_dispatches()` to include `pr_number` in the payload. The `BatchedDispatchPayload` already has a `pr_number` field. When the workflow completes, extract `pr_number` from `inputs.payload`.

2. **Search recent PRs for the comment marker:** Expensive and fragile.

**Recommendation: Option 1.** The `pr_number` is already in `BatchedDispatchPayload`. When the `workflow_run` handler extracts `trigger_sha` from `inputs.payload`, it also gets `pr_number`. Then it can search comments on that specific PR for the `<!-- ferry:apply:{trigger_sha} -->` marker.

### Apply Comment Format

```python
APPLY_MARKER_TEMPLATE = "<!-- ferry:apply:{sha} -->"

def format_apply_comment(
    affected: list[AffectedResource],
    environment: EnvironmentMapping | None,
    head_sha: str,
) -> str:
    """Format the initial apply comment."""
    marker = APPLY_MARKER_TEMPLATE.format(sha=head_sha)
    parts = [marker]

    env_name = environment.name if environment else "default"
    parts.append(f"## {FERRY_EMOJI} Ferry: Deploy Triggered")
    parts.append("")
    parts.append(
        f"Deploying **{len(affected)} resource(s)** to **{env_name}** "
        f"at `{head_sha[:7]}`..."
    )
    parts.append("")
    parts.append("_Waiting for workflow to complete..._")
    return "\n".join(parts)


def format_apply_status_update(
    original_body: str,
    conclusion: str,
    run_url: str,
) -> str:
    """Append status to an existing apply comment."""
    status_emoji = {"success": "check", "failure": "x", "cancelled": "warning"}
    emoji = status_emoji.get(conclusion, "question")
    status_line = f"\n\n**Result:** :{emoji}: `{conclusion}` — [View run]({run_url})"
    # Replace the "Waiting..." line
    updated = original_body.replace(
        "_Waiting for workflow to complete..._",
        status_line.strip(),
    )
    return updated
```

### find_apply_comment

Reuses the same paginated search pattern as the removed `find_plan_comment`, but with a SHA-specific marker:

```python
def find_apply_comment(
    client: GitHubClient,
    repo: str,
    pr_number: int,
    trigger_sha: str,
) -> dict | None:
    """Find an apply comment by its SHA-specific marker."""
    marker = APPLY_MARKER_TEMPLATE.format(sha=trigger_sha)
    page = 1
    per_page = 100
    while True:
        resp = client.get(
            f"/repos/{repo}/issues/{pr_number}/comments",
            params={"per_page": per_page, "page": page},
        )
        if resp.status_code != 200:
            return None
        comments = resp.json()
        if not comments:
            return None
        for comment in comments:
            if marker in comment.get("body", ""):
                return comment
        if len(comments) < per_page:
            return None
        page += 1
```

### _handle_pull_request Modifications

Replace sticky upsert logic with direct POST:

```python
# Before (phase 30):
if affected:
    body = format_plan_comment(affected, environment)
    upsert_plan_comment(github_client, repo, pr_number, body)
else:
    existing = find_plan_comment(github_client, repo, pr_number)
    if existing:
        body = format_no_changes_comment()
        upsert_plan_comment(github_client, repo, pr_number, body)

# After (phase 31):
if affected:
    body = format_plan_comment(affected, environment)
    post_pr_comment(github_client, repo, pr_number, body)
else:
    body = format_no_changes_comment()
    post_pr_comment(github_client, repo, pr_number, body)
```

Note: Phase 30 was silent on no-changes for first open. Phase 31 changes this: every plan invocation creates a new comment, including no-changes.

### Recommended Project Structure

```
backend/src/ferry_backend/
  checks/
    plan.py          # MODIFIED: Remove find_plan_comment, upsert_plan_comment, PLAN_MARKER.
                     #   Add: format_apply_comment, format_apply_status_update,
                     #   find_apply_comment, APPLY_MARKER_TEMPLATE, parse_ferry_command
    runs.py          # Unchanged
  webhook/
    handler.py       # MODIFIED: Add issue_comment + workflow_run routing,
                     #   _handle_issue_comment(), _handle_workflow_run().
                     #   Modify _handle_pull_request() for non-sticky comments.
    dedup.py         # MODIFIED: Add issue_comment + workflow_run event keys
    signature.py     # Unchanged
  dispatch/
    trigger.py       # Unchanged (already has pr_number in payload)
  github/
    client.py        # Unchanged (get/post/patch already available)
tests/test_backend/
  test_handler_comment.py  # NEW: integration tests for issue_comment handler
  test_handler_workflow.py # NEW: integration tests for workflow_run handler
  test_handler_pr.py       # MODIFIED: update for non-sticky plan comments
  test_plan.py             # MODIFIED: remove sticky tests, add apply format tests
  test_dedup.py            # MODIFIED: add issue_comment + workflow_run dedup tests
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Command parsing | Complex NLP/fuzzy matching | Single regex with `re.IGNORECASE \| re.DOTALL` | Two commands, exact syntax, forward-compatible with flags |
| Reaction API | Custom emoji handler | Direct `POST` to Reactions endpoint | One-liner API call |
| Apply comment search | Full-text search across all PRs | Paginated search on specific PR by HTML marker | PR number comes from dispatch payload |
| Comment templates | Jinja2 template engine | f-string concatenation | ~10 lines per comment format, no dependency needed |
| Dispatch correlation | Custom tracking DB | Store `trigger_sha` + `pr_number` in existing dispatch payload | `BatchedDispatchPayload` already has both fields |

## Common Pitfalls

### Pitfall 1: No "ship" emoji in GitHub Reactions
**What goes wrong:** Attempting to use `"ship"` as the reaction `content` value results in a 422 Validation Error.
**Why it happens:** GitHub only supports 8 reaction types: `+1`, `-1`, `laugh`, `confused`, `heart`, `hooray`, `rocket`, `eyes`. The ship emoji is a Unicode emoji available in comment text but NOT as a reaction type.
**How to avoid:** Use `"rocket"` as the reaction content. It is the closest available option and commonly used for deploy/launch acknowledgments.
**Warning signs:** 422 response from the Reactions API.

### Pitfall 2: issue_comment payload lacks PR details
**What goes wrong:** Trying to extract `head_sha` or `base_branch` from the `issue_comment` payload -- they are not there.
**Why it happens:** The `issue_comment` payload contains an `issue` object with a `pull_request` sub-object, but that sub-object only has URLs (not the full PR data). This is by GitHub design -- PRs are issues with code, so issue events carry minimal PR metadata.
**How to avoid:** Always fetch fresh PR data via `GET /repos/{repo}/pulls/{pr_number}` for head SHA and base branch. This is actually the correct behavior per CONTEXT.md ("Deploy uses current PR head SHA fetched fresh from GitHub API").
**Warning signs:** `KeyError` on `payload["issue"]["head"]` or similar.

### Pitfall 3: workflow_run webhook lacks dispatch inputs
**What goes wrong:** Trying to read `trigger_sha` directly from `payload["workflow_run"]["inputs"]` -- the field does not exist in the webhook payload.
**Why it happens:** The `workflow_run` webhook payload mirrors the workflow run object but omits `inputs`. This is a known limitation documented in [GitHub community discussions](https://github.com/orgs/community/discussions/9752).
**How to avoid:** After receiving the webhook, call `GET /repos/{owner}/{repo}/actions/runs/{run_id}` to fetch the complete run object which includes `inputs`. Parse `inputs.payload` JSON string to extract `trigger_sha` and `pr_number`.
**Warning signs:** `None` or `KeyError` when accessing inputs from the webhook payload.

### Pitfall 4: Reaction API returns 200 (not 201) for existing reactions
**What goes wrong:** Checking for `status_code == 201` to confirm reaction was added, but getting `200` if the bot already reacted.
**Why it happens:** GitHub returns 200 if the reaction already exists (idempotent), 201 if newly created.
**How to avoid:** Accept both 200 and 201 as success. In practice, check `resp.status_code < 300` or just log and continue.

### Pitfall 5: Race condition between comment and dedup
**What goes wrong:** Two identical webhook deliveries for the same `issue_comment` event arrive simultaneously, both pass dedup, both post comments.
**Why it happens:** GitHub may retry if the first response is slow.
**How to avoid:** The DynamoDB conditional write in dedup handles this -- only one delivery wins the write. Use `comment_id` in the event-level dedup key for deterministic dedup.

### Pitfall 6: Modifying _handle_pull_request breaks existing tests
**What goes wrong:** Existing `test_handler_pr.py` tests mock `find_plan_comment()` and `upsert_plan_comment()` calls. Removing these functions breaks the mocks.
**Why it happens:** Tests are tightly coupled to the sticky comment implementation.
**How to avoid:** Update tests alongside code changes. The new tests should expect POST calls instead of GET+PATCH sequences. Specifically:
- Remove `_mock_find_no_plan_comment()` and `_mock_find_existing_plan_comment()` helpers
- Remove `_mock_update_comment()` helper
- All plan scenarios now use `_mock_create_comment()` only (POST)
- Test for no-changes should expect a POST (new comment), not silence

### Pitfall 7: workflow_run fires for ALL workflows, not just Ferry
**What goes wrong:** Processing workflow_run events for CI/CD workflows, linting, etc.
**Why it happens:** The `workflow_run` webhook fires for every workflow completion in the repo.
**How to avoid:** Filter on `payload["workflow_run"]["event"] == "workflow_dispatch"` AND `payload["workflow_run"]["path"]` matching the Ferry workflow path (`.github/workflows/ferry.yml`).

### Pitfall 8: Comment body with trailing newlines
**What goes wrong:** User types `/ferry plan` but the comment body is `/ferry plan\n` or `/ferry plan\r\n` due to browser behavior.
**Why it happens:** Web UI may add trailing whitespace.
**How to avoid:** The regex pattern with `\s*` at boundaries or `body.strip()` before parsing handles this cleanly.

## Code Examples

### Example: issue_comment payload extraction

```python
# Verified structure from GitHub webhook documentation
action = payload.get("action", "")  # "created"
issue = payload["issue"]
pr_number = issue["number"]
state = issue["state"]  # "open" or "closed"
is_pr = "pull_request" in issue  # True for PRs, False for issues
comment = payload["comment"]
comment_id = comment["id"]
comment_body = comment["body"]
repo = payload["repository"]["full_name"]
```

### Example: Adding a rocket reaction

```python
# POST /repos/{owner}/{repo}/issues/comments/{comment_id}/reactions
resp = client.post(
    f"/repos/{repo}/issues/comments/{comment_id}/reactions",
    json={"content": "rocket"},
)
# 201 = new reaction, 200 = already exists -- both are success
```

### Example: Fetching fresh PR data

```python
# GET /repos/{owner}/{repo}/pulls/{pull_number}
resp = client.get(f"/repos/{repo}/pulls/{pr_number}")
pr_data = resp.json()
head_sha = pr_data["head"]["sha"]
base_branch = pr_data["base"]["ref"]
pr_state = pr_data["state"]  # "open" or "closed"
```

### Example: Fetching workflow run inputs

```python
# GET /repos/{owner}/{repo}/actions/runs/{run_id}
run_id = payload["workflow_run"]["id"]
resp = client.get(f"/repos/{repo}/actions/runs/{run_id}")
run_data = resp.json()
inputs = run_data.get("inputs") or {}
payload_json = inputs.get("payload", "{}")
dispatch_data = json.loads(payload_json)
trigger_sha = dispatch_data.get("trigger_sha", "")
pr_number = dispatch_data.get("pr_number", "")
```

### Example: Command parser with test cases

```python
import re

_COMMAND_RE = re.compile(
    r"^\s*/ferry\s+(plan|apply)(?:\s.*)?$",
    re.IGNORECASE | re.DOTALL,
)

def parse_ferry_command(body: str) -> str | None:
    """Parse /ferry command from comment body. Returns 'plan'|'apply'|None."""
    match = _COMMAND_RE.match(body.strip())
    return match.group(1).lower() if match else None

# Tests:
assert parse_ferry_command("/ferry plan") == "plan"
assert parse_ferry_command("/ferry apply") == "apply"
assert parse_ferry_command("  /ferry  plan  ") == "plan"
assert parse_ferry_command("/Ferry Apply") == "apply"
assert parse_ferry_command("/FERRY PLAN") == "plan"
assert parse_ferry_command("/ferry apply staging") == "apply"
assert parse_ferry_command("Please /ferry plan") is None
assert parse_ferry_command("/ferry") is None
assert parse_ferry_command("/ferry status") is None
assert parse_ferry_command("hello world") is None
```

### Example: Dedup key for issue_comment

```python
# In _build_event_key():
comment = payload.get("comment")
if comment is not None:
    repo = payload.get("repository", {}).get("full_name")
    comment_id = comment.get("id")
    if repo and comment_id is not None:
        return f"EVENT#issue_comment#{repo}#{comment_id}"

# For workflow_run:
workflow_run = payload.get("workflow_run")
if workflow_run is not None:
    repo = payload.get("repository", {}).get("full_name")
    run_id = workflow_run.get("id")
    if repo and run_id is not None:
        return f"EVENT#workflow_run#{repo}#{run_id}"
```

### Example: _handle_issue_comment test helper

```python
def _make_issue_comment_event(
    body: str = "/ferry plan",
    pr_number: int = 42,
    comment_id: int = 99,
    is_pr: bool = True,
    state: str = "open",
    delivery_id: str = "delivery-comment-001",
) -> dict:
    """Build a Lambda Function URL event for an issue_comment webhook."""
    issue = {
        "number": pr_number,
        "state": state,
    }
    if is_pr:
        issue["pull_request"] = {
            "url": f"https://api.github.com/repos/owner/repo/pulls/{pr_number}",
        }
    payload = {
        "action": "created",
        "issue": issue,
        "comment": {
            "id": comment_id,
            "body": body,
        },
        "repository": {
            "full_name": "owner/repo",
            "default_branch": "main",
        },
    }
    body_str = json.dumps(payload)
    signature = _make_signature(body_str)
    return {
        "body": body_str,
        "isBase64Encoded": False,
        "headers": {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": "issue_comment",
            "Content-Type": "application/json",
        },
    }
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-httpx 0.30+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/python -m pytest tests/test_backend/test_handler_comment.py tests/test_backend/test_handler_workflow.py tests/test_backend/test_plan.py -x` |
| Full suite command | `.venv/bin/python -m pytest tests/test_backend/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAN-05 | `/ferry plan` comment triggers plan preview | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_comment.py::TestIssuePlan -x` | Wave 0 |
| DEPLOY-02 | `/ferry apply` triggers deploy via dispatch | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_comment.py::TestIssueApply -x` | Wave 0 |
| DEPLOY-03 | Apply deploys to environment mapped to base branch | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_comment.py::TestIssueApply::test_apply_uses_environment -x` | Wave 0 |
| DEPLOY-04 | Apply ignores comments on issues (non-PR) | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_comment.py::TestIssueApply::test_apply_on_issue_ignored -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/test_backend/test_handler_comment.py tests/test_backend/test_plan.py -x`
- **Per wave merge:** `.venv/bin/python -m pytest tests/test_backend/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_backend/test_handler_comment.py` -- covers PLAN-05, DEPLOY-02, DEPLOY-03, DEPLOY-04
- [ ] `tests/test_backend/test_handler_workflow.py` -- covers workflow_run status update
- [ ] Updated `tests/test_backend/test_handler_pr.py` -- non-sticky plan comment behavior
- [ ] Updated `tests/test_backend/test_plan.py` -- remove sticky tests, add apply format tests, add parser tests
- [ ] Updated `tests/test_backend/test_dedup.py` -- add issue_comment + workflow_run dedup keys

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sticky plan comment (find + upsert) | New comment per invocation (POST only) | Phase 31 | Remove `find_plan_comment`, `upsert_plan_comment`, simplify handler |
| Push + PR events only | Push + PR + issue_comment + workflow_run | Phase 31 | Handler routes 4 event types |
| No user-initiated commands | `/ferry plan` + `/ferry apply` via PR comments | Phase 31 | Interactive deployment workflow |
| Deploy only on merge to default branch | Deploy on `/ferry apply` from any open PR | Phase 31 | Mid-flight deployment capability |

## Open Questions

1. **Reaction emoji: rocket vs ship**
   - What we know: GitHub Reactions API only supports 8 values (`+1`, `-1`, `laugh`, `confused`, `heart`, `hooray`, `rocket`, `eyes`). There is no `ship` reaction type.
   - CONTEXT.md says ":ship: reaction emoji" but this is not available as a GitHub reaction.
   - Recommendation: Use `rocket` as the reaction. It is the standard "launch/deploy" reaction. Flag this for user confirmation during planning.

2. **workflow_run handler: filtering by workflow path**
   - What we know: `payload["workflow_run"]["path"]` contains `.github/workflows/ferry.yml`
   - What's unclear: Should we hard-code the workflow filename or use the `WORKFLOW_FILENAME` constant from `ferry_utils.constants`?
   - Recommendation: Use `WORKFLOW_FILENAME` constant for consistency. Construct the expected path as `.github/workflows/{WORKFLOW_FILENAME}`.

3. **Plan comment format: PLAN_MARKER removal**
   - What we know: `format_plan_comment()` currently starts with `PLAN_MARKER = "<!-- ferry:plan -->"`. Since comments are no longer sticky, the marker is unnecessary.
   - What's unclear: Should we remove the marker entirely, or keep it for identification purposes?
   - Recommendation: Remove the marker. Plan comments are identified by their visual format, not by a hidden marker. Only apply comments need markers (for `workflow_run` status updates).

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `handler.py`, `plan.py`, `runs.py`, `dedup.py`, `client.py`, `trigger.py`, `dispatch.py`, `constants.py`, `schema.py`, `settings.py` -- direct code reading
- Codebase analysis: `test_handler_pr.py`, `test_plan.py`, `test_dedup.py` -- direct test reading
- Phase 30 RESEARCH.md -- prior research on PR event handling patterns
- GitHub REST API (live): `gh api repos/AmitLaviDev/ferry/actions/runs/{id}` confirmed `inputs` field exists on workflow run objects, is `null` for push events, contains dispatch inputs for `workflow_dispatch` events
- GitHub REST API (live): `gh api repos/diggerhq/digger/pulls` confirmed PR response includes `head.sha`, `base.ref`, `state`

### Secondary (MEDIUM confidence)
- [GitHub REST API - Reactions](https://docs.github.com/en/rest/reactions/reactions) -- confirmed 8 allowed content values, no "ship" type, POST endpoint for issue comment reactions
- [GitHub Webhook Events - issue_comment](https://docs.github.com/en/webhooks/webhook-events-and-payloads) -- payload structure with `issue.pull_request` for PR detection, `issue.state` for open/closed
- [GitHub Webhook Events - workflow_run](https://docs.github.com/en/webhooks/webhook-events-and-payloads) -- `workflow_run` object with `id`, `event`, `conclusion`, `head_sha`, `path`
- [GitHub REST API - Workflow Runs](https://docs.github.com/en/rest/actions/workflow-runs) -- GET endpoint returns `inputs` for workflow_dispatch runs
- [GitHub community: workflow_run inputs limitation](https://github.com/orgs/community/discussions/9752) -- confirmed webhook payload does not include dispatch inputs

### Tertiary (LOW confidence)
None -- all findings verified against codebase or live API.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - pure Python, no new dependencies, extends existing patterns
- Architecture: HIGH - handler routing, command parsing, API interactions are all well-understood
- GitHub API: HIGH - reactions endpoint verified against docs; workflow_run inputs limitation verified against live API
- Pitfalls: HIGH - identified from direct codebase analysis and API verification

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable domain, no fast-moving dependencies)
