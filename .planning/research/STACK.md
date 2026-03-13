# Technology Stack: Ferry v2.0 PR Integration

**Project:** Ferry - PR-triggered deployments with plan/apply model, environment mapping, GitHub Environments
**Researched:** 2026-03-12
**Overall confidence:** HIGH (GitHub APIs verified against official docs, existing codebase analyzed directly, GHA expression contexts confirmed)

## Scope

This STACK.md covers ONLY what changes or gets added for PR integration (v2.0). The existing stack (Python 3.14, httpx, PyJWT+cryptography, boto3, Pydantic v2, structlog, uv workspace, batched dispatch v2 payload) is shipped and validated -- not re-researched here.

## Key Finding: No New Python Libraries Required

PR integration is a webhook handler expansion + new GitHub API calls + config schema extension + dispatch payload evolution + workflow template changes. Every Python dependency needed already exists in the codebase. The changes are architectural (new event handling paths, new Pydantic models, new GitHub API calls via existing httpx client), not new-dependency changes.

---

## New Webhook Events (Backend Changes)

### 1. `pull_request` Event

**Currently handled:** Only `push` events (line 102 of `handler.py`: `if event_type != "push": return ignored`)

**New requirement:** Handle `pull_request` with actions: `opened`, `synchronize`, `reopened`

**Payload structure (verified from GitHub docs):**

| Field | Path | Purpose |
|-------|------|---------|
| Action type | `payload["action"]` | "opened", "synchronize", "reopened" |
| PR number | `payload["pull_request"]["number"]` | For posting comments, Check Runs |
| Head SHA | `payload["pull_request"]["head"]["sha"]` | Commit to check out, attach Check Run to |
| Head ref (branch) | `payload["pull_request"]["head"]["ref"]` | Branch name for environment mapping |
| Base ref (branch) | `payload["pull_request"]["base"]["ref"]` | Target branch for environment mapping |
| Repo full name | `payload["repository"]["full_name"]` | Standard repo identifier |
| Installation ID | `payload["installation"]["id"]` | For GitHub App auth (same as push) |

**Confidence:** HIGH -- `pull_request` webhook is one of the most documented GitHub events. Activity types `opened`/`synchronize`/`reopened` confirmed in official docs.

**Key difference from push:** The `pull_request` payload nests PR data under `payload["pull_request"]`, not at the top level. The SHA is at `pull_request.head.sha`, not `payload.after`. The handler must branch on `event_type` early to extract context differently.

### 2. `issue_comment` Event

**New requirement:** Handle `issue_comment` with action `created`, specifically for `/ferry apply` comment triggers on PRs.

**Payload structure (verified):**

| Field | Path | Purpose |
|-------|------|---------|
| Action | `payload["action"]` | "created" (only handle this) |
| Comment body | `payload["comment"]["body"]` | Check for `/ferry apply` command |
| PR check | `payload["issue"]["pull_request"]` | Non-null means comment is on a PR (not issue) |
| PR number | `payload["issue"]["number"]` | PR number to operate on |
| Comment author | `payload["comment"]["user"]["login"]` | For audit logging |
| Repo full name | `payload["repository"]["full_name"]` | Standard repo identifier |

**Distinguishing PR comments from issue comments:** Per GitHub docs, `issue_comment` fires for both issues and PRs. The `payload["issue"]["pull_request"]` field is truthy (contains a URL object) when the comment is on a PR, and absent/null when on an issue. This is the canonical check.

**Important:** The `issue_comment` payload does NOT include the full PR object -- it includes a minimal `issue` object with a `pull_request` field containing only URLs. To get the head SHA and branch name, a follow-up API call to `GET /repos/{owner}/{repo}/pulls/{number}` is required.

**Confidence:** HIGH -- well-documented pattern used by Digger, Atlantis, and many other PR-ops tools.

### GitHub App Permission Changes

**Current permissions (from setup runbook):**
- Contents: Read (for file access)
- Checks: Read & Write (for Check Runs)
- Pull requests: Read (for PR lookup)
- Issues: Read & Write (for PR comments)

**Additional permissions needed for v2.0:**

| Permission | Current | Needed | Why |
|------------|---------|--------|-----|
| Pull requests | Read | Read & Write | Write needed to... no, actually Read is sufficient for reading PR data. Write would be needed only if we used the Pulls API to post review comments. Since Ferry posts via Issues API (PRs are issues), Read is sufficient. |
| Issues | Read & Write | Read & Write (no change) | Already have write for PR comments |

