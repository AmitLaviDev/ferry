# API Gateway Workflows

The API Gateway workflow deploys OpenAPI (Swagger) specifications to Amazon API Gateway REST APIs. Ferry uploads the spec, creates a new deployment to the specified stage, and uses content-hash skip detection to avoid unnecessary deployments when the spec has not changed.

## ferry.yaml Configuration

Define your API Gateways in the `api_gateways` section of `ferry.yaml`:

```yaml
api_gateways:
  - name: public-api                  # Required: logical name (used for logging/display)
    source_dir: api/public            # Required: directory containing the spec file
    rest_api_id: abc123def4           # Required: AWS REST API ID
    stage_name: prod                  # Required: deployment stage name
    spec_file: openapi.yaml           # Required: OpenAPI spec file, relative to source_dir
```

### Field Reference

| Field          | Required | Description |
|----------------|----------|-------------|
| `name`         | Yes      | Logical name for the resource. Used in logs and PR status. |
| `source_dir`   | Yes      | Path to the directory containing the spec file, relative to repo root. Ferry detects changes by watching files under this path. |
| `rest_api_id`  | Yes      | The AWS REST API ID. Find this in the API Gateway console or your IaC outputs. |
| `stage_name`   | Yes      | The stage to deploy to (e.g., `prod`, `staging`). The stage must already exist. |
| `spec_file`    | Yes      | The OpenAPI spec file name, relative to `source_dir`. |

## Workflow File

Create `.github/workflows/ferry-api_gateways.yml` in your repository. The file name must be exactly `ferry-api_gateways.yml` -- Ferry dispatches to this name and a mismatch causes a silent 404.

```yaml
# .github/workflows/ferry-api_gateways.yml
# Ferry API Gateway deployment workflow
# Triggered by Ferry App via workflow_dispatch when spec files change

name: Ferry API Gateways

on:
  workflow_dispatch:
    inputs:
      payload:
        description: "Ferry dispatch payload (JSON)"  # Sent by Ferry App
        required: true

permissions:
  id-token: write    # OIDC JWT for AWS authentication
  contents: read     # Repository checkout
  checks: write      # Check Run status reporting

jobs:
  # Step 1: Parse the dispatch payload into a matrix
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

  # Step 2: Deploy each API Gateway in parallel
  deploy:
    needs: setup
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false                                # Deploy all resources even if one fails
    steps:
      - uses: actions/checkout@v4

      # Deploy: upload OpenAPI spec and create deployment
      - name: Deploy API Gateway
        uses: ./action/deploy-apigw                   # Ferry APIGW deploy composite action
        with:
          resource-name: ${{ matrix.name }}            # Logical resource name
          rest-api-id: ${{ matrix.rest_api_id }}       # AWS REST API ID
          stage-name: ${{ matrix.stage_name }}         # Deployment stage
          spec-file: ${{ matrix.spec_file }}           # OpenAPI spec file name
          source-dir: ${{ matrix.source }}             # Directory containing the spec
          trigger-sha: ${{ matrix.trigger_sha }}       # Git SHA that triggered the deploy
          deployment-tag: ${{ matrix.deployment_tag }} # Deployment tag (e.g., pr-42)
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}    # IAM role for OIDC auth
          aws-region: us-east-1                        # AWS region (adjust as needed)
          github-token: ${{ github.token }}            # Check Run reporting (auto-granted, not a PAT)
```

## Spec Format

Ferry supports OpenAPI/Swagger specification files in both YAML and JSON format. The spec is loaded, converted to canonical JSON for hashing, and uploaded via the API Gateway `PutRestApi` operation.

Your spec should include `x-amazon-apigateway-integration` extensions on each path/method to define the backend integrations (Lambda proxy, HTTP, mock, etc.). Without these extensions, API Gateway will accept the spec but the API will have no backend integrations configured.

## Terraform Lifecycle

Since Ferry manages the API spec at deploy time, your Terraform (or other IaC) should ignore changes to the `body` and the `ferry:content-hash` tag. Otherwise Terraform will try to revert Ferry's deployments:

```hcl
resource "aws_api_gateway_rest_api" "example" {
  name = "my-api"

  body = jsonencode({
    openapi = "3.0.1"
    info    = { title = "my-api", version = "1.0" }
    paths   = {}
  })

  lifecycle {
    ignore_changes = [body, tags["ferry:content-hash"]]
  }
}
```

## Content-Hash Skip Detection

Ferry computes a SHA-256 hash of the canonical JSON representation of your spec and stores it as a tag on the REST API (`ferry:content-hash`). On subsequent deployments, if the content hash matches the existing tag, the deployment is skipped. This avoids unnecessary API Gateway deployments when the spec has not actually changed.

The canonical representation uses sorted keys and compact separators, so reformatting your spec file (e.g., changing indentation or key order) will not trigger a spurious deployment.
