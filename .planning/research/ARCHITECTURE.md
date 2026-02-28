# Architecture Patterns: Ferry v1.1 Staging Deployment

**Domain:** Terraform IaC for deploying a GitHub App backend (Lambda + DynamoDB) to AWS
**Researched:** 2026-02-28
**Overall confidence:** MEDIUM-HIGH (Terraform AWS resources are well-documented and stable; web search/fetch unavailable so version details are from training data through early 2025)

## Recommended Architecture

### System Overview: Four Terraform Projects

```
iac/
├── global/cloud/aws/backend/           # TF Project 1: S3 state bucket (bootstrap)
│   ├── providers.tf                    #   No remote backend (local state or S3 after bootstrap)
│   ├── main.tf                         #   aws_s3_bucket, versioning, encryption
│   ├── variables.tf                    #   account_id, bucket_name
│   └── outputs.tf                      #   bucket_name, bucket_arn
│
├── global/cloud/aws/ecr/               # TF Project 2: ECR repo for Ferry Lambda
│   ├── providers.tf                    #   S3 backend → backend/ bucket
│   ├── main.tf                         #   terraform-aws-modules/ecr/aws
│   ├── variables.tf                    #   repo_name, lifecycle rules
│   └── outputs.tf                      #   repository_url, repository_arn
│
└── teams/platform/aws/staging/
    ├── shared/                         # TF Project 3: Cross-cutting IAM + Secrets
    │   ├── providers.tf                #   S3 backend → backend/ bucket
    │   ├── main.tf                     #   IAM roles, Secrets Manager
    │   ├── iam.tf                      #   Lambda execution role, OIDC provider
    │   ├── secrets.tf                  #   GitHub App private key, webhook secret
    │   ├── variables.tf
    │   ├── outputs.tf                  #   role_arn, secret_arns
    │   └── data.tf                     #   terraform_remote_state for ecr
    │
    └── us_east_1/ferry_backend/        # TF Project 4: Lambda + Function URL + DynamoDB
        ├── providers.tf                #   S3 backend → backend/ bucket
        ├── main.tf                     #   Lambda via terraform-aws-modules/lambda/aws
        ├── dynamodb.tf                 #   terraform-aws-modules/dynamodb-table/aws
        ├── variables.tf
        ├── outputs.tf                  #   function_url, lambda_function_name
        ├── data.tf                     #   terraform_remote_state for shared + ecr
        └── locals.tf                   #   computed values
```

### Dependency Graph and Apply Order

```
[1] backend (S3 bucket)
      |
      +---> [2] ecr (ECR repository)
      |           |
      +---> [3] shared (IAM + Secrets Manager)
                  |          |
                  +----------+
                  |
                  v
            [4] ferry_backend (Lambda + Function URL + DynamoDB)
```

**Apply order is strictly sequential:**

```
1. backend       — Creates S3 bucket for TF state (chicken-and-egg: see bootstrap section)
2. ecr           — Creates ECR repo. Needed by GHA to push images, and by ferry_backend for image_uri.
3. shared        — Creates IAM roles (referenced by Lambda) and Secrets Manager secrets.
4. ferry_backend — Creates Lambda (referencing ECR image, IAM role, secrets), Function URL, DynamoDB.
```

**Why this order:**
- `backend` has zero dependencies (it IS the state backend for everything else)
- `ecr` depends only on `backend` (for its own state storage)
- `shared` depends on `backend` (state) and reads `ecr` outputs via `terraform_remote_state`
- `ferry_backend` depends on `backend` (state), `ecr` (image_uri), and `shared` (IAM role ARN, secret ARNs)

### Integration Points Between TF Projects

The projects integrate via `terraform_remote_state` data sources -- the standard ConvergeBio/iac-tf pattern.

**Project 2 (ecr) exposes:**
```hcl
# iac/global/cloud/aws/ecr/outputs.tf
output "repository_url" {
  description = "ECR repository URL for Ferry Lambda container"
  value       = module.ecr.repository_url
}

output "repository_arn" {
  description = "ECR repository ARN"
  value       = module.ecr.repository_arn
}
```

