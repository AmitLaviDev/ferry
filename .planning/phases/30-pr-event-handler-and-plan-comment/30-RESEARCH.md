# Phase 30: PR Event Handler and Plan Comment - Research

**Researched:** 2026-03-12
**Domain:** GitHub webhook handling (pull_request events), GitHub Issues Comments API (sticky comments), Check Runs API
**Confidence:** HIGH

## Summary

Phase 30 adds `pull_request` event handling to the existing webhook handler. The backend will detect resource changes between the PR base branch and head SHA, post a branded sticky comment listing affected resources, and create a Check Run. No workflow_dispatch is triggered -- the backend handles everything directly.

The existing codebase provides nearly all the building blocks: `get_changed_files()` and `match_resources()` for change detection, `create_check_run()` for Check Runs, `post_pr_comment()` for posting comments, and the `GitHubClient` with `get`/`post`/`patch` methods. The new work is: (1) routing `pull_request` events in the handler, (2) a new `plan.py` module for sticky comment find-and-update logic and comment body formatting, (3) environment resolution from `ferry.yaml`, and (4) dedup key generation for `pull_request` events.

**Primary recommendation:** Extend `handler.py` with a `_handle_pull_request()` function alongside the existing push flow. Create `checks/plan.py` for sticky comment logic. Reuse existing change detection and Check Run functions without modification.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Zero-change behavior:** Silent on first open (no comment); update existing sticky comment if one exists. Only Check Run (neutral) for no changes. If sticky comment already exists, update it to "no changes."
2. **Draft PR behavior:** Treat draft PRs the same as regular PRs. No draft-state checking logic needed.
3. **Plan comment visual design:** Branded header with icon, grouped resource list (no file paths), context-aware CTA footer. Specific format defined in CONTEXT.md.
4. **Sticky comment pattern:** `<!-- ferry:plan -->` hidden HTML marker for find-and-update.
5. **No dispatch for plan mode:** Backend posts comment directly, zero GHA runner minutes.
6. **New `plan.py` module:** Sticky comment search-and-update logic lives in `backend/src/ferry_backend/checks/plan.py`.
7. **`pull_request` event actions:** Handle `opened`, `synchronize`, `reopened`.
8. **Dedup:** Existing DynamoDB dual-key pattern handles `pull_request` delivery IDs.
9. **Check Run:** Reuse existing `create_check_run()` -- conclusion is `success` when resources detected, `neutral` when no changes.
10. **Change detection:** Reuse `get_changed_files()` + `match_resources()` with PR base/head SHAs.
11. **Environment resolution:** Match PR base branch against `ferry.yaml` `environments[].branch`.

### Claude's Discretion

None specified -- all decisions are locked.

### Deferred Ideas (OUT OF SCOPE)

None captured during this discussion.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PLAN-01 | Ferry posts a sticky PR comment showing which resources would be deployed when a PR is opened | Handler routes `pull_request` `opened` events; `plan.py` formats and posts comment; change detection via existing `get_changed_files()` + `match_resources()` |
| PLAN-02 | Ferry updates the sticky PR comment when new commits are pushed to the PR | Handler routes `pull_request` `synchronize` events; `plan.py` finds existing comment by `<!-- ferry:plan -->` marker, updates via PATCH |
| PLAN-03 | Plan comment shows the target environment name (if environments configured) | `resolve_environment()` function matches PR base branch against `FerryConfig.environments[].branch` |
| PLAN-04 | Ferry creates a Check Run on the PR reflecting plan status (success/failure) | Reuse existing `create_check_run()` with `conclusion="success"` for resources detected, `conclusion="neutral"` for no changes |

</phase_requirements>

## Existing Codebase Analysis

### Current Push Handler Flow (handler.py)

