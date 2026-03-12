# Architecture Patterns: v2.0 PR Integration

**Domain:** PR-triggered plan/apply deployments with environment mapping for serverless deploy tool (Ferry v2.0)
**Researched:** 2026-03-12
**Confidence:** HIGH (based on existing codebase analysis + verified GitHub API/GHA capabilities)

## Problem Statement

Ferry v1.5 handles only `push` events on the default branch. When a developer opens a PR, they see a Check Run preview ("2 resources will be affected") but have no way to:

1. See a detailed plan of what would deploy (build validation, dry-run output)
2. Deploy to a staging/preview environment from the PR before merge
3. Have merges automatically deploy to the correct target environment
4. Use GitHub Environment-scoped secrets/variables per deployment target

v2.0 adds a plan/apply model where PRs get rich deployment previews, `/ferry apply` comments trigger mid-way deploys to mapped environments, and merges auto-deploy to the production environment.

## Current Architecture (v1.5 Baseline)

```
GitHub push event (default branch only)
  -> Ferry Lambda (webhook handler)
     -> Signature validation, dedup (DynamoDB)
     -> Fetch ferry.yaml (GitHub Contents API at commit SHA)
     -> Compare commit diff against path mappings
     -> Group affected resources by type
     -> Build BatchedDispatchPayload (v2 schema)
     -> POST workflow_dispatch to ferry.yml
     -> Post Check Run on associated PR (if any)

GitHub push event (non-default branch)
  -> Ferry Lambda
     -> Same validation/dedup/config/detect pipeline
     -> Create Check Run (deployment plan preview) on PR
     -> NO dispatch (non-default branches do not deploy)
```

**Key constraints inherited from v1.5:**
- Backend is a single Lambda + DynamoDB (no queues, no complex state)
- Backend processes synchronously (no background jobs)
- Dispatch uses a single `workflow_dispatch` to `ferry.yml` with JSON payload in `inputs.payload`
- All build/deploy logic runs in user's GHA runners via composite actions
- GitHub App auth: JWT + installation token (already has push, PR, checks permissions)
- 65535 char payload limit on workflow_dispatch inputs

## Recommended Architecture for v2.0

### High-Level Flow

```
EVENT: pull_request (opened | synchronize | reopened)
  -> Ferry Lambda (webhook handler)
     -> Validate, dedup (existing pipeline)
     -> Fetch ferry.yaml at PR head SHA
     -> Detect changes: compare PR head vs base branch (three-dot diff)
     -> Create/update Check Run with deployment plan
     -> NO dispatch (plan mode = preview only)

EVENT: issue_comment (created) with body containing "/ferry apply"
  -> Ferry Lambda (webhook handler)
     -> Validate, dedup
     -> Verify: comment is on a PR (check issue.pull_request field)
     -> Fetch PR details (head SHA, head branch, base branch)
     -> Fetch ferry.yaml at PR head SHA
     -> Resolve target environment from ferry.yaml environments mapping
     -> Detect changes (same as PR event)
     -> Dispatch to ferry.yml with mode="apply" + environment name
     -> Post acknowledgment comment on PR

EVENT: push to default branch (existing v1.5 flow, enhanced)
  -> Ferry Lambda (webhook handler)
     -> Existing validation/dedup/config/detect pipeline
     -> Resolve target environment: default branch -> production environment
     -> Dispatch to ferry.yml with mode="apply" + environment name
     -> Post Check Run (existing behavior)
```

### Why This Three-Event Model

1. **`pull_request` for plan:** The `pull_request` event fires on PR open/sync/reopen, providing the correct three-dot diff (base...head). This is the natural trigger for "show me what changed." No dispatch needed -- just a Check Run update.

2. **`issue_comment` for mid-way apply:** GitHub does not have a native "PR command" webhook. The standard pattern (used by Digger, Atlantis, terraform-cloud) is to listen for `issue_comment` events and parse the comment body for command strings like `/ferry apply`. The `issue_comment` event fires for both issue comments and PR comments -- we detect PR comments by checking for the `issue.pull_request` field in the payload.

3. **`push` for merge-triggered deploy:** When a PR merges, GitHub fires a `push` event on the default branch. This is the existing v1.5 trigger. We enhance it with environment resolution.

### Component Boundaries

