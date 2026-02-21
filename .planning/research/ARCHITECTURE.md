# Architecture Patterns

**Domain:** GitHub App + GitHub Action serverless deployment system
**Researched:** 2026-02-21
**Overall confidence:** MEDIUM (web search/fetch unavailable; based on training data knowledge of GitHub APIs, Digger architecture, and AWS Lambda patterns. Core GitHub App/Action mechanics are well-established and unlikely to have changed.)

## Recommended Architecture

### System Overview

```
                        GitHub.com
                       +-----------+
                       |  Push/PR  |
                       |  Event    |
                       +-----+-----+
                             |
                      webhook (HTTPS POST)
                             |
                    +--------v---------+
                    |  API Gateway /   |
                    |  Function URL    |
                    +--------+---------+
                             |
                    +--------v---------+
                    |   Ferry App      |
                    |   Lambda         |
                    |                  |
                    | 1. Validate sig  |
                    | 2. Dedup (DDB)   |
                    | 3. Fetch config  |
                    | 4. Diff analysis |
                    | 5. Dispatch GHA  |
                    | 6. Post checks   |
                    +--------+---------+
                             |
              workflow_dispatch (GitHub API)
                             |
                    +--------v---------+
                    |  User's GHA      |
                    |  Runner          |
                    |                  |
                    | ferry-action:    |
                    | 1. OIDC auth     |
                    | 2. Build images  |
                    | 3. Push ECR      |
                    | 4. Deploy        |
                    +------------------+
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **Ferry App Lambda** | Webhook ingestion, signature validation, dedup, config reading, change detection, dispatch triggering, PR status posting | GitHub API (inbound webhooks, outbound REST), DynamoDB |
| **DynamoDB Table** | Webhook dedup (delivery ID), optional state tracking | Ferry App Lambda (read/write) |
| **Ferry Action** | AWS auth (OIDC), container builds, ECR push, Lambda/StepFunction/APIGateway deployment | AWS APIs (STS, ECR, Lambda, StepFunctions, APIGateway), Docker |
| **ferry.yaml** | Source of truth for resource mappings | Read by Ferry App Lambda via GitHub Contents API |
| **User's GHA Workflow** | Thin wrapper that calls ferry-action on workflow_dispatch | GitHub Actions runtime, ferry-action |

### Data Flow

**Trigger Flow (Ferry App):**

1. GitHub delivers webhook (push or pull_request event) to Ferry App's HTTPS endpoint
2. Ferry App validates HMAC-SHA256 signature using webhook secret
3. Ferry App checks DynamoDB for `X-GitHub-Delivery` header (idempotency key) -- conditional put fails if duplicate
4. Ferry App generates JWT from App private key (RS256, 10-minute expiry)
5. Ferry App exchanges JWT for installation access token (scoped to the repo's installation)
6. Ferry App fetches `ferry.yaml` from the repo's default branch via Contents API
7. Ferry App fetches the commit comparison (diff) via Compare API or Commits API
8. Ferry App matches changed file paths against `ferry.yaml` source directories
9. For each affected resource type, Ferry App calls `POST /repos/{owner}/{repo}/dispatches` (repository_dispatch) or `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches` (workflow_dispatch)
10. Ferry App posts a Check Run via Checks API showing what will deploy (pending state)

**Execution Flow (Ferry Action):**

1. User's workflow file triggers on `workflow_dispatch` event
2. Workflow calls `ferry-action` with inputs from the dispatch payload
3. Ferry Action configures AWS credentials via OIDC federation (user-provided role ARN)
4. For Lambdas: builds Docker image using magic Dockerfile, pushes to ECR, updates Lambda function code, publishes version, updates alias
5. For Step Functions: reads definition JSON, runs envsubst for account/region, calls update-state-machine
6. For API Gateways: reads OpenAPI spec, calls put-rest-api + create-deployment
7. Ferry Action outputs success/failure status (picked up by GitHub workflow)

## The Digger/OpenTofu Cloud Model (Reference Architecture)

**Confidence: MEDIUM** (based on training data knowledge of Digger's open-source codebase)

Digger pioneered the "backend orchestrator + GHA executor" pattern for Terraform/OpenTofu:

### How Digger Works

1. **Digger Backend** (Go, hosted or self-hosted): GitHub App receives PR webhooks. Parses `digger.yml` to find which Terraform projects are affected. Generates "jobs" describing what to run. Triggers `workflow_dispatch` on the user's repo.

2. **Digger Action** (runs in user's GHA runner): Receives job spec via dispatch payload. Runs `terraform plan` or `terraform apply`. Posts plan output back to PR as a comment. Reports status.

3. **Key Digger patterns Ferry should adopt:**
   - Backend is stateless per-request (state lives in DynamoDB/Postgres, not in memory)
   - Dispatch payload is a serialized "job spec" -- all information the action needs is in the payload
   - Installation token is NOT passed to the action -- action uses its own auth (OIDC for AWS, GitHub token for API calls)
   - Backend handles concurrency/locking (Digger uses DynamoDB for locks)
   - PR comment as status mechanism (Ferry uses Checks API instead -- better UX)

4. **Where Ferry diverges from Digger:**
   - Digger's backend is complex (Go, multiple services, database migrations). Ferry keeps it to 1-2 Lambdas.
   - Digger passes Terraform commands. Ferry passes resource lists + deployment instructions.
   - Digger needs plan storage/locking. Ferry does not (container builds are idempotent).
   - Digger supports multiple VCS providers. Ferry is GitHub-only.

## GitHub App Authentication Deep-Dive

**Confidence: HIGH** (GitHub App auth is well-documented and stable)

### Three Auth Layers

1. **Webhook Signature Validation** (inbound security)
   - GitHub signs every webhook payload with HMAC-SHA256 using the app's webhook secret
   - Header: `X-Hub-Signature-256: sha256=<hex_digest>`
   - Validate by computing `HMAC-SHA256(webhook_secret, raw_body)` and comparing with constant-time comparison
   - MUST validate before any processing -- this is the trust boundary

2. **App JWT** (identify as the app itself)
   - Generated client-side using the App's private key (RSA, PEM format)
   - Algorithm: RS256
   - Claims: `iss` = App ID, `iat` = now - 60s (clock drift), `exp` = now + 600s (max 10 minutes)
   - Used for: listing installations, getting installation access tokens
   - NOT used for: accessing repo content (need installation token for that)

3. **Installation Access Token** (act on behalf of the app in a specific installation)
   - Obtained via `POST /app/installations/{installation_id}/access_tokens` (authenticated with JWT)
   - Scoped to the repositories the installation has access to
   - Expires after 1 hour (but generate fresh for each webhook -- do not cache across requests)
   - Used for: reading repo content, posting checks, creating dispatches, commenting on PRs
   - Can be further scoped to specific repos and permissions at creation time

### Auth Flow for Ferry App Lambda

```python
# Pseudocode for the auth flow
def handle_webhook(event):
    # 1. Validate signature (webhook secret, not JWT)
    raw_body = event["body"]
    signature = event["headers"]["x-hub-signature-256"]
    validate_hmac_sha256(WEBHOOK_SECRET, raw_body, signature)

    # 2. Parse payload, extract installation_id
    payload = json.loads(raw_body)
    installation_id = payload["installation"]["id"]

    # 3. Generate JWT (short-lived, for this request only)
    now = int(time.time())
    jwt_payload = {"iss": APP_ID, "iat": now - 60, "exp": now + 600}
    jwt_token = jwt.encode(jwt_payload, PRIVATE_KEY, algorithm="RS256")

    # 4. Exchange JWT for installation token
    token = github_api.post(
        f"/app/installations/{installation_id}/access_tokens",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"permissions": {"contents": "read", "checks": "write", "actions": "write"}}
    ).json()["token"]

    # 5. Use installation token for all subsequent API calls
    config = github_api.get(
        f"/repos/{repo}/contents/ferry.yaml",
        headers={"Authorization": f"token {token}"}
    )
