# Ferry Setup Guide

## What is Ferry

Ferry is a deployment tool for serverless AWS infrastructure, built as a GitHub App paired with GitHub Actions. When a developer pushes code, Ferry automatically detects which serverless resources changed, builds container images, and deploys them -- with full visibility on the PR before merge.

Ferry has two components: the **Ferry App** (a hosted backend that receives GitHub webhooks and orchestrates deployments) and the **Ferry Action** (composite GitHub Actions that run in your repository's CI environment to build and deploy resources).

## Installation

1. **Install the Ferry GitHub App** on your repository from the GitHub Marketplace.
2. **Create workflow files** in `.github/workflows/` for each resource type you use (see [Workflow File Naming](#workflow-file-naming-convention) below).
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

## Workflow File Naming Convention

Ferry triggers GitHub Actions workflows by dispatching to specific workflow file names. These names are **not configurable** -- they are derived from the resource type and must match exactly, or dispatches will fail silently with a 404.

The naming convention follows the pattern `ferry-{type}.yml`:

| Resource Type   | Workflow File Name           |
|-----------------|------------------------------|
| Lambda          | `ferry-lambdas.yml`          |
| Step Function   | `ferry-step_functions.yml`   |
| API Gateway     | `ferry-api_gateways.yml`     |

Place these files in `.github/workflows/` in your repository. You only need workflow files for the resource types you use. For example, if your `ferry.yaml` only defines `lambdas`, you only need `ferry-lambdas.yml`.

**Why does naming matter?** When Ferry detects changes, it groups affected resources by type and fires one `workflow_dispatch` event per type. The dispatch targets the workflow file by name. If the file name does not match, GitHub returns a 404 and the deployment is silently skipped.

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

4. **Pass the role ARN** as the `aws-role-arn` input in your workflow files (see the per-resource-type guides).

The Ferry Action handles the `AssumeRoleWithWebIdentity` exchange automatically using the `aws-actions/configure-aws-credentials` action.

## How Dispatch Works

When you push code to a branch with an open PR (or to the default branch), Ferry processes the event in five stages:

1. **Webhook received** -- The Ferry App receives a `push` webhook from GitHub.
2. **Change detection** -- Ferry reads your `ferry.yaml`, compares the changed files against each resource's `source_dir`, and groups affected resources by type.
3. **Dispatch** -- For each resource type with changes, Ferry fires one `workflow_dispatch` event to the corresponding workflow file (e.g., `ferry-lambdas.yml`). The dispatch payload is a JSON string containing all affected resources of that type.
4. **Matrix fan-out** -- Your workflow uses the Ferry Setup action (`./action/setup`) to parse the payload into a GHA matrix. Each matrix job handles one resource.
5. **Build and deploy** -- Each matrix job uses the Ferry Build and/or Deploy actions to build container images, push to ECR, and update the AWS resource.

Ferry posts status updates to the PR throughout this process, so you can see deployment progress directly on the pull request.

## Per-Resource-Type Guides

For detailed workflow setup instructions and annotated example workflow files, see:

- [Lambda Workflows](lambdas.md) -- Build container images and deploy Lambda functions
- [Step Functions Workflows](step-functions.md) -- Deploy state machine definitions with variable substitution
- [API Gateway Workflows](api-gateways.md) -- Deploy REST APIs from OpenAPI specs