**Project 3 (shared) reads ecr and exposes:**
```hcl
# iac/teams/platform/aws/staging/shared/data.tf
data "terraform_remote_state" "ecr" {
  backend = "s3"
  config = {
    bucket = "ferry-terraform-state"
    key    = "global/cloud/aws/ecr/terraform.tfstate"
    region = "us-east-1"
  }
}

# iac/teams/platform/aws/staging/shared/outputs.tf
output "lambda_execution_role_arn" {
  description = "IAM role ARN for Ferry Lambda"
  value       = aws_iam_role.ferry_lambda.arn
}

output "github_app_secret_arn" {
  description = "Secrets Manager ARN for GitHub App credentials"
  value       = aws_secretsmanager_secret.github_app.arn
}

output "webhook_secret_arn" {
  description = "Secrets Manager ARN for webhook HMAC secret"
  value       = aws_secretsmanager_secret.webhook_secret.arn
}

output "ecr_repository_url" {
  description = "ECR repo URL (passed through from global ecr project)"
  value       = data.terraform_remote_state.ecr.outputs.repository_url
}
```

**Project 4 (ferry_backend) reads shared:**
```hcl
# iac/teams/platform/aws/staging/us_east_1/ferry_backend/data.tf
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = "ferry-terraform-state"
    key    = "teams/platform/aws/staging/shared/terraform.tfstate"
    region = "us-east-1"
  }
}

data "terraform_remote_state" "ecr" {
  backend = "s3"
  config = {
    bucket = "ferry-terraform-state"
    key    = "global/cloud/aws/ecr/terraform.tfstate"
    region = "us-east-1"
  }
}
```

## Component Details

### Project 1: Backend (Bootstrap)

**Confidence: HIGH**

The classic Terraform bootstrap problem: the S3 bucket that stores state cannot itself have its state stored in S3 (on first run).

**Bootstrap strategy:**
1. First `terraform apply` uses local state (no backend block)
2. After bucket exists, add S3 backend config to `providers.tf`
3. Run `terraform init -migrate-state` to move local state to S3
4. Commit the providers.tf with S3 backend

This is a one-time operation. After bootstrap, the backend project manages itself.

```hcl
# iac/global/cloud/aws/backend/main.tf
resource "aws_s3_bucket" "terraform_state" {
  bucket = "ferry-terraform-state"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Optional: DynamoDB table for state locking
resource "aws_dynamodb_table" "terraform_locks" {
  name         = "ferry-terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
```

**After bootstrap, providers.tf becomes:**
```hcl
# iac/global/cloud/aws/backend/providers.tf
terraform {
  backend "s3" {
    bucket         = "ferry-terraform-state"
    key            = "global/cloud/aws/backend/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "ferry-terraform-locks"
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "ferry"
      Environment = "global"
      ManagedBy   = "terraform"
    }
  }
}
```

### Project 2: ECR

**Confidence: HIGH**

Uses `terraform-aws-modules/ecr/aws` per ConvergeBio conventions.

```hcl
# iac/global/cloud/aws/ecr/main.tf
module "ecr" {
  source  = "terraform-aws-modules/ecr/aws"
  version = "~> 2.0"

  repository_name = "ferry/backend"

  repository_lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 30 images"
        selection = {
          tagStatus     = "any"
          countType     = "imageCountMoreThan"
          countNumber   = 30
        }
        action = {
          type = "expire"
        }
      }
    ]
  })

  repository_image_tag_mutability = "MUTABLE"

  # Allow GHA OIDC role to push images
  repository_read_write_access_arns = [
    # Will be set after shared/ creates the OIDC role
    # For now, use the account root or a known role ARN
  ]
}
```

**Key decision: Global, not per-environment.** ECR repos are in `global/` because the same container images are used across staging and production. The environment difference is which image tag the Lambda points to, not which ECR repo it pulls from.

