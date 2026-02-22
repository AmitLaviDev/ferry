# Phase 1: Foundation and Shared Contract - Research

**Researched:** 2026-02-22
**Domain:** Python monorepo setup, webhook security, DynamoDB idempotency, GitHub App authentication, Pydantic data contracts
**Confidence:** HIGH

## Summary

Phase 1 establishes the foundational infrastructure that all subsequent phases depend on: a uv workspace monorepo with three packages (utils, backend, action), a webhook receiver Lambda that validates HMAC-SHA256 signatures and deduplicates deliveries via DynamoDB conditional writes, GitHub App authentication (JWT + installation token exchange), and the shared Pydantic data contract that decouples App and Action development.

The technical domain is well-understood. Every component uses mature, stable APIs: Python stdlib `hmac`/`hashlib` for signature validation, boto3 conditional `put_item` for DynamoDB dedup, PyJWT for GitHub App JWT generation, and httpx for the GitHub API wrapper. The Lambda Function URL event format (payload format v2) provides the raw request body as a string in `event['body']`, which is exactly what webhook signature validation needs. Pydantic v2 discriminated unions provide type-safe dispatch payload models with efficient validation.

**Primary recommendation:** Build the four Phase 1 components in dependency order: (1) uv workspace + package scaffolding, (2) shared Pydantic models in utils, (3) webhook handler with HMAC validation + DynamoDB dedup in backend, (4) GitHub App auth module in backend. Each is independently testable and the shared contract (step 2) unblocks parallel Phase 2+3 development.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Dispatch payload contract**: Schema version field in the payload (e.g., `"v": 1`) -- Action checks version and handles accordingly. Minimal payload -- only ORCH-02 required fields: resource_type, resources[], trigger_sha, deployment_tag, pr_number. Action fetches anything else it needs from GitHub/AWS. Typed union (Pydantic discriminated union) for resource models -- LambdaResource, StepFunctionResource, ApiGatewayResource as separate models with strong validation.
- **Webhook error behavior**: Push events only in Phase 1 -- Phase 2 adds PR event routing. Keep it minimal for Phase 1, refactor to router pattern when Phase 2 adds PR handlers.
- **Package boundaries (monorepo layout)**: `utils/` -- shared Pydantic models, constants, enums, error types (the contract layer). `backend/` -- Ferry App Lambda (webhook handler, GitHub API wrapper, orchestration). `action/` -- Ferry Action composite action and Python scripts. `iac/` -- SAM templates and infrastructure definitions. GitHub API wrapper lives in `backend/` only, not shared.
- **DynamoDB data model**: 24-hour TTL on dedup records -- GitHub retries within hours, no need for longer retention.