```

### Critical Auth Details

- **Private key storage**: Store in AWS Secrets Manager or SSM Parameter Store (SecureString). Load at Lambda cold start, cache in memory.
- **Do not pass installation tokens to the Action**: The Action runs in the user's environment. It should use OIDC for AWS and `GITHUB_TOKEN` (automatically provided by Actions) for GitHub API calls.
- **Webhook secret vs signing key**: These are different. Webhook secret is a shared symmetric key for HMAC. The App private key is RSA for JWT. Do not confuse them.
- **Rate limits**: Installation tokens have 5,000 requests/hour per installation. For Ferry's use case (a few API calls per webhook), this is more than sufficient.

## Composite Action vs Docker Action

**Confidence: HIGH** (well-documented, stable GitHub Actions feature)

### Comparison Matrix

| Criterion | Composite Action | Docker Container Action |
|-----------|-----------------|------------------------|
| **Startup time** | Near-zero (runs in host) | 10-60s (build or pull image) |
| **Isolation** | None (shares host environment) | Full (container boundary) |
| **Can run Docker commands** | Yes (via `run` steps calling docker CLI) | No (already inside container) |
| **Can call other actions** | Yes (`uses` steps) | No |
| **Language** | Any (via `run` steps) | Any (defined by Dockerfile) |
| **Access to host Docker** | Yes | No (Docker-in-Docker is problematic) |
| **Marketplace distribution** | Yes | Yes |
| **File system** | Shares runner workspace | Mounts workspace at `/github/workspace` |

### Recommendation: Composite Action

**Use a composite action for Ferry.** The reasoning is decisive:

1. **Ferry Action needs to build Docker images** (magic Dockerfile). A Docker container action runs INSIDE a container -- it cannot easily run `docker build` because Docker-in-Docker is fragile and slow. A composite action runs on the host and has direct access to the Docker daemon.

2. **Ferry Action needs to call `docker login`** for ECR. This requires the host's Docker daemon.

3. **Ferry Action needs to call `aws` CLI or use boto3** for deployments. A composite action can install these or rely on the runner's pre-installed tools.

4. **Startup time matters** for deployment tools. Composite actions start instantly. Docker actions add 10-60 seconds for image pull/build.

5. **Composite actions can call other actions** via `uses` steps. This lets Ferry Action compose with `aws-actions/configure-aws-credentials` for OIDC and `aws-actions/amazon-ecr-login` for ECR auth.

### Composite Action Structure

```yaml
# action.yml
name: 'Ferry Deploy'
description: 'Build and deploy serverless AWS resources'
inputs:
  resource-type:
    description: 'Type of resources to deploy (lambdas, step_functions, api_gateways)'
    required: true
  resources:
    description: 'JSON array of resources to deploy'
    required: true
  aws-role-arn:
    description: 'AWS IAM role ARN for OIDC authentication'
    required: true
  aws-region:
    description: 'AWS region'
    required: true
  aws-account-id:
    description: 'AWS account ID (for ECR registry)'
    required: true

