# Phase 8: Error Surfacing and Failure Reporting - Research

**Researched:** 2026-02-28
**Domain:** Error surfacing, GitHub Check Runs, GHA workflow commands, structured logging
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Check Run presentation**: Resource-specific titles (e.g., "Ferry: my-api-lambda build failed"). Summary body contains error message only -- terse and scannable. Check Runs created for both success and failure (not failure-only).
- **Log output format**: Use both GHA annotations (`::error::`) and structured log blocks -- annotations for summary view, blocks for detail. Step-by-step progress on success: show building, pushing, deploying, done. Collapsible `::group::` sections per resource. Explicit skip messages when deploy skipped due to unchanged image digest.
- **Error detail level**: AWS identifiers use partial masking -- show last 4 of account ID, use logical names primarily. Actionable hints for recognizable errors (e.g., "ECR repo not found -- ensure repo exists in your IaC"). Hints appear in GHA logs only, NOT in Check Run summary (keep PR view terse). Stack traces hidden by default, shown when debug flag/env var is set.
- **Backend error visibility**: Config errors (invalid ferry.yaml) surface as PR comment, not Check Run. Auth errors (bad JWT, expired token) are backend logs only -- system-level, not developer-actionable. Separate handling: config errors -> PR-visible, auth errors -> infra-visible.

### Claude's Discretion
- Backend HTTP response format (structured JSON vs status codes)
- Backend logging format (structured JSON vs human-readable)
- Pre-merge vs post-merge Check Run relationship (separate vs update existing)
- Debug flag mechanism (env var name, enabling pattern)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WHOOK-03 | Build and deploy failures are surfaced in GitHub PR status checks and GHA workflow logs | All research sections below -- Check Run API for PR status, GHA workflow commands for log surfacing, structured error classification for backend, action-side error reporting patterns |
</phase_requirements>

## Summary

This phase closes the last open v1 requirement (WHOOK-03) by adding structured error handling across both Ferry components. The existing codebase already has substantial error handling infrastructure: the backend has structlog JSON logging, ConfigError handling, and Check Run creation; the action has GHA workflow command wrappers (`gha.py`), `::group::` sections, `::error::` annotations, actionable hints for common AWS errors, and `GITHUB_STEP_SUMMARY` markdown output. The phase is about *closing gaps* and *upgrading consistency*, not building from scratch.

The key gaps are: (1) the backend handler has no top-level exception handler -- an unhandled exception produces a Lambda 500, not a structured response; (2) config errors on the default branch (post-merge) are logged but not surfaced as a PR comment; (3) the action does not create GitHub Check Runs to report build/deploy status back to the PR; (4) auth failures in the backend produce unstructured errors; (5) debug-mode stack trace toggling does not exist. The action currently has `pr_number` in the dispatch payload and `GITHUB_REPOSITORY` from GHA environment, but no GitHub API client or token to create Check Runs.

**Primary recommendation:** Add a top-level exception handler to the backend, add a `post_pr_comment` function for config errors, add a `PATCH /check-runs/{id}` method to GitHubClient, and create an action-side Check Run reporter that uses `GITHUB_TOKEN` to post success/failure Check Runs per resource. Use `FERRY_DEBUG=1` as the debug flag.

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| structlog | >=24.1 | Backend structured JSON logging | Already configured with JSONRenderer, contextvars, CloudWatch-compatible |
| httpx | >=0.27 | GitHub API client | Already used; needs PATCH method added |
| ferry_action.gha | n/a | GHA workflow commands | Already has error(), warning(), begin_group(), end_group(), write_summary(), mask_value() |

### Supporting (already in project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | v2 | Structured error response models | For backend HTTP response body validation |
| boto3 | >=1.34 | AWS API (existing) | No new AWS APIs needed |
| ferry_utils.errors | n/a | Error hierarchy | Extend with BuildError, DeployError if needed |

