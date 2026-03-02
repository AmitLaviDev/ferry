# Phase 13: Backend Core - Research

**Researched:** 2026-03-02
**Domain:** Terraform AWS infrastructure — Lambda (container image), Function URL, DynamoDB, CloudWatch
**Confidence:** HIGH

## Summary

Phase 13 creates a single Terraform project at `iac/aws/staging/us-east-1/ferry_backend/` that deploys four AWS resources: a Lambda function (arm64 container image from ECR), a Lambda Function URL (auth=NONE), a DynamoDB dedup table (PAY_PER_REQUEST with TTL), and a CloudWatch log group (30-day retention). The project uses `terraform_remote_state` data sources to reference IAM role ARNs and secret names from the existing shared and ECR projects.

All Terraform resource types needed are well-established (`aws_lambda_function`, `aws_lambda_function_url`, `aws_dynamodb_table`, `aws_cloudwatch_log_group`) with stable APIs in the AWS provider ~6.0. The project follows the same patterns already established in Phases 11-12 (S3 backend, `default_tags`, no assume_role for now, raw resources instead of modules). The main implementation consideration is wiring `lifecycle { ignore_changes = [image_uri] }` on the Lambda so Terraform owns infrastructure while GHA owns the deployed code.

**Primary recommendation:** Create a single Terraform project with 5-6 files following existing conventions. Use `terraform_remote_state` to pull IAM role ARN from shared project and ECR image URI from ECR project. The Lambda initially runs the placeholder image; GHA will update it in Phase 14.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Lambda Configuration: 256 MB memory, 30s timeout, arm64, 512 MB ephemeral storage (default), Function URL auth=NONE, no reserved concurrency
- TF Project Location: `iac/aws/staging/us-east-1/ferry_backend/`
- DynamoDB Table: name `ferry-webhook-dedup`, pk `pk` (String, HASH), sk `sk` (String, RANGE), TTL on `expires_at`, PAY_PER_REQUEST billing — matches existing `dedup.py` code exactly
- Environment Variable Contract:
  - `FERRY_APP_ID_SECRET` -> Secrets Manager secret name for GitHub App ID
  - `FERRY_PRIVATE_KEY_SECRET` -> Secrets Manager secret name for private key
  - `FERRY_WEBHOOK_SECRET_SECRET` -> Secrets Manager secret name for webhook secret
  - `FERRY_TABLE_NAME` -> DynamoDB table name (`ferry-webhook-dedup`)
  - `FERRY_LOG_LEVEL` -> set explicitly in TF (default: `INFO`)
- Note: settings.py will need updating (Phase 14 scope) to resolve secrets from names at cold start

### Claude's Discretion
- `FERRY_INSTALLATION_ID` handling — TF variable or Secrets Manager secret, whichever fits the pattern better
- CloudWatch log group naming convention
- Terraform file organization within the ferry_backend project (providers.tf, main.tf, variables.tf, outputs.tf pattern)
- How to reference remote state from shared IAM and ECR projects

### Deferred Ideas (OUT OF SCOPE)
- IaC directory restructure + state migration — captured as Phase 12.1 (must execute before Phase 13)
- settings.py modification to resolve secrets from names at cold start — Phase 14 (DEPLOY-03)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | Ferry Lambda deployed as arm64 container image with Function URL (auth=NONE) | `aws_lambda_function` with `package_type = "Image"`, `architectures = ["arm64"]`, `image_uri` from ECR remote state; `aws_lambda_function_url` with `authorization_type = "NONE"`. Python 3.14 base image confirmed available on Lambda (GA since Nov 2025). `lifecycle { ignore_changes = [image_uri] }` per project convention. |
| INFRA-02 | DynamoDB dedup table with PAY_PER_REQUEST billing and TTL on expires_at | `aws_dynamodb_table` with `billing_mode = "PAY_PER_REQUEST"`, `hash_key = "pk"`, `range_key = "sk"`, `ttl { attribute_name = "expires_at", enabled = true }`. Schema matches `dedup.py` exactly. |
| INFRA-03 | CloudWatch log group with 30-day retention | `aws_cloudwatch_log_group` with `name = "/aws/lambda/ferry-backend"`, `retention_in_days = 30`. Must be created before Lambda to avoid auto-creation without retention. |
| INFRA-04 | Lambda env vars reference Secrets Manager secret names and DynamoDB table name via Terraform | Environment block with `FERRY_APP_ID_SECRET`, `FERRY_PRIVATE_KEY_SECRET`, `FERRY_WEBHOOK_SECRET_SECRET` (secret names from remote state), `FERRY_TABLE_NAME` (from DynamoDB resource), `FERRY_LOG_LEVEL` (TF variable). All values come from Terraform resources/data sources, not hardcoded. |
</phase_requirements>