### Claude's Discretion
- Resource list structure within dispatch payload (flat vs grouped) -- Claude picks what works best with per-type dispatch model
- uv workspace configuration -- separate packages vs single package with directories
- Webhook error responses -- security-minimal vs debugging-friendly (Claude picks standard approach)
- Internal logging strategy -- structured JSON vs errors-only
- DynamoDB table design -- single-table vs table-per-concern
- Dedup record metadata -- minimal vs observability-rich
- Dedup key hashing strategy -- full payload hash vs key fields only

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WHOOK-01 | Ferry App validates webhook signature (HMAC-SHA256) against raw body bytes before any JSON parsing | Lambda Function URL event format provides raw body as string in `event['body']`. Python stdlib `hmac.new()` + `hashlib.sha256` + `hmac.compare_digest()` handles validation. Verified against GitHub's official webhook security docs and AWS Lambda Function URL webhook tutorial. |
| WHOOK-02 | Ferry App deduplicates webhook deliveries via DynamoDB conditional write (delivery ID + event content composite key) | DynamoDB `put_item` with `ConditionExpression='attribute_not_exists(pk)'` provides atomic check-and-write. `ConditionalCheckFailedException` is the expected signal for duplicates -- catch it explicitly and return 200. Dual-key dedup (delivery ID + event composite) prevents re-queued events with new delivery IDs. TTL handles cleanup. |
| AUTH-01 | Ferry App authenticates as GitHub App (JWT generation + installation token exchange) to read repos and trigger dispatches | PyJWT with RS256 algorithm. JWT claims: `iss` (client_id or app_id), `iat` (now - 60s for clock drift), `exp` (now + 540s, under 10-min max). Exchange JWT for installation token via `POST /app/installations/{id}/access_tokens`. Fresh JWT per webhook processing cycle -- do not cache JWTs. |
| ACT-02 | Ferry Action, Ferry App, and shared models live in one monorepo managed by uv workspace | uv workspace with `[tool.uv.workspace] members = ["utils", "backend", "action"]` in root pyproject.toml. Workspace members reference each other via `[tool.uv.sources] ferry-utils = { workspace = true }`. Single lockfile ensures consistent dependencies. src layout for each package. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.14 | Runtime | Project constraint. uv workspace already configured for this. |
| pydantic | >=2.6 | Data validation, shared models | Type-safe dispatch payloads, webhook event models, ferry.yaml models. Discriminated unions for resource types. v2 is faster and more Pythonic. |
| pydantic-settings | >=2.2 | Environment config | Load Lambda env vars (APP_ID, WEBHOOK_SECRET, TABLE_NAME) with type validation. Fails fast on missing config. |
| PyJWT[crypto] | >=2.8 | GitHub App JWT generation | RS256 signing for App auth. `[crypto]` extra installs cryptography automatically. ~5 lines for JWT generation. |
| httpx | >=0.27 | HTTP client for GitHub API | Modern, sync+async, excellent timeout handling. Ferry needs exactly 6 GitHub endpoints -- a thin wrapper (~150 lines) is sufficient. |
| boto3 | >=1.34 | AWS SDK (DynamoDB) | DynamoDB operations for dedup. Use low-level `client` (not `resource`) for faster Lambda cold starts. |
| structlog | >=24.1 | Structured JSON logging | JSON-structured logs for CloudWatch Logs Insights. Adds context (installation_id, repo, delivery_id) to every log line. AWS Lambda natively supports JSON log format. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| PyYAML | >=6.0.1 | Parse ferry.yaml | Phase 2+ (ferry.yaml parsing). Include in utils dependencies now for model definitions. |
| tenacity | >=8.3 | Retry logic | GitHub API retries on 502/503. Decorative `@retry` API. Add when implementing GitHub client. |

### Dev Dependencies
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=8.0 | Test runner | All testing. |
| moto[dynamodb] | >=5.0 | AWS service mocking | DynamoDB dedup tests. Use `mock_aws` decorator (moto v5 unified API). |
| pytest-httpx | >=0.30 | Mock httpx calls | GitHub API response mocking. Register expected requests and responses declaratively. |
| pytest-cov | >=5.0 | Coverage reporting | Coverage metrics. |
| ruff | >=0.4 | Linting + formatting | Single tool replaces flake8, isort, black. Rust-based, very fast. |
| mypy | >=1.10 | Static type checking | Catch type errors. Works well with Pydantic v2 plugin. |
| pre-commit | >=3.7 | Git hooks | Run Ruff + mypy on commit. |
| boto3-stubs[dynamodb] | >=1.34 | Type stubs for boto3 | Mypy type checking for DynamoDB calls. Dev dependency only. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| httpx (direct) | PyGithub | Sync-only, heavy (~15MB). For 6 endpoints, direct calls are cleaner. |
| httpx (direct) | gidgethub | Lightweight, GitHub App-focused. Single maintainer risk. Reasonable Plan B. |
| structlog | stdlib logging | structlog produces cleaner JSON for CloudWatch with less boilerplate. |
| PyJWT | python-jose | python-jose is unmaintained (last release 2022). PyJWT is actively maintained. |
| pydantic-settings | manual os.environ | pydantic-settings validates types and fails fast on missing config. Worth the micro-dependency. |

**Installation (workspace root):**
```bash
uv add --dev pytest moto pytest-httpx pytest-cov ruff mypy pre-commit boto3-stubs
```

## Architecture Patterns