### Project 3: Shared (IAM + Secrets)

**Confidence: HIGH**

Creates the IAM role for Lambda execution and the OIDC provider for GHA.

```hcl
# iac/teams/platform/aws/staging/shared/iam.tf

# Lambda execution role
resource "aws_iam_role" "ferry_lambda" {
  name = "ferry-lambda-staging"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Basic Lambda execution (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.ferry_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB access for webhook dedup
resource "aws_iam_policy" "dynamodb_access" {
  name = "ferry-dynamodb-staging"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:DeleteItem",
        ]
        Resource = "arn:aws:dynamodb:us-east-1:*:table/ferry-state-staging"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "dynamodb_access" {
  role       = aws_iam_role.ferry_lambda.name
  policy_arn = aws_iam_policy.dynamodb_access.arn
}

# Secrets Manager read access
resource "aws_iam_policy" "secrets_access" {
  name = "ferry-secrets-staging"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
        ]
        Resource = [
          aws_secretsmanager_secret.github_app.arn,
          aws_secretsmanager_secret.webhook_secret.arn,
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "secrets_access" {
  role       = aws_iam_role.ferry_lambda.name
  policy_arn = aws_iam_policy.secrets_access.arn
}

# OIDC provider for GitHub Actions (self-deploy workflow)
module "github_oidc" {
  source  = "terraform-module/github-oidc-provider/aws"
  version = "~> 2.0"

  create_oidc_provider = true

  # Role for the self-deploy GHA workflow
  create_oidc_role = true
  oidc_role_name   = "ferry-gha-deploy-staging"

  repositories = [
    "your-org/ferry"
  ]

  oidc_role_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser",
  ]
}

# Additional policy: update Lambda function code
resource "aws_iam_policy" "gha_lambda_deploy" {
  name = "ferry-gha-lambda-deploy-staging"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction",
        ]
        Resource = "arn:aws:lambda:us-east-1:*:function:ferry-backend-staging"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "gha_lambda_deploy" {
  role       = module.github_oidc.oidc_role_name
  policy_arn = aws_iam_policy.gha_lambda_deploy.arn
}
```

```hcl
# iac/teams/platform/aws/staging/shared/secrets.tf

resource "aws_secretsmanager_secret" "github_app" {
  name        = "ferry/staging/github-app"
  description = "Ferry GitHub App credentials (app_id, private_key, installation_id)"
}

# Secret VALUE is set manually via AWS console or CLI -- NOT in Terraform
# Terraform manages the secret resource, not its content.

resource "aws_secretsmanager_secret" "webhook_secret" {
  name        = "ferry/staging/webhook-secret"
  description = "Ferry GitHub App webhook HMAC secret"
}
```

**Critical: Secrets Manager values are NOT in Terraform.** Terraform creates the secret containers. The actual secret values (private key PEM, webhook secret string, app ID, installation ID) are populated manually via AWS Console or `aws secretsmanager put-secret-value`. This is intentional -- secrets must never be in Terraform state or version control.

### Project 4: Ferry Backend (Lambda + Function URL + DynamoDB)

**Confidence: HIGH**

This is the main deployment target.

```hcl
# iac/teams/platform/aws/staging/us_east_1/ferry_backend/main.tf

module "lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "~> 7.0"

  function_name = "ferry-backend-staging"
  description   = "Ferry GitHub App webhook handler"

  # Container image deployment
  package_type  = "Image"
  create_package = false
  image_uri     = "${data.terraform_remote_state.ecr.outputs.repository_url}:latest"

  # CRITICAL: Let GHA update the image, don't let TF revert it
  ignore_source_code_hash = true

  memory_size = 256
  timeout     = 30
  architectures = ["x86_64"]

  # Function URL (replaces API Gateway)
  create_lambda_function_url = true
  authorization_type         = "NONE"
  cors = {
    allow_origins = ["*"]
    allow_methods = ["POST"]
    allow_headers = ["content-type", "x-hub-signature-256", "x-github-delivery", "x-github-event"]
  }

  # IAM role from shared project
  create_role = false
  lambda_role = data.terraform_remote_state.shared.outputs.lambda_execution_role_arn

  # Environment variables
  environment_variables = {
    FERRY_APP_ID          = local.app_id
    FERRY_TABLE_NAME      = module.dynamodb.dynamodb_table_id
    FERRY_INSTALLATION_ID = local.installation_id
    FERRY_LOG_LEVEL       = "INFO"
    # FERRY_PRIVATE_KEY and FERRY_WEBHOOK_SECRET loaded from Secrets Manager at runtime
    # (See "Secrets Loading" section below)
  }

  # CloudWatch log retention
  cloudwatch_logs_retention_in_days = 14
}
```