The handler follows this pipeline for `push` events:
1. Extract body, normalize headers
2. Validate HMAC-SHA256 signature
3. Check delivery ID header
4. **Filter: only `push` events accepted** (line 102) -- `pull_request` returns "ignored"
5. Parse JSON payload
6. Dedup check via DynamoDB
7. Auth: JWT -> installation token
8. Fetch + validate ferry.yaml at `after` SHA
9. Detect changes via Compare API
10. Branch-dependent: default branch -> dispatch; PR branch -> Check Run

**Key observation:** Step 4 currently rejects `pull_request` events. This is the primary gate to modify.

### Reusable Functions

| Function | Module | Reusable As-Is? | Notes |
|----------|--------|-----------------|-------|
| `get_changed_files(client, repo, base, head)` | `detect/changes.py` | YES | Pass PR base branch + head SHA. Uses Compare API `base...head`. |
| `match_resources(config, changed_files)` | `detect/changes.py` | YES | Takes config + file list, returns `AffectedResource` list |
| `detect_config_changes(old, new)` | `detect/changes.py` | YES | For ferry.yaml diffs |
| `merge_affected(source, config)` | `detect/changes.py` | YES | Merge source + config affected lists |
| `create_check_run(client, repo, sha, affected, error)` | `checks/runs.py` | MOSTLY | Need to change conclusion for no-changes from `success` to `neutral` for PR events |
| `post_pr_comment(client, repo, pr_number, body)` | `checks/runs.py` | YES | Creates new comment. Used for initial sticky comment. |
| `find_open_prs(client, repo, sha)` | `checks/runs.py` | NOT NEEDED | PR number comes directly from the webhook payload |
| `fetch_ferry_config(client, repo, sha)` | `config/loader.py` | YES | Fetch at PR head SHA |
| `parse_config(raw_yaml)` | `config/loader.py` | YES | |
| `validate_config(parsed)` | `config/schema.py` | YES | |
| `is_duplicate(delivery_id, payload, table, client)` | `webhook/dedup.py` | NEEDS UPDATE | `_build_event_key` only handles push payloads |
| `verify_signature(body, sig, secret)` | `webhook/signature.py` | YES | Works for any event type |

### Check Run Conclusion: "neutral" vs "success"

The CONTEXT.md specifies `neutral` for no changes. Currently `create_check_run()` uses `success` for no changes. Two approaches:

1. **Add a `conclusion` parameter** to `create_check_run()` for the no-changes case so callers can choose.
2. **Create a dedicated `create_plan_check_run()`** in the new `plan.py` module.

Recommendation: Add an optional `conclusion` override parameter to `create_check_run()`. This is minimally invasive and keeps check run logic centralized.

### Dedup Changes Needed

The current `_build_event_key()` in `dedup.py` only handles push payloads:
```python
def _build_event_key(payload: dict) -> str | None:
    repo = payload.get("repository", {}).get("full_name")
    after_sha = payload.get("after")
    if repo and after_sha:
        return f"EVENT#push#{repo}#{after_sha}"
    return None
```

For `pull_request` events, the payload structure is different:
- `payload["action"]` = "opened" / "synchronize" / "reopened"
- `payload["number"]` = PR number
- `payload["pull_request"]["head"]["sha"]` = head commit SHA
- `payload["repository"]["full_name"]` = repo

The event key for PR events should be: `EVENT#pull_request#{repo}#{pr_number}#{head_sha}`

This needs the event type to be passed to `is_duplicate()` or `_build_event_key()` needs to be smarter about detecting the payload shape. Since the handler knows the event type, the cleanest approach is to pass it in.

### GitHubClient Methods Available

```python
client.get(path, **kwargs)   # kwargs includes params={}
client.post(path, **kwargs)  # kwargs includes json={}
client.patch(path, **kwargs) # kwargs includes json={}
```

All return `httpx.Response`. The client is already module-level in `handler.py`.

## Architecture Patterns

### pull_request Webhook Payload Structure

When GitHub sends a `pull_request` event (HIGH confidence -- well-established API):

