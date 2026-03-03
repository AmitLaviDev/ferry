# Phase 14: Self-Deploy + Manual Setup - Research

**Researched:** 2026-03-03
**Domain:** Docker containerization, GHA CI/CD, Secrets Manager integration, GitHub App registration
**Confidence:** HIGH

## Summary

Phase 14 bridges the gap between Terraform-provisioned infrastructure (Phases 11-13) and a running Ferry backend. It requires four code artifacts (backend Dockerfile, GHA workflow, settings.py modification, setup runbook) plus two manual actions (GitHub App registration, secrets population). The technical domain is well-understood -- Docker multi-stage builds for Python monorepos, GitHub Actions OIDC-authenticated ECR/Lambda deploys, and boto3 Secrets Manager resolution are all mature patterns with extensive documentation.

The main complexity is the backend Dockerfile, which must install two workspace packages (`ferry-utils` and `ferry-backend`) from the monorepo using `uv export`. The official uv documentation provides a verified pattern for this: export third-party dependencies separately from workspace members for optimal Docker layer caching.

**Primary recommendation:** Use `uv export` with `--no-emit-workspace` for the dependency layer, then a second `uv export` (without the flag) to include workspace members. Build from repo root context. Use raw `aws lambda update-function-code` CLI instead of third-party deploy actions -- simpler, one fewer dependency, and the IAM permissions already scope to exactly that API call.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Triggers on **every push to main** -- no path filtering. Simple and predictable.
- **Fail loudly, no rollback** -- workflow fails with red X, Lambda keeps running previous image, user investigates manually.
- **Run Ferry's own pytest suite before building** -- test job runs first, build+deploy job depends on it passing.
- **Separate ARN env vars** -- Lambda env vars like `FERRY_APP_ID_SECRET`, `FERRY_PRIVATE_KEY_SECRET`, `FERRY_WEBHOOK_SECRET_SECRET` hold Secrets Manager secret names. At cold start, settings.py resolves names to actual values and populates the corresponding fields.
- **Only sensitive values from Secrets Manager** -- `app_id`, `private_key`, `webhook_secret` resolved from SM. Non-secrets (`table_name`, `installation_id`, `log_level`) stay as plain `FERRY_*` env vars.
- **Individual secrets** -- Three separate secrets already created by Phase 12: `ferry/github-app/app-id`, `ferry/github-app/private-key`, `ferry/github-app/webhook-secret`. One SM API call per secret at cold start.
- **Local dev uses plain env vars** -- If `FERRY_*_SECRET` vars are absent, settings.py uses `FERRY_*` values directly. SM resolution only activates when secret name vars are present. No LocalStack needed.
- Runbook lives at **`docs/setup-runbook.md`**
- Audience: **us / future contributors** -- assumes AWS access and Terraform familiarity, focuses on Ferry-specific steps and order.
- Scope: **Phase 14 manual steps only** -- GitHub App registration, secrets population, triggering first deploy. Does not cover Phases 11-13 apply order.
- **Includes verification steps** at the end -- curl the Function URL, send a test webhook from GitHub App settings, check CloudWatch logs.

### Claude's Discretion
- Backend Dockerfile structure (multi-stage, base image, layer caching)
- GHA workflow job structure and step ordering
- How settings.py internally organizes the SM resolution (validator, factory, etc.)
- Exact runbook formatting and section headers

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DEPLOY-01 | Backend Dockerfile builds ferry-utils + ferry-backend from repo root context | uv export workspace pattern, multi-stage Docker build, Python 3.14 Lambda base image |
| DEPLOY-02 | Self-deploy GHA workflow builds, pushes to ECR, and updates Lambda on push to main | OIDC auth, ECR login, docker build-push, aws lambda update-function-code CLI |
| DEPLOY-03 | settings.py modified to load secrets from Secrets Manager at cold start | boto3 get_secret_value by secret name, pydantic-settings model_post_init pattern |
| SETUP-01 | GitHub App registered with Function URL as webhook endpoint | GitHub App registration guide, required permissions, webhook secret |
| SETUP-02 | Secrets Manager values populated via CLI after GitHub App registration | aws secretsmanager put-secret-value command syntax |
| SETUP-03 | Setup runbook documented in repo (apply order + manual steps) | Verification steps: curl, test webhook delivery, CloudWatch logs |
</phase_requirements>

## Standard Stack