## Standard Stack

### Core
| Library/Tool | Version | Purpose | Why Standard |
|--------------|---------|---------|--------------|
| hashicorp/aws provider | ~> 6.0 | AWS resource management | Already pinned in all existing TF projects |
| Terraform | ~> 1.12.0 | IaC orchestration | Already pinned in all existing TF projects |

### Resources Used
| Resource Type | Purpose | Confidence |
|---------------|---------|------------|
| `aws_lambda_function` | Deploy container-image Lambda | HIGH — verified in provider docs |
| `aws_lambda_function_url` | Public HTTP endpoint for webhooks | HIGH — verified in provider docs |
| `aws_dynamodb_table` | Webhook dedup table | HIGH — verified in provider docs |
| `aws_cloudwatch_log_group` | Structured logging with retention | HIGH — verified in provider docs |

### Data Sources Used
| Data Source | Purpose | Confidence |
|-------------|---------|------------|
| `terraform_remote_state.shared` | IAM role ARN, secret names | HIGH — pattern exists in `staging/aws/shared/data.tf` |
| `terraform_remote_state.ecr` | ECR repository URL for image_uri | HIGH — pattern exists in `staging/aws/shared/data.tf` |
| `aws_caller_identity.current` | Account ID (if needed) | HIGH — used in existing projects |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `aws_lambda_function` | terraform-aws-modules/lambda | Module adds abstraction overhead for 1 Lambda — out of scope per REQUIREMENTS.md |
| `terraform_remote_state` | `aws_iam_role` data source | Remote state is cleaner, avoids hardcoding names, already established pattern |

## Architecture Patterns

### Recommended Project Structure
```
iac/aws/staging/us-east-1/ferry_backend/
├── providers.tf      # S3 backend config + AWS provider with default_tags
├── data.tf           # terraform_remote_state (shared, ecr) + aws_caller_identity
├── main.tf           # Lambda function, Function URL, DynamoDB table, CloudWatch log group
├── variables.tf      # region, log_level, installation_id
└── outputs.tf        # function_url, dynamodb_table_name, log_group_name
```

This follows the ConvergeBio/iac-tf convention and matches the existing `iac/staging/aws/shared/` (soon `iac/aws/staging/shared/`) project structure.

### Pattern 1: Remote State References for Cross-Project Dependencies
**What:** Use `terraform_remote_state` data sources to pull outputs from the shared IAM project and the ECR project, avoiding hardcoded ARNs or names.
**When to use:** When one TF project needs values from another TF project's outputs.
**Example:**
```hcl
# Source: existing pattern from iac/staging/aws/shared/data.tf
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = "ferry-global-terraform-state"
    key    = "aws/staging/shared/terraform.tfstate"
    region = "us-east-1"
  }
}

data "terraform_remote_state" "ecr" {
  backend = "s3"
  config = {
    bucket = "ferry-global-terraform-state"
    key    = "global/cloud/aws/ecr/terraform.tfstate"
    region = "us-east-1"
  }
}

# Usage:
# data.terraform_remote_state.shared.outputs.lambda_execution_role_arn
# data.terraform_remote_state.shared.outputs.github_app_secret_arns
# data.terraform_remote_state.ecr.outputs.repository_url
```

### Pattern 2: Lambda with Container Image + lifecycle ignore
**What:** Deploy Lambda from ECR container image, with `lifecycle { ignore_changes = [image_uri] }` so Terraform owns infrastructure but GHA owns the deployed code version.
**When to use:** When Lambda code is deployed separately from infrastructure (CI/CD pipeline updates `image_uri`).
**Example:**
```hcl
resource "aws_lambda_function" "backend" {
  function_name = "ferry-backend"
  role          = data.terraform_remote_state.shared.outputs.lambda_execution_role_arn
  package_type  = "Image"
  image_uri     = "${data.terraform_remote_state.ecr.outputs.repository_url}:latest"
  architectures = ["arm64"]
  memory_size   = 256
  timeout       = 30

  environment {
    variables = {
      FERRY_APP_ID_SECRET         = "ferry/github-app/app-id"
      FERRY_PRIVATE_KEY_SECRET    = "ferry/github-app/private-key"
      FERRY_WEBHOOK_SECRET_SECRET = "ferry/github-app/webhook-secret"
      FERRY_TABLE_NAME            = aws_dynamodb_table.dedup.name
      FERRY_LOG_LEVEL             = var.log_level
    }
  }

  depends_on = [aws_cloudwatch_log_group.backend]

  lifecycle {
    ignore_changes = [image_uri]
  }
}
```