```python
{
    "action": "opened",  # or "synchronize", "reopened"
    "number": 42,
    "pull_request": {
        "number": 42,
        "head": {
            "sha": "abc123...",
            "ref": "feature-branch",
            "repo": {"full_name": "owner/repo"},
        },
        "base": {
            "sha": "def456...",
            "ref": "main",
            "repo": {"full_name": "owner/repo"},
        },
        "draft": False,  # ignored per decision
    },
    "repository": {
        "full_name": "owner/repo",
        "default_branch": "main",
    },
    "sender": {...},
}
```

Key fields for this phase:
- `payload["action"]` -- to filter valid actions
- `payload["number"]` -- PR number for comments
- `payload["pull_request"]["head"]["sha"]` -- head SHA for change detection + Check Run
- `payload["pull_request"]["base"]["ref"]` -- base branch for environment resolution
- `payload["repository"]["full_name"]` -- repo for API calls

### GitHub Issues Comments API

**List comments:** `GET /repos/{owner}/{repo}/issues/{issue_number}/comments`
- Query params: `per_page` (max 100), `page` (1-indexed), `since` (ISO 8601)
- Returns array of comment objects: `[{"id": 123, "body": "...", "user": {...}, ...}]`

**Create comment:** `POST /repos/{owner}/{repo}/issues/{issue_number}/comments`
- Body: `{"body": "markdown content"}`
- Returns the created comment object

**Update comment:** `PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}`
- Body: `{"body": "updated markdown content"}`
- Returns the updated comment object
- Note: URL uses `/issues/comments/{id}`, NOT `/issues/{number}/comments/{id}`

### Sticky Comment Pattern

The sticky comment approach uses an HTML comment marker invisible to readers:

```markdown
<!-- ferry:plan -->
## content here
```

**Find existing comment:** List all comments on the PR, search each comment's `body` for the marker string `<!-- ferry:plan -->`. If found, use `PATCH` to update. If not found, use `POST` to create.

**Pagination concern:** For PRs with many comments (>100), pagination is needed. However, in practice, Ferry-managed repos will have few PR comments. A reasonable approach: fetch up to 100 comments per page, paginate if needed. For simplicity, iterate pages until found or exhausted.

Implementation:

```python
PLAN_MARKER = "<!-- ferry:plan -->"

def find_plan_comment(
    client: GitHubClient,
    repo: str,
    pr_number: int,
) -> int | None:
    """Find existing Ferry plan comment by marker. Returns comment ID or None."""
    page = 1
    while True:
        resp = client.get(
            f"/repos/{repo}/issues/{pr_number}/comments",
            params={"per_page": 100, "page": page},
        )
        if resp.status_code != 200:
            return None
        comments = resp.json()
        if not comments:
            return None
        for comment in comments:
            if PLAN_MARKER in comment.get("body", ""):
                return comment["id"]
        if len(comments) < 100:
            return None
        page += 1
```

### upsert_plan_comment Flow

```python
def upsert_plan_comment(
    client: GitHubClient,
    repo: str,
    pr_number: int,
    body: str,
) -> dict:
    """Create or update the Ferry plan sticky comment."""
    existing_id = find_plan_comment(client, repo, pr_number)
    if existing_id:
        resp = client.patch(
            f"/repos/{repo}/issues/comments/{existing_id}",
            json={"body": body},
        )
    else:
        resp = client.post(
            f"/repos/{repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
    return resp.json()
```

### Environment Resolution

Match the PR base branch against `FerryConfig.environments[].branch`:

```python
def resolve_environment(
    config: FerryConfig,
    base_branch: str,
) -> EnvironmentMapping | None:
    """Find environment mapping for a branch. Returns None if no match."""
    for env in config.environments:
        if env.branch == base_branch:
            return env
    return None
```

Returns the full `EnvironmentMapping` (name, branch, auto_deploy) so the comment formatter can use `auto_deploy` for the CTA footer.

### Plan Comment Body Formatting

Based on the locked visual design in CONTEXT.md:

```python
def format_plan_comment(
    affected: list[AffectedResource],
    environment: EnvironmentMapping | None = None,
) -> str:
    """Format the sticky plan comment body."""
    parts = [PLAN_MARKER]  # Hidden marker first

    # Header
    if environment:
        parts.append(f"## :ferry: Ferry: Deployment Plan -> **{environment.name}**")
    else:
        parts.append("## :ferry: Ferry: Deployment Plan")

    parts.append("")

    # Resource list grouped by type
    grouped: dict[str, list[AffectedResource]] = {}
    for r in affected:
        grouped.setdefault(r.resource_type, []).append(r)

    for rtype in ("lambda", "step_function", "api_gateway"):
        resources = grouped.get(rtype)
        if not resources:
            continue
        parts.append(f"#### {_TYPE_DISPLAY_NAMES[rtype]}")
        for r in resources:
            parts.append(f"- **{r.name}** _({r.change_kind})_")
        parts.append("")

    # CTA footer
    if environment and environment.auto_deploy:
        parts.append(f"Will auto-deploy to **{environment.name}** on merge. Comment `/ferry apply` to deploy now.")
    elif environment:
        parts.append(f"Comment `/ferry apply` to deploy to **{environment.name}**.")
    else:
        parts.append("Will deploy on merge to default branch.")

    return "\n".join(parts)
```

**No-changes update** (when sticky comment exists but no resources affected):

```python
def format_no_changes_comment() -> str:
    parts = [PLAN_MARKER]
    parts.append("## :ferry: Ferry: Deployment Plan")
    parts.append("")
    parts.append("No Ferry-managed resources affected by this PR.")
    return "\n".join(parts)
```

Note: The CONTEXT.md shows the ferry emoji as the boat emoji. Use the literal emoji character in the actual implementation.

### Handler Routing Pattern

Extend the handler to route both `push` and `pull_request` events:

```python
# Replace the current filter block:
# if event_type != "push":
#     return _response(200, {"status": "ignored"})

SUPPORTED_EVENTS = {"push", "pull_request"}
if event_type not in SUPPORTED_EVENTS:
    return _response(200, {"status": "ignored"})

# After dedup + auth + config...
if event_type == "push":
    return _handle_push(payload, config, ...)
elif event_type == "pull_request":
    return _handle_pull_request(payload, config, ...)
```

### _handle_pull_request Flow

```
1. Extract PR context: action, number, head_sha, base_branch
2. Filter: action not in {opened, synchronize, reopened} -> ignore
3. Change detection: get_changed_files(base_branch, head_sha) + match_resources
4. Environment resolution: match base_branch to environments
5. Comment logic:
   a. If affected resources: format plan comment -> upsert
   b. If no affected resources:
      - Find existing sticky comment
      - If exists: update to "no changes"
      - If not exists: skip (silent)
6. Check Run: create_check_run with appropriate conclusion
   - success if resources detected
   - neutral if no changes
7. Return response
```

### Recommended Project Structure