### Core
| Library/Tool | Version | Purpose | Why Standard |
|-------------|---------|---------|--------------|
| `public.ecr.aws/lambda/python` | `3.14` | Lambda base image | Official AWS Lambda Python runtime, GA since Nov 2025 |
| `ghcr.io/astral-sh/uv` | `0.10.x` | Build-time dependency resolution | Official uv Docker image, used for `uv export` in Dockerfile |
| `aws-actions/configure-aws-credentials` | `v6` | OIDC authentication in GHA | Official AWS action, v6 is latest (Feb 2026) |
| `aws-actions/amazon-ecr-login` | `v2` | ECR Docker login in GHA | Official AWS action, v2 is current stable |
| `docker/setup-buildx-action` | `v3` | Docker Buildx setup in GHA | Required for efficient builds |
| `docker/build-push-action` | `v6` | Docker build and push in GHA | Current major version, supports cache export |
| `boto3` | `>=1.34` | Secrets Manager client | Already a dependency of ferry-backend |

### Supporting
| Library/Tool | Version | Purpose | When to Use |
|-------------|---------|---------|-------------|
| `actions/checkout` | `v4` | Repository checkout in GHA | Every workflow |
| `actions/setup-python` | `v5` | Python setup for test job | Test job before build |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `docker/build-push-action` | Raw `docker build` + `docker push` | build-push-action adds cache management; raw commands are simpler but no GHA cache integration |
| `aws lambda update-function-code` CLI | `aws-actions/aws-lambda-deploy@v1` | CLI is simpler, one less dependency, already have exact IAM permissions for it |
| `pydantic-settings-aws` extension | Manual boto3 in `model_post_init` | Extension adds dependency; manual approach is ~15 lines, fully transparent |

## Architecture Patterns

### Recommended Project Structure (new files)
```
ferry/
├── Dockerfile                    # NEW: Backend Lambda Dockerfile (repo root)
├── .github/
│   └── workflows/
│       └── self-deploy.yml       # NEW: Self-deploy workflow
├── backend/
│   └── src/
│       └── ferry_backend/
│           └── settings.py       # MODIFIED: Add SM resolution
├── docs/
│   └── setup-runbook.md          # NEW: Setup runbook
```

### Pattern 1: Multi-stage Docker Build with uv Workspace
**What:** Two-stage Dockerfile that separates third-party dependency installation from workspace member installation for optimal layer caching.
**When to use:** Any Lambda container image built from a uv workspace monorepo.

```dockerfile
# syntax=docker/dockerfile:1

# --- Stage 1: Build dependencies ---
FROM ghcr.io/astral-sh/uv:0.10 AS uv
FROM public.ecr.aws/lambda/python:3.14 AS builder

COPY --from=uv /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1
ENV UV_NO_INSTALLER_METADATA=1

WORKDIR /build

# Copy workspace root files for dependency resolution
COPY pyproject.toml uv.lock /build/
COPY utils/pyproject.toml /build/utils/
COPY backend/pyproject.toml /build/backend/

# Install third-party dependencies (cached separately from workspace changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-emit-workspace --no-dev --package ferry-backend \
      -o requirements.txt && \
    uv pip install --no-cache-dir -r requirements.txt \
      --target /build/deps

# Copy workspace source and install workspace members
COPY utils/src /build/utils/src
COPY backend/src /build/backend/src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-editable --package ferry-backend \
      -o requirements-all.txt && \
    uv pip install --no-cache-dir -r requirements-all.txt \
      --target /build/all

# --- Stage 2: Runtime ---
FROM public.ecr.aws/lambda/python:3.14

# Copy all dependencies (third-party + workspace members)
COPY --from=builder /build/all ${LAMBDA_TASK_ROOT}

CMD ["ferry_backend.webhook.handler.handler"]
```