```hcl
# iac/teams/platform/aws/staging/us_east_1/ferry_backend/dynamodb.tf

module "dynamodb" {
  source  = "terraform-aws-modules/dynamodb-table/aws"
  version = "~> 4.0"

  name         = "ferry-state-staging"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attributes = [
    {
      name = "pk"
      type = "S"
    },
    {
      name = "sk"
      type = "S"
    },
  ]

  ttl_enabled        = true
  ttl_attribute_name = "expires_at"
}
```

## Lambda Function URL vs API Gateway

**Confidence: HIGH**

### What is a Lambda Function URL?

A Lambda Function URL is a dedicated HTTPS endpoint built into Lambda itself -- no separate API Gateway resource needed. It provides:

- An auto-generated HTTPS URL: `https://<url-id>.lambda-url.<region>.on.aws`
- Two auth modes: `AWS_IAM` or `NONE`
- Built-in CORS configuration
- Request/response payload format v2 (same as HTTP API Gateway)

### Terraform Resource: `aws_lambda_function_url`

When using the `terraform-aws-modules/lambda/aws` module, you do NOT need a separate `aws_lambda_function_url` resource. The module handles it via these variables:

```hcl
create_lambda_function_url = true     # Creates the function URL
authorization_type         = "NONE"    # No IAM auth (GitHub validates via HMAC)
cors = {                              # CORS configuration
  allow_origins = ["*"]
  allow_methods = ["POST"]
}
```

If using raw resources instead of the module:
```hcl
resource "aws_lambda_function_url" "webhook" {
  function_name      = aws_lambda_function.ferry.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = ["*"]
    allow_methods = ["POST"]
    allow_headers = ["content-type", "x-hub-signature-256", "x-github-delivery", "x-github-event"]
  }
}
```

### Function URL vs API Gateway Comparison

| Criterion | Lambda Function URL | API Gateway (HTTP API) | API Gateway (REST API) |
|-----------|--------------------|-----------------------|----------------------|
| **Cost** | Free (Lambda pricing only) | $1.00/million requests | $3.50/million requests |
| **Terraform resources** | 1 (part of Lambda) | 3-5 separate resources | 5-10 separate resources |
| **Custom domain** | Requires CloudFront distribution | Built-in custom domain mapping | Built-in custom domain mapping |
| **Rate limiting** | None built-in | Built-in throttling | Built-in throttling |
| **WAF integration** | No (requires CloudFront) | Yes (HTTP API v2) | Yes |
| **Request validation** | None | JSON schema validation | JSON schema validation |
| **Auth options** | IAM or NONE | IAM, JWT, Lambda authorizer | IAM, API key, Cognito, Lambda authorizer |
| **Payload format** | v2 (same as HTTP API) | v1 or v2 | v1 |
| **Max payload size** | 6 MB | 10 MB | 10 MB |
| **Max timeout** | 15 min (Lambda limit) | 30 sec (HTTP API) | 29 sec (REST API) |
| **Setup complexity** | Minimal (1 flag) | Moderate | High |

### Why Function URL is correct for Ferry