### Recommended Project Structure
```
ferry/
  pyproject.toml              # Workspace root (defines members, dev deps)
  uv.lock                     # Single lockfile for entire workspace
  utils/                      # ferry-utils: shared Pydantic models
    pyproject.toml
    src/
      ferry_utils/
        __init__.py
        models/
          __init__.py
          dispatch.py          # DispatchPayload, resource type models
          webhook.py           # PushEvent, webhook header models
          config.py            # FerryConfig (ferry.yaml schema) - Phase 2
        constants.py           # Resource type enums, schema version
        errors.py              # Shared error types
  backend/                    # ferry-backend: App Lambda
    pyproject.toml
    src/
      ferry_backend/
        __init__.py
        webhook/
          __init__.py
          handler.py           # Lambda handler entry point
          signature.py         # HMAC-SHA256 validation
          dedup.py             # DynamoDB dedup logic
        auth/
          __init__.py
          jwt.py               # GitHub App JWT generation
          tokens.py            # Installation token exchange
        github/
          __init__.py
          client.py            # Thin httpx wrapper (~150 lines)
        settings.py            # pydantic-settings config
  action/                     # ferry-action: GHA composite action
    pyproject.toml
    src/
      ferry_action/
        __init__.py
  iac/                        # SAM templates (not a uv package)
    template.yaml
  tests/                      # Shared test directory
    conftest.py               # Shared fixtures (DynamoDB table, httpx mocks)
    test_utils/
      test_dispatch_models.py
      test_webhook_models.py
    test_backend/
      test_handler.py
      test_signature.py
      test_dedup.py
      test_jwt.py
      test_tokens.py
```

### Pattern 1: Lambda Function URL Webhook Handler
**What:** Raw Lambda handler that validates signature, deduplicates, and processes the event. No framework.
**When to use:** Always for Phase 1. The webhook receiver is a single function processing one event type.
**Why:** A raw handler with Pydantic validation is the simplest correct solution for a single-route Lambda.

```python
# Source: AWS Lambda Function URL webhook tutorial + GitHub webhook security docs
import json
import hmac
import hashlib
from ferry_backend.settings import Settings
from ferry_backend.webhook.dedup import record_delivery, is_duplicate
from ferry_backend.auth.jwt import generate_app_jwt
from ferry_backend.auth.tokens import get_installation_token

settings = Settings()  # Load once at module level (Lambda cold start)

def handler(event: dict, context) -> dict:
    # 1. Extract raw body and headers
    body = event.get("body", "")
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}

    # 2. Validate HMAC-SHA256 signature (raw body, before JSON parsing)
    signature = headers.get("x-hub-signature-256", "")
    if not verify_signature(body, signature, settings.webhook_secret):
        return {"statusCode": 401, "body": json.dumps({"error": "invalid signature"})}

    # 3. Parse payload
    payload = json.loads(body)
    delivery_id = headers.get("x-github-delivery", "")
    event_type = headers.get("x-github-event", "")

    # 4. Deduplicate
    if is_duplicate(delivery_id, payload):
        return {"statusCode": 200, "body": json.dumps({"status": "duplicate"})}

    # 5. Process (Phase 1: just validate and return; Phase 2: full pipeline)
    # ... auth, config read, change detection, dispatch ...

    return {"statusCode": 200, "body": json.dumps({"status": "ok"})}

def verify_signature(body: str, signature: str, secret: str) -> bool:
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Pattern 2: DynamoDB Dual-Key Dedup
**What:** Deduplicate on both delivery ID (catches retries) AND event composite key (catches re-queued events with new delivery IDs).
**When to use:** Every webhook processing cycle.
**Why:** GitHub's `X-GitHub-Delivery` header is unique per delivery attempt, not per logical event. If GitHub re-queues an event, it gets a new delivery ID. Dual-key dedup catches both cases.

```python
# Source: DynamoDB conditional writes docs + GitHub webhook behavior
import time
import boto3
from botocore.exceptions import ClientError

TTL_SECONDS = 86400  # 24 hours