| Component | Responsibility | Change Type | Risk |
|-----------|---------------|-------------|------|
| `webhook/handler.py` | Route events by type, orchestrate processing | **MODIFY**: Add event routing for pull_request and issue_comment | HIGH |
| `config/schema.py` | ferry.yaml Pydantic models | **MODIFY**: Add `environments` section to FerryConfig | MEDIUM |
| `detect/changes.py` | Change detection from file diffs | **MINOR MODIFY**: Already handles non-default branch diffs | LOW |
| `dispatch/trigger.py` | Build payload, POST workflow_dispatch | **MODIFY**: Add `mode` and `environment` to dispatch payload | MEDIUM |
| `checks/runs.py` | Check Run creation and PR comments | **MODIFY**: Richer plan output, apply acknowledgment comments | MEDIUM |
| `webhook/dedup.py` | Deduplication for webhook deliveries | **MODIFY**: New event key patterns for PR and comment events | LOW |
| `utils/models/dispatch.py` | Dispatch payload Pydantic models | **MODIFY**: Add `mode` and `environment` fields to payloads | LOW |
| `utils/constants.py` | Constants and enums | **MODIFY**: Add DispatchMode enum, bump schema version | LOW |
| `action/parse_payload.py` | Parse payload, output matrices | **MODIFY**: Pass through `mode` and `environment` outputs | LOW |
| `action/setup/action.yml` | Composite action declaring outputs | **MODIFY**: Add `mode` and `environment` outputs | LOW |
| `action/deploy.py` | Lambda deploy script | **MODIFY**: Respect `mode` (skip actual deploy in plan mode, if we add build-only plan) | LOW-MEDIUM |
| `ferry.yml` template | User's workflow file | **MODIFY**: Add `environment:` to deploy jobs, use dynamic env name | MEDIUM |
| `docs/setup.md` | Setup documentation | **MODIFY**: New ferry.yaml schema, new workflow template | LOW |
| GitHub App config | Webhook subscriptions | **MANUAL**: Subscribe to `pull_request` and `issue_comment` events | LOW |
| DynamoDB table | Dedup storage | **NO CHANGE**: Same table, new key patterns only | NONE |

### New vs Modified Components Summary

**New components: NONE.** All changes are modifications to existing modules. This is deliberate -- the v2.0 architecture extends the existing processing pipeline rather than creating parallel infrastructure.

**Modified components: 14 files** across backend, action, shared models, workflow template, and docs.

**Manual step: 1** -- Update GitHub App webhook subscriptions to include `pull_request` and `issue_comment` events. Requires "Issues: Read" and "Pull requests: Read & write" permissions (PR read likely already configured).

## Detailed Architecture: Event Handling

### Event Router in handler.py

The current handler has a hard filter at line 102: `if event_type != "push": return ignored`. This becomes a router:

```python
# Current (v1.5):
if event_type != "push":
    return _response(200, {"status": "ignored"})

# v2.0:
EVENT_HANDLERS = {
    "push": _handle_push,
    "pull_request": _handle_pull_request,
    "issue_comment": _handle_issue_comment,
}

handler_fn = EVENT_HANDLERS.get(event_type)
if handler_fn is None:
    return _response(200, {"status": "ignored"})
return handler_fn(payload, github_client, settings)
```

**Why a dispatch table instead of if/elif:** Clean separation of event-specific logic. Each handler function receives the same base context (payload, client, settings) and returns a response dict. Testing is simpler -- each handler can be tested independently.

**What stays before the router:** Signature validation, delivery ID extraction, event type extraction, and dedup. These are common to all event types.

**What changes about dedup:** The current dedup builds event keys as `EVENT#push#{repo}#{after_sha}`. For PR events, the key becomes `EVENT#pull_request#{repo}#{pr_number}#{action}#{head_sha}`. For comment events: `EVENT#issue_comment#{repo}#{comment_id}`. The dedup module needs a new `_build_event_key` that dispatches by event type.

### pull_request Handler

```python
def _handle_pull_request(payload: dict, client: GitHubClient, settings: Settings) -> dict:
    """Handle pull_request webhook events.

    Supported actions: opened, synchronize, reopened.
    Creates/updates a Check Run with deployment plan.
    Does NOT dispatch -- plan mode is preview only.
    """
    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return _response(200, {"status": "ignored", "reason": f"pr_action_{action}"})

    pr = payload["pull_request"]
    repo = payload["repository"]["full_name"]
    head_sha = pr["head"]["sha"]
    base_branch = pr["base"]["ref"]

    # Fetch config at PR head
    raw_yaml = fetch_ferry_config(client, repo, head_sha)
    parsed = parse_config(raw_yaml)
    config = validate_config(parsed)

    # Detect changes: three-dot diff (base_branch...head_sha)
    changed_files = get_changed_files(client, repo, base_branch, head_sha)
    affected = match_resources(config, changed_files)

    # Config diff if ferry.yaml changed
    if "ferry.yaml" in changed_files:
        # ... same config diff logic as existing push handler ...

    # Create/update Check Run with plan
    create_check_run(client, repo, head_sha, affected)

    return _response(200, {"status": "plan_created", "affected": len(affected)})
```

