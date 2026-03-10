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