def is_duplicate(delivery_id: str, payload: dict, table_name: str) -> bool:
    """Check both delivery-level and event-level dedup."""
    client = boto3.client("dynamodb")
    now = int(time.time())
    expires_at = now + TTL_SECONDS

    # Try delivery-level dedup first (most common case)
    if not _try_record(client, table_name, f"DELIVERY#{delivery_id}", expires_at):
        return True  # Duplicate delivery

    # Try event-level dedup (catches re-queued events with new delivery IDs)
    event_key = _build_event_key(payload)
    if event_key and not _try_record(client, table_name, event_key, expires_at):
        return True  # Duplicate event

    return False  # New, process it

def _try_record(client, table_name: str, pk: str, expires_at: int) -> bool:
    """Attempt conditional write. Returns True if new, False if duplicate."""
    try:
        client.put_item(
            TableName=table_name,
            Item={
                "pk": {"S": pk},
                "sk": {"S": "METADATA"},
                "expires_at": {"N": str(expires_at)},
                "created_at": {"N": str(int(time.time()))},
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
        return True  # New record
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False  # Duplicate
        raise  # Unexpected error, propagate

def _build_event_key(payload: dict) -> str | None:
    """Build event-level dedup key from push event payload."""
    # For push events: repo + event type + after SHA
    repo = payload.get("repository", {}).get("full_name")
    after_sha = payload.get("after")
    if repo and after_sha:
        return f"EVENT#push#{repo}#{after_sha}"
    return None
```

### Pattern 3: GitHub App JWT + Installation Token
**What:** Generate RS256 JWT, exchange for scoped installation access token.
**When to use:** Every webhook processing cycle. Fresh JWT per cycle, do not cache.
**Why:** JWT is cheap to generate (~1ms). Installation tokens expire after 1 hour. Always generating a fresh JWT avoids clock skew bugs at token boundaries.

```python
# Source: GitHub App auth docs (docs.github.com/en/apps)
import time
import jwt  # PyJWT
import httpx

def generate_app_jwt(app_id: str, private_key: str) -> str:
    """Generate a GitHub App JWT. Valid for ~9 minutes."""
    now = int(time.time())
    payload = {
        "iat": now - 60,        # Backdate 60s for clock drift
        "exp": now + (9 * 60),  # 9 minutes (buffer before 10-min max)
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")

def get_installation_token(
    client: httpx.Client,
    jwt_token: str,
    installation_id: int,
) -> str:
    """Exchange App JWT for scoped installation access token."""
    resp = client.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "permissions": {
                "contents": "read",
                "checks": "write",
                "actions": "write",
            }
        },
    )
    resp.raise_for_status()
    return resp.json()["token"]
```

### Pattern 4: Pydantic v2 Discriminated Union for Resource Types
**What:** Use `Literal` field as discriminator to route validation to the correct resource model.
**When to use:** Dispatch payload parsing. Each resource type has different fields.
**Why:** Efficient validation -- Pydantic checks the discriminator field first and validates against only the matching model. Clear error messages on invalid types.

```python
# Source: Pydantic v2 unions docs (docs.pydantic.dev/latest/concepts/unions/)
from typing import Literal, Union
from typing_extensions import Annotated
from pydantic import BaseModel, Field

class LambdaResource(BaseModel):
    resource_type: Literal["lambda"] = "lambda"
    name: str
    source: str
    ecr: str

class StepFunctionResource(BaseModel):
    resource_type: Literal["step_function"] = "step_function"
    name: str
    source: str

class ApiGatewayResource(BaseModel):
    resource_type: Literal["api_gateway"] = "api_gateway"
    name: str
    source: str

Resource = Annotated[
    Union[LambdaResource, StepFunctionResource, ApiGatewayResource],
    Field(discriminator="resource_type"),
]

class DispatchPayload(BaseModel):
    v: int = 1  # Schema version
    resource_type: str  # "lambdas", "step_functions", "api_gateways"
    resources: list[Resource]
    trigger_sha: str
    deployment_tag: str
    pr_number: str = ""  # Empty string if not a PR
```

### Pattern 5: pydantic-settings for Lambda Configuration
**What:** Type-safe environment variable loading with validation at import time.
**When to use:** Lambda cold start. Load once at module level, fail fast on missing config.

```python
# Source: pydantic-settings docs (docs.pydantic.dev/latest/concepts/pydantic_settings/)
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FERRY_")

    app_id: str                   # FERRY_APP_ID
    private_key: str              # FERRY_PRIVATE_KEY (PEM content or SSM reference)
    webhook_secret: str           # FERRY_WEBHOOK_SECRET
    table_name: str               # FERRY_TABLE_NAME
    log_level: str = "INFO"       # FERRY_LOG_LEVEL
```

### Pattern 6: uv Workspace Configuration
**What:** Root pyproject.toml defines workspace members. Each member has its own pyproject.toml with workspace dependencies.
**When to use:** Project initialization. All subsequent development uses this structure.

Root `pyproject.toml`:
```toml
[project]
name = "ferry"
version = "0.1.0"
requires-python = ">=3.14"

[tool.uv.workspace]
members = ["utils", "backend", "action"]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "moto[dynamodb]>=5.0",
    "pytest-httpx>=0.30",
    "pytest-cov>=5.0",
    "ruff>=0.4",
    "mypy>=1.10",
    "pre-commit>=3.7",
    "boto3-stubs[dynamodb]>=1.34",
]

