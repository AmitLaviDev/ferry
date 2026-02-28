# Phase 3 Research: Build and Lambda Deploy

**Researched:** 2026-02-25
**Phase Goal:** The Ferry Action receives a dispatch, authenticates to AWS via OIDC, builds Lambda containers with the Magic Dockerfile, pushes to ECR, and deploys Lambda functions with version and alias management

## 1. Composite Action Architecture

### Structure Decision: Two Composite Actions

The CONTEXT.md specifies a `ferry-action/setup` step (parses dispatch payload, outputs matrix JSON) and the main `ferry-action` (build/deploy). Both live in the `action/` directory.

```
action/
  setup/
    action.yml          # Composite: parse payload → output matrix JSON
  action.yml            # Composite: build + deploy one Lambda resource
  src/ferry_action/
    __init__.py
    parse_payload.py    # Parse + validate dispatch payload
    build.py            # Docker build + ECR push
    deploy.py           # Lambda update + version + alias
    auth.py             # OIDC helpers (if needed beyond configure-aws-credentials)
    digest.py           # Digest comparison for skip logic
    logging.py          # GHA logging helpers (groups, masks, summaries)
```

### Composite Action Mechanics

- `action.yml` uses `runs: using: composite` with `steps:`
- Python scripts invoked via `shell: bash` calling `python ${{ github.action_path }}/src/ferry_action/script.py`
- Inputs passed as environment variables (composite actions don't auto-expose inputs as env vars)
- Outputs set via `echo "name=value" >> $GITHUB_OUTPUT`
- `${{ github.action_path }}` resolves to the action's checkout location

### User Workflow Template

The user creates `ferry-lambdas.yml` in their repo:

```yaml
name: Ferry Lambda Deploy
on:
  workflow_dispatch:
    inputs:
      payload:
        required: true
        type: string

permissions:
  id-token: write    # Required for OIDC
  contents: read

jobs:
  setup:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.parse.outputs.matrix }}
    steps:
      - uses: ferry-action/setup@v1
        id: parse
        with:
          payload: ${{ github.event.inputs.payload }}

  deploy:
    needs: setup
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false
    steps:
      - uses: ferry-action@v1
        with:
          resource-name: ${{ matrix.name }}
          source-dir: ${{ matrix.source }}
          ecr-repo: ${{ matrix.ecr }}
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}
          trigger-sha: ${{ matrix.trigger_sha }}
          deployment-tag: ${{ matrix.deployment_tag }}
```

### Setup Action Output

The setup action parses the dispatch payload and outputs a matrix JSON:

```json
{
  "include": [
    {"name": "order-processor", "source": "services/order-processor", "ecr": "ferry/order-processor", "trigger_sha": "abc1234...", "deployment_tag": "pr-42"}
  ]
}
```

This fans out one job per Lambda resource for parallel builds.

## 2. AWS OIDC Authentication

### Approach: Use `aws-actions/configure-aws-credentials`

The standard approach is to use `aws-actions/configure-aws-credentials@v4` as a step within the composite action. The user provides their IAM role ARN as an input.

**Key requirements:**
- User's workflow must have `permissions: id-token: write`
- User creates an IAM OIDC provider for `token.actions.githubusercontent.com`
- User creates an IAM role with trust policy scoped to their repo/branch
- The action uses `role-to-assume` input with the user-provided ARN

**In composite action steps:**
```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ inputs.aws-role-arn }}
    aws-region: ${{ inputs.aws-region }}
```

**Important:** Composite actions can use other actions in their steps. This is the cleanest approach — no custom OIDC token exchange code needed.

### Region Handling

Default to `us-east-1`. User can override via `aws-region` input.

## 3. Magic Dockerfile

### The Pattern

One generic Dockerfile that builds ANY Lambda function. From PROJECT.md reference implementation:

```dockerfile
# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12
FROM public.ecr.aws/lambda/python:${PYTHON_VERSION}

# Optional system packages (glob trick: file[t] matches file if exists, no-op otherwise)
COPY system-requirements.tx[t] /tmp/
RUN if [ -f /tmp/system-requirements.txt ]; then \
      dnf install -y $(cat /tmp/system-requirements.txt) && dnf clean all; \
    fi

# Optional system config script
COPY system-config.s[h] /tmp/
RUN if [ -f /tmp/system-config.sh ]; then \
      chmod +x /tmp/system-config.sh && /tmp/system-config.sh; \
    fi

# Install Python dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN --mount=type=secret,id=github_token \
    if [ -f /run/secrets/github_token ]; then \
      export GIT_TOKEN=$(cat /run/secrets/github_token) && \
      git config --global url."https://${GIT_TOKEN}@github.com/".insteadOf "https://github.com/" ; \
    fi && \
    pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy entire source directory (user's directory = their container)
COPY . ${LAMBDA_TASK_ROOT}/

CMD ["main.handler"]
```

### Research Flag Resolution: COPY Glob on BuildKit

**Finding:** The `COPY file[t] dest/` glob trick works on BuildKit (default since Docker 20.10+). GitHub Actions `ubuntu-latest` uses Docker 24+ with BuildKit enabled by default. This is safe.

The pattern `COPY system-requirements.tx[t] /tmp/` matches `system-requirements.txt` if it exists and is a no-op if it doesn't — BuildKit doesn't fail on empty glob matches.

### Research Flag Resolution: Python 3.14 Lambda Runtime

**Finding:** AWS announced Python 3.14 runtime support for Lambda (both managed and container images). The base image `public.ecr.aws/lambda/python:3.14` is available. Based on Amazon Linux 2023 minimal.

### Runtime Version from ferry.yaml

`LambdaConfig` already has `runtime: str = "python3.10"`. The Dockerfile uses `ARG PYTHON_VERSION` which maps to this field (strip the "python" prefix).

### Docker Build Invocation

```bash
docker build \
  --build-arg PYTHON_VERSION=${runtime_version} \
  --secret id=github_token,env=GITHUB_TOKEN \
  --tag ${ecr_uri}:${deployment_tag} \
  --file ${action_path}/Dockerfile \
  ${source_dir}
```

**Build context** is the source_dir. The Dockerfile lives in the action repo, referenced via `--file`.

## 4. ECR Push

### Flow

1. Authenticate to ECR: `aws ecr get-login-password | docker login --username AWS --password-stdin ${ecr_uri}`
2. Tag image: already tagged with `${ecr_uri}:${deployment_tag}` during build
3. Push: `docker push ${ecr_uri}:${deployment_tag}`
4. Capture digest from push output or `docker inspect --format='{{.RepoDigests}}' ${image}`

### ECR URI Construction

The user provides the ECR repo name in ferry.yaml (e.g., `ferry/order-processor`). The full URI is constructed:
```
${aws_account_id}.dkr.ecr.${aws_region}.amazonaws.com/${ecr_repo}
```

AWS account ID comes from the OIDC credentials (STS `get-caller-identity`).

### Tagging Strategy

From CONTEXT.md:
- Merge deploys: `pr-{pr_number}` tag
- The `deployment_tag` field in the dispatch payload already contains this

## 5. Lambda Deployment

### Sequence

1. **Update function code:** `lambda:UpdateFunctionCode` with the new image URI
2. **Wait for update:** Use `function_updated` waiter (polls every 5s, max 60 checks = 5 min timeout)
3. **Publish version:** `lambda:PublishVersion` creates an immutable snapshot
4. **Update alias:** `lambda:UpdateAlias` to point alias to new version

### boto3 Implementation

```python
lambda_client = boto3.client("lambda")

# 1. Update function code
lambda_client.update_function_code(
    FunctionName=function_name,
    ImageUri=f"{ecr_uri}:{deployment_tag}",
)

# 2. Wait for LastUpdateStatus: Successful
waiter = lambda_client.get_waiter("function_updated")
waiter.wait(FunctionName=function_name)

# 3. Publish version
version_resp = lambda_client.publish_version(
    FunctionName=function_name,
    Description=f"Deployed by Ferry: {deployment_tag}",
)
new_version = version_resp["Version"]

# 4. Update alias
lambda_client.update_alias(
    FunctionName=function_name,
    Name=alias_name,  # e.g., "live"
    FunctionVersion=new_version,
)
```

### Alias Naming

CONTEXT.md leaves this to Claude's discretion. Recommend `live` as the alias name — clear, short, not overloaded like "latest" or "current".

### function_name Resolution

`LambdaConfig.function_name` defaults to `name` (already implemented in schema.py). The dispatch payload sends `name`, so the action uses this directly as the Lambda function name.

## 6. Digest-Based Skip Logic

### Approach

Compare the digest of the just-pushed ECR image against the currently deployed Lambda image.

```python
# Get current Lambda image URI
func_resp = lambda_client.get_function(FunctionName=function_name)
current_image_uri = func_resp["Code"]["ImageUri"]

# Get digest of just-pushed image
# After docker push, capture digest: docker inspect --format='{{index .RepoDigests 0}}' IMAGE
# Or use ECR describe_images to get the digest for the tag

# Compare
if current_digest == new_digest:
    print(f"Skipping deploy for {function_name} — image unchanged")
    # Set output: skipped=true
    return
```

**When to check:** After ECR push, before Lambda update. This avoids unnecessary Lambda updates when the image content is identical (e.g., re-running a workflow without code changes).

**Implementation detail:** `docker push` returns the digest in its output. Alternatively, after push, call `ecr:BatchGetImage` with the tag to get the `imageDigest`. Then compare against the digest in the Lambda function's current `ImageUri` (which contains the digest after resolution).

**Simpler approach:** After pushing to ECR, get the pushed image digest. Then get the Lambda function's resolved image digest via `get_function()` → `Code.ResolvedImageUri` (contains `@sha256:...`). Compare the two sha256 values.

## 7. Build & Deploy Logging

### GHA Logging Patterns

From CONTEXT.md decisions:

**Collapsible groups for verbose output:**
```python
print(f"::group::Building {resource_name}")
# ... docker build output ...
print("::endgroup::")
```

**Masking sensitive values:**
```python
print(f"::add-mask::{aws_account_id}")
print(f"::add-mask::{role_arn}")
```

**Job summary (per-resource markdown):**
```python
with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
    f.write(f"## {resource_name}\n")
    f.write(f"| Field | Value |\n|---|---|\n")
    f.write(f"| ECR Tag | `{deployment_tag}` |\n")
    f.write(f"| Lambda Version | `{new_version}` |\n")
    f.write(f"| Status | Deployed |\n")
    f.write(f"| Duration | {duration}s |\n")
```

**Common failure hints:**
- Missing `main.py` → "Lambda handler not found. Ensure main.py exists in source_dir with a handler() function."
- Bad `requirements.txt` → "pip install failed. Check requirements.txt for syntax errors or unavailable packages."
- ECR auth failure → "ECR login failed. Verify the IAM role has ecr:GetAuthorizationToken permission."

## 8. Python Script Execution in Composite Action

### Dependency Challenge

The action Python scripts need `boto3`, `pydantic`, and `ferry-utils` (shared models). Two approaches:

**Option A: Install via uv in the action (recommended)**
```yaml
steps:
  - uses: astral-sh/setup-uv@v4
  - run: uv pip install --system ./action
    shell: bash
```

This installs `ferry-action` package and its dependencies (including `ferry-utils` from workspace). The action checkout includes the full repo.

**Option B: Vendored dependencies**
Bundle all deps in the action directory. Avoids install step but creates maintenance burden.

**Recommendation:** Option A. The install step takes ~5 seconds with uv, and keeps the action using the same package structure as the rest of the monorepo.

**Important consideration:** The composite action runs in the user's workflow. The action repo needs to be checked out for the Python scripts to be available. With `uses: owner/ferry@v1`, GitHub automatically checks out the action repo. The `${{ github.action_path }}` gives the path.

### Script Invocation Pattern

```yaml
- name: Build and deploy
  shell: bash
  env:
    INPUT_RESOURCE_NAME: ${{ inputs.resource-name }}
    INPUT_SOURCE_DIR: ${{ inputs.source-dir }}
    INPUT_ECR_REPO: ${{ inputs.ecr-repo }}
    INPUT_DEPLOYMENT_TAG: ${{ inputs.deployment-tag }}
    INPUT_TRIGGER_SHA: ${{ inputs.trigger-sha }}
  run: python ${{ github.action_path }}/src/ferry_action/main.py
```

## 9. Testing Strategy

### Unit Tests (pytest + moto)

- **parse_payload.py**: Test DispatchPayload parsing with valid/invalid inputs
- **build.py**: Test Docker command construction (don't actually build — mock subprocess)
- **deploy.py**: Test Lambda update sequence with moto (`@mock_aws`)
- **digest.py**: Test digest comparison logic with moto ECR + Lambda
- **logging.py**: Test GHA output formatting

### Integration Concerns

- Docker build: Can't easily test in CI without DinD. Test command construction, not execution.
- ECR push: moto supports ECR operations
- Lambda deploy: moto supports `update_function_code`, `publish_version`, `update_alias`, `get_function`
- OIDC: Tested by `aws-actions/configure-aws-credentials` — not our concern

### Test Location

Following project convention: `tests/test_action/` directory, parallel to `tests/test_backend/`.

## 10. Requirement Coverage

| Requirement | How Addressed |
|-------------|---------------|
| AUTH-02 | `aws-actions/configure-aws-credentials@v4` with OIDC in composite action |
| BUILD-01 | Magic Dockerfile with `ARG PYTHON_VERSION`, single Dockerfile for all Lambdas |
| BUILD-02 | `runtime` field from ferry.yaml → `--build-arg PYTHON_VERSION` |
| BUILD-03 | `--secret id=github_token` in Docker build for private repo deps |
| BUILD-04 | Glob trick `COPY system-requirements.tx[t]` + conditional RUN |
| BUILD-05 | `docker push` to `${ecr_uri}:${deployment_tag}` |
| DEPLOY-01 | update_function_code → wait → publish_version → update_alias |
| DEPLOY-04 | Digest comparison: pushed image vs deployed Lambda image |
| DEPLOY-05 | Deployment tag (pr-{N}) as ECR image tag + Lambda version description |
| ACT-01 | Composite action with Python scripts in `action/src/ferry_action/` |

## 11. Key Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Docker build fails silently | Capture exit codes, parse stderr for known patterns, surface in GHA logs |
| ECR push timeout | Set reasonable timeout, retry once on transient network errors |
| Lambda waiter timeout (5 min) | Log progress, surface clear error if function stays in `InProgress` |
| Missing IAM permissions | Document required permissions, detect permission errors early with clear hints |
| Large images slow to push | Recommend keeping Lambda packages lean in docs; not an action concern |

## RESEARCH COMPLETE

All Phase 3 requirements have clear implementation paths. Key technical questions resolved:
- BuildKit COPY glob works on ubuntu-latest (Docker 24+ with BuildKit default)
- Python 3.14 Lambda base image is available on public.ecr.aws
- `function_updated` waiter handles LastUpdateStatus polling
- `aws-actions/configure-aws-credentials` handles OIDC — no custom exchange needed
- Composite action can invoke Python scripts via `${{ github.action_path }}`