runs:
  using: 'composite'
  steps:
    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v4
      with:
        role-to-assume: ${{ inputs.aws-role-arn }}
        aws-region: ${{ inputs.aws-region }}

    - name: Login to ECR
      if: inputs.resource-type == 'lambdas'
      uses: aws-actions/amazon-ecr-login@v2

    - name: Deploy resources
      shell: bash
      run: |
        python ${{ github.action_path }}/deploy.py \
          --type "${{ inputs.resource-type }}" \
          --resources '${{ inputs.resources }}' \
          --region "${{ inputs.aws-region }}" \
          --account-id "${{ inputs.aws-account-id }}"
```

### Why NOT a Docker Action

- Cannot run `docker build` inside a Docker action without Docker-in-Docker (DinD)
- DinD requires privileged mode (security risk, not available on all runners)
- DinD adds significant startup overhead (docker daemon inside docker)
- Breaks the ability to use `aws-actions/configure-aws-credentials` (which is itself an action)

## Dispatch Payload Design

**Confidence: MEDIUM** (GitHub API for workflow_dispatch is stable; payload design is Ferry-specific)

### workflow_dispatch vs repository_dispatch

| Feature | workflow_dispatch | repository_dispatch |
|---------|-------------------|---------------------|
| **Trigger** | `POST /repos/{owner}/{repo}/actions/workflows/{id}/dispatches` | `POST /repos/{owner}/{repo}/dispatches` |
| **Payload location** | `inputs` (string key-value pairs) | `client_payload` (arbitrary JSON) |
| **Workflow selection** | Explicit (by workflow ID or filename) | Event type string matched in workflow `on:` |
| **Visibility in UI** | Shows as "workflow_dispatch" with inputs | Shows as "repository_dispatch" |
| **Input constraints** | Max 10 inputs, all strings, max 65535 chars each | Arbitrary JSON, max ~65KB total |
| **Manual trigger** | Can also be triggered manually from UI | API-only |

### Recommendation: workflow_dispatch

Use `workflow_dispatch` because:

1. **Explicit workflow targeting**: Ferry knows exactly which workflow file to trigger (e.g., `.github/workflows/ferry-lambdas.yml`). No need for event_type routing.
2. **UI visibility**: If a user manually checks their Actions tab, they see clear "workflow_dispatch" triggers with input values.
3. **Input validation**: GitHub validates that required inputs are provided before the workflow starts.

However, `workflow_dispatch` inputs are all strings. For structured data (list of resources), serialize as JSON string.

### Recommended Payload Structure

```json
{
  "ref": "main",
  "inputs": {
    "ferry_version": "1",
    "trigger_sha": "abc123def456",
    "trigger_ref": "refs/heads/main",
    "trigger_pr": "42",
    "resource_type": "lambdas",
    "resources": "[{\"name\":\"order-processor\",\"source\":\"services/order-processor\",\"ecr\":\"ferry/order-processor\"},{\"name\":\"payment-handler\",\"source\":\"services/payment-handler\",\"ecr\":\"ferry/payment-handler\"}]",
    "deployment_tag": "pr-42"
  }
}
```

### Payload Field Rationale

| Field | Type | Purpose |
|-------|------|---------|
| `ferry_version` | string | Schema version for forward compatibility. Action can reject unknown versions. |
| `trigger_sha` | string | The exact commit to build. Action checks out this SHA, not HEAD. |
| `trigger_ref` | string | The branch/ref that triggered the build. For logging and tag derivation. |
| `trigger_pr` | string | PR number if applicable. Used for deployment tags (`pr-42`) and check reporting. Empty string if not a PR. |
| `resource_type` | string | `lambdas`, `step_functions`, or `api_gateways`. Determines the deploy strategy. |
| `resources` | string (JSON) | JSON array of resource objects. Each has the fields from ferry.yaml needed for deployment. |
| `deployment_tag` | string | The ECR image tag / deployment identifier. Computed by Ferry App for consistency. |

### User's Workflow File (Thin Wrapper)

```yaml
# .github/workflows/ferry-deploy.yml
name: Ferry Deploy
on:
  workflow_dispatch:
    inputs:
      ferry_version:
        required: true
      trigger_sha:
        required: true
      trigger_ref:
        required: true
      trigger_pr:
        required: false
        default: ''
      resource_type:
        required: true
      resources:
        required: true
      deployment_tag:
        required: true

