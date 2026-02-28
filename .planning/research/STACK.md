# Technology Stack: Ferry v1.1 Deploy to Staging

**Project:** Ferry - Deploy to AWS via Terraform
**Researched:** 2026-02-28
**Overall confidence:** MEDIUM (training data covers Terraform AWS provider through ~5.x, terraform-aws-modules through mid-2024; exact latest version numbers need verification at implementation time)

## Scope

This STACK.md covers ONLY the Terraform IaC needed to deploy Ferry's existing backend to AWS staging. The application code (Python 3.14, httpx, Pydantic, etc.) is shipped and validated -- not re-researched here.

## Terraform Core

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Terraform | >= 1.9.0 | IaC engine | Current stable branch. 1.9 added input variable validation improvements and moved-block enhancements. Pin minimum, not exact. | MEDIUM |
| hashicorp/aws provider | ~> 5.80 | AWS resource management | The 5.x line has been stable since late 2024. Lambda Function URL support (aws_lambda_function_url) was added in 4.x and is mature. Use pessimistic constraint (~>) to allow patch updates but not major. | MEDIUM |

**Version verification needed:** Check `registry.terraform.io/providers/hashicorp/aws/latest` at implementation time. The 5.x line may be at 5.80+ or 5.90+ by now.

## Decision: Raw Resources vs terraform-aws-modules

**Use raw AWS resources (no terraform-aws-modules).** Here is why:

1. **Ferry's infra is small.** One Lambda, one DynamoDB table, one ECR repo, a few IAM roles, one Secrets Manager secret. The terraform-aws-modules abstractions (lambda, dynamodb-table) are designed for teams managing dozens of resources with consistent patterns. For 5-6 resources, raw `aws_*` resources are simpler, more transparent, and easier to debug.

2. **Lambda module complexity mismatch.** The `terraform-aws-modules/lambda/aws` module (~v7.x) handles package building, layer management, container image builds, provisioned concurrency, VPC configs, and more. Ferry needs exactly: create a Lambda from an ECR image, attach a Function URL, set environment variables, assign an IAM role. The module's 40+ variables add cognitive overhead for a 6-variable use case.

3. **Function URL is a single resource.** `aws_lambda_function_url` is one resource with 4 fields. No module needed.

4. **ConvergeBio/iac-tf uses custom modules** -- their Lambda module in `modules/lambda/` is hand-built, not terraform-aws-modules. Ferry should follow the same pattern of explicit resource definitions.

5. **Debugging.** When something breaks in production at 2 AM, you want to read `aws_lambda_function` directly, not trace through a module's `main.tf` -> `locals.tf` -> conditional resource creation.

**Exception: S3 backend bucket.** Use raw resources here too -- it is literally one `aws_s3_bucket` + versioning + encryption.

## AWS Resources Required

### TF State Backend (`iac/global/cloud/aws/backend/`)

| Resource | Terraform Type | Purpose | Notes |
|----------|---------------|---------|-------|
| S3 bucket | `aws_s3_bucket` | TF state storage | Name: `ferry-terraform-state-{account_id}` |
| Bucket versioning | `aws_s3_bucket_versioning` | State file history | Required for state recovery |
| Bucket encryption | `aws_s3_bucket_server_side_encryption_configuration` | Encrypt state at rest | AES256 (S3-managed keys sufficient for staging) |
| Public access block | `aws_s3_bucket_public_access_block` | Prevent accidental exposure | Block all public access |
| DynamoDB table | `aws_dynamodb_table` | State locking | Name: `ferry-terraform-locks`, PAY_PER_REQUEST |

**Bootstrap note:** This project must be applied first with local state (`terraform init` with no backend), then migrated to itself (`terraform init -migrate-state` after the bucket exists). This is a one-time manual step.

### ECR Repository (`iac/global/cloud/aws/ecr/`)

| Resource | Terraform Type | Purpose | Notes |
|----------|---------------|---------|-------|
| ECR repository | `aws_ecr_repository` | Ferry Lambda container images | Name: `ferry/backend` |
| Lifecycle policy | `aws_ecr_lifecycle_policy` | Limit stored images | Keep last 10 tagged images, expire untagged after 1 day |
| Repository policy | `aws_ecr_repository_policy` | Access control | Allow Lambda service to pull (optional -- Lambda role suffices) |

**Lifecycle policy rationale:** ECR charges $0.10/GB/month. Lambda container images are ~100-200MB. Without cleanup, 100 deploys = 10-20GB = $1-2/month. Low cost, but good hygiene.

### Shared Resources (`iac/teams/platform/aws/staging/shared/`)

