# Technology Stack

**Project:** Ferry
**Researched:** 2026-02-21
**Overall confidence:** MEDIUM-HIGH (core Python/AWS/GitHub ecosystems well-known from training data; version numbers need verification before implementation)

## Recommended Stack

### Core Framework (Ferry App Backend)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.14 | Runtime | Already decided in project constraints. uv workspace already set up. | HIGH |
| Pydantic | >=2.6 | Data validation, settings, models | Type-safe webhook payloads, ferry.yaml parsing, dispatch payloads. v2 is faster and more Pythonic than v1. The data contract between App and Action is the architectural spine -- Pydantic models define it. | HIGH |
| PyJWT | >=2.8 | GitHub App JWT generation | Lightweight, well-maintained. Only need `jwt.encode()` with RS256 for App auth. Under 100KB installed. | HIGH |
| cryptography | >=42.0 | RSA key handling for JWT | Required by PyJWT for RS256 signing. Handles PEM private key loading. Large dependency but unavoidable for RSA operations. | HIGH |
| boto3 | >=1.34 | AWS SDK | DynamoDB operations in App Lambda; Lambda/SFN/APIGW deployment in Action. Bundled in Lambda runtime but pin for local dev/testing. | HIGH |
| httpx | >=0.27 | HTTP client for GitHub API | Modern, supports sync and async, excellent timeout handling, connection pooling. Better than `requests` for typed responses. Lighter than any GitHub SDK. | HIGH |
| PyYAML | >=6.0.1 | Parse ferry.yaml | Standard YAML parser. Use `yaml.safe_load()` only (never `yaml.load()`). Pydantic validates after parsing. | HIGH |

### GitHub API Interaction

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| httpx (direct API calls) | >=0.27 | GitHub REST API | **Use direct HTTP calls, not a GitHub SDK.** Ferry needs exactly 6 GitHub API endpoints. A full SDK adds dependency weight for minimal benefit. | HIGH |

**The 6 endpoints Ferry calls:**
1. `POST /app/installations/{id}/access_tokens` -- get installation token
2. `GET /repos/{owner}/{repo}/contents/{path}?ref={sha}` -- read ferry.yaml
3. `GET /repos/{owner}/{repo}/compare/{base}...{head}` -- get changed files
4. `POST /repos/{owner}/{repo}/actions/workflows/{id}/dispatches` -- trigger workflow
5. `POST /repos/{owner}/{repo}/check-runs` -- create check run
6. `PATCH /repos/{owner}/{repo}/check-runs/{id}` -- update check run

Build a thin `GitHubClient` class (~150 lines) wrapping httpx with:
- Automatic `Authorization: Bearer {token}` header injection
- `Accept: application/vnd.github+json` header
- `X-GitHub-Api-Version: 2022-11-28` header (API versioning)
- Retry on 502/503 with exponential backoff (via tenacity)
- Rate limit header tracking (`X-RateLimit-Remaining`)

**Why NOT PyGithub:** Synchronous-only (uses `requests`), heavy (~15MB installed), wraps the entire GitHub API surface. For 6 endpoints, it is pure overhead.

**Why NOT githubkit:** Modern, typed, auto-generated from GitHub's OpenAPI spec. Best Python GitHub library if you need broad API coverage. But ~50MB installed, and auto-generated code is harder to debug. Overkill for 6 endpoints.

**Why NOT gidgethub:** Designed specifically for GitHub bots/Apps -- closest conceptual fit. Lightweight, async-native. Reasonable alternative to raw httpx. However: single maintainer (Brett Cannon, Python core dev), small community, less likely to be quickly updated if GitHub changes something. For 6 endpoints, the 150-line wrapper gives full control with zero dependency risk.

### GitHub App Authentication

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| PyJWT + cryptography | >=2.8, >=42.0 | JWT generation for App auth | GitHub App auth requires: (1) generate JWT from App private key, (2) exchange JWT for installation access token. PyJWT handles step 1 (~5 lines). httpx handles step 2 (~10 lines). | HIGH |