permissions:
  id-token: write  # Required for OIDC
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ inputs.trigger_sha }}

      - uses: ferry-app/ferry-action@v1
        with:
          resource-type: ${{ inputs.resource_type }}
          resources: ${{ inputs.resources }}
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}
          aws-account-id: ${{ vars.AWS_ACCOUNT_ID }}
          deployment-tag: ${{ inputs.deployment_tag }}
```

### Design Constraints

- **workflow_dispatch inputs max 10**: Ferry uses 7 inputs. Room for 3 more if needed.
- **Each input max 65535 chars**: The `resources` JSON must stay under this. For a typical repo with < 50 Lambda functions, this is well within limits. Flag for validation if someone has hundreds of resources.
- **Workflow must exist on default branch**: `workflow_dispatch` only triggers workflows that exist on the repo's default branch. The user must have the workflow file merged to main before Ferry can dispatch to it.

## Webhook Delivery and Reliability

**Confidence: HIGH** (GitHub's webhook behavior is well-documented)

### GitHub Webhook Guarantees

- **At-least-once delivery**: GitHub may re-deliver webhooks. DynamoDB dedup is essential.
- **10-second timeout**: GitHub expects a response within 10 seconds or marks delivery as failed. Ferry App Lambda must respond quickly.
- **Retry policy**: GitHub retries failed deliveries (non-2xx response or timeout) up to 3 times with exponential backoff.
- **Ordering**: Webhooks are NOT guaranteed to arrive in order. A push to `main` and its PR merge event may arrive in any order.

### Idempotency Strategy

```
webhook arrives
  -> extract X-GitHub-Delivery header (UUID)
  -> DynamoDB conditional put: PutItem with condition "attribute_not_exists(delivery_id)"
     -> if succeeds: process the webhook (first delivery)
     -> if ConditionalCheckFailedException: return 200 (duplicate, already processed)