### Pattern 3: CloudWatch Log Group Created Before Lambda
**What:** Explicitly create the log group in Terraform before the Lambda function, with `depends_on` ensuring ordering.
**When to use:** Always, when you want retention policy control. If Lambda creates the log group itself, it gets infinite retention.
**Example:**
```hcl
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/aws/lambda/ferry-backend"
  retention_in_days = 30
}
```

### Anti-Patterns to Avoid
- **Hardcoded ARNs/account IDs:** Use `terraform_remote_state` outputs or `aws_caller_identity` data source instead
- **Missing lifecycle ignore on image_uri:** Without it, every `terraform plan` after a GHA deploy would show a diff and try to revert the image
- **Letting Lambda auto-create log group:** Results in infinite retention and log group not managed by Terraform
- **Putting secret VALUES in environment variables:** Phase 13 passes secret NAMES; Phase 14 modifies settings.py to resolve them at runtime

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-project value sharing | Hardcoded ARNs in variables | `terraform_remote_state` data source | Single source of truth, auto-updates when upstream changes |
| Lambda log group | Let Lambda auto-create | Explicit `aws_cloudwatch_log_group` | Control retention, manage in Terraform, prevent orphaned log groups |

**Key insight:** This phase is pure Terraform with no custom code. Every resource is a standard AWS resource with well-documented configuration. The complexity is in the wiring (remote state references, env var contract), not in the resources themselves.

## Common Pitfalls

### Pitfall 1: Log Group Auto-Creation
**What goes wrong:** Lambda creates its own log group on first invocation with infinite retention, which then conflicts with Terraform trying to create the same log group.
**Why it happens:** Lambda automatically creates `/aws/lambda/<function-name>` on first invocation if it doesn't exist.
**How to avoid:** Create `aws_cloudwatch_log_group` with `depends_on` from Lambda, or create it first and ensure the Lambda's IAM role only has `logs:CreateLogStream` and `logs:PutLogEvents` (not `logs:CreateLogGroup`). The existing IAM policy in `iac/staging/aws/shared/iam.tf` already scopes to `logs:CreateLogStream` and `logs:PutLogEvents` only — no `logs:CreateLogGroup`.
**Warning signs:** `terraform apply` errors with "log group already exists" after first Lambda invocation.

### Pitfall 2: image_uri Drift Without lifecycle ignore
**What goes wrong:** After GHA deploys a new image, `terraform plan` shows image_uri as changed and wants to revert to the Terraform-specified tag.
**Why it happens:** `image_uri` includes the full digest/tag, which changes on every deploy.
**How to avoid:** Add `lifecycle { ignore_changes = [image_uri] }` to the Lambda resource.
**Warning signs:** Terraform plans showing "~ image_uri" diffs after CI/CD deploys.

### Pitfall 3: Secret Names vs ARNs vs Values
**What goes wrong:** Confusion between passing secret ARNs, secret names, or actual secret values as environment variables.
**Why it happens:** Three different patterns exist in the ecosystem. CONTEXT.md locks this to **secret names**.
**How to avoid:** Env vars contain the Secrets Manager secret NAME (e.g., `ferry/github-app/app-id`). The app code (Phase 14 changes to settings.py) will resolve these names to values at cold start using `boto3 secretsmanager get_secret_value`.
**Warning signs:** Lambda crashes with "secret not found" — check if name vs ARN mismatch.

### Pitfall 4: DynamoDB Attribute Definitions
**What goes wrong:** Defining attributes in `aws_dynamodb_table` that are not used as keys or in indexes causes Terraform errors.
**Why it happens:** Terraform requires `attribute` blocks ONLY for hash_key, range_key, and GSI/LSI keys. The `expires_at` and `created_at` fields are NOT defined as attributes — they're schemaless DynamoDB columns.
**How to avoid:** Only define `pk` and `sk` as attributes. TTL references `expires_at` by name in the `ttl` block but does NOT need an `attribute` block.
**Warning signs:** Terraform error "All attributes must be indexed" if you define non-key attributes.

### Pitfall 5: Backend Key for New Project
**What goes wrong:** Using the wrong S3 key convention for the new `ferry_backend` project.
**Why it happens:** The key convention changed during Phase 12.1. New projects must follow the new convention.
**How to avoid:** Use key `aws/staging/us-east-1/ferry_backend/terraform.tfstate` — matching the directory path under `iac/`.
**Warning signs:** State stored in wrong location, hard to find later.