**Key insight:** The existing change detection already supports three-dot diffs for non-default branches (line 166 in current handler.py: `compare_base = before_sha if is_default_branch else default_branch`). For `pull_request` events, we use `base_branch` as the compare base, which is equivalent. The `get_changed_files` function already calls the GitHub Compare API with three-dot syntax.

**What about the existing push-to-PR-branch path?** Currently, when someone pushes to a branch with an open PR, the `push` handler (line 218-226) creates a Check Run. With v2.0, the `pull_request` handler handles this via the `synchronize` action (which fires when commits are pushed to the PR branch). We should remove the Check Run creation from the push handler for non-default branches to avoid duplicate Check Runs. The push handler should ONLY create Check Runs/dispatch for default branch pushes.

### issue_comment Handler (/ferry apply)

```python
def _handle_issue_comment(payload: dict, client: GitHubClient, settings: Settings) -> dict:
    """Handle issue_comment webhook events.

    Detects /ferry apply commands on pull requests.
    Triggers a deploy dispatch to the mapped environment.
    """
    action = payload.get("action", "")
    if action != "created":
        return _response(200, {"status": "ignored", "reason": "comment_not_created"})

    comment_body = payload.get("comment", {}).get("body", "")
    if not _is_ferry_command(comment_body):
        return _response(200, {"status": "ignored", "reason": "not_ferry_command"})

    # Verify this is a PR comment, not an issue comment
    issue = payload.get("issue", {})
    if "pull_request" not in issue:
        return _response(200, {"status": "ignored", "reason": "not_pr_comment"})

    repo = payload["repository"]["full_name"]
    pr_number = issue["number"]

    # Fetch full PR details (issue_comment payload lacks head SHA)
    pr = client.get(f"/repos/{repo}/pulls/{pr_number}").json()
    head_sha = pr["head"]["sha"]
    head_branch = pr["head"]["ref"]
    base_branch = pr["base"]["ref"]

    # Fetch config, detect changes
    raw_yaml = fetch_ferry_config(client, repo, head_sha)
    parsed = parse_config(raw_yaml)
    config = validate_config(parsed)

    changed_files = get_changed_files(client, repo, base_branch, head_sha)
    affected = match_resources(config, changed_files)

    if not affected:
        post_pr_comment(client, repo, pr_number, "**Ferry:** No resources affected by this PR.")
        return _response(200, {"status": "no_changes"})

    # Resolve environment from ferry.yaml mapping
    environment = resolve_environment(config, head_branch, base_branch)

    # Build and dispatch
    tag = build_deployment_tag(str(pr_number), head_branch, head_sha)
    trigger_dispatches(
        client, repo, config, affected, head_sha, tag,
        str(pr_number),
        default_branch=pr["base"]["ref"],
        mode="apply",
        environment=environment,
    )

    # Post acknowledgment
    post_pr_comment(
        client, repo, pr_number,
        f"**Ferry:** Deploying {len(affected)} resource(s) to **{environment}**..."
    )

    return _response(200, {"status": "apply_dispatched", "environment": environment})
```

**Critical detail:** The `issue_comment` webhook payload does NOT include the PR's head SHA or branch information. The payload only contains `issue.pull_request.url` (an API URL). We must make an additional API call to `GET /repos/{repo}/pulls/{pr_number}` to get the head SHA and branch names. This is one extra API call per `/ferry apply` command -- acceptable given the low frequency of this event.

**Command parsing:** Start simple. `_is_ferry_command(body)` checks if the comment body starts with `/ferry apply` (case-insensitive, stripped). Future: could parse environment override (`/ferry apply staging`), but for v2.0, environment is resolved from ferry.yaml branch mapping.

### Enhanced Push Handler (Default Branch)

The existing push handler needs two changes:

1. **Add environment resolution:** After detecting changes on default branch push, resolve the target environment from ferry.yaml's environment mapping (default branch maps to production environment).

2. **Remove non-default-branch Check Run creation:** Lines 218-226 currently create Check Runs for PR pushes. With v2.0, the `pull_request` handler covers this. The push handler should only process default branch pushes.