### No New Dependencies
This phase requires zero new library additions. All needed functionality exists in the current stack:
- structlog for backend logging (already configured)
- httpx for GitHub API calls (already wrapped in GitHubClient)
- `gha.py` for GHA workflow commands (already has all needed commands)
- `GITHUB_TOKEN` available in GHA environment for Check Run creation

## Architecture Patterns

### Recommended Changes by Component

```
backend/src/ferry_backend/
  webhook/handler.py        # ADD: top-level try/except, structured error responses
  github/client.py          # ADD: patch() method for Check Run updates
  checks/runs.py            # MODIFY: config error -> PR comment (not Check Run)
                             # ADD: post_pr_comment() function
  logging.py                # ADD: format_exc_info processor (conditional on debug)

action/src/ferry_action/
  gha.py                    # ADD: mask_account_id() helper
  report.py                 # NEW: Check Run creation from action side
  build.py                  # MODIFY: call report.py on success/failure
  deploy.py                 # MODIFY: call report.py on success/failure
  deploy_stepfunctions.py   # MODIFY: call report.py on success/failure
  deploy_apigw.py           # MODIFY: call report.py on success/failure

utils/src/ferry_utils/
  errors.py                 # ADD: BuildError, DeployError (optional)
```

### Pattern 1: Backend Top-Level Exception Handler
**What:** Wrap the entire handler body in try/except to catch any unhandled exception and return a structured JSON response instead of a Lambda 500.
**When to use:** Always -- the handler currently has no safety net beyond ConfigError.
**Example:**
```python
def handler(event: dict, context: object) -> dict:
    try:
        # ... existing handler body ...
    except ConfigError as exc:
        log.error("config_error", error=str(exc))
        # ... existing config error handling ...
    except GitHubAuthError as exc:
        log.error("auth_error", error=str(exc))
        return _response(500, {"status": "auth_error", "error": str(exc)})
    except Exception as exc:
        log.error("unhandled_error", error=str(exc), exc_info=True)
        return _response(500, {"status": "internal_error", "error": "internal server error"})
```
**Source:** Codebase analysis -- handler.py currently catches ConfigError but nothing else.

### Pattern 2: Config Error as PR Comment (Not Check Run)
**What:** When ferry.yaml validation fails on a push to the default branch, post a PR comment (via `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`) to the merged PR. On PR branches, keep the current Check Run behavior.
**When to use:** Per user decision -- config errors -> PR comment, not Check Run.
**Example:**
```python
def post_pr_comment(client: GitHubClient, repo: str, pr_number: int, body: str) -> dict:
    """Post a comment on a PR (issues API -- PRs are issues)."""
    resp = client.post(
        f"/repos/{repo}/issues/{pr_number}/comments",
        json={"body": body},
    )
    return resp.json()
```
**Source:** GitHub REST API -- `POST /repos/{owner}/{repo}/issues/{issue_number}/comments` (PRs are issues).

**Important nuance:** The CONTEXT.md says "Config errors (invalid ferry.yaml): surface as PR comment, not Check Run." Currently, config errors on PR branches create a failed Check Run (conclusion=failure, title="Configuration Error"). The decision changes this to a PR comment instead. On default branch pushes, the handler already looks up PRs via `find_open_prs` -- the merged PR can receive the comment.