**Webhook event subscriptions to add:**

| Event | Current | Needed | Why |
|-------|---------|--------|-----|
| `push` | Subscribed | No change | Still needed for default branch deploys |
| `pull_request` | Not subscribed | Subscribe | Plan on PR open/sync |
| `issue_comment` | Not subscribed | Subscribe | `/ferry apply` command trigger |

**Confidence:** HIGH -- `issue_comment` requires Issues Read permission to subscribe; Issues Write to post. Both already exist. `pull_request` requires Pull requests Read permission to subscribe, which already exists.

---

## GitHub API Endpoints (New Calls via Existing httpx Client)

Ferry's `GitHubClient` is a thin httpx wrapper with `get()`, `post()`, and `patch()` methods. All new API calls use these existing methods. No new HTTP verbs needed.

### New Endpoints Required

| Endpoint | Method | Purpose | Used By |
|----------|--------|---------|---------|
| `GET /repos/{owner}/{repo}/pulls/{number}` | GET | Fetch full PR data (head SHA, branch) after `issue_comment` event | Backend handler |
| `GET /repos/{owner}/{repo}/issues/{number}/comments` | GET | List existing comments for sticky-comment pattern | Backend (plan comment) |
| `PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}` | PATCH | Update existing plan comment (sticky pattern) | Backend (plan update) |

**Already used endpoints (no change):**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /repos/{owner}/{repo}/issues/{number}/comments` | POST | Create new PR comment (plan preview, errors) |
| `POST /repos/{owner}/{repo}/check-runs` | POST | Create Check Run on PR |
| `GET /repos/{owner}/{repo}/commits/{sha}/pulls` | GET | Find PRs associated with a commit |
| `POST /repos/{owner}/{repo}/actions/workflows/{file}/dispatches` | POST | Trigger workflow_dispatch |
| `GET /repos/{owner}/{repo}/compare/{base}...{head}` | GET | Get changed files between refs |
| `GET /repos/{owner}/{repo}/contents/{path}` | GET | Fetch ferry.yaml |

**Confidence:** HIGH -- all are stable REST v3 endpoints documented at docs.github.com/en/rest.

### Sticky Comment Pattern

The plan preview should update in-place (not create a new comment on each push). Pattern:

1. List comments on PR: `GET /repos/{owner}/{repo}/issues/{number}/comments?per_page=100`
2. Find existing Ferry comment by hidden HTML marker: `<!-- ferry:plan -->`
3. If found: `PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}` with updated body
4. If not found: `POST /repos/{owner}/{repo}/issues/{number}/comments` with new body

This is the same pattern used by Terraform Cloud, Digger, Atlantis, and `marocchino/sticky-pull-request-comment`. The hidden HTML comment is invisible to users but findable by the bot.

**Pagination concern:** If a PR has >100 comments, the sticky comment might not be found on the first page. In practice, PRs with >100 comments are extremely rare. Use `per_page=100` and search only the first page. If not found, create a new comment. Worst case: a duplicate comment appears on a very chatty PR. Acceptable tradeoff vs. paginating through all comments.

**Confidence:** HIGH -- widely-used pattern, well-documented API.

---

## ferry.yaml Schema Extension (Pydantic v2)

### Current Schema (v1)

```python
class FerryConfig(BaseModel):
    version: int = 1
    lambdas: list[LambdaConfig] = []
    step_functions: list[StepFunctionConfig] = []
    api_gateways: list[ApiGatewayConfig] = []
```

### New Schema (v2) -- Environment Mapping

The schema needs a new top-level `environments` section to map branches to deployment environments.

```python
class EnvironmentMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str            # GitHub Environment name (e.g., "staging", "production")
    branch: str          # Branch pattern (e.g., "main", "develop")
    auto_deploy: bool = True  # Deploy automatically on merge (vs. require /ferry apply)

class FerryConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1     # Bump to 2 when environments are used? Or keep backward-compatible?
    lambdas: list[LambdaConfig] = []
    step_functions: list[StepFunctionConfig] = []
    api_gateways: list[ApiGatewayConfig] = []
    environments: list[EnvironmentMapping] = []  # NEW, optional, default empty
```

**Corresponding ferry.yaml:**

```yaml
version: 2
environments:
  - name: staging
    branch: develop
    auto_deploy: true
  - name: production
    branch: main
    auto_deploy: true

