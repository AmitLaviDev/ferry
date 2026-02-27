# Lambda Workflows

The Lambda workflow builds a container image from your source code, pushes it to Amazon ECR, and deploys it to an AWS Lambda function. Ferry uses a generic "Magic Dockerfile" that works for any Python Lambda without requiring you to write a Dockerfile.

## ferry.yaml Configuration

Define your Lambda functions in the `lambdas` section of `ferry.yaml`:

```yaml
lambdas:
  - name: order-processor            # Required: logical name (used for logging/display)
    source_dir: services/order        # Required: path to source code, relative to repo root
    ecr_repo: myorg/order-processor   # Required: pre-existing ECR repository name
    runtime: python3.14               # Optional: Python runtime version (default: python3.14)
    function_name: order-processor    # Optional: AWS Lambda function name (defaults to name)
```

### Field Reference

| Field           | Required | Default      | Description |
|-----------------|----------|--------------|-------------|
| `name`          | Yes      | --           | Logical name for the resource. Used in logs, PR status, and as the default `function_name`. |
| `source_dir`    | Yes      | --           | Path to the Lambda source directory, relative to repo root. Ferry detects changes by watching files under this path. |
| `ecr_repo`      | Yes      | --           | Name of a **pre-existing** ECR repository. Ferry does not create ECR repos -- your IaC should manage them. |
| `runtime`       | No       | `python3.14` | Python runtime version string (e.g., `python3.12`, `python3.14`). Controls the base image used in the container build. |
| `function_name` | No       | Same as `name` | The AWS Lambda function name. Set this if your Lambda function name in AWS differs from the logical `name`. |

## Workflow File

Create `.github/workflows/ferry-lambdas.yml` in your repository. The file name must be exactly `ferry-lambdas.yml` -- Ferry dispatches to this name and a mismatch causes a silent 404.

```yaml
# .github/workflows/ferry-lambdas.yml
# Ferry Lambda deployment workflow
# Triggered by Ferry App via workflow_dispatch when Lambda source files change

name: Ferry Lambdas

on:
  workflow_dispatch:
    inputs:
      payload:
        description: "Ferry dispatch payload (JSON)"  # Sent by Ferry App
        required: true

# OIDC requires id-token:write to request the JWT
# contents:read is needed to check out the repository
permissions:
  id-token: write
  contents: read

jobs:
  # Step 1: Parse the dispatch payload into a matrix
  # The setup action extracts one entry per affected Lambda
  setup:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.parse.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4

      - name: Parse Ferry payload
        id: parse
        uses: ./action/setup                          # Ferry setup composite action
        with:
          payload: ${{ inputs.payload }}               # Raw JSON from workflow_dispatch

  # Step 2: Build and deploy each Lambda in parallel
  # The matrix fans out one job per affected Lambda resource
  deploy:
    needs: setup
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false                                # Deploy all resources even if one fails
    steps:
      - uses: actions/checkout@v4

      # Build: create container image and push to ECR
      - name: Build container
        id: build
        uses: ./action/build                          # Ferry build composite action
        with:
          resource-name: ${{ matrix.name }}            # Logical resource name
          source-dir: ${{ matrix.source }}             # Path to Lambda source directory
          ecr-repo: ${{ matrix.ecr }}                  # ECR repository name
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}    # IAM role for OIDC auth
          aws-region: us-east-1                        # AWS region (adjust as needed)
          trigger-sha: ${{ matrix.trigger_sha }}       # Git SHA that triggered the build
          deployment-tag: ${{ matrix.deployment_tag }} # Image tag (e.g., pr-42)
          runtime: ${{ matrix.runtime }}               # Python runtime from ferry.yaml
          # github-token: ${{ secrets.GH_PAT }}       # Uncomment for private repo deps

      # Deploy: update Lambda function code with the new image
      - name: Deploy Lambda
        uses: ./action/deploy                         # Ferry deploy composite action
        with:
          resource-name: ${{ matrix.name }}            # Logical resource name
          function-name: ${{ matrix.function_name }}   # AWS Lambda function name
          image-uri: ${{ steps.build.outputs.image-uri }}       # Full ECR image URI
          image-digest: ${{ steps.build.outputs.image-digest }} # Image digest for skip detection
          deployment-tag: ${{ matrix.deployment_tag }} # Deployment tag
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}    # IAM role for OIDC auth
          aws-region: us-east-1                        # AWS region (adjust as needed)
```

## Runtime Override

The default runtime is set in your `ferry.yaml` (default: `python3.14`). This value flows through the dispatch pipeline and into the build action's `runtime` input.

If you need a different runtime for all Lambdas regardless of `ferry.yaml`, you can hardcode the `runtime` input on the build step:

```yaml
      - name: Build container
        uses: ./action/build
        with:
          runtime: python3.12  # Override ferry.yaml default for all Lambdas
          # ... other inputs
```

For per-Lambda runtime control, set the `runtime` field on each Lambda entry in `ferry.yaml`.

## Magic Dockerfile

Ferry uses a generic Dockerfile that handles common Python Lambda patterns without requiring you to write one. The Dockerfile supports:

- **`requirements.txt`** (required): Python dependencies installed via pip.
- **`system-requirements.txt`** (optional): System packages installed via dnf (e.g., `gcc`, `libpq-devel`).
- **`system-config.sh`** (optional): A shell script for custom system-level setup.
- **Private repository dependencies**: Pass a `github-token` input to the build action to authenticate `pip install` for private GitHub repositories.

Your `source_dir` is copied entirely into the container. The entrypoint defaults to `main.handler` -- place your handler function in `main.py` at the root of your `source_dir`.