**Key details:**
- Build context is the repo root (`docker build -f Dockerfile .`)
- `--no-emit-workspace` in first RUN = only third-party deps (cache-friendly)
- Second RUN includes workspace members after source copy
- `UV_COMPILE_BYTECODE=1` improves Lambda cold start
- Handler path is `ferry_backend.webhook.handler.handler` (module.submodule.function)
- Source: [uv AWS Lambda guide](https://docs.astral.sh/uv/guides/integration/aws-lambda/)

### Pattern 2: OIDC-Authenticated ECR Push + Lambda Update
**What:** GHA workflow authenticates via OIDC, builds and pushes Docker image to ECR, then updates Lambda function code using AWS CLI.
**When to use:** Self-deploy pattern where GHA owns the deployed code, Terraform owns the infrastructure.

```yaml
permissions:
  id-token: write
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - run: pip install uv && uv sync --frozen
      - run: uv run pytest

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v6
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - uses: aws-actions/amazon-ecr-login@v2
        id: ecr-login

      - uses: docker/setup-buildx-action@v3

      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.ecr-login.outputs.registry }}/lambda-ferry-backend:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - run: |
          aws lambda update-function-code \
            --function-name ferry-backend \
            --image-uri "$IMAGE_URI" \
            --no-cli-pager
          aws lambda wait function-updated-v2 \
            --function-name ferry-backend
        env:
          IMAGE_URI: ${{ steps.ecr-login.outputs.registry }}/lambda-ferry-backend:${{ github.sha }}
```

**Key details:**
- `function-updated-v2` waiter polls every 1s (vs 5s for original `function-updated`)
- `--no-cli-pager` prevents interactive pager from blocking CI
- Image tagged with `${{ github.sha }}` for traceability
- Source: [AWS configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials), [AWS CLI update-function-code](https://docs.aws.amazon.com/cli/latest/reference/lambda/update-function-code.html)

### Pattern 3: Secrets Manager Resolution in Pydantic Settings
**What:** At Lambda cold start, detect `FERRY_*_SECRET` env vars containing Secrets Manager secret names, resolve them to actual values, and populate the corresponding settings fields.
**When to use:** When sensitive config must come from Secrets Manager but local dev should work with plain env vars.

```python
import os
import boto3
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FERRY_")

    app_id: str = ""
    private_key: str = ""
    webhook_secret: str = ""
    table_name: str
    installation_id: int
    log_level: str = "INFO"

    # Secret name env vars (optional -- absent in local dev)
    app_id_secret: str = ""
    private_key_secret: str = ""
    webhook_secret_secret: str = ""

    @model_validator(mode="after")
    def resolve_secrets(self) -> "Settings":
        """Resolve Secrets Manager values when secret name env vars are present."""
        secret_map = {
            "app_id_secret": "app_id",
            "private_key_secret": "private_key",
            "webhook_secret_secret": "webhook_secret",
        }
        names_to_resolve = {
            field: getattr(self, source)
            for source, field in secret_map.items()
            if getattr(self, source)
        }
        if not names_to_resolve:
            return self
        client = boto3.client("secretsmanager")
        for field, secret_name in names_to_resolve.items():
            resp = client.get_secret_value(SecretId=secret_name)
            object.__setattr__(self, field, resp["SecretString"])
        return self
```

**Key details:**
- `model_validator(mode="after")` runs after all field validation
- `object.__setattr__` bypasses Pydantic's frozen model protection
- If `FERRY_APP_ID_SECRET` is empty/absent, `app_id_secret` defaults to `""` and resolution is skipped
- Local dev sets `FERRY_APP_ID`, `FERRY_PRIVATE_KEY`, `FERRY_WEBHOOK_SECRET` directly
- Lambda sets `FERRY_APP_ID_SECRET=ferry/github-app/app-id` etc. (from Terraform)
- `get_secret_value(SecretId=name)` accepts both secret name and ARN
- Source: [boto3 get_secret_value](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/secretsmanager/client/get_secret_value.html)

### Anti-Patterns to Avoid
- **Storing secrets in Terraform state:** Never use `aws_secretsmanager_secret_version` in Terraform for actual secret values. Populate via CLI only.
- **Using `COPY . .` in Dockerfile:** Copies entire repo including tests, docs, IaC. Use explicit COPY directives for only what's needed.
- **Hardcoding account IDs in workflow:** Use `aws-actions/amazon-ecr-login` output for the registry URL.
- **Skipping the waiter after update-function-code:** Lambda update is async; without `wait function-updated-v2`, the workflow may report success before the update completes (or fails).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Docker layer caching in GHA | Manual cache volume management | `docker/build-push-action` with `cache-from/to: type=gha` | GHA cache backend handles eviction, cross-run persistence |
| ECR authentication | Manual `aws ecr get-login-password` piping | `aws-actions/amazon-ecr-login@v2` | Handles token refresh, outputs registry URL |
| OIDC token exchange | Manual STS calls | `aws-actions/configure-aws-credentials@v6` | Handles OIDC token fetch, session management, credential cleanup |
| Python dependency export for Docker | `pip freeze` or manual requirements.txt | `uv export --frozen` | Respects workspace lockfile, handles workspace members correctly |

**Key insight:** The GHA actions ecosystem handles the plumbing (auth, caching, registry login) so the workflow focuses on the two unique steps: build the image, update the Lambda.

## Common Pitfalls

### Pitfall 1: Lambda Architecture Mismatch
**What goes wrong:** Dockerfile builds for x86_64 but Lambda is configured for arm64 (or vice versa), causing "exec format error" at runtime.
**Why it happens:** Lambda defaults to x86_64 when `architectures` is not set in Terraform. Docker builds for the host architecture by default.
**How to avoid:** Current Terraform does NOT set `architectures`, so Lambda runs x86_64. The Dockerfile uses `public.ecr.aws/lambda/python:3.14` which is x86_64 by default on GHA ubuntu runners. These match. Do NOT add `--platform linux/arm64` without also updating Terraform.
**Warning signs:** Lambda invocation returns "Runtime.ExitError" or "exec format error" in CloudWatch logs.

### Pitfall 2: Secrets Manager Cold Start Latency
**What goes wrong:** Three sequential `get_secret_value` calls add 100-300ms to cold start.
**Why it happens:** Each SM API call is a separate HTTPS request.
**How to avoid:** Accept the latency for v1 -- it only affects cold starts. Could batch-optimize later with `batch_get_secret_value` if needed. The Lambda already has 30s timeout.
**Warning signs:** Cold start duration > 5s in CloudWatch metrics. (Not expected for 3 calls.)

### Pitfall 3: Docker Build Context Too Large
**What goes wrong:** `docker build .` from repo root sends entire repo (including `.git`, `.venv`, IaC) as build context, making builds slow.
**Why it happens:** No `.dockerignore` file.
**How to avoid:** Create a `.dockerignore` at repo root excluding `.git/`, `.venv/`, `iac/`, `tests/`, `docs/`, `.planning/`, `action/`, `prd/`, `research/`, `scripts/`.
**Warning signs:** Build step takes > 30s just to "Sending build context to Docker daemon".

### Pitfall 4: GHA Workflow Permissions
**What goes wrong:** OIDC token request fails with "Error: Credentials could not be loaded".
**Why it happens:** Missing `permissions: id-token: write` in the workflow or the deploy job.
**How to avoid:** Set `id-token: write` at either the workflow level or the deploy job level. Also need `contents: read` for checkout.
**Warning signs:** 403 error from STS, or "Unable to get ACTIONS_ID_TOKEN_REQUEST_URL" in GHA logs.

### Pitfall 5: Terraform Env Var Naming vs Settings Field Naming
**What goes wrong:** settings.py can't find the secret name env vars because the pydantic-settings prefix doesn't match.
**Why it happens:** Terraform sets `FERRY_APP_ID_SECRET` but pydantic-settings with `env_prefix="FERRY_"` maps it to field `app_id_secret`. The naming must be consistent.
**How to avoid:** Verify the Terraform env var names (`FERRY_APP_ID_SECRET`, `FERRY_PRIVATE_KEY_SECRET`, `FERRY_WEBHOOK_SECRET_SECRET`) map to pydantic fields (`app_id_secret`, `private_key_secret`, `webhook_secret_secret`). The double "SECRET" in `FERRY_WEBHOOK_SECRET_SECRET` is intentional -- first "SECRET" is part of the field name (webhook_secret), second is the _SECRET suffix.
**Warning signs:** `ValidationError` on Lambda startup, missing field values.

### Pitfall 6: uv export Without --frozen
**What goes wrong:** `uv export` without `--frozen` may attempt to resolve dependencies, failing if network is unavailable or lock is stale.
**Why it happens:** Default behavior re-resolves.
**How to avoid:** Always use `--frozen` to use the exact lockfile versions.
**Warning signs:** Build fails with "Resolution failed" or takes unexpectedly long.

## Code Examples

### Backend Dockerfile (.dockerignore)
```
# .dockerignore at repo root
.git/
.venv/
.planning/
.claude/
.agents/
.pytest_cache/
.mypy_cache/
.ruff_cache/
iac/
tests/
docs/
prd/
research/
scripts/
action/
*.md
*.egg-info/
__pycache__/
```

### AWS CLI: Populate Secrets Manager Values
```bash
# After GitHub App registration, populate the three secrets:
aws secretsmanager put-secret-value \
  --secret-id ferry/github-app/app-id \
  --secret-string "123456"

aws secretsmanager put-secret-value \
  --secret-id ferry/github-app/private-key \
  --secret-string "$(cat ferry-app.private-key.pem)"

aws secretsmanager put-secret-value \
  --secret-id ferry/github-app/webhook-secret \
  --secret-string "$(openssl rand -hex 20)"
```

### GitHub App Registration: Required Permissions
The Ferry backend needs these GitHub App permissions:
- **Repository permissions:**
  - Contents: Read (fetch ferry.yaml, compare commits)
  - Pull requests: Read & Write (post comments)
  - Checks: Read & Write (create check runs)
  - Actions: Write (trigger workflow_dispatch)
  - Metadata: Read (always required)
- **Subscribe to events:**
  - Push

### Verification: Test Webhook Delivery
```bash
# 1. Curl the Function URL to verify Lambda is running
curl -s https://<function-url-id>.lambda-url.us-east-1.on.aws/ | jq .

# 2. Send test webhook from GitHub App settings page:
#    Settings > Developer settings > GitHub Apps > Ferry > Advanced > Recent Deliveries
#    Click "Redeliver" on any delivery to test

# 3. Check CloudWatch logs
aws logs tail /aws/lambda/ferry-backend --since 5m --follow
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pip install` in Dockerfile | `uv export` + `uv pip install` | 2024-2025 | 10-100x faster dependency resolution, lockfile-based |
| `aws-actions/configure-aws-credentials@v4` | `@v6` | Feb 2026 | Node 24, transitive tag keys support |
| `aws lambda wait function-updated` (5s poll) | `function-updated-v2` (1s poll) | 2024 | Faster CI feedback, 300 retries vs 60 |
| `docker/build-push-action@v5` | `@v6` | 2025 | Latest buildx features, improved cache |
| Static AWS credentials in GHA | OIDC via `configure-aws-credentials` | 2022+ | No long-lived secrets, automatic rotation |

## Open Questions

1. **Lambda architecture: x86_64 vs arm64**
   - What we know: Current Terraform does not set `architectures`, defaulting to x86_64. Python 3.14 GA image available for both.
   - What's unclear: Whether the project intends to use arm64 (mentioned in STATE.md blockers).
   - Recommendation: Stick with x86_64 for now (matches current TF). Switching to arm64 would require: (1) adding `architectures = ["arm64"]` to lambdas.tf, (2) using `3.14-arm64` base image tag or `--platform linux/arm64` in Docker build. This can be done later without workflow changes.

2. **GHA cache strategy for Docker builds**
   - What we know: `docker/build-push-action` supports `cache-from/to: type=gha` using GitHub Actions cache backend.
   - What's unclear: Whether GHA cache quota (10GB per repo) will be sufficient long-term.
   - Recommendation: Start with `type=gha` cache. Monitor cache hit rates. Fallback: ECR registry cache (`type=registry`).

3. **FERRY_INSTALLATION_ID value**
   - What we know: Phase 13 set it to placeholder `"0"`. The actual value is obtained after installing the GitHub App on a repository.
   - What's unclear: When exactly this gets set -- it requires GitHub App installation on a repo, which happens after registration.
   - Recommendation: The runbook should include updating the Terraform variable and running `terraform apply` after the App is installed on a repo, OR updating the Lambda env var directly via CLI. The latter is simpler for initial setup.

## Sources

### Primary (HIGH confidence)
- [uv AWS Lambda integration guide](https://docs.astral.sh/uv/guides/integration/aws-lambda/) - Dockerfile patterns for workspace builds
- [aws-actions/configure-aws-credentials v6](https://github.com/aws-actions/configure-aws-credentials) - OIDC authentication
- [aws-actions/amazon-ecr-login v2](https://github.com/aws-actions/amazon-ecr-login) - ECR Docker login
- [boto3 get_secret_value](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/secretsmanager/client/get_secret_value.html) - SecretId accepts name or ARN
- [AWS CLI update-function-code](https://docs.aws.amazon.com/cli/latest/reference/lambda/update-function-code.html) - Lambda code update
- [AWS CLI wait function-updated-v2](https://docs.aws.amazon.com/cli/latest/reference/lambda/wait/function-updated-v2.html) - 1s polling waiter

### Secondary (MEDIUM confidence)
- [Managing Python Monorepos with uv Workspaces and AWS Lambda](https://dev.to/nicocrm/managing-python-monorepos-with-uv-workspaces-and-aws-lambda-5a2i) - Real-world workspace pattern
- [docker/build-push-action v6](https://github.com/docker/build-push-action) - GHA cache integration
- [GitHub App webhooks docs](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/using-webhooks-with-github-apps) - Webhook setup

### Tertiary (LOW confidence)
- Python 3.14 GA status from [GitHub issue #327](https://github.com/aws/aws-lambda-base-images/issues/327) - Community confirmation, should verify tag exists before first build

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All tools are official AWS/Docker actions with stable major versions; uv Lambda pattern is officially documented
- Architecture: HIGH - Patterns are well-established (OIDC deploy, Docker multi-stage, SM resolution); existing Terraform infrastructure matches
- Pitfalls: HIGH - Based on actual Terraform code inspection (env var naming, architecture defaults) and official documentation

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (stable domain, action versions may bump minor)