**Auth implementation pattern:**
```python
import jwt
import time

def generate_app_jwt(app_id: str, private_key: str) -> str:
    """Generate a GitHub App JWT. Valid for 10 minutes."""
    now = int(time.time())
    payload = {
        "iat": now - 60,       # Backdate 60s for clock skew
        "exp": now + (9 * 60), # 9 minutes (buffer before 10-min max)
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")

def get_installation_token(
    client: httpx.Client, jwt_token: str, installation_id: int
) -> str:
    """Exchange App JWT for scoped installation access token."""
    resp = client.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"permissions": {"contents": "read", "checks": "write", "actions": "write"}},
    )
    resp.raise_for_status()
    return resp.json()["token"]
```

**Critical details:**
- Always backdate `iat` by 60 seconds (clock skew protection)
- Set `exp` to 9 minutes, not 10 (buffer)
- Generate fresh JWT per webhook processing cycle (do NOT cache JWTs)
- Installation tokens can be cached in DynamoDB with TTL (1 hour minus 5-minute buffer)
- Scope installation token to minimum permissions needed

### Webhook Handling

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| hmac + hashlib (stdlib) | N/A | HMAC-SHA256 signature validation | Standard library. `hmac.compare_digest()` provides constant-time comparison (timing attack prevention). Zero dependencies. | HIGH |
| Pydantic | >=2.6 | Webhook payload parsing | Define typed models for push/PR events. Validates structure and types in one step. Use `model_validate()` for parsing. | HIGH |

**Webhook validation (~10 lines, no dependencies beyond stdlib):**
```python
import hmac
import hashlib

def verify_webhook_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```

**CRITICAL:** Validate against raw request body bytes, BEFORE any JSON parsing. Re-serialized JSON may differ from the original (whitespace, key ordering).

### Database

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| DynamoDB (on-demand) | N/A (AWS service) | Webhook dedup, optional state tracking | Already decided. On-demand capacity mode -- no capacity planning needed, scales automatically, pay per request. | HIGH |
| boto3 DynamoDB client | >=1.34 | DynamoDB access | Use `client` (low-level) not `resource` (high-level) for Lambda -- faster cold starts (~50ms difference), more explicit API, better for simple operations. | HIGH |

**Table design (single table):**
```
Table: ferry-state
PK: pk (S)           -- e.g., "DELIVERY#uuid" or "EVENT#repo#sha"
SK: sk (S)           -- "METADATA" for single items
TTL: expires_at (N)  -- epoch timestamp for automatic cleanup

# Webhook dedup by delivery ID
PK="DELIVERY#abc-123", SK="METADATA", TTL=now+86400

# Event-level dedup (catches re-queued events with new delivery IDs)
PK="EVENT#owner/repo#push#sha123", SK="METADATA", TTL=now+86400
```

**Why NOT PynamoDB or other ORM:** For 2-3 access patterns on 1 table, boto3 client is sufficient. An ORM adds dependency weight and abstraction over `put_item`/`get_item`/`query`.

### Infrastructure (Ferry App Deployment)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| AWS SAM (sam-cli) | >=1.100 | Lambda packaging and deployment | Purpose-built for Lambda apps. `template.yaml` defines Lambda + Function URL + DynamoDB in ~50 lines. `sam build` + `sam deploy` handles everything. Superset of CloudFormation. | MEDIUM |
| Lambda Function URL | N/A | Webhook HTTPS endpoint | Free (included in Lambda pricing). No API Gateway needed for a single POST endpoint. GitHub just needs an HTTPS URL to send webhooks to. | HIGH |

**Why NOT API Gateway:** Overkill for one POST endpoint. Function URLs provide HTTPS, CORS, and IAM auth (though we use NONE + HMAC). Saves ~$3.50/million requests.

**Why NOT Terraform:** SAM is simpler for pure Lambda apps. The template is CloudFormation, so it's portable. Users' infrastructure uses Terraform; Ferry's own infra benefits from Lambda-optimized tooling.

**Why NOT CDK:** Heavy for 2 Lambdas + 1 DynamoDB table. CDK app would have more boilerplate than the Lambda code itself.