lambdas:
  order-processor:
    source: services/order-processor
    ecr: ferry/order-processor
    # ... rest of config
```

**Design rationale:**
- `environments` is a list (not a dict) because Pydantic v2 handles list-of-models well and ordering might matter for UI display
- `branch` is a simple string match for v2.0, not a glob pattern. Keep it simple. Glob patterns can be added later.
- `auto_deploy: true` means merge to this branch triggers deploy automatically. `false` means deploy only via `/ferry apply`. Default is `true` to match current push-on-merge behavior.
- No environment-level resource overrides in v2.0. All environments deploy the same resources. Environment-specific config comes from GitHub Environment secrets/variables.

**Version field strategy:** The `version` field is currently always 1. Option A: bump to 2 when environments are present. Option B: keep version 1 but make environments optional (backward compatible). **Recommend Option B** -- the `environments: []` default means existing ferry.yaml files work without changes. Version bumps create migration friction for zero benefit.

**Confidence:** HIGH -- straightforward Pydantic v2 model extension with known patterns.

---

## Dispatch Payload Extension (Pydantic v2)

### Current Batched Payload (v2)

```python
class BatchedDispatchPayload(BaseModel):
    v: Literal[2] = 2
    lambdas: list[LambdaResource] = []
    step_functions: list[StepFunctionResource] = []
    api_gateways: list[ApiGatewayResource] = []
    trigger_sha: str
    deployment_tag: str
    pr_number: str = ""
```

### New Fields for PR Integration

```python
class BatchedDispatchPayload(BaseModel):
    v: Literal[3] = 3              # Bump to v3
    lambdas: list[LambdaResource] = []
    step_functions: list[StepFunctionResource] = []
    api_gateways: list[ApiGatewayResource] = []
    trigger_sha: str
    deployment_tag: str
    pr_number: str = ""
    mode: str = "deploy"           # NEW: "plan" | "deploy"
    environment: str = ""          # NEW: GitHub Environment name
    head_ref: str = ""             # NEW: Source branch (for plan context)
    base_ref: str = ""             # NEW: Target branch (for environment resolution)
```

**New fields explained:**

| Field | Values | Purpose |
|-------|--------|---------|
| `mode` | `"plan"` or `"deploy"` | Tells the action whether to do a dry-run preview or actual deployment |
| `environment` | `""` or `"staging"` etc. | GitHub Environment name for the workflow job's `environment:` key |
| `head_ref` | Branch name | Source branch (PR head). Used for plan comment context. |
| `base_ref` | Branch name | Target branch (PR base). Used for environment resolution when `mode="deploy"`. |

**Why `mode` in the payload, not a separate workflow input:** Keeping all dispatch context in a single `payload` JSON string (one workflow_dispatch input) is the established Ferry pattern. Adding a second input would require the workflow template to pass it separately. Single payload is simpler.

**Why environment name in the payload:** The workflow job needs `environment: ${{ <something> }}` at the job level. The setup action will parse the payload and output `environment` as a GHA output. The workflow template references it. This works because `inputs` context is available in `jobs.<job_id>.environment` (verified against GitHub docs contexts table).

**Actually -- critical correction:** The `environment:` key on a job supports `inputs`, `needs`, `matrix`, `vars`, `github`, and `strategy` contexts. Since the environment name comes from the setup job's output (via `needs`), the workflow template uses:

```yaml
deploy-lambda:
  needs: setup
  environment: ${{ needs.setup.outputs.environment }}
```

This is valid and confirmed.

**Confidence:** HIGH -- expression contexts for `environment:` verified against GitHub Actions contexts documentation.

---

## GitHub Environments Integration

### How It Works

When a workflow job has `environment: <name>`, GitHub Actions:
1. Waits for any deployment protection rules (approval gates, wait timers, branch restrictions)
2. Makes environment-level secrets available via `${{ secrets.ENV_SECRET }}`
3. Makes environment-level variables available via `${{ vars.ENV_VAR }}`
4. Records the deployment in the repository's Deployments tab
5. Shows deployment status on the repository main page

### What Ferry Needs

Ferry does NOT need to create or manage GitHub Environments via API. Environments are created by the user in their repo settings (or by their IaC). Ferry only needs to:

1. **Resolve** which environment name to use (from ferry.yaml `environments` mapping + branch context)
2. **Pass** the environment name through the dispatch payload
3. **Output** the environment name from the setup action
4. **Reference** it in the workflow template's `environment:` key

This is a pass-through model. Ferry doesn't interact with the Environments API at all. The user's workflow template uses `environment: ${{ needs.setup.outputs.environment }}` and GHA handles the rest.

### Environment Resolution Logic (Backend)

```
Given: base_ref (target branch from PR or push)
Given: ferry.yaml environments list