| Resource | Terraform Type | Purpose | Notes |
|----------|---------------|---------|-------|
| Lambda execution role | `aws_iam_role` | Lambda assume role | Trust policy: `lambda.amazonaws.com` |
| DynamoDB policy | `aws_iam_role_policy` | Allow dedup table access | `dynamodb:PutItem`, `dynamodb:GetItem` on ferry-dedup table |
| Secrets Manager read policy | `aws_iam_role_policy` | Allow reading GitHub App secrets | `secretsmanager:GetSecretValue` on ferry secrets |
| CloudWatch Logs policy | `aws_iam_role_policy_attachment` | Allow Lambda logging | Attach `AWSLambdaBasicExecutionRole` managed policy |
| GitHub App secret | `aws_secretsmanager_secret` | Store GitHub App credentials | Name: `ferry/github-app` |
| GitHub App secret version | `aws_secretsmanager_secret_version` | Actual secret values | JSON: `{app_id, private_key, webhook_secret, installation_id}` |
| GHA OIDC provider | `aws_iam_openid_connect_provider` | GitHub Actions OIDC federation | Thumbprint for `token.actions.githubusercontent.com` |
| GHA deploy role | `aws_iam_role` | Self-deploy from GHA | Trust: OIDC provider, condition on repo + branch |
| GHA deploy policy | `aws_iam_role_policy` | Deploy permissions | ECR push, Lambda update, minimal scope |

**Secret structure (JSON in Secrets Manager):**
```json
{
  "app_id": "12345",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----",
  "webhook_secret": "whsec_...",
  "installation_id": "67890"
}
```

**Note:** The secret VERSION will be created with placeholder values in Terraform. Real values are populated manually after GitHub App registration (manual step in milestone). Use `lifecycle { ignore_changes = [secret_string] }` so Terraform does not overwrite manual updates.

### Ferry Backend (`iac/teams/platform/aws/staging/us_east_1/ferry_backend/`)

| Resource | Terraform Type | Purpose | Notes |
|----------|---------------|---------|-------|
| Lambda function | `aws_lambda_function` | Ferry webhook handler | Package type: Image, image_uri from ECR, 256MB memory, 30s timeout |
| Function URL | `aws_lambda_function_url` | HTTPS endpoint for GitHub webhooks | Auth type: NONE (Ferry validates HMAC itself) |
| DynamoDB table | `aws_dynamodb_table` | Webhook deduplication | PK: `pk` (S), SK: `sk` (S), TTL on `expires_at`, PAY_PER_REQUEST |
| CloudWatch log group | `aws_cloudwatch_log_group` | Lambda logs | Retention: 14 days (staging), name: `/aws/lambda/ferry-backend-staging` |

## Resource Configuration Details

### Lambda Function

```hcl
resource "aws_lambda_function" "ferry_backend" {
  function_name = "ferry-backend-staging"
  role          = data.terraform_remote_state.shared.outputs.lambda_execution_role_arn
  package_type  = "Image"
  image_uri     = "${data.terraform_remote_state.ecr.outputs.repository_url}:latest"
  memory_size   = 256
  timeout       = 30
  architectures = ["arm64"]  # Graviton: 20% cheaper, 15-20% faster for Python

  environment {
    variables = {
      FERRY_APP_ID          = data.aws_secretsmanager_secret_version.github_app.secret_string_map["app_id"]
      FERRY_PRIVATE_KEY     = data.aws_secretsmanager_secret_version.github_app.secret_string_map["private_key"]
      FERRY_WEBHOOK_SECRET  = data.aws_secretsmanager_secret_version.github_app.secret_string_map["webhook_secret"]
      FERRY_INSTALLATION_ID = data.aws_secretsmanager_secret_version.github_app.secret_string_map["installation_id"]
      FERRY_TABLE_NAME      = aws_dynamodb_table.dedup.name
      FERRY_LOG_LEVEL       = "DEBUG"  # Staging verbosity
    }
  }

  lifecycle {
    ignore_changes = [image_uri]  # Updated by CI/CD, not Terraform
  }
}
```

**Key decisions:**
- **arm64 (Graviton):** 20% cheaper per ms, measurably faster for Python workloads. The ECR image must be built for `linux/arm64`. Use `--platform linux/arm64` in `docker build`.
- **256MB memory:** Ferry backend does HTTP calls (GitHub API) and DynamoDB writes. No heavy computation. 256MB is generous. Can tune down to 128MB if cold starts are acceptable.
- **30s timeout:** GitHub expects webhook response within 10 seconds. 30s gives headroom for retries/slow GitHub API responses. Lambda Function URL has no separate timeout.
- **`ignore_changes = [image_uri]`:** Critical. Terraform manages infra configuration; CI/CD manages deployed code. Without this, every `terraform apply` would revert the Lambda to whatever image_uri is in state.

### Lambda Function URL