1. **Single endpoint**: Ferry has exactly one POST endpoint. API Gateway's routing, stages, and domain management are wasted complexity.
2. **Cost**: Zero additional cost. At Ferry's expected volume (< 100K webhooks/month), API Gateway would cost pennies, but free is simpler.
3. **Webhook compatibility**: GitHub webhooks POST to an HTTPS URL. Function URL provides that. The authentication is HMAC-SHA256 signature validation in the Lambda code itself, not at the gateway level.
4. **No custom domain needed for v1**: The auto-generated Function URL is configured as the GitHub App's webhook URL. Users never see or interact with it.
5. **Timeout advantage**: Function URLs inherit Lambda's 15-minute timeout. API Gateway HTTP API caps at 30 seconds. While Ferry processes webhooks in < 2 seconds, the longer timeout provides headroom.

### When to switch to API Gateway (v2+)

- Custom domain requirement (e.g., `webhooks.ferry.dev`)
- WAF/rate limiting for DDoS protection
- Multiple endpoints (health check, admin API, webhook status)
- Request throttling beyond Lambda concurrency limits

The migration path is clean: add API Gateway in front of the same Lambda. No Lambda code changes needed.

## Secrets Loading Pattern

**Confidence: MEDIUM** (pattern is well-established but implementation details need verification)

Ferry Lambda needs `FERRY_PRIVATE_KEY` (PEM, multi-line) and `FERRY_WEBHOOK_SECRET` at runtime. Two options:

### Option A: Environment Variables from Secrets Manager (Recommended)

Use the Lambda `aws_secretsmanager` environment variable integration (available since late 2022). Lambda resolves Secrets Manager references at startup and injects them as environment variables.

```hcl
environment_variables = {
  FERRY_PRIVATE_KEY     = "{{resolve:secretsmanager:ferry/staging/github-app:SecretString:private_key}}"
  FERRY_WEBHOOK_SECRET  = "{{resolve:secretsmanager:ferry/staging/webhook-secret:SecretString:value}}"
}
```

**Caveat:** The `{{resolve:...}}` syntax is a CloudFormation feature, not natively supported in Terraform's Lambda resource. For Terraform, the standard approach is:

### Option B: Load Secrets at Cold Start (Recommended for Terraform)

The Lambda code loads secrets from Secrets Manager at cold start. This is already a common pattern and avoids putting secret ARNs in environment variables directly.

```python
# In settings.py or a dedicated secrets loader
import boto3
import json

def load_secrets(secret_arn: str) -> dict:
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    return json.loads(response["SecretString"])
```

**Terraform configuration:**
```hcl
environment_variables = {
  FERRY_APP_ID             = local.app_id
  FERRY_TABLE_NAME         = module.dynamodb.dynamodb_table_id
  FERRY_INSTALLATION_ID    = local.installation_id
  FERRY_LOG_LEVEL          = "INFO"
  FERRY_SECRETS_ARN        = data.terraform_remote_state.shared.outputs.github_app_secret_arn
  FERRY_WEBHOOK_SECRET_ARN = data.terraform_remote_state.shared.outputs.webhook_secret_arn
}
```

The Lambda code reads `FERRY_SECRETS_ARN` and `FERRY_WEBHOOK_SECRET_ARN`, calls `secretsmanager:GetSecretValue`, and caches the results in module-level variables (cold start only).

**This means `Settings` needs modification:** Instead of `FERRY_PRIVATE_KEY` as a direct env var, it loads from Secrets Manager. This is a code change for v1.1, not just IaC.

## Self-Deploy GHA Workflow

**Confidence: HIGH**

The self-deploy workflow builds the ferry-backend container, pushes to ECR, and updates the Lambda function.

### Workflow Architecture

```
Push to main (backend/ or utils/ changes)
  |
  v
GHA Workflow: .github/workflows/deploy-ferry.yml
  |
  +-- Step 1: Checkout code
  +-- Step 2: Configure AWS credentials (OIDC)
  +-- Step 3: Login to ECR
  +-- Step 4: Build container image (docker build)
  +-- Step 5: Push to ECR (docker push)
  +-- Step 6: Update Lambda function code (aws lambda update-function-code)
```