```
backend/src/ferry_backend/
  checks/
    __init__.py
    runs.py          # Existing: create_check_run, find_open_prs, post_pr_comment, etc.
    plan.py          # NEW: format_plan_comment, find_plan_comment, upsert_plan_comment, resolve_environment
  webhook/
    handler.py       # MODIFIED: add pull_request routing, _handle_pull_request()
    dedup.py         # MODIFIED: extend _build_event_key for pull_request payloads
    signature.py     # Unchanged
tests/test_backend/
  test_plan.py       # NEW: unit tests for plan.py functions
  test_handler_pr.py # NEW: integration tests for pull_request handler flow
  test_dedup.py      # MODIFIED: add pull_request dedup tests
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Comment pagination | Custom page-walker with retries | Simple `while` loop with `per_page=100` | PRs rarely have >100 comments; over-engineering here wastes effort |
| Environment resolution | Complex branch pattern matching | Exact string match on `env.branch == base_branch` | v2.0 is exact-match only (glob patterns deferred) |
| Comment formatting | Template engine (Jinja2, etc.) | f-string concatenation in `format_plan_comment()` | Comment is ~15 lines max; a template engine adds dependency for no benefit |
| Check Run for plan | New check run function | Existing `create_check_run()` with conclusion override | One function, two callers |

## Common Pitfalls

### Pitfall 1: Compare API base parameter for PRs
**What goes wrong:** Using `before_sha` from the `pull_request` payload as the Compare API base, which gives an incremental diff instead of full PR diff.
**Why it happens:** `pull_request.synchronize` has a `before` field (previous head SHA), but the plan needs ALL changed files in the PR, not just the latest push.
**How to avoid:** Always use `pull_request.base.ref` (the base branch name, e.g., "main") as the Compare API base. The three-dot compare `main...head_sha` automatically uses merge-base to show the full PR diff. This is exactly what the push handler already does for PR branches (line 166: `compare_base = default_branch` for non-default branches).
**Warning signs:** Plan comment shows only files from the latest push, not the entire PR.

### Pitfall 2: PATCH URL for comment update
**What goes wrong:** Using `/repos/{owner}/{repo}/issues/{pr_number}/comments/{id}` instead of `/repos/{owner}/{repo}/issues/comments/{id}`.
**Why it happens:** The update endpoint uses a different URL structure than the list/create endpoints. The comment ID is globally unique, so no issue number is needed.
**How to avoid:** Use the correct PATCH endpoint: `/repos/{owner}/{repo}/issues/comments/{comment_id}`.

### Pitfall 3: HTML marker placement in comment body
**What goes wrong:** Marker placed after visible content causes `find_plan_comment` to scan more text before finding it, or worse, user editing the comment could shift the marker.
**How to avoid:** Always place `<!-- ferry:plan -->` as the very first line of the comment body. Search with `in` operator on the full body string.

### Pitfall 4: Race condition between duplicate webhook deliveries
**What goes wrong:** GitHub may send the same `pull_request` event twice (retry). Both arrive before either completes, resulting in two comments.
**Why it happens:** GitHub retries webhooks if the first response is slow (>10s timeout).
**How to avoid:** The existing DynamoDB dedup handles this -- one of the two deliveries will fail the conditional write and return "duplicate". The `_build_event_key` for `pull_request` must use `EVENT#pull_request#{repo}#{pr_number}#{head_sha}` to catch re-queued events with new delivery IDs.

### Pitfall 5: ferry.yaml not found in PR (new repo, no config yet)
**What goes wrong:** `fetch_ferry_config` raises `ConfigError` if `ferry.yaml` doesn't exist at the PR head SHA.
**Why it happens:** PR might be opened before ferry.yaml is committed, or the PR adds ferry.yaml for the first time.
**How to avoid:** The existing `ConfigError` handler in the handler already handles this -- it posts an error comment on the PR. This behavior is correct for the plan case too.

### Pitfall 6: Check Run conclusion mapping change
**What goes wrong:** Existing push handler uses `success` for no-changes Check Run, but CONTEXT.md specifies `neutral` for PR plan no-changes.
**Why it happens:** Different semantic meaning: on push, "no changes" is fine (success). On PR, "no changes" means "nothing for Ferry to do" which is informational (neutral).
**How to avoid:** Modify `create_check_run()` to accept an optional `no_change_conclusion` parameter, defaulting to `"success"` (backward-compatible). PR handler passes `"neutral"`.

## Code Examples

### Example: pull_request payload extraction

```python
# Verified structure from GitHub webhook docs
action = payload.get("action", "")
pr_number = payload["number"]
pr = payload["pull_request"]
head_sha = pr["head"]["sha"]
base_branch = pr["base"]["ref"]
repo = payload["repository"]["full_name"]
```

### Example: Sticky comment marker format

```python
PLAN_MARKER = "<!-- ferry:plan -->"

# Comment body always starts with the marker
body = f"{PLAN_MARKER}\n## rest of content..."

# Find by checking if marker is in comment body
for comment in comments:
    if PLAN_MARKER in comment.get("body", ""):
        return comment["id"]
```