[tool.ruff]
target-version = "py314"
line-length = 100
src = ["utils/src", "backend/src", "action/src"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "TCH"]

[tool.mypy]
python_version = "3.14"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Member `utils/pyproject.toml`:
```toml
[project]
name = "ferry-utils"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "pydantic>=2.6",
    "PyYAML>=6.0.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ferry_utils"]
```

Member `backend/pyproject.toml`:
```toml
[project]
name = "ferry-backend"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "ferry-utils",
    "httpx>=0.27",
    "pydantic-settings>=2.2",
    "PyJWT[crypto]>=2.8",
    "boto3>=1.34",
    "structlog>=24.1",
    "tenacity>=8.3",
]

[tool.uv.sources]
ferry-utils = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ferry_backend"]
```

### Anti-Patterns to Avoid
- **Parsing JSON before signature validation:** Lambda Function URL provides `event['body']` as a string. Validate the HMAC against this raw string, then parse. Re-serialized JSON may differ from the original.
- **Treating ConditionalCheckFailedException as an error:** This is the expected, happy-path signal for duplicate deliveries. Catch it explicitly, log at DEBUG, return 200.
- **Caching GitHub App JWTs across invocations:** JWTs are cheap to generate. Always create fresh per webhook processing cycle. Clock skew at token boundaries causes intermittent 401 errors.
- **Using `==` for signature comparison:** Always use `hmac.compare_digest()` for constant-time comparison. Prevents timing attacks.
- **Using boto3 `resource` (high-level) in Lambda:** The `client` (low-level) API has ~50ms faster cold starts. For simple `put_item`/`get_item`, the high-level API adds no value.
- **Sharing GitHub API wrapper in utils package:** The GitHub client belongs in `backend/` only. The Action uses `GITHUB_TOKEN` (automatic) and boto3 for AWS, not the App's installation token.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HMAC-SHA256 signature validation | Custom crypto | `hmac.new()` + `hashlib.sha256` (stdlib) | Stdlib is correct, audited, constant-time. Zero dependencies. |
| JWT RS256 signing | Manual RSA operations | `PyJWT[crypto]` | Handles PEM key loading, RS256 signing, claim encoding. ~5 lines of code. |
| Environment variable loading | Manual `os.environ.get()` | `pydantic-settings` BaseSettings | Type validation, missing-value errors, prefix support. Fails fast. |
| DynamoDB conditional writes | Custom locking | boto3 `ConditionExpression` | DynamoDB's conditional write is atomic and race-free. The database handles concurrency. |
| JSON structured logging | Manual `json.dumps()` in log calls | structlog | Context binding, processor chains, CloudWatch-compatible JSON output. |
| HTTP client for GitHub API | Custom urllib3/requests wrapper | httpx | Timeout handling, connection pooling, clean API. ~150-line wrapper on top. |

**Key insight:** Phase 1 is almost entirely "glue code" connecting well-understood building blocks. The only custom logic is the dedup key design and the dispatch payload schema. Everything else should use standard library or well-established packages.

## Common Pitfalls