**SAM template sketch:**
```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  WebhookFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: ferry_app.webhook.handler
      Runtime: python3.14
      MemorySize: 256
      Timeout: 30
      FunctionUrlConfig:
        AuthType: NONE
      Environment:
        Variables:
          GITHUB_APP_ID: !Ref GitHubAppId
          TABLE_NAME: !Ref StateTable
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref StateTable

  StateTable:
    Type: AWS::DynamoDB::Table
    Properties:
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - { AttributeName: pk, AttributeType: S }
        - { AttributeName: sk, AttributeType: S }
      KeySchema:
        - { AttributeName: pk, KeyType: HASH }
        - { AttributeName: sk, KeyType: RANGE }
      TimeToLiveSpecification:
        AttributeName: expires_at
        Enabled: true
```

### Ferry Action (GitHub Actions)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Composite Action | N/A | Action type | **Composite, not Docker.** Ferry Action must run `docker build` for Lambda containers. Docker actions run inside a container and cannot access the host Docker daemon without Docker-in-Docker (fragile, slow, security risk). Composite actions run on the host with full Docker access. | HIGH |
| actions/setup-python@v5 | v5 | Python runtime | Ensures Python 3.14 is available. Some runners may not have it pre-installed. | HIGH |
| aws-actions/configure-aws-credentials@v4 | v4 | OIDC auth | Standard GHA action for OIDC-based AWS auth. Handles `AssumeRoleWithWebIdentity` + optional role chaining. | HIGH |
| aws-actions/amazon-ecr-login@v2 | v2 | ECR Docker login | After OIDC auth, logs Docker into the ECR registry. | HIGH |
| docker/setup-buildx-action@v3 | v3 | Docker BuildKit | Ensures BuildKit is available and configured. Required for `--mount=type=secret` in magic Dockerfile. | MEDIUM |

**Why NOT a Docker action:**
- Cannot run `docker build` inside a Docker action without DinD
- DinD requires privileged mode (unavailable on GitHub-hosted runners by default)
- DinD adds 10-30s startup overhead
- Cannot call other actions (`uses` steps) from a Docker action
- Cannot use `aws-actions/configure-aws-credentials` for OIDC from inside a Docker action

### AWS Deployment (from Ferry Action)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| boto3 (via Python scripts) | >=1.34 | Lambda/SFN/APIGW deployment | **Use boto3 directly.** Ferry Action should own its deployment logic (20-30 lines per resource type) rather than depending on third-party GHA actions. Reduces supply-chain risk, enables custom error handling, allows digest-based skip logic. | HIGH |
| Docker CLI | N/A | Container builds | `docker build`, `docker tag`, `docker push`. Standard, reliable, no wrapper needed. | HIGH |

**Lambda deployment sequence (boto3, ~25 lines):**
```python
def deploy_lambda(function_name: str, image_uri: str, alias: str = "live") -> dict:
    client = boto3.client("lambda")

    # 1. Check if deploy is needed (digest-based skip)
    current = client.get_function(FunctionName=function_name)
    current_image = current["Code"]["ImageUri"]
    if images_have_same_digest(current_image, image_uri):
        return {"status": "skipped", "reason": "same digest"}

    # 2. Update function code
    client.update_function_code(FunctionName=function_name, ImageUri=image_uri)

    # 3. Wait for update to complete (CRITICAL -- do not skip)
    waiter = client.get_waiter("function_updated_v2")
    waiter.wait(FunctionName=function_name, WaiterConfig={"Delay": 5, "MaxAttempts": 60})

    # 4. Publish version
    version = client.publish_version(
        FunctionName=function_name,
        Description=f"Deployed by Ferry: {image_uri}",
    )

    # 5. Update alias
    client.update_alias(
        FunctionName=function_name,
        Name=alias,
        FunctionVersion=version["Version"],
    )

    return {"status": "deployed", "version": version["Version"]}
```