```hcl
resource "aws_lambda_function_url" "ferry_webhook" {
  function_name      = aws_lambda_function.ferry_backend.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = ["*"]
    allow_methods = ["POST"]
    allow_headers = ["content-type", "x-hub-signature-256", "x-github-delivery", "x-github-event"]
    max_age       = 86400
  }
}
```

**Auth type NONE:** GitHub sends webhooks as unauthenticated POST requests. Ferry validates authenticity via HMAC-SHA256 signature (the `x-hub-signature-256` header). IAM auth would prevent GitHub from reaching the endpoint.

**CORS:** Not strictly required for server-to-server webhook delivery. Included for potential browser-based health check or debugging tools. Costs nothing.

### DynamoDB Table

```hcl
resource "aws_dynamodb_table" "dedup" {
  name         = "ferry-dedup-staging"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false  # Staging: dedup is ephemeral, no backup needed
  }

  tags = {
    Environment = "staging"
    Service     = "ferry"
  }
}
```

**PAY_PER_REQUEST:** Ferry processes webhooks on-demand. Traffic is bursty (pushes happen in clusters). Provisioned capacity would be wasteful or require auto-scaling. Pay-per-request costs $1.25/million writes, $0.25/million reads. At staging volume (hundreds of writes/day), cost rounds to $0.00.

### ECR Repository

```hcl
resource "aws_ecr_repository" "ferry_backend" {
  name                 = "ferry/backend"
  image_tag_mutability = "MUTABLE"  # Allow :latest tag for simple deploys

  image_scanning_configuration {
    scan_on_push = true  # Free basic vulnerability scanning
  }

  encryption_configuration {
    encryption_type = "AES256"  # S3-managed encryption (free)
  }
}

resource "aws_ecr_lifecycle_policy" "ferry_backend" {
  repository = aws_ecr_repository.ferry_backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep last 10 tagged images"
        selection = {
          tagStatus   = "tagged"
          tagPrefixList = ["pr-", "main-"]
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}
```

### OIDC Provider for GitHub Actions

```hcl
resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["ffffffffffffffffffffffffffffffffffffffff"]  # AWS validates directly, thumbprint is legacy
}
```

**Thumbprint note:** AWS added native validation for the GitHub OIDC provider in 2023. The thumbprint is effectively ignored for github.com, but Terraform still requires the field. Use the placeholder value.

### GHA Deploy Role

```hcl
resource "aws_iam_role" "gha_deploy" {
  name = "ferry-gha-deploy-staging"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github_actions.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:OWNER/ferry:ref:refs/heads/main"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "gha_deploy" {
  name = "ferry-deploy-permissions"
  role = aws_iam_role.gha_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECRPush"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = "*"  # GetAuthorizationToken requires *
      },
      {
        Sid    = "LambdaUpdate"
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction"
        ]
        Resource = "arn:aws:lambda:us-east-1:*:function:ferry-backend-staging"
      }
    ]
  })
}
```

**OIDC condition:** Restricts to `repo:OWNER/ferry:ref:refs/heads/main` so only pushes to main on the ferry repo can assume this role. Replace `OWNER` with the actual GitHub org/user at implementation time.

## Remote State References

The 4 TF projects reference each other via `terraform_remote_state`:

```
backend/ --> (no dependencies, bootstrapped first)
ecr/     --> (no dependencies)
shared/  --> references ecr/ (for repository ARN in IAM policies)
ferry_backend/ --> references shared/ (IAM role ARN) + ecr/ (repository URL)
```

```hcl
# In ferry_backend/data.tf
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = "ferry-terraform-state-ACCOUNT_ID"
    key    = "teams/platform/aws/staging/shared/terraform.tfstate"
    region = "us-east-1"
  }
}

data "terraform_remote_state" "ecr" {
  backend = "s3"
  config = {
    bucket = "ferry-terraform-state-ACCOUNT_ID"
    key    = "global/cloud/aws/ecr/terraform.tfstate"
    region = "us-east-1"
  }
}
```

**State key convention:** Match directory path to state key path. Each TF project directory maps to a unique state key.

## Provider Configuration Pattern

Each TF project directory gets a `providers.tf`:

```hcl
terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  backend "s3" {
    bucket         = "ferry-terraform-state-ACCOUNT_ID"
    key            = "PATH/terraform.tfstate"  # Unique per project
    region         = "us-east-1"
    dynamodb_table = "ferry-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "ferry"
      Environment = "staging"
      ManagedBy   = "terraform"
    }
  }
}
```

**Exception:** The backend/ project itself uses local state initially (no `backend "s3"` block) until the bucket exists, then migrates.

## Apply Order

TF projects must be applied in dependency order:

1. **`global/cloud/aws/backend/`** -- S3 bucket + DynamoDB lock table (bootstrap, local state then migrate)
2. **`global/cloud/aws/ecr/`** -- ECR repository (depends on S3 backend existing)
3. **`teams/platform/aws/staging/shared/`** -- IAM roles, Secrets Manager, OIDC provider
4. **`teams/platform/aws/staging/us_east_1/ferry_backend/`** -- Lambda + Function URL + DynamoDB dedup table

Steps 2 and 3 can run in parallel (no dependency between them), but both must complete before step 4.

## Self-Deploy GHA Workflow Dependencies

The workflow needs these Terraform outputs:

| Output | From Project | Used For |
|--------|-------------|----------|
| `repository_url` | ecr/ | `docker tag` + `docker push` target |
| `lambda_function_name` | ferry_backend/ | `aws lambda update-function-code` |
| `gha_deploy_role_arn` | shared/ | `aws-actions/configure-aws-credentials` |
| `function_url` | ferry_backend/ | GitHub App webhook URL configuration |

## Alternatives Considered

| Category | Chosen | Alternative | Why Not |
|----------|--------|-------------|---------|
| IaC tool | Terraform | SAM (original v1 research) | Project switched to Terraform to match ConvergeBio/iac-tf patterns. SAM is simpler for pure Lambda but does not match the team's existing workflow (Digger for TF plan/apply). |
| IaC tool | Terraform | CDK | Heavy for 5-6 resources. Requires Node.js runtime. Does not match team conventions. |
| IaC tool | Terraform | Pulumi | Team uses Terraform. No reason to introduce another tool. |
| Module approach | Raw resources | terraform-aws-modules | Ferry has 5-6 AWS resources total. Modules add abstraction overhead with no payoff at this scale. See "Decision" section above. |
| Lambda architecture | arm64 (Graviton) | x86_64 | 20% cheaper, measurably faster for Python. Requires arm64-compatible container image (easy: `--platform linux/arm64`). |
| State backend | S3 + DynamoDB | Terraform Cloud | Self-hosted is simpler for a single-team project. No external service dependency. Free. |
| State backend | S3 + DynamoDB | HCP Terraform | Same reasoning. S3 backend is proven, well-documented, zero cost. |
| Secrets | Secrets Manager | SSM Parameter Store | Secrets Manager supports automatic rotation, JSON structured secrets, and cross-account access. SSM SecureString would work but SM is the standard for credentials. Costs $0.40/secret/month -- negligible. |
| Secrets | Secrets Manager | Environment variables only | Private key in Lambda env vars works but is less secure (visible in console, in TF state). SM allows rotation without redeploy. |

## File Layout Per TF Project

Following ConvergeBio/iac-tf conventions:

```
any-tf-project/
  providers.tf    # Backend config + provider block + default tags
  main.tf         # Primary resource definitions (or split into resource-specific files)
  variables.tf    # Input variables
  outputs.tf      # Output values (consumed by remote_state or GHA)
  data.tf         # Data sources + remote state references
  locals.tf       # Computed values (if needed)
```

For `ferry_backend/`, the small resource count means `main.tf` holds everything. No need for `lambda.tf`, `dynamodb.tf` splits when there is one of each.

## Version Verification Checklist

These versions are from training data and MUST be verified at implementation time:

| Item | Stated Version | How to Verify |
|------|---------------|---------------|
| AWS provider | ~> 5.80 | `registry.terraform.io/providers/hashicorp/aws/latest` |
| Terraform | >= 1.9.0 | `releases.hashicorp.com/terraform/` |
| Lambda arm64 + Python 3.14 | Assumed available | Check `public.ecr.aws/lambda/python` tags for `3.14` arm64 |
| OIDC thumbprint behavior | Placeholder works | AWS docs on GitHub OIDC provider setup |
| Function URL CORS config | Schema assumed | `registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function_url` |

**Highest risk:** Python 3.14 Lambda base image availability. If `public.ecr.aws/lambda/python:3.14` does not exist for arm64, fall back to a custom image based on `public.ecr.aws/lambda/provided:al2023` with Python 3.14 installed, or use Python 3.13 (the latest GA version likely available).

## Sources

- Terraform AWS provider documentation (registry.terraform.io) -- HIGH confidence on resource schemas, MEDIUM on exact version numbers
- ConvergeBio/iac-tf conventions (project memory) -- HIGH confidence
- Ferry backend source code (settings.py, handler.py, dedup.py) -- HIGH confidence on env vars and resource requirements
- AWS Lambda Function URL documentation -- HIGH confidence on auth model and CORS
- AWS OIDC provider documentation -- HIGH confidence on GitHub Actions federation
- Training data (through early 2025) -- MEDIUM confidence on version numbers