### Example: Environment resolution

```python
from ferry_backend.config.schema import EnvironmentMapping, FerryConfig

def resolve_environment(
    config: FerryConfig,
    base_branch: str,
) -> EnvironmentMapping | None:
    for env in config.environments:
        if env.branch == base_branch:
            return env
    return None

# Usage:
env = resolve_environment(config, base_branch="staging")
# env.name -> "staging", env.auto_deploy -> True
```

### Example: Dedup key for pull_request

```python
def _build_event_key(payload: dict) -> str | None:
    repo = payload.get("repository", {}).get("full_name")
    # Push events
    after_sha = payload.get("after")
    if repo and after_sha and "pull_request" not in payload:
        return f"EVENT#push#{repo}#{after_sha}"
    # Pull request events
    pr = payload.get("pull_request")
    number = payload.get("number")
    if repo and pr and number:
        head_sha = pr.get("head", {}).get("sha")
        if head_sha:
            return f"EVENT#pull_request#{repo}#{number}#{head_sha}"
    return None
```

### Example: Test helper for pull_request events

```python
def _make_pr_event(
    action: str = "opened",
    pr_number: int = 42,
    head_sha: str = "b" * 40,
    base_ref: str = "main",
    head_ref: str = "feature-branch",
    delivery_id: str = "delivery-pr-001",
) -> dict:
    payload = {
        "action": action,
        "number": pr_number,
        "pull_request": {
            "number": pr_number,
            "head": {
                "sha": head_sha,
                "ref": head_ref,
            },
            "base": {
                "ref": base_ref,
            },
            "draft": False,
        },
        "repository": {
            "full_name": "owner/repo",
            "default_branch": "main",
        },
    }
    body = json.dumps(payload)
    signature = _make_signature(body)
    return {
        "body": body,
        "isBase64Encoded": False,
        "headers": {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    }
```

## Test Patterns

### Existing Test Patterns (from codebase analysis)

The project uses a consistent testing approach:

1. **pytest + pytest-httpx** for mocking HTTP calls to GitHub API
2. **moto mock_aws** for DynamoDB in handler integration tests
3. **monkeypatch** for env vars and JWT generation
4. **Class-based test organization** (`TestClassName` with `test_method_name`)
5. **Helper functions** at module level for event construction (`_make_push_event`, `_mock_installation_token`, etc.)
6. **Autouse fixtures** for env vars and JWT mocking
7. **Import inside test methods** for handler tests (avoids module-level Settings initialization)

### New Test Files Needed

**`test_plan.py`** -- Unit tests for `checks/plan.py`:
- `format_plan_comment()` with affected resources (single type, multiple types)
- `format_plan_comment()` with environment (auto_deploy true/false)
- `format_plan_comment()` without environment
- `format_no_changes_comment()` output
- `find_plan_comment()` with marker found
- `find_plan_comment()` with no comments
- `find_plan_comment()` with marker not found
- `find_plan_comment()` with pagination (>100 comments, marker on page 2)
- `upsert_plan_comment()` creates when no existing
- `upsert_plan_comment()` updates when existing found
- `resolve_environment()` with match
- `resolve_environment()` with no match
- `resolve_environment()` with empty environments list

**`test_handler_pr.py`** -- Integration tests for PR handler:
- PR opened with resource changes -> sticky comment + Check Run (success)
- PR synchronize updates existing sticky comment (PATCH, not new POST)
- PR opened with no resource changes -> no comment, Check Run (neutral)
- PR synchronize removes all changes (had comment) -> update to "no changes"
- PR with environments configured -> comment shows environment name
- PR with unsupported action (e.g., "closed") -> ignored
- PR with config error -> error comment posted
- No dispatch triggered for any PR event