```

DynamoDB table design:
```
Table: ferry-webhook-deliveries
  PK: delivery_id (S)     -- X-GitHub-Delivery UUID
  TTL: expires_at (N)     -- epoch + 24 hours (auto-cleanup)
```

### Responding Within 10 Seconds

The Ferry App Lambda must complete all work (validate, dedup, read config, diff, dispatch, post check) within 10 seconds. This is tight but achievable because:

1. Signature validation: < 1ms
2. DynamoDB conditional write: < 50ms
3. JWT generation: < 10ms
4. Installation token exchange: ~100ms
5. Fetch ferry.yaml: ~100ms
6. Fetch commit diff: ~200ms
7. Change detection logic: < 10ms
8. Trigger workflow_dispatch(es): ~100ms each (1-3 dispatches)
9. Post check run: ~100ms

Total: ~700ms-1s for typical case. Well within 10 seconds.

If this becomes a concern: return 200 immediately after dedup, do remaining work asynchronously. But for v1, synchronous processing should be fine.

## Patterns to Follow

### Pattern 1: Stateless Request Handler

**What:** Each webhook invocation is fully self-contained. The Lambda generates a fresh JWT, gets a fresh installation token, reads config, and processes -- no state carried between invocations.

**When:** Always. This is the core pattern for the Ferry App Lambda.

**Why:** Lambda may be running on a new cold start or a warm instance. Stateless handlers are inherently idempotent and horizontally scalable. The only shared state is DynamoDB for dedup.

**Example:**
```python
def handler(event, context):
    # Each invocation is independent
    body = event["body"]
    headers = event["headers"]

    # 1. Validate (no external state needed)
    validate_signature(headers, body)

    # 2. Dedup (DynamoDB -- shared state, but idempotent)
    if not record_delivery(headers["x-github-delivery"]):
        return {"statusCode": 200, "body": "duplicate"}

    # 3. Auth (fresh tokens every time)
    jwt_token = generate_jwt(APP_ID, PRIVATE_KEY)
    installation_id = parse_installation_id(body)
    access_token = get_installation_token(jwt_token, installation_id)

    # 4. Process (pure function of inputs)
    config = fetch_ferry_yaml(access_token, repo, ref)
    changed = detect_changes(access_token, repo, before_sha, after_sha, config)

    # 5. Dispatch (idempotent -- worst case, duplicate workflow runs)
    for resource_type, resources in changed.items():
        dispatch_workflow(access_token, repo, resource_type, resources)

    return {"statusCode": 200, "body": "ok"}
```

### Pattern 2: Config-Driven Change Detection

**What:** The `ferry.yaml` config file defines what directories map to what resources. Change detection is the intersection of "files changed in this push" and "source directories defined in config."

**When:** On every push/PR webhook.

**Why:** This is the core logic that makes Ferry useful. Without it, users would need to write their own change detection in GitHub Actions (which is what they do today with `tj-actions/changed-files`).

**Example:**
```python
def detect_changes(
    access_token: str,
    repo: str,
    base_sha: str,
    head_sha: str,
    config: FerryConfig,
) -> dict[str, list[Resource]]:
    """Return resources grouped by type that have changes."""

    # Get list of changed files from GitHub Compare API
    comparison = github_api.get(
        f"/repos/{repo}/compare/{base_sha}...{head_sha}",
        token=access_token,
    )
    changed_files = {f["filename"] for f in comparison["files"]}

    affected: dict[str, list[Resource]] = {}

    for resource_type, resources in config.resource_groups():
        for resource in resources:
            # Check if any changed file is under this resource's source directory
            if any(f.startswith(resource.source + "/") for f in changed_files):
                affected.setdefault(resource_type, []).append(resource)

    return affected