1. Find environment where env.branch == base_ref
2. If found: environment_name = env.name
3. If not found: environment_name = "" (no environment)
```

When `environment_name` is empty string, the workflow job's `environment:` evaluates to empty string, which means no environment is used. This is the fallback for repos that don't configure environments.

**Confidence:** HIGH -- standard GHA pattern. Empty string in `environment:` is equivalent to not specifying it.

---

## Workflow Template Changes

### Current Template (v1.5 -- Batched Dispatch)

```yaml
on:
  workflow_dispatch:
    inputs:
      payload:
        description: "Ferry dispatch payload"
        required: true

jobs:
  setup:
    runs-on: ubuntu-latest
    outputs:
      has_lambdas: ${{ steps.parse.outputs.has_lambdas }}
      # ... other outputs
    steps:
      - uses: AmitLaviDev/ferry/action/setup@main
        with:
          payload: ${{ inputs.payload }}

  deploy-lambda:
    needs: setup
    if: needs.setup.outputs.has_lambdas == 'true'
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.lambda_matrix) }}
    # ...
```

### New Template (v2.0 -- With Environment + Mode)

```yaml
on:
  workflow_dispatch:
    inputs:
      payload:
        description: "Ferry dispatch payload"
        required: true

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
      mode: ${{ steps.parse.outputs.mode }}
      environment: ${{ steps.parse.outputs.environment }}
    steps:
      - uses: AmitLaviDev/ferry/action/setup@main
        with:
          payload: ${{ inputs.payload }}

  deploy-lambda:
    needs: setup
    if: needs.setup.outputs.has_lambdas == 'true' && needs.setup.outputs.mode == 'deploy'
    environment: ${{ needs.setup.outputs.environment }}
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.lambda_matrix) }}
    steps:
      - uses: AmitLaviDev/ferry/action/build@main
        # ... (same as today, environment secrets/vars now available)

  plan-comment:
    needs: setup
    if: needs.setup.outputs.mode == 'plan'
    runs-on: ubuntu-latest
    steps:
      # Plan mode: no actual deployment, just preview
      # The plan preview is posted by the backend as a PR comment
      # This job is a no-op placeholder OR could do a build-only dry run
```

**Key changes:**
- `mode` output gates whether deploy jobs run (`mode == 'deploy'`) or plan jobs run (`mode == 'plan'`)
- `environment:` on deploy jobs references the setup output. Empty string = no environment (backward compatible).
- Plan mode may not need a GHA job at all -- the backend can post the plan preview directly as a PR comment without dispatching. This is the simpler approach and avoids burning GHA runner minutes for a preview that's just text.

**Plan preview without dispatch (recommended):** The backend already has all the information needed for the plan preview (affected resources, change kinds, file lists). It already posts Check Runs on PR pushes. For v2.0 plan mode, the backend can post a PR comment with the plan preview directly -- no workflow_dispatch needed. Dispatch is only for `mode == 'deploy'`.

**Confidence:** HIGH -- `needs` context in `environment:` verified. Empty string fallback tested in community patterns.

---

## Backend Handler Architecture Changes

### Current Flow

```
push event -> handler.py
  -> signature validation
  -> dedup
  -> auth
  -> fetch config
  -> detect changes
  -> if default_branch: trigger_dispatches()
  -> if PR branch: create_check_run()
```

### New Flow

```
push event -> handler.py
  -> [existing push flow, mostly unchanged]
  -> if default_branch: resolve_environment() -> trigger_dispatches(mode="deploy", environment=...)
  -> if PR branch: create_check_run() [existing]

pull_request event -> handler.py
  -> signature validation, dedup, auth
  -> fetch config at PR head SHA
  -> detect changes (base_ref...head_sha)
  -> resolve_environment(base_ref)
  -> post_plan_comment() [NEW - sticky comment with plan preview]
  -> create_check_run() [existing]

issue_comment event -> handler.py
  -> signature validation (no dedup -- comments are not retried)
  -> check: is PR comment? (issue.pull_request truthy)
  -> check: body matches "/ferry apply"?
  -> auth
  -> GET /repos/{owner}/{repo}/pulls/{number} for head SHA + branches
  -> fetch config at head SHA
  -> detect changes (base_ref...head_sha)
  -> resolve_environment(base_ref)
  -> trigger_dispatches(mode="deploy", environment=...)