### Pitfall 6: Phase 12.1 Migration Must Run First
**What goes wrong:** The migration script hasn't been run yet — directories are still in old layout, remote state references point to old keys that don't exist yet.
**Why it happens:** Phase 12.1 code changes are committed but the migration script is a manual step.
**How to avoid:** Verify migration completed before creating Phase 13 project. After migration, shared project state is at `aws/staging/shared/terraform.tfstate` and ECR state is at `global/cloud/aws/ecr/terraform.tfstate`.
**Warning signs:** `terraform init` fails with "state not found" errors on remote state data sources.

## Code Examples

Verified patterns from official AWS provider documentation and existing project code:

### Complete Lambda Function (Container Image, arm64)
```hcl
# Source: hashicorp/aws provider docs + project convention (lifecycle ignore)
resource "aws_lambda_function" "backend" {
  function_name = "ferry-backend"
  role          = data.terraform_remote_state.shared.outputs.lambda_execution_role_arn
  package_type  = "Image"
  image_uri     = "${data.terraform_remote_state.ecr.outputs.repository_url}:latest"
  architectures = ["arm64"]
  memory_size   = 256
  timeout       = 30

  environment {
    variables = {
      FERRY_APP_ID_SECRET         = "ferry/github-app/app-id"
      FERRY_PRIVATE_KEY_SECRET    = "ferry/github-app/private-key"
      FERRY_WEBHOOK_SECRET_SECRET = "ferry/github-app/webhook-secret"
      FERRY_TABLE_NAME            = aws_dynamodb_table.dedup.name
      FERRY_LOG_LEVEL             = var.log_level
    }
  }

  depends_on = [aws_cloudwatch_log_group.backend]

  lifecycle {
    ignore_changes = [image_uri]
  }

  tags = {
    Name = "ferry-backend"
  }
}
```

### Lambda Function URL (auth=NONE)
```hcl
# Source: hashicorp/aws provider docs
resource "aws_lambda_function_url" "backend" {
  function_name      = aws_lambda_function.backend.function_name
  authorization_type = "NONE"
}
```

### DynamoDB Dedup Table
```hcl
# Source: hashicorp/aws provider docs + dedup.py schema
resource "aws_dynamodb_table" "dedup" {
  name         = "ferry-webhook-dedup"
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

  tags = {
    Name = "ferry-webhook-dedup"
  }
}
```

### CloudWatch Log Group
```hcl
# Source: hashicorp/aws provider docs
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/aws/lambda/ferry-backend"
  retention_in_days = 30

  tags = {
    Name = "ferry-backend-logs"
  }
}
```

### providers.tf (following existing convention)
```hcl
terraform {
  required_version = "~> 1.12.0"

  backend "s3" {
    bucket       = "ferry-global-terraform-state"
    key          = "aws/staging/us-east-1/ferry_backend/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      ManagedBy = "terraform"
      Project   = "ferry"
    }
  }
}
```

## Discretion Recommendations

### FERRY_INSTALLATION_ID Handling
**Recommendation:** Add as a Secrets Manager secret — fits the "resolve at cold start" pattern. However, since Phase 14 handles settings.py changes, and the installation ID is only known after GitHub App registration (also Phase 14), the simplest approach is to add `FERRY_INSTALLATION_ID` as a TF variable with a placeholder default. Phase 14 can add it to Secrets Manager if desired.

**Alternative:** Make it a TF variable with a placeholder value (e.g., `0`). This keeps Phase 13 simpler and defers the decision to Phase 14 where the GitHub App is actually registered.

**Chosen approach:** Use a TF variable with placeholder value `"0"` passed as `FERRY_INSTALLATION_ID` env var. Phase 14 can update this via `terraform apply` with the real value, or migrate to Secrets Manager if preferred.

### CloudWatch Log Group Naming
**Recommendation:** `/aws/lambda/ferry-backend` — this is the AWS convention for Lambda log groups. Lambda expects this exact pattern and will write to it automatically. Deviating would require custom logging configuration.

### Terraform File Organization
**Recommendation:** Follow the ConvergeBio/iac-tf convention exactly:
- `providers.tf` — backend + provider
- `data.tf` — remote state data sources
- `main.tf` — all four resources (Lambda, Function URL, DynamoDB, CloudWatch)
- `variables.tf` — input variables
- `outputs.tf` — outputs