```

### Pattern 3: Separation of Orchestration and Execution

**What:** Ferry App (backend) decides WHAT to deploy. Ferry Action (GHA runner) does the HOW. The dispatch payload is the contract between them.

**When:** This is the fundamental architectural split.

**Why:** This is the Digger model's key insight. The backend is thin (decision-making only). The execution environment (GHA runner) is the user's -- they pay for compute, they control the network access, they own the AWS credentials (via OIDC). Ferry never touches the user's AWS account directly.

### Pattern 4: Version the Dispatch Contract

**What:** Include `ferry_version` in every dispatch payload. The action checks this field and can reject unsupported versions.

**When:** From day one.

**Why:** The dispatch payload is an API contract between two independently deployed systems (Ferry App backend and Ferry Action). They will evolve at different rates. Versioning prevents breaking changes from causing silent failures.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Passing Secrets in Dispatch Payload

**What:** Including AWS credentials, GitHub tokens, or other secrets in the `workflow_dispatch` inputs.

**Why bad:** Dispatch inputs are visible in the Actions UI. Anyone with read access to the repo can see workflow run inputs. Also, GitHub logs workflow inputs in the audit log.

**Instead:** The Action should obtain its own credentials. AWS via OIDC (user configures trust policy). GitHub via the automatic `GITHUB_TOKEN`. Any additional secrets go in GitHub Secrets and are referenced in the workflow file.

### Anti-Pattern 2: Backend Performing Deployments

**What:** Having the Ferry App Lambda directly call AWS APIs to deploy resources.

**Why bad:** Requires Ferry's backend to have AWS credentials for every user's account. Massive security liability. Also, container builds require Docker, which Lambda cannot run.

**Instead:** Ferry App only orchestrates. Deployment runs in the user's GHA runner with their credentials.

### Anti-Pattern 3: Monolithic Dispatch (One Dispatch for All Types)

**What:** Sending a single workflow_dispatch containing lambdas AND step functions AND API gateways.

**Why bad:** Different resource types have fundamentally different deployment steps. Lambdas need Docker builds. Step Functions need envsubst. API Gateways need OpenAPI processing. A monolithic workflow becomes a giant conditional mess. Also, if Lambda deploys fail, it should not block Step Function deploys.

**Instead:** One dispatch per resource type. Each triggers a focused workflow (or the same workflow with type-specific logic). Resource types deploy independently and can fail independently.

### Anti-Pattern 4: Caching Installation Tokens Across Requests

**What:** Storing installation access tokens in DynamoDB or environment variables for reuse across Lambda invocations.

**Why bad:** Installation tokens expire after 1 hour, but the permissions they grant can change if the user modifies the GitHub App installation. Always generating a fresh token ensures you have current permissions. The API call is fast (~100ms) and the 5,000/hour rate limit is not a concern.

**Instead:** Generate a fresh installation token for each webhook processing request.

### Anti-Pattern 5: Using repository_dispatch with Event Routing

**What:** Using `repository_dispatch` with `event_type` strings like `ferry-deploy-lambdas` and routing in the workflow's `on.repository_dispatch.types`.

**Why bad:** `repository_dispatch` requires the workflow file to list all event types it handles. Adding a new resource type requires updating the user's workflow file. Also, `client_payload` is untyped -- no input validation from GitHub.

**Instead:** Use `workflow_dispatch` with explicit inputs. The workflow ID targeting is more direct and the input validation is built-in.

## Component Build Order (Dependencies)

The components have clear dependency ordering:

```
Phase 1: Foundation (no external dependencies)
  |
  +-- Webhook signature validation
  +-- DynamoDB dedup logic
  +-- GitHub App JWT generation
  +-- Installation token exchange
  +-- Pydantic models for ferry.yaml, webhook payloads, dispatch payloads
  |
Phase 2: Core App Logic (depends on Phase 1)
  |
  +-- ferry.yaml parser and validator
  +-- Change detection engine (diff analysis + config matching)
  +-- Dispatch payload builder
  +-- workflow_dispatch trigger
  +-- Checks API integration (PR status)
  |
Phase 3: Ferry Action - Build (independent of Phase 2 for development)
  |
  +-- Composite action scaffolding (action.yml)
  +-- Magic Dockerfile (port from pipelines-hub)
  +-- Docker build + ECR push logic
  +-- Lambda deployment logic
  |
Phase 4: Ferry Action - Extended Deploy (depends on Phase 3)
  |
  +-- Step Functions deployment
  +-- API Gateway deployment
  |