### Pitfall 1: Lambda Function URL Body Encoding
**What goes wrong:** For requests with `Content-Type` other than `application/json` or `text/*`, Lambda Function URL base64-encodes the body. If `isBase64Encoded` is `true` in the event, you must decode before HMAC validation.
**Why it happens:** Lambda Function URL follows API Gateway payload format v2, which base64-encodes binary content types.
**How to avoid:** Check `event.get('isBase64Encoded', False)`. If true, decode with `base64.b64decode(event['body'])`. GitHub webhooks send `application/json`, so this should normally be false, but handle it defensively.
**Warning signs:** HMAC validation fails on all webhooks despite correct secret. The `body` looks like a base64 string.

### Pitfall 2: GitHub Webhook Delivery Duplicates with New IDs
**What goes wrong:** GitHub can re-queue the same event with a NEW `X-GitHub-Delivery` ID during infrastructure issues. Dedup on delivery ID alone misses these.
**Why it happens:** `X-GitHub-Delivery` is unique per delivery attempt, not per logical event. Re-queued events get new delivery IDs.
**How to avoid:** Dual-key dedup: check delivery ID (catches retries) AND event composite key like `push#{repo}#{after_sha}` (catches re-queued events).
**Warning signs:** Multiple DynamoDB records for the same commit SHA with different delivery IDs. Multiple workflow runs triggered for the same commit.

### Pitfall 3: JWT Clock Skew at Token Boundaries
**What goes wrong:** Lambda execution environments can have clocks that drift. JWTs generated with `iat = now` and `exp = now + 600` fail intermittently when the Lambda clock is ahead of GitHub's clock.
**Why it happens:** GitHub validates JWT timestamps against its own clock. Even small clock differences cause 401 at boundary.
**How to avoid:** Always backdate `iat` by 60 seconds: `iat = now - 60`. Set `exp = now + 540` (9 minutes, buffer before 10-minute max). Generate fresh JWT per webhook cycle -- do not cache.
**Warning signs:** Sporadic 401 errors on GitHub API calls. Pattern of failures clustered around token expiry boundaries.

### Pitfall 4: DynamoDB ConditionalCheckFailedException Handling
**What goes wrong:** Developers treat `ConditionalCheckFailedException` as an error, log at ERROR level, or let it propagate as unhandled. This causes Lambda to return 500, which causes GitHub to retry, which creates more duplicates.
**Why it happens:** The exception name sounds like an error, but it is the expected signal for "item already exists" in conditional writes.
**How to avoid:** Catch `ConditionalCheckFailedException` explicitly. Log at DEBUG/INFO. Return 200 to GitHub. This is the happy path for duplicate deliveries.
**Warning signs:** ERROR-level logs for every duplicate webhook. GitHub retrying deliveries in a loop.

### Pitfall 5: Lambda Function URL Header Case Sensitivity
**What goes wrong:** Lambda Function URL event headers may not be consistently lowercased. Code that checks for `x-hub-signature-256` fails when the header arrives as `X-Hub-Signature-256`.
**Why it happens:** Lambda Function URL follows payload format v2 which presents headers as-is from the request. GitHub sends headers with mixed case.
**How to avoid:** Normalize all headers to lowercase immediately: `headers = {k.lower(): v for k, v in event.get("headers", {}).items()}`. Then access with lowercase keys.
**Warning signs:** Signature validation always fails. Headers appear to be missing when they're actually present with different casing.

### Pitfall 6: uv Workspace requires-python Intersection
**What goes wrong:** uv enforces a single `requires-python` across the entire workspace by taking the intersection of all members' constraints. If one member specifies `>=3.12` and another `>=3.14`, the workspace uses `>=3.14`.
**Why it happens:** Workspace members share a single lockfile and virtual environment.
**How to avoid:** Use the same `requires-python = ">=3.14"` in all member pyproject.toml files. Since the project constraint is Python 3.14, this is consistent.
**Warning signs:** Dependency resolution failures mentioning Python version incompatibility.

## Code Examples

Verified patterns from official sources:

### Lambda Function URL Event Handling
```python
# Source: docs.aws.amazon.com/lambda/latest/dg/urls-invocation.html
# Source: docs.aws.amazon.com/lambda/latest/dg/urls-webhook-tutorial.html

import json
import base64

def handler(event: dict, context) -> dict:
    # Extract body -- handle possible base64 encoding
    body = event.get("body", "")
    if event.get("isBase64Encoded", False):
        body = base64.b64decode(body).decode("utf-8")

    # Normalize headers to lowercase
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}

    # Validate HMAC-SHA256 signature against raw body string
    signature = headers.get("x-hub-signature-256", "")
    # ... verify_signature(body, signature, secret) ...

    # Parse JSON AFTER signature validation
    payload = json.loads(body)

    # Response format
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": "ok"}),
    }
```

### DynamoDB Table Creation for Testing (moto v5)
```python
# Source: docs.getmoto.org/en/latest/docs/getting_started.html
import pytest
import boto3
from moto import mock_aws

@pytest.fixture
def dynamodb_table():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName="ferry-state",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
        )
        # Enable TTL (moto supports this)
        client.update_time_to_live(
            TableName="ferry-state",
            TimeToLiveSpecification={
                "Enabled": True,
                "AttributeName": "expires_at",
            },
        )
        yield client

def test_dedup_first_delivery(dynamodb_table):
    """First delivery should be recorded successfully."""
    from ferry_backend.webhook.dedup import is_duplicate
    result = is_duplicate("delivery-123", {"after": "abc123"}, "ferry-state")
    assert result is False  # New, not duplicate

def test_dedup_duplicate_delivery(dynamodb_table):
    """Second delivery with same ID should be flagged as duplicate."""
    from ferry_backend.webhook.dedup import is_duplicate
    is_duplicate("delivery-123", {"after": "abc123"}, "ferry-state")
    result = is_duplicate("delivery-123", {"after": "abc123"}, "ferry-state")
    assert result is True  # Duplicate
```

### pytest-httpx for GitHub API Mocking
```python
# Source: colin-b.github.io/pytest_httpx/
import httpx
import pytest

def test_get_installation_token(httpx_mock):
    """Test exchanging JWT for installation token."""
    httpx_mock.add_response(
        method="POST",
        url="https://api.github.com/app/installations/12345/access_tokens",
        json={"token": "ghs_test_token_abc123", "expires_at": "2026-02-22T12:00:00Z"},
        status_code=201,
    )
    with httpx.Client() as client:
        from ferry_backend.auth.tokens import get_installation_token
        token = get_installation_token(client, "fake-jwt", 12345)
        assert token == "ghs_test_token_abc123"
```

### structlog Configuration for Lambda
```python
# Source: structlog docs + AWS Lambda JSON logging docs
import structlog

def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for AWS Lambda JSON output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| moto `@mock_dynamodb` (service-specific) | moto `@mock_aws` (unified decorator) | moto v5 (2024) | Single decorator for all AWS services. Old decorators still work but deprecated. |
| Pydantic v1 `schema_extra` | Pydantic v2 `model_config` + `json_schema_extra` | Pydantic 2.0 (2023) | Complete rewrite of configuration API. v2 is faster and more Pythonic. |
| PyJWT with `iss` = App ID (integer) | PyJWT with `iss` = Client ID (string) | GitHub 2024 | GitHub now accepts both App ID and Client ID as JWT issuer. Client ID is recommended for new apps. |
| Lambda API Gateway v1 payload | Lambda Function URL (payload format v2) | AWS 2022 | Function URL is free, simpler to configure for single-endpoint webhooks. Same event format as API Gateway v2. |
| `pip install` + `requirements.txt` | `uv` workspace + `pyproject.toml` | uv 0.4+ (2024) | Faster resolution, workspace support, lockfile. Standard `pyproject.toml` configuration. |

**Deprecated/outdated:**
- `moto.mock_dynamodb2`: Use `moto.mock_aws` instead
- `jwt.encode()` returning bytes: PyJWT 2.0+ returns strings
- GitHub `X-Hub-Signature` (SHA-1): Use `X-Hub-Signature-256` (SHA-256) instead

## Open Questions

1. **Python 3.14 Lambda Runtime Availability**
   - What we know: AWS Lambda supports Python 3.12 and 3.13 as of early 2025. Python 3.14 was released in Oct 2025.
   - What's unclear: Whether `python3.14` is available as a managed Lambda runtime, or if a container-based Lambda (Docker image) is required.
   - Recommendation: Check AWS Lambda runtimes page before implementation. If not available, use container-based Lambda deployment with Python 3.14 base image. This aligns with SAM template configuration.

2. **GitHub App `iss` Claim: App ID vs Client ID**
   - What we know: GitHub documentation now recommends using Client ID as the `iss` claim. Older docs used App ID (integer). Both currently work.
   - What's unclear: Whether App ID will be deprecated as a valid `iss` value.
   - Recommendation: Use Client ID (string) for new apps. Store as `FERRY_APP_ID` environment variable. This is forward-compatible.

3. **DynamoDB Single-Table vs Separate Tables**
   - What we know: Phase 1 only needs dedup. Future phases may need deployment tracking, config cache.
   - What's unclear: Whether future access patterns will conflict with the dedup table design.
   - Recommendation: Use single-table design with `pk`/`sk` pattern. Prefix `pk` values: `DELIVERY#`, `EVENT#`. This is extensible -- future patterns add new prefixes without schema changes.