### Workflow File

```yaml
# .github/workflows/deploy-ferry.yml
name: Deploy Ferry Backend

on:
  push:
    branches: [main]
    paths:
      - 'backend/**'
      - 'utils/**'
      - 'action/Dockerfile'  # If the Dockerfile itself changes, redeploy

  workflow_dispatch:  # Manual trigger for emergencies

permissions:
  id-token: write   # OIDC
  contents: read

env:
  AWS_REGION: us-east-1
  ECR_REPOSITORY: ferry/backend
  LAMBDA_FUNCTION: ferry-backend-staging

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.FERRY_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        id: ecr-login
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and tag image
        env:
          REGISTRY: ${{ steps.ecr-login.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build \
            -f backend/Dockerfile.deploy \
            -t $REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG \
            -t $REGISTRY/$ECR_REPOSITORY:latest \
            .

      - name: Push image to ECR
        env:
          REGISTRY: ${{ steps.ecr-login.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker push $REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker push $REGISTRY/$ECR_REPOSITORY:latest

      - name: Update Lambda function
        env:
          REGISTRY: ${{ steps.ecr-login.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          aws lambda update-function-code \
            --function-name $LAMBDA_FUNCTION \
            --image-uri $REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
```

### Backend Dockerfile (New File Needed)

The existing `action/Dockerfile` is the **magic Dockerfile** for user Lambda builds. Ferry's own backend needs a **separate Dockerfile** for containerizing the ferry-backend package.

```dockerfile
# backend/Dockerfile.deploy
# Builds the Ferry backend Lambda container
FROM public.ecr.aws/lambda/python:3.14

# Copy workspace files needed for installation
COPY utils/ /tmp/utils/
COPY backend/ /tmp/backend/

# Install ferry-utils first (dependency), then ferry-backend
RUN pip install --no-cache-dir /tmp/utils/ /tmp/backend/

# Clean up source copies
RUN rm -rf /tmp/utils/ /tmp/backend/

# Lambda handler entry point
CMD ["ferry_backend.webhook.handler.handler"]
```

**Key considerations:**
- The Dockerfile builds from the repo root (not from `backend/`) because it needs both `utils/` and `backend/` packages
- Uses the official AWS Lambda Python base image (same as user Lambdas)
- Installs packages via pip from local directories (uv workspace wheel builds)
- The CMD points to the actual handler function path
- Docker context is the repo root, Dockerfile is at `backend/Dockerfile.deploy`

### Alternative: Two-Stage Build (Cleaner)

```dockerfile
# backend/Dockerfile.deploy
FROM public.ecr.aws/lambda/python:3.14

# Install build tools
RUN pip install --no-cache-dir hatchling

# Copy and build ferry-utils wheel
COPY utils/ /tmp/build/utils/
RUN pip install --no-cache-dir /tmp/build/utils/

# Copy and build ferry-backend wheel (depends on ferry-utils)
COPY backend/ /tmp/build/backend/
RUN pip install --no-cache-dir /tmp/build/backend/

# Clean up
RUN rm -rf /tmp/build/

CMD ["ferry_backend.webhook.handler.handler"]
```

### Why NOT Use the Magic Dockerfile

The magic Dockerfile (`action/Dockerfile`) expects a specific structure: `main.py` + `requirements.txt` in a single flat directory. Ferry's backend is a proper Python package installed via `pip install`. Using the magic Dockerfile would require restructuring the backend into the user-facing Lambda convention, which defeats the purpose of having a well-structured workspace.

## Patterns to Follow

### Pattern 1: Placeholder Image URI

**What:** Terraform creates the Lambda with a placeholder/initial image. The real image is pushed by GHA and the Lambda is updated via `update-function-code`. Terraform never manages the running image after initial creation.

**Why:** Separates infrastructure provisioning from code deployment. Terraform manages the Lambda resource, GHA manages what code runs on it.