Phase 5: Integration (depends on Phases 2 + 3)
  |
  +-- End-to-end flow testing
  +-- GitHub App registration and configuration
  +-- AWS infrastructure (Lambda, API Gateway/Function URL, DynamoDB)
```

**Key dependency insight:** Phases 2 and 3 can be built in parallel. The Ferry App and Ferry Action communicate only through the dispatch payload contract. Define the payload schema in Phase 1 (as Pydantic models) and both sides can develop against it independently.

## Single Lambda vs Two Lambdas

**Confidence: MEDIUM**

The PROJECT.md mentions "1-2 Lambdas." Recommendation: **start with one Lambda.**

**One Lambda (recommended for v1):**
- Handles all webhook events (push, pull_request)
- Routes internally based on event type
- Simpler deployment, fewer moving parts
- Lambda cold start is minimal for Python (~200ms)
- All logic shares the same auth/config code

**When to split into two Lambdas:**
- If webhook processing exceeds 10 seconds regularly (unlikely for v1)
- If you need async processing (webhook receiver returns 200, processor runs separately)
- If different events need different memory/timeout configurations

**Architecture if you do split:**
```
Lambda 1 (webhook receiver): validate, dedup, return 200
  -> Invokes Lambda 2 asynchronously (via Lambda.invoke with InvocationType='Event')
Lambda 2 (processor): auth, config, diff, dispatch, checks
```

This is the "return 200 quickly, process later" pattern. Not needed for v1 but a clean escape hatch.

## API Gateway Function URL vs API Gateway

**Confidence: HIGH**

For receiving webhooks, use **Lambda Function URL** (not API Gateway):

| Criterion | Lambda Function URL | API Gateway (REST/HTTP) |
|-----------|-------------------|------------------------|
| **Cost** | Free (included in Lambda pricing) | $1/million requests + data transfer |
| **Setup** | One setting on the Lambda | Separate resource, routes, stages |
| **Custom domain** | Requires CloudFront | Built-in custom domain |
| **Features** | Basic (no rate limiting, no API keys) | Full (throttling, caching, WAF) |
| **Webhook use case** | Perfect -- just needs an HTTPS endpoint | Overkill for a single POST endpoint |

For v1, Function URL is the right choice. GitHub just needs an HTTPS endpoint to POST to. If you later need rate limiting or custom domains, add API Gateway in front.

## Scalability Considerations

| Concern | At 10 installations | At 1K installations | At 10K installations |
|---------|---------------------|---------------------|----------------------|
| **Lambda concurrency** | Default (1000 concurrent) is fine | Still fine -- each invocation is < 2s | May need reserved concurrency |
| **DynamoDB throughput** | On-demand, pennies | On-demand, still cheap | On-demand scales automatically |
| **GitHub rate limits** | 5K req/hr per installation -- no issue | Each installation has its own limit | No issue (limits are per-installation) |
| **Secrets management** | One App private key for all | Same -- single multi-tenant App | Same |
| **Dispatch volume** | ~10s of dispatches/day | ~1000s of dispatches/day | May hit GitHub secondary rate limits |

The architecture scales naturally because:
- Lambda scales horizontally
- DynamoDB on-demand scales automatically
- GitHub rate limits are per-installation (not per-app)
- No shared mutable state beyond dedup table

The main scaling concern at 10K+ installations is GitHub's secondary rate limits (anti-abuse throttling on API calls). Mitigation: add exponential backoff/retry to dispatch calls.

## Sources

- GitHub Docs: About authentication with a GitHub App (training data, HIGH confidence for auth mechanics)
- GitHub Docs: About custom actions (training data, HIGH confidence for action types)
- GitHub Docs: Events that trigger workflows - workflow_dispatch (training data, HIGH confidence)
- GitHub Docs: Webhooks - securing your webhooks (training data, HIGH confidence)
- Digger GitHub repository: github.com/diggerhq/digger (training data, MEDIUM confidence -- architecture may have evolved)
- AWS Lambda Function URLs documentation (training data, HIGH confidence)

**Note:** Web search and web fetch were unavailable during this research session. Findings are based on training data knowledge of GitHub APIs (which are stable and well-documented) and the Digger open-source project. The core GitHub App and Actions mechanics are very unlikely to have changed materially. The Digger-specific details should be verified against the current Digger codebase if precision is needed.