3. **Pass mode and environment to dispatch:** The dispatch payload gains `mode="apply"` and `environment="production"` (or whatever the user configured).

```python
# Enhanced dispatch call:
if is_default_branch and affected:
    environment = resolve_environment(config, branch, default_branch)
    trigger_dispatches(
        client, repo, config, affected, after_sha, tag, pr_number,
        default_branch=default_branch,
        mode="apply",
        environment=environment,
    )
```

## Detailed Architecture: Environment Mapping

### ferry.yaml Schema Extension

```yaml
version: 2  # Bump version for environment support

environments:
  staging:
    branches: ["develop", "staging/*"]
  production:
    branches: ["main"]

lambdas:
  order-processor:
    source_dir: services/order
    ecr_repo: myorg/order-processor
    # ... same as v1
```

**Design decisions:**

1. **Top-level `environments` section**, not per-resource. Environments are deployment targets, not resource properties. A Lambda and a Step Function in the same repo deploy to the same environment when triggered by the same branch.

2. **Branch patterns in environment config.** Each environment lists branches that map to it. When a push lands on `main`, Ferry looks up which environment has `main` in its branches list. Pattern matching supports wildcards (`staging/*` matches `staging/feature-123`).

3. **Version bump to 2.** The `environments` section is a breaking schema change. `version: 2` signals the new schema. The backend handles both v1 (no environments -- everything goes to a default unnamed environment) and v2 (explicit environment mapping).

4. **No per-resource environment overrides.** Keeping it simple: all resources in a repo share the same environment mapping. If a user needs different environments for different resources, they should use separate repos (or we add this in a future version).

### Pydantic Schema Changes

```python
class EnvironmentConfig(BaseModel):
    """Environment definition in ferry.yaml."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    branches: list[str]  # Branch patterns that map to this environment

class FerryConfig(BaseModel):
    """Top-level ferry.yaml configuration model."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    environments: dict[str, EnvironmentConfig] = {}  # name -> config
    lambdas: list[LambdaConfig] = []
    step_functions: list[StepFunctionConfig] = []
    api_gateways: list[ApiGatewayConfig] = []
```

### Environment Resolution Logic

```python
def resolve_environment(
    config: FerryConfig,
    branch: str,
    default_branch: str,
) -> str:
    """Resolve which environment a branch maps to.

    Args:
        config: Parsed FerryConfig with environments section.
        branch: The branch being deployed from.
        default_branch: The repo's default branch name.

    Returns:
        Environment name string, or "default" if no mapping found.
    """
    for env_name, env_config in config.environments.items():
        for pattern in env_config.branches:
            if _branch_matches(branch, pattern):
                return env_name

    # Fallback: if no environments defined (v1 config), return "default"
    # This preserves backward compatibility
    return "default"
```

**Fallback behavior:** If `environments` is empty (v1 ferry.yaml or v2 without environments), `resolve_environment` returns `"default"`. The workflow template should handle this gracefully -- if environment is `"default"`, the deploy job runs without a GitHub Environment (same as v1.5 behavior).

## Detailed Architecture: Dispatch Payload Changes

### Schema v3 Payload

```python
class BatchedDispatchPayload(BaseModel):
    """Batched payload for workflow_dispatch.

    v3 adds mode and environment fields for plan/apply support.
    """
    model_config = ConfigDict(frozen=True)

    v: Literal[3] = 3
    lambdas: list[LambdaResource] = []
    step_functions: list[StepFunctionResource] = []
    api_gateways: list[ApiGatewayResource] = []
    trigger_sha: str
    deployment_tag: str
    pr_number: str = ""
    mode: str = "apply"       # NEW: "plan" or "apply"
    environment: str = ""     # NEW: target environment name
```

**Why add `mode` to the payload?** Even though v2.0's "plan" is a Check Run (no dispatch), we include mode in the payload for future extensibility. A future "build-only plan" (build the container to verify it works, but don't deploy) would need to dispatch to GHA with `mode="plan"`. For now, `mode` is always `"apply"` in dispatched payloads, but the field exists for forward compatibility.

**Why add `environment` to the payload?** The workflow template needs to know which GitHub Environment to use for the deploy job. The environment name flows from `ferry.yaml -> resolve_environment() -> dispatch payload -> setup action output -> deploy job environment: field`.

### Backward Compatibility

The parse_payload action already supports v1/v2 routing. Add v3 support:

```python
def parse_payload(payload_str: str) -> ParseResult:
    raw = json.loads(payload_str)
    version = raw.get("v", 1)

    if version >= 3:
        return _parse_v3(payload_str)  # NEW: v3 with mode + environment
    elif version == 2:
        return _parse_v2(payload_str)  # Existing: batched without env
    return _parse_v1(payload_str)      # Legacy: per-type
```

### Parse Result Extension

```python
@dataclass(frozen=True)
class ParseResult:
    lambda_matrix: dict
    sf_matrix: dict
    ag_matrix: dict
    has_lambdas: bool
    has_step_functions: bool
    has_api_gateways: bool
    resource_types: str
    mode: str = "apply"        # NEW
    environment: str = ""      # NEW
```

New outputs from setup action: `mode` and `environment`.

## Detailed Architecture: Workflow Template Changes

### Updated ferry.yml Template

```yaml
name: Ferry Deploy
run-name: "Ferry: ${{ ... }}"

on:
  workflow_dispatch:
    inputs:
      payload:
        description: "Ferry dispatch payload (JSON)"
        required: true

env:
  AWS_ROLE_ARN: ${{ secrets.AWS_ROLE_ARN }}
  AWS_REGION: us-east-1

permissions:
  id-token: write
  contents: read
  checks: write

jobs:
  setup:
    runs-on: ubuntu-latest
    outputs:
      has_lambdas: ${{ steps.parse.outputs.has_lambdas }}
      has_step_functions: ${{ steps.parse.outputs.has_step_functions }}
      has_api_gateways: ${{ steps.parse.outputs.has_api_gateways }}
      lambda_matrix: ${{ steps.parse.outputs.lambda_matrix }}
      sf_matrix: ${{ steps.parse.outputs.sf_matrix }}
      ag_matrix: ${{ steps.parse.outputs.ag_matrix }}
      environment: ${{ steps.parse.outputs.environment }}
    steps:
      - uses: actions/checkout@v4
      - id: parse
        uses: AmitLaviDev/ferry/action/setup@main
        with:
          payload: ${{ inputs.payload }}

  deploy-lambda:
    name: "Ferry: deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.has_lambdas == 'true'
    runs-on: ubuntu-latest
    environment:
      name: ${{ needs.setup.outputs.environment }}
    concurrency:
      group: ferry-deploy-lambda-${{ matrix.name }}
      cancel-in-progress: false
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.lambda_matrix) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
      - name: Build container
        id: build
        uses: AmitLaviDev/ferry/action/build@main
        with:
          resource-name: ${{ matrix.name }}
          source-dir: ${{ matrix.source }}
          ecr-repo: ${{ matrix.ecr }}
          aws-role-arn: ${{ env.AWS_ROLE_ARN }}
          # ...
      - name: Deploy Lambda
        uses: AmitLaviDev/ferry/action/deploy@main
        with:
          resource-name: ${{ matrix.name }}
          function-name: ${{ matrix.function_name }}
          # ...

  # Similar for deploy-step-function and deploy-api-gateway,
  # each with environment: name: ${{ needs.setup.outputs.environment }}
```

**Key change: `environment:` on deploy jobs.** The `environment: name:` field must use the object syntax (not the shorthand `environment: staging`) because it reads from a job output. GHA requires the object format for expressions: `environment: name: ${{ needs.setup.outputs.environment }}`.

**GitHub Environment behavior:**
- If the environment name matches a configured GitHub Environment, the job gets that environment's secrets and variables via `secrets.*` and `vars.*` contexts.
- If the environment name is empty or doesn't match any configured environment, the job runs without environment scope (same as v1.5 behavior). This provides backward compatibility for v1 ferry.yaml users.
- Environment protection rules (required reviewers, wait timers) apply automatically when configured on the GitHub Environment.

**What this enables for users:**
- Store per-environment AWS role ARNs: `secrets.AWS_ROLE_ARN` resolves to the staging role ARN in the staging environment and the production role ARN in the production environment.
- Environment protection rules: require approval before production deploys.
- Environment-specific variables (API endpoints, feature flags, etc.).

## Detailed Architecture: Check Run Enhancements

### Richer Plan Output

The current Check Run format (from `checks/runs.py`) shows:

```
#### Lambdas
  ~ **order-processor** _(modified)_
    - `services/order/main.py`
```

v2.0 enhances this with environment context:

```
#### Deployment Plan

**Target:** staging (from branch `feature/add-auth` -> environment mapping in ferry.yaml)
**Trigger:** `/ferry apply` or merge to `main`

#### Lambdas
  ~ **order-processor** _(modified)_
    - `services/order/main.py`

#### Step Functions
  + **checkout-flow** _(new)_
    - `ferry.yaml`

_Ferry will deploy these resources when you run `/ferry apply` or merge this PR._
_Run `/ferry apply` to deploy to **staging** now._
```

### Comment-Based Feedback

For `/ferry apply` commands, Ferry posts two comments:

1. **Acknowledgment** (immediately after receiving the command):
   ```
   **Ferry:** Deploying 3 resource(s) to **staging**...
   Workflow: [Ferry Deploy #42](link-to-workflow-run)
   ```

2. **Result** (posted by the action after deploy completes -- already exists via Check Runs, but could also be a summary comment).

For errors, Ferry posts inline:
```
**Ferry:** Cannot apply -- no resources affected by this PR.
```

## Data Flow: Complete v2.0 Pipeline

### Plan Flow (PR Open/Update)

```
Developer opens/updates PR
  -> GitHub sends pull_request webhook (action: opened/synchronize)
  -> Ferry Lambda: handler.py
     -> Signature validation (existing)
     -> Dedup: EVENT#pull_request#{repo}#{pr_number}#{action}#{head_sha}
     -> Auth: generate JWT, get installation token (existing)
     -> Fetch ferry.yaml at PR head SHA (existing fetch_ferry_config)
     -> Validate config (existing validate_config, now with v2 schema)
     -> Detect changes: get_changed_files(base_branch, head_sha)
     -> match_resources(config, changed_files) (existing)
     -> Resolve environment from config.environments + PR base branch
     -> Create Check Run with enhanced plan (environment context, command hints)
  -> Developer sees Check Run on PR: "3 resources will deploy to staging"
```

### Apply Flow (Comment Trigger)

```
Developer comments "/ferry apply" on PR
  -> GitHub sends issue_comment webhook (action: created)
  -> Ferry Lambda: handler.py
     -> Signature validation, dedup
     -> Parse command from comment body
     -> Verify: issue.pull_request field exists (it's a PR comment)
     -> GET /repos/{repo}/pulls/{pr_number} for head SHA + branches
     -> Auth, fetch config, detect changes (same as plan)
     -> Resolve environment from config.environments + head branch
     -> Build BatchedDispatchPayload (v3, mode="apply", environment="staging")
     -> POST workflow_dispatch to ferry.yml
     -> Post acknowledgment comment on PR
  -> GHA: ferry.yml triggers
     -> Setup job: parse payload, output environment="staging"
     -> Deploy jobs: run with environment: staging
        -> AWS credentials from staging environment secrets
        -> Build + deploy resources
        -> Report Check Run results
```

### Apply Flow (Merge to Default Branch)

```
Developer merges PR to main
  -> GitHub sends push webhook (existing v1.5 trigger)
  -> Ferry Lambda: handler.py
     -> Existing v1.5 pipeline (validate, dedup, auth, config, detect)
     -> Resolve environment: main -> production (from config.environments)
     -> Build BatchedDispatchPayload (v3, mode="apply", environment="production")
     -> POST workflow_dispatch to ferry.yml
  -> GHA: ferry.yml triggers with environment="production"
     -> Deploy jobs run with production environment secrets
```

## Patterns to Follow

### Pattern 1: Event Router with Shared Pipeline

**What:** Extract common webhook processing (validate, dedup, auth) into shared steps. Event-specific logic goes into handler functions called from a dispatch table.

**When:** Processing multiple GitHub webhook event types in a single Lambda.

**Why:** The alternative (separate Lambdas per event type) would require separate Function URLs and separate GitHub App webhook configurations. A single Lambda with event routing is simpler and matches the Digger Cloud model.

**Example:**
```python
# Common pipeline runs first:
body = extract_body(event)
verify_signature(body, signature, secret)
delivery_id = headers["x-github-delivery"]
event_type = headers["x-github-event"]
if is_duplicate(...): return duplicate_response

# Then route to event-specific handler:
handlers = {"push": handle_push, "pull_request": handle_pr, "issue_comment": handle_comment}
return handlers.get(event_type, handle_ignored)(payload, client, settings)
```

### Pattern 2: Environment Resolution as a Pure Function

**What:** `resolve_environment(config, branch, default_branch)` is a pure function that takes config and branch, returns environment name. No side effects, no API calls.

**When:** Determining which environment a branch deploys to.