**Implementation:**
```hcl
# In ferry_backend/main.tf
image_uri                  = "${data.terraform_remote_state.ecr.outputs.repository_url}:latest"
ignore_source_code_hash    = true
```

The `ignore_source_code_hash = true` is critical. Without it, every `terraform plan` would detect that the image has changed (because GHA pushed a new one) and try to revert it.

### Pattern 2: terraform_remote_state for Cross-Project References

**What:** Projects reference each other's outputs via `terraform_remote_state` data sources. All state lives in the same S3 bucket with different keys.

**Why:** Avoids hardcoding ARNs and URLs. Changes to upstream projects (e.g., renaming the ECR repo) automatically propagate on next plan/apply of downstream projects.

**State key convention:**
```
global/cloud/aws/backend/terraform.tfstate
global/cloud/aws/ecr/terraform.tfstate
teams/platform/aws/staging/shared/terraform.tfstate
teams/platform/aws/staging/us_east_1/ferry_backend/terraform.tfstate
```

### Pattern 3: Environment-Scoped Naming

**What:** All resource names include the environment suffix: `ferry-backend-staging`, `ferry-state-staging`, etc.

**Why:** Enables future production environment without naming conflicts. Also makes CloudWatch logs and AWS console navigation unambiguous.

### Pattern 4: Separate Terraform State Lock Table

**What:** A DynamoDB table (`ferry-terraform-locks`) in the backend project provides state locking for all TF projects.

**Why:** Prevents concurrent applies from corrupting state. Especially important when the self-deploy workflow and manual `terraform apply` might overlap.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Single Monolithic TF Project

**What:** Putting all resources (S3, ECR, IAM, Lambda, DynamoDB) in one Terraform project.

**Why bad:** One `terraform apply` manages everything. Blast radius is enormous. A mistake in IAM config could destroy the DynamoDB table. Also, state locking means only one person/workflow can apply at a time across ALL resources.

**Instead:** Four focused projects with clear dependency ordering.

### Anti-Pattern 2: Managing Container Image in Terraform

**What:** Building and pushing the Docker image as part of `terraform apply` (e.g., using `null_resource` with `docker build` provisioner).

**Why bad:** Terraform is for infrastructure, not application deployment. Mixing them means every `terraform apply` triggers a build, or Terraform state tracks image hashes and fights with GHA deployments.

**Instead:** Terraform creates the Lambda with `ignore_source_code_hash = true`. GHA owns the build-push-update cycle.

### Anti-Pattern 3: Secrets in Terraform Variables

**What:** Passing the GitHub App private key or webhook secret as Terraform variables.

**Why bad:** Terraform state stores all variable values in plaintext. Even with encrypted S3 state, anyone with state access sees the secrets.

**Instead:** Terraform creates `aws_secretsmanager_secret` resources (the containers). Secret values are populated manually via CLI or Console, never in TF.

### Anti-Pattern 4: Cross-Account assume_role in Staging

**What:** Using `assume_role` in the provider block when Ferry runs in its own dedicated account.

**Why bad:** Unnecessary complexity. The ConvergeBio/iac-tf pattern uses `assume_role` because Terraform runs from a management account into target accounts. For Ferry's own account, the TF runner (your local machine or a GHA runner) has direct credentials.

**Instead:** Simple provider with region and default_tags. No `assume_role` unless Ferry later moves to a multi-account setup.

## Build Order for Self-Deploy

The complete build and deploy sequence:

```
1. [One-time] terraform apply: backend/    (creates S3 bucket, lock table)
2. [One-time] terraform init -migrate-state: backend/  (move local state to S3)
3. [One-time] terraform apply: ecr/        (creates ECR repo)
4. [One-time] terraform apply: shared/     (creates IAM roles, secret containers)
5. [Manual]   aws secretsmanager put-secret-value: populate secrets
6. [One-time] Build + push initial container image to ECR
7. [One-time] terraform apply: ferry_backend/  (creates Lambda, Function URL, DynamoDB)
8. [Manual]   Register GitHub App with Function URL as webhook endpoint
9. [Ongoing]  GHA self-deploy workflow: push to main -> build -> push ECR -> update Lambda
```