### Pattern 3: Action-Side Check Run Reporter
**What:** After build/deploy completes (success or failure), the action creates a GitHub Check Run on the PR's head SHA. This gives developers a per-resource pass/fail view directly on the PR.
**When to use:** Locked decision -- Check Runs for both success and failure.
**Implementation notes:**
- The action already has `pr_number` from `DispatchPayload.pr_number`
- GHA provides `GITHUB_TOKEN` as `${{ secrets.GITHUB_TOKEN }}` or `${{ github.token }}`
- The action needs: repo name (`GITHUB_REPOSITORY` env var), head SHA (`trigger_sha` from payload), and a way to call the Check Runs API
- Use httpx directly (it's already a transitive dep via ferry-utils -> pydantic) OR add a thin GitHub API function in the action
- Check Run name: `"Ferry: {resource_name} {phase}"` where phase is "build" or "deploy"

**Example:**
```python
import httpx
import os

def create_check_run(
    resource_name: str,
    conclusion: str,  # "success" or "failure"
    title: str,
    summary: str,
    sha: str,
) -> None:
    """Create a GitHub Check Run from the action side."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        return  # Silent skip if not in GHA context

    httpx.post(
        f"https://api.github.com/repos/{repo}/check-runs",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "name": f"Ferry: {resource_name}",
            "head_sha": sha,
            "status": "completed",
            "conclusion": conclusion,
            "output": {"title": title, "summary": summary},
        },
    )
```
**Source:** GitHub Check Runs API -- `POST /repos/{owner}/{repo}/check-runs`. Requires `checks:write` permission. GHA's built-in `GITHUB_TOKEN` has this permission by default.

**IMPORTANT:** The action runs on default branch pushes (post-merge). The Check Run is created against `trigger_sha`. For this to appear on the original PR, the trigger SHA must be the merge commit or a commit that was part of the PR. The `find_open_prs` mechanism in the backend uses the commit SHA to find associated PRs -- Check Runs on the merge commit SHA will associate with the correct commit history.

### Pattern 4: Account ID Masking
**What:** Show only last 4 digits of AWS account ID in error messages.
**When to use:** Per user decision -- partial masking.
**Example:**
```python
def mask_account_id(account_id: str) -> str:
    """Mask account ID to show only last 4 digits."""
    if len(account_id) > 4:
        return f"****{account_id[-4:]}"
    return account_id
```

### Pattern 5: Debug Flag for Stack Traces
**What:** Control stack trace visibility via environment variable.
**When to use:** Claude's discretion -- recommended `FERRY_DEBUG=1`.
**Example:**
```python
import os
import traceback

def format_error_detail(exc: Exception) -> str:
    """Format error with optional stack trace based on debug flag."""
    msg = str(exc)
    if os.environ.get("FERRY_DEBUG", "").lower() in ("1", "true", "yes"):
        msg += f"\n\nStack trace:\n{traceback.format_exc()}"
    return msg
```

### Pattern 6: Structured Backend HTTP Responses
**What:** All backend responses use consistent JSON structure.
**Claude's discretion area.** Recommendation: Use structured JSON for all responses.
**Example:**
```python
# Success responses
{"status": "processed", "affected": 3}
{"status": "ignored"}
{"status": "duplicate"}

# Error responses
{"status": "config_error", "error": "Missing required field: name"}
{"status": "auth_error", "error": "Installation token exchange failed: 401"}
{"status": "internal_error", "error": "internal server error"}
```
The existing handler already follows this pattern for success cases. Error cases need the same consistency. Status codes: 200 for processed/ignored/duplicate, 200 for config_error (per existing behavior -- not the backend's fault), 500 for auth_error and internal_error.

### Pre-merge vs Post-merge Check Run Relationship
**Claude's discretion area.** Recommendation: **Separate Check Runs with distinct names.**

- Pre-merge (backend, PR branch push): `"Ferry: Deployment Plan"` -- already exists, shows what WILL deploy
- Post-merge (action, default branch push): `"Ferry: {resource_name}"` -- shows build/deploy result per resource

Rationale: These are different phases of the lifecycle. The pre-merge Check Run is about *planning* (what will change). The post-merge Check Runs are about *execution* (did it work). Different names keep them separate in the PR's Checks tab. Using PATCH to update the planning check run would conflate two different concerns and make the UI confusing.

### Anti-Patterns to Avoid
- **Silent HTTP 200 on error**: The current handler returns 200 for config errors (correct -- it's not a webhook validation failure), but on the default branch with no open PRs, the error is only logged. Post-merge config errors must produce a PR comment.
- **Unmasked AWS account IDs in error messages**: Error hints in GHA logs should use logical names and masked IDs, not raw account numbers.
- **Unstructured Lambda 500**: Any unhandled exception in the handler should produce a structured JSON response, not a raw traceback.
- **Check Run without annotation context**: Don't put actionable hints in Check Run summaries -- keep them terse. Hints go in GHA logs only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GHA workflow commands | Custom print formatting | Existing `gha.py` module | Already has error(), warning(), begin_group(), end_group(), write_summary(), mask_value() |
| GitHub API client | New HTTP wrapper | Existing `GitHubClient` (add patch() method) | Consistency with existing patterns, shared auth handling |
| JSON structured logging | Custom log formatter | Existing structlog configuration | Already configured with JSONRenderer and CloudWatch-compatible output |
| Error type hierarchy | Ad-hoc string matching | Existing `ferry_utils.errors` module | Already has FerryError, ConfigError, GitHubAuthError |

**Key insight:** This phase is mostly about *connecting existing pieces* and *filling gaps*, not building new infrastructure. The error handling plumbing exists; the surfacing layer does not.

## Common Pitfalls

### Pitfall 1: Check Run Permissions from GHA Token
**What goes wrong:** The action tries to create a Check Run using `GITHUB_TOKEN` but gets 403 because the token lacks `checks:write` permission.
**Why it happens:** By default, `GITHUB_TOKEN` has read/write permissions for most scopes in the same repository, BUT the repository settings can restrict this via "Workflow permissions" settings (read-only default).
**How to avoid:** Document that the user's workflow needs `permissions: checks: write` in the workflow YAML. The composite action YAML cannot set permissions -- it must be set in the calling workflow.
**Warning signs:** 403 errors when the action tries to create Check Runs.

### Pitfall 2: GHA Annotation Limits
**What goes wrong:** More than 10 error annotations per step are silently dropped.
**Why it happens:** GitHub Actions limits: 10 error annotations per step, 10 warning annotations per step, 50 per job.
**How to avoid:** Use annotations sparingly -- one `::error::` per resource failure, not per error line. For detailed output, use `::group::` blocks and plain print statements.
**Warning signs:** Missing annotations when deploying many resources simultaneously.

### Pitfall 3: Check Run on Merge Commit SHA
**What goes wrong:** The action creates a Check Run on `trigger_sha` (the merge commit), but it doesn't appear on the original PR.
**Why it happens:** After a PR is merged, the merge commit is on the default branch. GitHub associates Check Runs with the commit SHA. PRs show Check Runs for commits that are part of the PR.
**How to avoid:** The merge commit IS part of the merged PR's history. GitHub should display Check Runs from the merge commit on the merged PR. However, if the PR is already merged/closed, the Check Run may be less visible. This is acceptable -- the GHA workflow log is the primary visibility channel for post-merge status.
**Warning signs:** Check Runs not appearing on merged PRs.

### Pitfall 4: PR Comment on Default Branch Config Error
**What goes wrong:** Config error occurs on default branch push, but `find_open_prs` returns no open PRs (the PR is already merged/closed).
**Why it happens:** The existing `find_open_prs` filters by `state=="open"`, but merged PRs have `state=="closed"`.
**How to avoid:** For PR comment on config error, the handler needs to find the *merged* PR associated with the push. The current `find_open_prs` already returns all associated PRs from the API before filtering -- modify the filter or add a `find_merged_pr` variant that looks for recently merged PRs.
**Warning signs:** Config errors on default branch silently logged with no PR comment.

### Pitfall 5: Action-Side httpx Not Installed
**What goes wrong:** The action creates a `report.py` module that uses httpx for Check Run creation, but httpx is not a direct dependency of `ferry-action`.
**Why it happens:** httpx is a dependency of `ferry-backend`, not `ferry-action`. The action package only depends on boto3, ferry-utils, and pyyaml.
**How to avoid:** Either add httpx to ferry-action dependencies, OR use the standard library `urllib.request` for this single POST call. Recommendation: add httpx -- it's a small addition and maintains consistency.
**Warning signs:** Import errors in the action when trying to use httpx.

## Code Examples

### Backend: Structured Error Response Wrapper
```python
# Source: Existing handler.py pattern (extended)
def _response(status_code: int, body: dict) -> dict:
    """Build Lambda Function URL response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }

# Current: _response(200, {"status": "config_error", "error": str(exc)})
# New:     _response(500, {"status": "auth_error", "error": str(exc)})
# New:     _response(500, {"status": "internal_error", "error": "internal server error"})
```

### Backend: Post PR Comment for Config Error
```python
# Source: GitHub REST API /repos/{owner}/{repo}/issues/{issue_number}/comments
def post_pr_comment(
    client: GitHubClient, repo: str, pr_number: int, body: str
) -> dict:
    resp = client.post(
        f"/repos/{repo}/issues/{pr_number}/comments",
        json={"body": body},
    )
    return resp.json()

# Usage in handler:
prs = find_open_prs(github_client, repo, after_sha)
if prs:
    comment_body = (
        f"**Ferry: Configuration Error**\n\n"
        f"ferry.yaml validation failed:\n"
        f"```\n{str(exc)}\n```"
    )
    post_pr_comment(github_client, repo, prs[0]["number"], comment_body)
```

### Backend: GitHubClient.patch() Method
```python
# Source: Existing get/post pattern in client.py
def patch(self, path: str, **kwargs: Any) -> httpx.Response:
    """Send PATCH request to GitHub API."""
    url = f"{self.base_url}{path}"
    return self._client.patch(url, headers=self._headers, **kwargs)
```

### Action: Check Run Reporter
```python
# Source: GitHub Check Runs API + existing gha.py patterns
import httpx
import os

GITHUB_API = "https://api.github.com"

def report_check_run(
    resource_name: str,
    phase: str,  # "build" or "deploy"
    conclusion: str,  # "success" or "failure"
    summary: str,
    trigger_sha: str,
) -> None:
    """Create a Check Run to report build/deploy status."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        return

    title = f"{phase.capitalize()} {'succeeded' if conclusion == 'success' else 'failed'}"
    name = f"Ferry: {resource_name} {phase}"

    httpx.post(
        f"{GITHUB_API}/repos/{repo}/check-runs",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "name": name,
            "head_sha": trigger_sha,
            "status": "completed",
            "conclusion": conclusion,
            "output": {"title": title, "summary": summary},
        },
        timeout=30.0,
    )
```

### Action: GHA Progress Output Pattern
```python
# Source: Existing gha.py + CONTEXT.md decisions
from ferry_action import gha

def build_with_reporting(resource_name: str, ...):
    gha.begin_group(f"Building {resource_name}")
    try:
        print(f"[1/3] Building Docker image...")
        # ... build logic ...
        print(f"[2/3] Authenticating to ECR...")
        # ... ecr login ...
        print(f"[3/3] Pushing to ECR...")
        # ... push ...
        print(f"Done: {resource_name} built and pushed")
    except subprocess.CalledProcessError as exc:
        gha.error(f"Build failed for {resource_name}: {hint}")
        # Create failed Check Run
        report_check_run(resource_name, "build", "failure", hint, trigger_sha)
        sys.exit(1)
    finally:
        gha.end_group()

    # Create success Check Run
    report_check_run(resource_name, "build", "success", f"Built {resource_name}", trigger_sha)
```

### Action: Debug-Mode Stack Trace
```python
# Source: CONTEXT.md decision -- stack traces hidden by default
import os
import traceback

def format_action_error(exc: Exception, hint: str) -> str:
    """Format error for GHA log output with optional stack trace."""
    msg = hint
    if os.environ.get("FERRY_DEBUG", "").lower() in ("1", "true", "yes"):
        msg += f"\n\nFull traceback:\n{traceback.format_exc()}"
    return msg
```

### Backend: structlog Exception Logging
```python
# Source: structlog docs -- exc_info parameter
# Already supported by current structlog config (JSONRenderer handles exc_info)
log.error("auth_error", error=str(exc), exc_info=True)
# JSONRenderer will include the traceback in the JSON output for CloudWatch
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Unstructured Lambda 500 | Structured JSON error responses | This phase | All errors produce parseable JSON, not raw tracebacks |
| Config error as Check Run | Config error as PR comment | This phase (user decision) | PR view stays clean -- comments for config issues, Check Runs for deploy status |
| No post-merge status | Per-resource Check Runs from action | This phase | Developers see build/deploy results without checking CloudWatch |
| No debug mode | FERRY_DEBUG=1 for stack traces | This phase | Developers can opt into verbose output for debugging |

**Key change from existing behavior:** Config errors on PR branches currently create a failed Check Run (`"Ferry: Deployment Plan"` with `conclusion=failure`). The user decided to change this to a PR comment. This means the "Deployment Plan" Check Run should only show resource detection results (success or neutral), not config errors.

## Open Questions

1. **PR comment for config errors on PR branches vs default branch**
   - What we know: User decided "config errors -> PR comment, not Check Run." This applies to both PR branch pushes and default branch pushes.
   - What's unclear: On PR branches, the current Check Run for config errors is visible and useful. Switching to PR comments changes the UX.
   - Recommendation: Apply consistently -- PR comment for config errors everywhere. The Check Run (`"Ferry: Deployment Plan"`) should only appear when config is valid.

2. **Check Run visibility on merged PRs**
   - What we know: GitHub associates Check Runs with commit SHAs. The action runs post-merge against the merge commit SHA.
   - What's unclear: Whether Check Runs on a merge commit consistently appear on the merged PR's Checks tab.
   - Recommendation: Implement and verify. The GHA workflow logs are the guaranteed visibility channel. Check Runs are a bonus if GitHub shows them.

3. **Action needs GITHUB_TOKEN passed explicitly**
   - What we know: Composite actions don't automatically get `GITHUB_TOKEN`. The calling workflow must pass it.
   - What's unclear: Whether to use `${{ github.token }}` (automatic) or `${{ secrets.GITHUB_TOKEN }}` (explicit) in the composite action inputs.
   - Recommendation: Add a `github-token` input to all composite actions that need Check Run creation (build, deploy, deploy-stepfunctions, deploy-apigw). Default to `${{ github.token }}` in the workflow examples.

4. **find_open_prs returns no results for merged PRs**
   - What we know: `find_open_prs` filters by `state=="open"`. After a PR merges, the state is "closed".
   - What's unclear: Whether the GitHub API for "list pulls associated with commit" returns merged PRs for the merge commit.
   - Recommendation: Test the API behavior. If merged PRs are returned (with state "closed"), modify the filter. If not, the `pr_number` from the dispatch payload is the reliable source for the merged PR number.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: handler.py, client.py, runs.py, gha.py, build.py, deploy.py, deploy_stepfunctions.py, deploy_apigw.py, errors.py, logging.py
- [GitHub REST API endpoints for check runs](https://docs.github.com/en/rest/checks/runs) -- Create/Update Check Run API
- [GitHub REST API endpoints for issue comments](https://docs.github.com/en/rest/issues/comments) -- PR comment creation (issues API)
- [GitHub Actions workflow commands](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands) -- ::error::, ::group::, annotations syntax

### Secondary (MEDIUM confidence)
- [Creating GitHub Checks - Ken Muse](https://www.kenmuse.com/blog/creating-github-checks/) -- Check Run lifecycle patterns, naming best practices, annotation limits
- [structlog exceptions documentation](https://www.structlog.org/en/stable/exceptions.html) -- exc_info handling, format_exc_info, dict_tracebacks
- [GitHub community discussion on annotation limits](https://github.com/orgs/community/discussions/26680) -- 10 per step, 50 per job limits confirmed

### Tertiary (LOW confidence)
- Check Run visibility on merged PR merge commits -- needs empirical validation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, no new deps (except optionally httpx for action)
- Architecture: HIGH -- patterns follow existing codebase conventions, API endpoints well-documented
- Pitfalls: MEDIUM -- Check Run visibility on merged PRs and PR comment for config errors on default branch need validation

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable -- GitHub API is versioned, structlog is stable)