All four resources go in `main.tf` because they're tightly coupled (Lambda references DynamoDB table name, depends on log group). Splitting into separate files (lambda.tf, dynamodb.tf) would be over-engineering for 4 resources.

### Remote State References
**Recommendation:** Two `terraform_remote_state` data sources:
1. `shared` — for `lambda_execution_role_arn` and `github_app_secret_arns`
2. `ecr` — for `repository_url`

The secret names can be derived from `github_app_secret_arns` map keys, or hardcoded as they match the known `for_each` keys in `secrets.tf`. Since the secret names are `ferry/github-app/{key}` and the keys are `app-id`, `private-key`, `webhook-secret`, the env var values are deterministic. However, to maintain the "no hardcoded values" principle, extract the names from the remote state:

```hcl
# The shared project outputs github_app_secret_arns as a map:
# { "app-id" = "arn:...", "private-key" = "arn:...", "webhook-secret" = "arn:..." }
# But we need secret NAMES, not ARNs.
# Secret names are deterministic: "ferry/github-app/${key}"
# Since secrets.tf uses name = "ferry/github-app/${each.key}", we know the names.
```

The shared project doesn't currently output secret names — only ARNs. Two options:
1. **Add a `github_app_secret_names` output to the shared project** (requires modifying an upstream project)
2. **Hardcode the names** since they follow a deterministic pattern from the `for_each` keys

**Chosen approach:** Hardcode the secret names directly as `"ferry/github-app/app-id"`, `"ferry/github-app/private-key"`, `"ferry/github-app/webhook-secret"`. These are deterministic from the `secrets.tf` code and won't change. Adding a new output to the shared project just to avoid hardcoding three strings is over-engineering.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| API Gateway + Lambda | Lambda Function URL | Apr 2022 | Free, simpler, sufficient for webhooks |
| ZIP package Lambda | Container image Lambda | Dec 2020 | Better for complex deps, consistent local/prod |
| Provisioned capacity DynamoDB | PAY_PER_REQUEST | Nov 2018 | No capacity planning for low-traffic tables |
| Python 3.12 Lambda | Python 3.14 Lambda | Nov 2025 | Latest runtime, matches project Python version |

## Open Questions

1. **Migration script execution status**
   - What we know: Phase 12.1 code changes are committed (backend keys updated, migration script created)
   - What's unclear: Whether the user has actually run `scripts/migrate-iac-layout.sh` yet
   - Recommendation: The plan should note this as a prerequisite. The user must run the migration script before `terraform init` on the ferry_backend project, otherwise remote state references will fail.

2. **FERRY_INSTALLATION_ID value**
   - What we know: Installation ID is only known after GitHub App registration (Phase 14)
   - What's unclear: Whether to include it as a placeholder env var now or defer entirely
   - Recommendation: Include as TF variable with placeholder default `"0"`. The Lambda will fail at runtime (expected — secrets aren't populated either until Phase 14), but the infrastructure is complete.

## Sources

### Primary (HIGH confidence)
- hashicorp/aws provider docs — [aws_lambda_function](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function), [aws_lambda_function_url](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function_url), [aws_dynamodb_table](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/dynamodb_table), [aws_cloudwatch_log_group](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) — verified via raw GitHub markdown docs
- Existing project code — `iac/staging/aws/shared/` (providers.tf, data.tf, iam.tf, secrets.tf, outputs.tf, variables.tf) — verified by reading actual files
- Existing app code — `backend/src/ferry_backend/webhook/dedup.py` (DynamoDB schema), `backend/src/ferry_backend/settings.py` (env var contract), `backend/src/ferry_backend/webhook/handler.py` (handler structure)

### Secondary (MEDIUM confidence)
- [Python 3.14 Lambda runtime GA announcement](https://aws.amazon.com/blogs/compute/python-3-14-runtime-now-available-in-aws-lambda/) — confirmed GA since Nov 19, 2025
- [aws/aws-lambda-base-images#327](https://github.com/aws/aws-lambda-base-images/issues/327) — Python 3.14 base image confirmed available

### Tertiary (LOW confidence)
- None — all findings verified against primary or secondary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — using exact same Terraform version, provider, and patterns as Phases 11-12
- Architecture: HIGH — all resource types are well-documented, patterns verified against existing project code
- Pitfalls: HIGH — pitfalls identified from real patterns in existing code (lifecycle ignore, log group creation order, DynamoDB attribute definitions)

**Research date:** 2026-03-02
**Valid until:** 2026-04-01 (stable Terraform resources, unlikely to change)