Steps 1-8 are the initial setup. Step 9 is the ongoing deployment cycle.

**Step 6 detail:** Before `terraform apply` for ferry_backend, ECR needs at least one image tagged `latest` (because the Lambda resource references it). Push a placeholder:

```bash
# Build and push initial image
docker build -f backend/Dockerfile.deploy -t ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/ferry/backend:latest .
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.us-east-1.amazonaws.com
docker push ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/ferry/backend:latest
```

## New Files Needed (Summary)

| File | Type | Purpose |
|------|------|---------|
| `backend/Dockerfile.deploy` | Dockerfile | Containerize ferry-backend for Lambda |
| `.github/workflows/deploy-ferry.yml` | GHA workflow | Self-deploy on push to main |
| `iac/global/cloud/aws/backend/` | TF project (4 files) | S3 state bucket + lock table |
| `iac/global/cloud/aws/ecr/` | TF project (4 files) | ECR repository |
| `iac/teams/platform/aws/staging/shared/` | TF project (6 files) | IAM roles, Secrets Manager, OIDC |
| `iac/teams/platform/aws/staging/us_east_1/ferry_backend/` | TF project (6 files) | Lambda + Function URL + DynamoDB |

## Code Changes Needed

| File | Change | Why |
|------|--------|-----|
| `backend/src/ferry_backend/settings.py` | Add Secrets Manager loading | Private key and webhook secret loaded from Secrets Manager ARNs instead of direct env vars |

The `Settings` class currently expects `FERRY_PRIVATE_KEY` and `FERRY_WEBHOOK_SECRET` as direct environment variables. For Secrets Manager, it needs to accept `FERRY_SECRETS_ARN` and `FERRY_WEBHOOK_SECRET_ARN`, then load the actual values at cold start.

## Scalability Considerations

| Concern | Staging (< 100 webhooks/day) | Production (10K webhooks/day) |
|---------|------|------|
| Lambda concurrency | Default 1000, no concern | Default 1000, monitor with alarms |
| DynamoDB | PAY_PER_REQUEST, pennies | PAY_PER_REQUEST, still cheap |
| ECR storage | 30 images ~3GB, ~$0.30/month | Same (lifecycle policy keeps 30) |
| Function URL | No throttling concern | Consider adding CloudFront + WAF |
| State locking | No contention | Use Digger for TF CI/CD if multiple contributors |

## Sources

- Training data knowledge of Terraform AWS provider resources (stable, well-documented) -- HIGH confidence on resource schemas
- Training data knowledge of terraform-aws-modules/lambda/aws module -- HIGH confidence on variables/features
- Training data knowledge of terraform-aws-modules/ecr/aws module -- HIGH confidence
- Training data knowledge of terraform-aws-modules/dynamodb-table/aws module -- HIGH confidence
- Training data knowledge of terraform-module/github-oidc-provider/aws -- MEDIUM confidence on exact version/interface
- Training data knowledge of Lambda Function URLs -- HIGH confidence
- Training data knowledge of GHA OIDC + aws-actions -- HIGH confidence
- ConvergeBio/iac-tf patterns from memory/terraform-conventions.md -- HIGH confidence (first-party)
- pipelines-hub analysis from memory/pipelines-hub-analysis.md -- HIGH confidence (first-party)
- Ferry v1.0 codebase analysis (handler.py, settings.py, pyproject.toml) -- HIGH confidence (first-party)

**Note:** Web search, web fetch, and Brave search were all unavailable during this research session. The `terraform-aws-modules` module version numbers (~> 7.0 for lambda, ~> 2.0 for ecr, ~> 4.0 for dynamodb-table) should be verified against the Terraform Registry before implementation. The module variable names and features described are from training data and are very likely accurate (these modules are mature and stable), but exact variable names should be confirmed via `terraform init` + documentation.