```

### Dedup Considerations for New Events

| Event | Dedup Needed? | Why |
|-------|---------------|-----|
| `push` | Yes (existing) | GitHub may retry webhook delivery |
| `pull_request` | Yes | GitHub may retry. Use delivery_id. Plan comment is idempotent (sticky update). |
| `issue_comment` | Yes | Avoid double-deploy if GitHub retries. Use delivery_id with DynamoDB same as push. |

**Confidence:** HIGH -- same dedup pattern, different event types. DynamoDB conditional write works for any delivery_id.

---

## What NOT to Add

| Temptation | Why Not |
|------------|---------|
| `PyGithub` or `ghapi` library | httpx wrapper is ~100 lines, covers all needed endpoints, no dependency bloat. Adding 3 new API calls does not justify a full SDK. |
| GraphQL API for comment management | REST API is sufficient for list + create + update comments. GraphQL adds complexity for zero benefit here. |
| `aiohttp` or async httpx | Lambda handler is synchronous. Webhook processing is sequential (auth -> config -> detect -> dispatch). No concurrent API calls needed. |
| Jinja2 for plan comment templates | Python f-strings and the existing `format_deployment_plan()` pattern are sufficient. Plan comments are simple markdown. |
| GitHub Environments API calls | Ferry does not create/manage environments. Users create them. Ferry just passes the name through. |
| GitHub Deployments API calls | When a job references `environment:`, GHA automatically creates a deployment record. Ferry doesn't need to call the Deployments API. |
| Separate `plan` workflow file | One workflow file (`ferry.yml`) with mode-based job routing is cleaner than maintaining separate plan and deploy workflows. But see below -- plan may not need dispatch at all. |
| Branch glob patterns in environment mapping | Simple string match (`branch == "main"`) is sufficient for v2.0. Glob/regex matching adds complexity for an edge case. |
| Per-environment resource overrides | All environments deploy the same resources. Environment-specific config (different Lambda aliases, different stage names) comes from GitHub Environment secrets/vars, not from ferry.yaml. |
| New DynamoDB tables | Existing dedup table works for all event types. No new state to track. |
| Comment reaction tracking | `/ferry apply` is detected by comment body text, not reactions. Reactions are ambiguous. |
| PR approval gates in Ferry | GitHub Environments already have deployment protection rules (required reviewers, wait timers). Don't reimplement this. |

---

## Summary: Changes by Package

| Package | What Changes | New Dependencies |
|---------|-------------|-----------------|
| `ferry-utils` (shared) | New `EnvironmentMapping` model. Dispatch payload v3 with `mode`, `environment`, `head_ref`, `base_ref` fields. | None |
| `ferry-backend` | `handler.py`: route `pull_request` and `issue_comment` events alongside `push`. New `plan.py` module for sticky comment posting. `trigger.py`: accept `mode` and `environment` params. `schema.py`: add `environments` field to `FerryConfig`. | None |
| `ferry-action` | `parse_payload.py`: output `mode` and `environment` from v3 payload. `action/setup/action.yml`: new `mode` and `environment` outputs. | None |
| Workflow template (docs) | Add `mode` and `environment` outputs from setup. Deploy jobs gated on `mode == 'deploy'`. `environment:` key on deploy jobs. | None |
| GitHub App settings | Subscribe to `pull_request` and `issue_comment` webhook events. | N/A |
| Test repo | Update `ferry.yaml` to add `environments` section. Update `ferry.yml` workflow template. | N/A |

**Total new Python dependencies: 0**
**Total new GitHub Actions: 0**
**Total new infrastructure: 0**
**Total new GitHub App permissions: 0** (existing permissions are sufficient)
**New webhook subscriptions: 2** (`pull_request`, `issue_comment`)

---

## New GitHub API Calls Summary

Only 3 new REST API calls, all via existing httpx `GitHubClient`:

| Call | HTTP | Endpoint | When |
|------|------|----------|------|
| Fetch PR details | GET | `/repos/{owner}/{repo}/pulls/{number}` | After `issue_comment` to get head SHA |
| List PR comments | GET | `/repos/{owner}/{repo}/issues/{number}/comments?per_page=100` | Before posting plan to find existing sticky comment |
| Update comment | PATCH | `/repos/{owner}/{repo}/issues/comments/{comment_id}` | Update existing sticky plan comment |

**Note:** `GitHubClient` already has `get()`, `post()`, and `patch()` methods. No new methods needed.

---

## Existing Capabilities Reused (Not Changed)

These capabilities already work and are reused as-is:

| Capability | Used For in v2.0 |
|------------|-----------------|
| HMAC webhook validation | Validate `pull_request` and `issue_comment` events |
| DynamoDB dedup | Deduplicate all webhook deliveries |
| GitHub App JWT auth | Authenticate for all new API calls |
| Installation token | Same auth flow for all events |
| `fetch_ferry_config()` | Fetch config at PR head SHA |
| `get_changed_files()` | Compare base_ref...head_sha for PR changes |
| `match_resources()` | Detect affected resources in PR |
| `create_check_run()` | Show plan on PR checks tab |
| `post_pr_comment()` | Post plan preview on PR |
| `trigger_dispatches()` | Dispatch deploy workflow (extended with mode/env) |
| `format_deployment_plan()` | Format affected resources for plan preview |
| `BatchedDispatchPayload` | Base for v3 payload (extend, don't replace) |
| Workflow `if:` guards | Gate deploy vs plan jobs |

---

## Implementation Order Recommendation

Based on dependency analysis:

1. **ferry.yaml schema** -- `EnvironmentMapping` model + `environments` field on `FerryConfig` (no dependencies)
2. **Dispatch payload v3** -- Add `mode`, `environment`, `head_ref`, `base_ref` to `BatchedDispatchPayload` (depends on #1 for env resolution)
3. **Backend: `pull_request` handler** -- Route PR events, detect changes, post plan preview (depends on #1 schema, uses existing detection + comment APIs)
4. **Backend: sticky plan comment** -- List + find + update/create comment pattern (depends on #3)
5. **Backend: `issue_comment` handler** -- Parse `/ferry apply`, fetch PR details, trigger deploy dispatch (depends on #2 payload, #1 schema)
6. **Backend: environment resolution** -- Map branch to environment name from config (depends on #1 schema)
7. **Setup action: v3 payload parsing** -- Output `mode` and `environment` (depends on #2)
8. **Workflow template update** -- Add `environment:` and mode gating (depends on #7)
9. **GitHub App webhook subscriptions** -- Add `pull_request` and `issue_comment` events (manual step)
10. **E2E testing** -- Full PR lifecycle test

## Sources

- [GitHub Docs: Events that trigger workflows](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows) -- `pull_request` activity types (`opened`, `synchronize`, `reopened`), `issue_comment` activity types, event filtering
- [GitHub Docs: Webhook events and payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads) -- `pull_request` and `issue_comment` payload structures, `issue.pull_request` field for distinguishing PR vs issue comments
- [GitHub Docs: Contexts reference](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts) -- Expression contexts available for `jobs.<job_id>.environment` (`github`, `needs`, `strategy`, `matrix`, `vars`, `inputs`)
- [GitHub Docs: Deployment environments](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments) -- How `environment:` on jobs works, secret access, protection rules
- [GitHub Docs: Managing environments for deployment](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment) -- Environment configuration, branch restrictions, required reviewers
- [GitHub Docs: REST API - Issue comments](https://docs.github.com/en/rest/issues/comments) -- `GET /repos/{owner}/{repo}/issues/{number}/comments`, `PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}`
- [GitHub Docs: REST API - Pulls](https://docs.github.com/en/rest/pulls/pulls) -- `GET /repos/{owner}/{repo}/pulls/{number}` for fetching PR details
- [GitHub Docs: Choosing permissions for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app) -- Permission requirements for webhook subscriptions
- [GitHub Community Discussion #37686](https://github.com/orgs/community/discussions/37686) -- `workflow_dispatch` with environment secrets, passing input to job `environment:` key
- [GitHub Actions runner issue #998](https://github.com/actions/runner/issues/998) -- Dynamic environment name via expressions
- [marocchino/sticky-pull-request-comment](https://github.com/marocchino/sticky-pull-request-comment) -- Sticky comment pattern using hidden HTML markers
- [Digger PR comment UX](https://github.com/diggerhq/digger/pull/1071) -- Reference implementation for plan/apply comment flow
- Existing codebase: `handler.py`, `trigger.py`, `client.py`, `runs.py`, `schema.py`, `dispatch.py`, `parse_payload.py`, `action/setup/action.yml` -- analyzed directly