**Why:** Easy to test. Easy to reason about. The mapping lives in ferry.yaml (user-controlled), not in backend logic. The backend just reads the mapping.

### Pattern 3: Dynamic GitHub Environment via Job Output

**What:** The `environment: name:` field on deploy jobs reads from the setup job's output.

**When:** The target environment is determined at runtime (from the dispatch payload).

**Why:** This is the only way to parameterize GitHub Environments in a workflow triggered by `workflow_dispatch`. The environment name cannot be a workflow-level input directly (it must be set at the job level). Using the object syntax `environment: name: ${{ expression }}` is the documented GHA pattern for dynamic environments.

**Verified syntax:**
```yaml
environment:
  name: ${{ needs.setup.outputs.environment }}
```

**Confidence:** HIGH -- verified via GitHub community discussions and official docs. The shorthand `environment: ${{ expression }}` does NOT work; the object format with `name:` is required.

### Pattern 4: Idempotent Comment Commands

**What:** `/ferry apply` must be safe to run multiple times. Each invocation triggers a new dispatch (new workflow run). The dedup layer prevents the same comment from being processed twice (same `comment_id`), but different comments with the same text are independent deployments.

**When:** Users re-run `/ferry apply` after a failed deployment or after pushing new commits.

**Why:** Users expect "retry" behavior. If they push a fix and comment `/ferry apply` again, they want a new deployment with the latest code. The dedup key includes `comment_id`, not comment content, so each comment is treated independently.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Using repository_dispatch Instead of workflow_dispatch

**What:** Switching from `workflow_dispatch` to `repository_dispatch` for more flexibility.

**Why bad:** `repository_dispatch` does not support the `environment:` field on jobs (the environment is determined by the workflow file, not the event). It also doesn't appear in the "Actions" tab as a named workflow -- it shows as a generic event. `workflow_dispatch` with a JSON payload is the right approach.

**Instead:** Keep `workflow_dispatch` with the JSON payload pattern. Add `mode` and `environment` fields to the existing payload.

### Anti-Pattern 2: Dispatching for Plan Mode

**What:** Sending a `workflow_dispatch` with `mode="plan"` to run builds without deploying (dry-run validation).

**Why bad for v2.0:** Plan mode's primary value is showing WHAT will deploy, not whether it WILL BUILD. Building containers is slow (30-90 seconds per Lambda) and costs GHA minutes. The information users need for plan ("order-processor will be updated, checkout-flow is new") is already available from change detection without running any GHA workflow. Save build validation for a future "ferry validate" command if needed.

**Instead:** Plan mode = Check Run only. No dispatch, no GHA runner cost. The Check Run shows the deployment plan from change detection.

### Anti-Pattern 3: Storing Environment State in DynamoDB

**What:** Tracking "which environment is currently deployed" in DynamoDB.

**Why bad:** Ferry's philosophy is "thin backend." DynamoDB is for dedup only. Environment state belongs to the user's AWS resources (the deployed Lambda knows its own version). Adding deployment state to DynamoDB creates a state synchronization problem that doesn't need to exist.

**Instead:** Environment mapping is stateless -- purely derived from ferry.yaml config + the branch being deployed. No state to track.

### Anti-Pattern 4: Separate Workflow Files per Environment

**What:** Creating `ferry-staging.yml` and `ferry-production.yml` instead of a single `ferry.yml` with dynamic environment.

**Why bad:** Doubles the user's workflow maintenance. The dispatch logic would need to know which file to target. The setup action would need environment-aware routing. All of this complexity is unnecessary when `environment: name: ${{ expression }}` solves it cleanly.

**Instead:** Single `ferry.yml` with `environment: name:` populated from the dispatch payload.

### Anti-Pattern 5: Reacting to pull_request closed+merged for Deploy

**What:** Using `pull_request` event with `action: closed` and checking `merged: true` to trigger post-merge deploys.

**Why bad:** When a PR merges, GitHub fires BOTH a `pull_request` (closed, merged=true) event AND a `push` event on the target branch. Handling both creates duplicate dispatches. The `push` event is the canonical trigger for "code landed on branch" -- it's what v1.5 already handles.

**Instead:** Use `push` event for merge-triggered deploys (existing v1.5 behavior, enhanced with environment). Use `pull_request` event only for plan (preview).

## Scalability Considerations

