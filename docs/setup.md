# Ferry Setup Guide

## What is Ferry

Ferry is a deployment tool for serverless AWS infrastructure, built as a GitHub App paired with GitHub Actions. When a developer pushes code, Ferry automatically detects which serverless resources changed, builds container images, and deploys them -- with full visibility on the PR before merge.

Ferry has two components: the **Ferry App** (a hosted backend that receives GitHub webhooks and orchestrates deployments) and the **Ferry Action** (composite GitHub Actions that run in your repository's CI environment to build and deploy resources).

## Installation

1. **Install the Ferry GitHub App** on your repository from the GitHub Marketplace.
2. **Create the workflow file** `.github/workflows/ferry.yml` in your repository (see [Workflow File](#workflow-file) below).
3. **Add a `ferry.yaml`** to your repository root describing your serverless resources.
4. **Configure AWS OIDC** so the Ferry Action can authenticate to your AWS account (see [OIDC Authentication](#oidc-authentication) below).

## ferry.yaml Structure

Ferry reads a single configuration file named `ferry.yaml` in your repository root. The file name must be exactly `ferry.yaml` -- not `.ferry.yaml`, not `ferry.yml`.

The file has a `version` field (currently `1`) and three top-level sections corresponding to the three supported resource types. Each section is optional; use an empty list or omit it entirely if you do not use that resource type.

```yaml
# ferry.yaml -- lives in repo root
version: 1

# Lambda functions: build container images and deploy to AWS Lambda
lambdas:
  - name: order-processor            # Logical name (used for logging and display)
    source_dir: services/order        # Path to source code, relative to repo root
    ecr_repo: myorg/order-processor   # Pre-existing ECR repository name
    runtime: python3.14               # Optional: Python runtime version (default: python3.14)
    function_name: order-processor    # Optional: AWS Lambda function name (defaults to name)

  - name: notification-sender
    source_dir: services/notify
    ecr_repo: myorg/notification-sender

# Step Functions state machines: deploy ASL definitions with variable substitution
step_functions:
  - name: order-workflow              # Logical name
    source_dir: workflows/order       # Directory containing the definition file
    state_machine_name: OrderWorkflow # AWS state machine name
    definition_file: definition.asl.json  # ASL definition file, relative to source_dir

# API Gateway REST APIs: deploy OpenAPI specs
api_gateways:
  - name: public-api                  # Logical name
    source_dir: api/public            # Directory containing the spec file
    rest_api_id: abc123def4           # AWS REST API ID
    stage_name: prod                  # Deployment stage name
    spec_file: openapi.yaml           # OpenAPI spec file, relative to source_dir
```

## Workflow File

Ferry uses a single workflow file named `ferry.yml`. When Ferry detects changes, it groups affected resources by type and fires a single `workflow_dispatch` event targeting this file. The dispatch payload contains all affected types in one batch. The workflow routes to the correct deploy jobs using boolean flags output by the setup action.

Create `.github/workflows/ferry.yml` in your repository with the following template:

```yaml
# .github/workflows/ferry.yml
name: Ferry Deploy

run-name: "Ferry Deploy: ${{ github.event.inputs.payload && (fromJson(github.event.inputs.payload).resource_types || fromJson(github.event.inputs.payload).resource_type || 'dispatched') || 'manual' }}"

on:
  workflow_dispatch:
    inputs:
      payload:
        description: "Ferry dispatch payload (JSON) -- sent by Ferry App, not for manual use"
        required: true

env:
  AWS_ROLE_ARN: ${{ secrets.AWS_ROLE_ARN }}
  AWS_REGION: us-east-1                    # Adjust to your AWS region

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
      resource_types: ${{ steps.parse.outputs.resource_types }}
    steps:
      - uses: actions/checkout@v4
      - name: Parse Ferry payload
        id: parse
        uses: AmitLaviDev/ferry/action/setup@main
        with:
          payload: ${{ inputs.payload }}

  deploy-lambda:
    name: "Ferry: deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.has_lambdas == 'true'
    runs-on: ubuntu-latest
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
          aws-region: ${{ env.AWS_REGION }}
          trigger-sha: ${{ matrix.trigger_sha }}
          deployment-tag: ${{ matrix.deployment_tag }}
          runtime: ${{ matrix.runtime }}
      - name: Deploy Lambda
        uses: AmitLaviDev/ferry/action/deploy@main
        with:
          resource-name: ${{ matrix.name }}
          function-name: ${{ matrix.function_name }}
          image-uri: ${{ steps.build.outputs.image-uri }}
          image-digest: ${{ steps.build.outputs.image-digest }}
          deployment-tag: ${{ matrix.deployment_tag }}
          trigger-sha: ${{ matrix.trigger_sha }}
          aws-role-arn: ${{ env.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
          github-token: ${{ github.token }}

  deploy-step-function:
    name: "Ferry: deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.has_step_functions == 'true'
    runs-on: ubuntu-latest
    concurrency:
      group: ferry-deploy-step-function-${{ matrix.name }}
      cancel-in-progress: false
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.sf_matrix) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
      - name: Deploy Step Functions
        uses: AmitLaviDev/ferry/action/deploy-stepfunctions@main
        with:
          resource-name: ${{ matrix.name }}
          state-machine-name: ${{ matrix.state_machine_name }}
          definition-file: ${{ matrix.definition_file }}
          source-dir: ${{ matrix.source }}
          trigger-sha: ${{ matrix.trigger_sha }}
          deployment-tag: ${{ matrix.deployment_tag }}
          aws-role-arn: ${{ env.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
          github-token: ${{ github.token }}

  deploy-api-gateway:
    name: "Ferry: deploy ${{ matrix.name }}"
    needs: setup
    if: needs.setup.outputs.has_api_gateways == 'true'
    runs-on: ubuntu-latest
    concurrency:
      group: ferry-deploy-api-gateway-${{ matrix.name }}
      cancel-in-progress: false
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.ag_matrix) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
      - name: Deploy API Gateway
        uses: AmitLaviDev/ferry/action/deploy-apigw@main
        with:
          resource-name: ${{ matrix.name }}
          rest-api-id: ${{ matrix.rest_api_id }}
          stage-name: ${{ matrix.stage_name }}
          spec-file: ${{ matrix.spec_file }}
          source-dir: ${{ matrix.source }}
          trigger-sha: ${{ matrix.trigger_sha }}
          deployment-tag: ${{ matrix.deployment_tag }}
          aws-role-arn: ${{ env.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
          github-token: ${{ github.token }}
```

### Migration from Per-Type Dispatch

If you previously used Ferry v1.4 (per-type dispatch), update your `ferry.yml` to the template above. The setup action now outputs per-type boolean flags and matrices instead of a single `matrix` and `resource_type`. No other changes are needed -- the Ferry backend handles the transition automatically.

## OIDC Authentication

Ferry uses the GitHub OIDC provider to authenticate with AWS -- no long-lived credentials are stored in your repository.

### Setup

1. **Create an IAM OIDC identity provider** in your AWS account for `token.actions.githubusercontent.com`.
2. **Create an IAM role** with a trust policy that allows your repository's GitHub Actions to assume it:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
           },
           "StringLike": {
             "token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/YOUR_REPO:*"
           }
         }
       }
     ]
   }
   ```

3. **Attach IAM policies** to the role granting permissions for the resource types you deploy:
   - **Lambdas**: `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:BatchGetImage`, `lambda:UpdateFunctionCode`, `lambda:PublishVersion`, `lambda:CreateAlias`, `lambda:UpdateAlias`, `lambda:ListTags`
   - **Step Functions**: `states:UpdateStateMachine`, `states:DescribeStateMachine`, `states:ListTagsForResource`, `states:TagResource`, `sts:GetCallerIdentity`
   - **API Gateways**: `apigateway:PutRestApi`, `apigateway:CreateDeployment`, `apigateway:GetTags`, `apigateway:TagResource`

4. **Pass the role ARN** as the `AWS_ROLE_ARN` secret referenced in the `ferry.yml` workflow template (see [Workflow File](#workflow-file) above).

The Ferry Action handles the `AssumeRoleWithWebIdentity` exchange automatically using the `aws-actions/configure-aws-credentials` action.

## How Dispatch Works

When you push code to a branch with an open PR (or to the default branch), Ferry processes the event in five stages:

1. **Webhook received** -- The Ferry App receives a `push` webhook from GitHub.
2. **Change detection** -- Ferry reads your `ferry.yaml`, compares the changed files against each resource's `source_dir`, and groups affected resources by type.
3. **Dispatch** -- Ferry fires a single `workflow_dispatch` event to `ferry.yml` containing all affected resource types in one batched payload. If the payload exceeds 65KB, Ferry falls back to one dispatch per type.
4. **Matrix fan-out** -- Your workflow uses the Ferry Setup action to parse the payload into per-type boolean flags and matrices. Deploy jobs gate on the boolean flags and use per-type matrices for fan-out.
5. **Build and deploy** -- Each matrix job uses the Ferry Build and/or Deploy actions to build container images, push to ECR, and update the AWS resource.

Ferry posts status updates to the PR throughout this process, so you can see deployment progress directly on the pull request.

## Per-Resource-Type Guides

For resource-specific configuration details, see:

- [Lambda Workflows](lambdas.md) -- ferry.yaml configuration, runtime override, and Magic Dockerfile
- [Step Functions Workflows](step-functions.md) -- ferry.yaml configuration, variable substitution, and content-hash skip detection
- [API Gateway Workflows](api-gateways.md) -- ferry.yaml configuration, spec format, and content-hash skip detection