4. **pytest-httpx Compatibility with httpx Version**
   - What we know: pytest-httpx is tightly coupled to httpx versions. Version mismatches cause import errors.
   - What's unclear: Exact compatible version pair for latest releases.
   - Recommendation: Let uv resolve compatible versions. Pin `httpx>=0.27` and `pytest-httpx>=0.30` and verify they co-resolve in the lockfile.

## Sources

### Primary (HIGH confidence)
- [AWS Lambda Function URL Invocation](https://docs.aws.amazon.com/lambda/latest/dg/urls-invocation.html) - event format, body encoding, response format
- [AWS Lambda Function URL Webhook Tutorial](https://docs.aws.amazon.com/lambda/latest/dg/urls-webhook-tutorial.html) - complete webhook handler example with HMAC
- [GitHub Webhook Validation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries) - HMAC-SHA256 signature verification, Python example
- [GitHub App JWT Generation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app) - JWT claims, RS256, Python code example
- [uv Workspaces Documentation](https://docs.astral.sh/uv/concepts/projects/workspaces/) - workspace configuration, member dependencies, lockfile behavior
- [Pydantic v2 Unions Documentation](https://docs.pydantic.dev/latest/concepts/unions/) - discriminated unions, Field(discriminator=...), Literal types
- [DynamoDB PutItem API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_PutItem.html) - conditional expressions, attribute_not_exists
- [moto v5 Getting Started](https://docs.getmoto.org/en/latest/docs/getting_started.html) - mock_aws decorator, DynamoDB mocking

### Secondary (MEDIUM confidence)
- [pytest-httpx Documentation](https://colin-b.github.io/pytest_httpx/) - httpx mocking patterns, add_response API
- [structlog for AWS Lambda CloudWatch](https://dltj.org/article/python-structlog-for-aws-lambda-cloudwatch/) - structlog configuration for Lambda JSON output
- [pydantic-settings Documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) - BaseSettings, env_prefix configuration

### Tertiary (LOW confidence)
- [GitHub Push Event Payload Example](https://gist.github.com/walkingtospace/0dcfe43116ca6481f129cdaa0e112dc4) - community gist, push event structure (validate against official docs when implementing)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries are mature, well-documented, and widely used. Version numbers verified against official sources.
- Architecture: HIGH - Lambda Function URL + DynamoDB + PyJWT is a well-established pattern for GitHub App backends. Event format verified against AWS official docs.
- Pitfalls: HIGH - Documented pitfalls from official GitHub and AWS documentation. Dual-key dedup is MEDIUM (based on observed GitHub behavior during outages, not officially documented).
- uv workspace: HIGH - Configuration verified against official uv docs. Workspace pattern is stable and well-documented.

**Research date:** 2026-02-22
**Valid until:** 2026-03-22 (stable domain, 30-day validity)