| Concern | At 10 repos | At 100 repos | At 1K repos |
|---------|-------------|--------------|-------------|
| Lambda concurrency | Trivial (< 10 concurrent) | ~50 concurrent (burst during work hours) | Need reserved concurrency (~200) |
| DynamoDB throughput | On-demand handles it | On-demand handles it | Monitor consumed capacity |
| GitHub API rate limits | 5000 req/hr per installation | Spread across installations | Per-installation limits are fine |
| PR comment commands | Low frequency | Low frequency | Low frequency (human-triggered) |
| Payload size | Well under 65KB | Well under 65KB | Still under 65KB |

**Key insight:** The `/ferry apply` command is human-triggered (typing a comment), so its frequency is inherently low. The `pull_request` event fires at developer-push frequency, which is manageable. The `push`-to-default-branch event frequency is unchanged from v1.5.

## Build Order (Suggested Phase Structure)

The dependency chain determines build order:

```
Phase 1: Shared Models + Constants (foundation)
  |-- ferry.yaml schema: Add EnvironmentConfig, bump version
  |-- dispatch models: Add mode + environment to BatchedDispatchPayload (v3)
  |-- constants: Add DispatchMode enum, SCHEMA_VERSION = 3
  |-- Tests for all model changes
  |
Phase 2: Backend Event Handling (depends on Phase 1)
  |-- handler.py: Event router, extract _handle_push (refactor existing)
  |-- handler.py: Add _handle_pull_request (plan)
  |-- handler.py: Add _handle_issue_comment (/ferry apply)
  |-- dedup.py: New event key patterns for PR and comment events
  |-- Environment resolution function
  |-- dispatch/trigger.py: Accept mode + environment, include in payload
  |-- checks/runs.py: Enhanced plan output with environment context
  |-- Tests for all handler paths
  |
Phase 3: Action Changes (depends on Phase 1, parallel with Phase 2)
  |-- parse_payload.py: v3 parser, output mode + environment
  |-- setup/action.yml: Declare mode + environment outputs
  |-- Tests for v3 parsing + backward compat
  |
Phase 4: Workflow Template + Docs (depends on Phases 2 and 3)
  |-- ferry.yml template: Add environment: to deploy jobs
  |-- docs/setup.md: Updated ferry.yaml schema, environment guide
  |-- docs/pr-integration.md: New doc for plan/apply workflow
  |
Phase 5: GitHub App Config + E2E (depends on all above)
  |-- Update GitHub App webhook subscriptions (manual step)
  |-- Update test repo ferry.yaml with environments section
  |-- Update test repo ferry.yml to v2.0 template
  |-- E2E: Open PR -> verify Check Run plan
  |-- E2E: Comment /ferry apply -> verify dispatch + deploy to staging
  |-- E2E: Merge PR -> verify deploy to production
```

### Phase Ordering Rationale

1. **Phase 1 first** because both backend (Phase 2) and action (Phase 3) depend on the shared models.
2. **Phases 2 and 3 can run in parallel** -- backend event handling does not depend on action parsing, and vice versa. They share only the Pydantic models from Phase 1.
3. **Phase 4 depends on both 2 and 3** because the workflow template references outputs from the action (Phase 3) and assumes the backend sends v3 payloads (Phase 2).
4. **Phase 5 is E2E validation** requiring all components deployed together. The manual GitHub App config step must happen before E2E testing.

## Sources

- Existing codebase analysis: `handler.py`, `trigger.py`, `schema.py`, `changes.py`, `runs.py`, `dedup.py`, `dispatch.py`, `parse_payload.py`, all `action.yml` files, `setup.md` (PRIMARY source, HIGH confidence)
- [GitHub Docs: Webhook events and payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads) -- issue_comment event has `issue.pull_request` field to detect PR comments (HIGH confidence)
- [GitHub Docs: Using environments for deployment](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment) -- environment secrets/variables injection, environment protection rules (HIGH confidence)
- [GitHub Actions runner issue #998](https://github.com/actions/runner/issues/998) -- dynamic environment name requires object format `environment: name: ${{ expr }}` (HIGH confidence)
- [GitHub Community: Dynamic environment names](https://github.com/orgs/community/discussions/38178) -- confirmed object format syntax (MEDIUM confidence)
- [GitHub Docs: Events that trigger workflows](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows) -- pull_request action types, issue_comment event (HIGH confidence)
- [Digger/OpenTaco: Getting started with Terraform](https://docs.opentaco.dev/ce/getting-started/with-terraform) -- plan/apply PR model reference implementation (MEDIUM confidence)
- v1.5 research: `ARCHITECTURE.md`, `PITFALLS.md` -- existing patterns, concurrency model, GHA constraints (PRIMARY source)
