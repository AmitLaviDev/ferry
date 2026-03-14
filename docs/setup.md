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

# Environment-to-branch mapping (optional)
# Each push to a mapped branch auto-deploys to that environment.
# GitHub Environments with matching names provide environment-level secrets.
environments:
  staging:
    branch: develop              # Pushes to 'develop' deploy to staging
  production:
    branch: main                 # Pushes to 'main' deploy to production
    auto_deploy: false           # Require explicit /ferry apply (default: true)

# Lambda functions: build container images and deploy to AWS Lambda
lambdas:
  - name: order-processor            # AWS Lambda function name (used for display and deploy)
    source_dir: services/order        # Path to source code, relative to repo root
    ecr_repo: myorg/order-processor   # Pre-existing ECR repository name
    runtime: python3.14               # Optional: Python runtime version (default: python3.14)

  - name: notification-sender
    source_dir: services/notify
    ecr_repo: myorg/notification-sender

# Step Functions state machines: deploy ASL definitions with variable substitution
step_functions:
  - name: OrderWorkflow              # AWS state machine name
    source_dir: workflows/order       # Directory containing the definition file
    definition_file: definition.asl.json  # ASL definition file, relative to source_dir

# API Gateway REST APIs: deploy OpenAPI specs
api_gateways:
  - name: public-api                  # Logical name
    source_dir: api/public            # Directory containing the spec file
    rest_api_id: abc123def4           # AWS REST API ID
    stage_name: prod                  # Deployment stage name
    spec_file: openapi.yaml           # OpenAPI spec file, relative to source_dir
```

`name` is used as the AWS resource name. For Lambdas, it is the Lambda function name. For Step Functions, it is the state machine name. For API Gateways, it is a logical identifier (the REST API ID and stage are separate fields).

### Environments

The `environments` section is optional. When present, Ferry maps branches to named environments:

- **`branch`** (required): The branch name that triggers deployment to this environment.
- **`auto_deploy`** (optional, default `true`): When `true`, pushes to the mapped branch auto-deploy. When `false`, deploy only happens via `/ferry apply` on a PR targeting this branch.

When no `environments` section is defined, pushes do not trigger Ferry deployments. Use `/ferry apply` on PRs for manual deploy control.

To use GitHub Environment-level secrets, create a [GitHub Environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment) in your repository settings with a name matching the environment name in `ferry.yaml` (e.g., "staging", "production"). The workflow template automatically injects the environment, giving deploy jobs access to environment-scoped secrets and variables.

## Workflow File

Ferry uses a single workflow file named `ferry.yml`. When Ferry detects changes, it groups affected resources by type and fires a single `workflow_dispatch` event targeting this file. The dispatch payload contains all affected types in one batch. The workflow routes to the correct deploy jobs using boolean flags output by the setup action.

Create `.github/workflows/ferry.yml` in your repository with the following template:

```yaml
# .github/workflows/ferry.yml
name: Ferry Deploy

run-name: "Ferry Deploy: ${{ github.event.inputs.payload && (fromJson(github.event.inputs.payload).resource_types || fromJson(github.event.inputs.payload).resource_type || 'dispatched') || 'manual' }}${{ github.event.inputs.payload && fromJson(github.event.inputs.payload).environment != '' && format(' → {0}', fromJson(github.event.inputs.payload).environment) || '' }}"

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
      mode: ${{ steps.parse.outputs.mode }}
      environment: ${{ steps.parse.outputs.environment }}
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
    if: needs.setup.outputs.has_lambdas == 'true' && needs.setup.outputs.mode == 'deploy'
    runs-on: ubuntu-latest
    environment: ${{ needs.setup.outputs.environment }}
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
    if: needs.setup.outputs.has_step_functions == 'true' && needs.setup.outputs.mode == 'deploy'
    runs-on: ubuntu-latest
    environment: ${{ needs.setup.outputs.environment }}
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
    if: needs.setup.outputs.has_api_gateways == 'true' && needs.setup.outputs.mode == 'deploy'
    runs-on: ubuntu-latest
    environment: ${{ needs.setup.outputs.environment }}
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

### Migration from v1.x

If you previously used Ferry v1.5 (batched dispatch without environments), update your `ferry.yml` to the template above. Key changes:

- **Setup outputs**: `mode` and `environment` are new outputs from the setup job
- **Deploy guards**: Each deploy job's `if:` now includes `&& needs.setup.outputs.mode == 'deploy'`
- **Environment injection**: Each deploy job has `environment: ${{ needs.setup.outputs.environment }}`
- **Run name**: Now shows the target environment (e.g., "Ferry Deploy: lambda → staging")

- **Schema simplification**: `function_name` (Lambdas) and `state_machine_name` (Step Functions) are removed from ferry.yaml. `name` is now the AWS resource name directly. Old ferry.yaml files with these fields still parse (backward compatible), but you should update them.

The setup action is backward compatible -- v1.5 payloads (without mode/environment) still work with defaults (`mode="deploy"`, `environment=""`). An empty environment string is a no-op in GHA; the job runs normally without Environment-level secrets.

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

## GitHub App Webhook Events

The Ferry GitHub App must be subscribed to these webhook events:

| Event | Purpose |
|-------|---------|
| `push` | Detect code changes and trigger auto-deploy on merge (when `auto_deploy: true`) |
| `pull_request` | Post plan preview comment on PR open/update |
| `issue_comment` | Handle `/ferry plan` and `/ferry apply` PR commands |
| `workflow_run` | Update PR comment with deploy status after workflow completes |

Configure these in your GitHub App settings under "Permissions & events" → "Subscribe to events".

## Per-Resource-Type Guides

For resource-specific configuration details, see:

- [Lambda Workflows](lambdas.md) -- ferry.yaml configuration, runtime override, and Magic Dockerfile
- [Step Functions Workflows](step-functions.md) -- ferry.yaml configuration, variable substitution, and content-hash skip detection
- [API Gateway Workflows](api-gateways.md) -- ferry.yaml configuration, spec format, and content-hash skip detection