**`test_dedup.py`** -- Additional tests:
- `pull_request` event dedup key generation
- Re-queued `pull_request` event caught by event key

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-httpx 0.30+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/python -m pytest tests/test_backend/test_plan.py tests/test_backend/test_handler_pr.py -x` |
| Full suite command | `.venv/bin/python -m pytest tests/test_backend/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAN-01 | PR opened -> sticky comment with affected resources | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_pr.py::TestHandlerPR::test_pr_opened_with_changes_posts_plan_comment -x` | Wave 0 |
| PLAN-02 | PR synchronize -> update existing sticky comment | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_pr.py::TestHandlerPR::test_pr_synchronize_updates_existing_comment -x` | Wave 0 |
| PLAN-03 | Plan comment shows environment name | unit | `.venv/bin/python -m pytest tests/test_backend/test_plan.py::TestFormatPlanComment::test_format_with_environment -x` | Wave 0 |
| PLAN-04 | Check Run with correct conclusion | integration | `.venv/bin/python -m pytest tests/test_backend/test_handler_pr.py::TestHandlerPR::test_pr_opened_creates_check_run -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/test_backend/test_plan.py tests/test_backend/test_handler_pr.py -x`
- **Per wave merge:** `.venv/bin/python -m pytest tests/test_backend/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_backend/test_plan.py` -- covers PLAN-01, PLAN-02, PLAN-03 (unit tests for plan.py)
- [ ] `tests/test_backend/test_handler_pr.py` -- covers PLAN-01, PLAN-02, PLAN-03, PLAN-04 (integration tests)
- [ ] Additional `pull_request` dedup tests in existing `test_dedup.py`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Check Run `success` for no changes | `neutral` for PR plan no-changes | Phase 30 | Distinct visual treatment in PR status area |
| Push-only webhook handling | Push + pull_request events | Phase 30 | Must extend handler routing |
| Single event key format in dedup | Event-type-aware dedup keys | Phase 30 | `_build_event_key` needs PR event support |

## Open Questions

1. **Config error handling in PR context**
   - What we know: Current push handler posts a config error comment via `post_pr_comment()`. For PR events, the same pattern works since we have the PR number directly.
   - What's unclear: Should the config error comment also be a sticky comment (using the plan marker)?
   - Recommendation: Keep config errors as separate non-sticky comments (current behavior). The sticky pattern is only for the plan comment. Config errors are exceptional and should be visible as distinct comments.

2. **ferry.yaml change detection in PR**
   - What we know: Push handler checks if `ferry.yaml` is in `changed_files` and diffs old vs new config.
   - What's unclear: For PRs, should we diff `ferry.yaml` at base branch vs head SHA?
   - Recommendation: Yes, apply the same logic. If `ferry.yaml` is in the changed files, fetch old config at base branch and diff. This ensures the plan comment shows resources added/modified in `ferry.yaml`.

## Sources

### Primary (HIGH confidence)
- Codebase analysis of all source files in `backend/src/ferry_backend/` -- direct code reading
- Codebase analysis of all test files in `tests/test_backend/` -- direct code reading
- Phase 29 output: `utils/src/ferry_utils/models/dispatch.py` -- verified v3 payload model with environment fields
- `config/schema.py` -- verified `EnvironmentMapping` model with `name`, `branch`, `auto_deploy` fields

### Secondary (MEDIUM confidence)
- [GitHub REST API - Issue Comments](https://docs.github.com/en/rest/issues/comments) -- endpoint patterns for list/create/update
- [GitHub Webhooks - pull_request event](https://docs.github.com/en/webhooks/webhook-events-and-payloads) -- payload structure for opened/synchronize/reopened

### Tertiary (LOW confidence)
None -- all findings verified against codebase or well-established GitHub API patterns.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - pure Python, no new dependencies, extends existing patterns
- Architecture: HIGH - handler routing, sticky comments, env resolution are all straightforward
- Pitfalls: HIGH - identified from direct codebase analysis (e.g., Compare API base param, PATCH URL)
- GitHub API: HIGH - well-established API, stable since 2022-11-28 version

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable domain, no fast-moving dependencies)