**Step Functions deployment (boto3, ~15 lines):**
```python
def deploy_step_function(state_machine_arn: str, definition_path: str, variables: dict) -> dict:
    client = boto3.client("stepfunctions")

    # 1. Read and template the definition
    with open(definition_path) as f:
        definition = f.read()
    for key, value in variables.items():
        definition = definition.replace(f"${{{key}}}", value)

    # 2. Validate before deploying
    validation = client.validate_state_machine_definition(
        definition=definition, type="STANDARD"
    )
    if validation.get("diagnostics"):
        # Log warnings/errors but may still proceed for warnings
        pass

    # 3. Update state machine
    client.update_state_machine(stateMachineArn=state_machine_arn, definition=definition)
    return {"status": "deployed"}
```

**API Gateway deployment (boto3, ~10 lines):**
```python
def deploy_api_gateway(rest_api_id: str, spec_path: str, stage: str = "live") -> dict:
    client = boto3.client("apigateway")

    # 1. Import OpenAPI spec (overwrite mode)
    with open(spec_path, "rb") as f:
        spec_body = f.read()
    client.put_rest_api(restApiId=rest_api_id, mode="overwrite", body=spec_body)

    # 2. Create deployment (CRITICAL -- put-rest-api alone does not deploy)
    client.create_deployment(restApiId=rest_api_id, stageName=stage)
    return {"status": "deployed"}
```

**Why NOT int128/deploy-lambda-action:** Works well (used in pipelines-hub reference), but Ferry should own its deploy logic. Third-party action adds supply-chain risk and limits customization (e.g., custom skip logic, structured output, error handling). The boto3 calls are straightforward.

### Testing

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pytest | >=8.0 | Test runner | Already decided. Standard Python testing. | HIGH |
| moto | >=5.0 | AWS service mocking | Already decided. Mock DynamoDB, Lambda, SFN, APIGW, ECR. Covers all AWS services Ferry uses. | HIGH |
| pytest-httpx | >=0.30 | Mock httpx calls | Mock GitHub API responses in tests. Works natively with httpx (no adapter needed). Register expected requests and responses declaratively. | MEDIUM |
| pytest-cov | >=5.0 | Coverage reporting | Standard coverage plugin. | HIGH |

**Test strategy by component:**
- **Webhook handler:** moto (DynamoDB dedup) + pytest-httpx (GitHub API calls)
- **Change detection:** Pure unit tests (input: config + file list, output: affected resources)
- **ferry.yaml parser:** Pure unit tests with fixture YAML files
- **GitHub client:** pytest-httpx with response fixtures
- **Lambda deployer:** moto (Lambda/ECR mocks)
- **SFN deployer:** moto (Step Functions mock)
- **APIGW deployer:** moto (API Gateway mock) -- verify moto coverage for `put_rest_api`

### Code Quality

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Ruff | >=0.4 | Linting + formatting | Already decided. Replaces flake8, isort, black. Single tool, very fast (Rust-based). | HIGH |
| mypy | >=1.10 | Static type checking | Catch type errors. Works well with Pydantic v2 (use plugin). All functions should have type annotations. | MEDIUM |
| pre-commit | >=3.7 | Git hooks | Already decided. Run Ruff + mypy on commit. | HIGH |

### Package Management

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| uv | >=0.4 | Package manager + workspace | Already decided. Fast, supports workspaces for monorepo. | HIGH |

## Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| structlog | >=24.1 | Structured logging | All Lambda functions. JSON-structured logs for CloudWatch Logs Insights queries. Adds context (installation_id, repo, commit_sha) to every log line. | MEDIUM |
| pydantic-settings | >=2.2 | Environment config | Load Lambda env vars (APP_ID, WEBHOOK_SECRET, TABLE_NAME) with type validation. Fails fast on missing config. | MEDIUM |
| tenacity | >=8.3 | Retry logic | Retry GitHub API calls (502/503) and AWS API calls (throttling) with exponential backoff. Decorative `@retry` API is clean. | MEDIUM |
| boto3-stubs | >=1.34 | Type stubs for boto3 | Mypy type checking for AWS API calls. Install with service extras: `boto3-stubs[dynamodb,lambda,stepfunctions,apigateway,ecr]`. Dev dependency only. | MEDIUM |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| GitHub API client | httpx (direct) | PyGithub | Sync-only, heavy (~15MB), wraps entire API. For 6 endpoints, direct calls are cleaner. |
| GitHub API client | httpx (direct) | githubkit | Heavy (~50MB installed), auto-generated, overkill for v1. Reconsider if API surface grows to 20+ endpoints. |
| GitHub API client | httpx (direct) | gidgethub | Lightweight, GitHub App-focused. Single maintainer risk. Reasonable Plan B if httpx wrapper becomes burdensome. |
| HTTP client | httpx | requests | httpx has better timeout handling, async support, modern API. requests is showing its age. |
| HTTP client | httpx | aiohttp | More complex API. httpx covers both sync and async use cases. |
| Lambda framework | None (raw handler) | AWS Lambda Powertools | Adds tracing, structured logging, validation middleware. Good library but adds complexity for a thin backend. Consider for v2 if observability needs grow. |
| Lambda framework | None (raw handler) | Chalice | Opinionated Flask-like framework for Lambda. Ties you to its deployment model. Community growth has stalled. |
| Lambda framework | None (raw handler) | Mangum + Starlette | ASGI adapter + lightweight framework. Overkill for single-route Lambda. Consider if Ferry grows to need multiple HTTP routes. |
| IaC (Ferry's own infra) | SAM | Terraform | SAM is simpler for pure Lambda apps. ~50 lines vs ~150 lines of Terraform. |
| IaC (Ferry's own infra) | SAM | CDK | Heavy for 2 resources. CDK app would be more boilerplate than the Lambda code. |
| Action type | Composite | Docker action | Cannot run docker build inside Docker action without DinD. Composite is faster, more flexible, and can compose with other actions. |
| Lambda deploy | boto3 (direct) | int128/deploy-lambda-action | Supply-chain risk. Ferry should own its deploy logic for customization and reliability. |
| DynamoDB ORM | boto3 client | PynamoDB | Unnecessary abstraction for 1 table with 2-3 access patterns. |
| YAML parsing | PyYAML | ruamel.yaml | PyYAML is simpler. ruamel preserves comments and ordering (not needed -- Ferry only reads YAML, never writes). |
| YAML parsing | PyYAML | pydantic-yaml | Adds a dependency to save 2 lines of code (`yaml.safe_load` + `Model.model_validate`). Not worth it. |
| Logging | structlog | stdlib logging | structlog produces clean JSON for CloudWatch with less boilerplate. Structured context (installation_id, repo) is trivial with structlog, awkward with stdlib. |
| JWT | PyJWT | python-jose | python-jose is unmaintained (last release 2022). PyJWT is actively maintained. |
| JWT | PyJWT | authlib | authlib is a full OAuth library. Ferry only needs JWT encoding -- PyJWT is sufficient. |

## Dependency Summary

### Ferry App (Backend Lambda)

```toml
# pyproject.toml dependencies
[project]
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "PyJWT[crypto]>=2.8",       # [crypto] extra installs cryptography
    "PyYAML>=6.0.1",
    "boto3>=1.34",
    "structlog>=24.1",
    "tenacity>=8.3",
]
```

**Total dependency footprint:** ~80MB installed (dominated by cryptography + boto3). In Lambda runtime, boto3 is pre-installed, so the deployment package adds ~30MB.

### Ferry Action (GHA Runner)

```toml
[project]
dependencies = [
    "boto3>=1.34",
    "pydantic>=2.6",
    "PyYAML>=6.0.1",
    "httpx>=0.27",
    "PyJWT[crypto]>=2.8",       # For GitHub API calls from action
    "structlog>=24.1",
    "tenacity>=8.3",
]
```

### Ferry Shared (Shared Models Library)

```toml
[project]
dependencies = [
    "pydantic>=2.6",
    "PyYAML>=6.0.1",
]
```

Shared package contains: ferry.yaml Pydantic models, dispatch payload models, webhook event models. No boto3 or httpx dependency -- pure data models.

### Dev Dependencies

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "moto[all]>=5.0",
    "pytest-httpx>=0.30",
    "pytest-cov>=5.0",
    "ruff>=0.4",
    "mypy>=1.10",
    "pre-commit>=3.7",
    "boto3-stubs[dynamodb,lambda,stepfunctions,apigateway,ecr]>=1.34",
]
```

### GitHub Actions (used in Ferry Action composite steps)

```yaml
# Standard GHA marketplace actions (pinned to major version tags)
- aws-actions/configure-aws-credentials@v4   # OIDC auth
- aws-actions/amazon-ecr-login@v2            # ECR Docker login
- docker/setup-buildx-action@v3              # BuildKit setup
- actions/setup-python@v5                     # Python runtime
- actions/checkout@v4                          # Repo checkout
```

## Key Architecture Decisions Embedded in Stack

### 1. Direct GitHub API over SDK
Ferry talks to 6 GitHub endpoints. A thin `GitHubClient` class (~150 lines) wrapping httpx with Pydantic response models gives us type safety, full control, minimal dependencies, and easy testing (pytest-httpx mocks).

### 2. Raw Lambda Handler over Framework
The webhook receiver is a single function processing one event type. No routing, middleware, or API versioning needed. A raw handler with Pydantic validation is the simplest correct solution:
```python
def handler(event: dict, context) -> dict:
    body = event["body"]  # Raw string for signature validation
    headers = {k.lower(): v for k, v in event["headers"].items()}
    # Validate, dedup, process, dispatch
    return {"statusCode": 200, "body": "ok"}
```

If Ferry App grows to need multiple routes (admin API, webhook status, health check), add a lightweight router or split into separate Lambdas. Do NOT pre-build a framework.

### 3. Composite Action over Docker Action
Composite actions run on the host, start instantly, can call other actions, and have direct Docker daemon access. For a tool that builds Docker images, composite is the only viable option.

### 4. uv Workspace for Monorepo
```
ferry/
  packages/
    ferry-app/              # Backend Lambda code
      pyproject.toml
      src/ferry_app/
    ferry-action/           # GHA Action Python scripts
      pyproject.toml
      src/ferry_action/
    ferry-shared/           # Shared Pydantic models
      pyproject.toml
      src/ferry_shared/
  action.yml                # Composite action definition (repo root)
  pyproject.toml            # Workspace root
  template.yaml             # SAM template for backend infra
```

The shared package avoids duplicating ferry.yaml models and dispatch payload models between App and Action. `uv` workspace ensures they stay in sync.

### 5. PyJWT[crypto] over Separate cryptography Pin
Installing `PyJWT[crypto]` automatically installs the correct version of `cryptography` as a dependency. This avoids version pinning conflicts and ensures compatibility.

## Version Verification Notice

**All version numbers are from training data (through early 2025).** Before implementation, verify:

1. **Python 3.14 Lambda runtime availability.** As of early 2025, AWS Lambda supported up to Python 3.12/3.13. Python 3.14 may require a container-based Lambda (not zip deployment). Verify current runtime availability.

2. **moto coverage for Python 3.14.** moto tracks AWS service coverage closely but may lag on newest Python versions. Test early.

3. **pytest-httpx compatibility with httpx version.** These libraries are tightly coupled. Use compatible versions.

4. **aws-actions versions.** Pin to SHA hashes in production workflows (not version tags) for supply-chain security.

5. **Docker BuildKit version on GitHub-hosted runners.** The magic Dockerfile's `--mount=type=secret` syntax requires BuildKit. Verify the default Docker version on `ubuntu-latest` runners.

## Sources

- Training data knowledge of Python ecosystem (through early 2025) -- MEDIUM confidence on exact version numbers
- GitHub REST API documentation (well-established, stable API) -- HIGH confidence on endpoint behavior
- GitHub Apps authentication documentation -- HIGH confidence on auth flow
- GitHub Actions documentation (composite action specification) -- HIGH confidence
- AWS SDK documentation (boto3 is extremely stable) -- HIGH confidence on API calls
- AWS Lambda Function URL documentation -- HIGH confidence
- AWS SAM documentation -- HIGH confidence
- AWS STS role chaining documentation -- HIGH confidence
- Project constraints from PROJECT.md and MEMORY.md -- HIGH confidence (first-party)
- pipelines-hub reference implementation analysis -- HIGH confidence (first-party)
