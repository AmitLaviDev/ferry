# Phase 11: Bootstrap + Global Resources - Research

**Researched:** 2026-02-28
**Domain:** Terraform IaC bootstrap, ECR, container images
**Confidence:** HIGH

## Summary

Phase 11 creates the foundational AWS infrastructure that all subsequent IaC phases depend on: an S3 bucket for Terraform remote state with native S3 locking (`use_lockfile = true`), an ECR repository for the Ferry backend Lambda container images, and a placeholder container image so the Lambda resource can be created in Phase 13.

The bootstrap pattern is well-established: create the S3 state bucket using Terraform with local state, then migrate that state into the newly-created S3 backend using `terraform init -migrate-state -force-copy`. This is a one-time operation automated by an idempotent `scripts/bootstrap.sh`. All resources use raw Terraform (no modules), Terraform v1.14.x with AWS provider ~> 6.0, and follow the ConvergeBio file-split conventions.

**Primary recommendation:** Two small Terraform projects (`iac/global/aws/backend/` and `iac/global/aws/ecr/`), each with the standard file split, orchestrated by a single idempotent bootstrap script. The placeholder image is a minimal Python Lambda handler built from a Dockerfile in `iac/global/aws/ecr/placeholder/`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Follow ConvergeBio pattern: `global/aws/` for account-wide resources, `environments/staging/{region}/` for per-environment
- Global resources: `iac/global/aws/backend/` (S3 state bucket), `iac/global/aws/ecr/` (ECR repo)
- Per-environment resources (future phases): `iac/environments/staging/us-east-1/iam/`, `iac/environments/staging/us-east-1/app/`
- Include region level in environment path (`us-east-1`) per ConvergeBio convention
- Each TF project has standard file split: providers.tf, main.tf, variables.tf, outputs.tf, data.tf, locals.tf
- S3 state bucket: `ferry-terraform-state`
- ECR repo: `lambda-ferry-backend` (one ECR repo per Lambda, naming pattern: `lambda-ferry-{lambda-name}`)
- State keys mirror directory structure: e.g., `global/aws/ecr/terraform.tfstate`
- Region: us-east-1
- Dedicated AWS account for Ferry (no project prefixes needed for uniqueness)
- Assume-role provider pattern in all TF projects (not bare credentials)
- No DynamoDB lock table -- use Terraform native `use_lockfile = true`
- Idempotent `scripts/bootstrap.sh` handles full sequence: S3 init with local state -> apply -> add backend config -> init -migrate-state; ECR terraform apply; placeholder image build+tag+push
- Script checks state at each step, skips what's already done -- safe to re-run
- Minimal hello-world placeholder image (not just a base image pull) -- returns health check response

### Claude's Discretion
- Exact Terraform resource configurations (encryption, versioning, tags)
- Hello-world Dockerfile implementation details
- Bootstrap script error handling and logging
- ECR lifecycle policy specifics (keep last 10 per requirements)

### Deferred Ideas (OUT OF SCOPE)
- Python package restructuring (ferry_backend -> ferry.backend namespace package) -- potential future tech debt phase
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BOOT-01 | Terraform state stored in S3 with locking in Ferry's AWS account | S3 backend with `use_lockfile = true` (native S3 locking, no DynamoDB). Terraform 1.14.x fully supports this. Bootstrap pattern: local state -> apply -> migrate to S3. |
| BOOT-02 | ECR repository (`lambda-ferry-backend`) exists with lifecycle policy (keep last 10 images) | `aws_ecr_repository` + `aws_ecr_lifecycle_policy` with `countType: imageCountMoreThan`, `countNumber: 10`. Standard Terraform pattern. |
| BOOT-03 | Placeholder container image pushed to ECR to unblock Lambda creation | Minimal Dockerfile using `public.ecr.aws/lambda/python:3.14` (confirmed available, arm64 supported). Hello-world handler returning health check JSON. Built and pushed by bootstrap script. |
</phase_requirements>

## Standard Stack

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| Terraform | ~> 1.14.x (latest 1.14.5) | Infrastructure as Code | Current stable. Supports `use_lockfile = true` natively (introduced ~1.10, stable since 1.11). |
| AWS Provider | ~> 6.0 (latest 6.33.0) | AWS resource management | Current major version. No breaking changes affecting S3/ECR resources vs v5. |
| S3 Backend | built-in | Remote state storage | Standard pattern for AWS Terraform state management |

### Supporting
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| Docker | any recent | Build placeholder image | Bootstrap script builds and pushes the placeholder image |
| AWS CLI v2 | any recent | ECR login, manual verification | `aws ecr get-login-password` for Docker auth to ECR |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `use_lockfile = true` | DynamoDB lock table | DynamoDB adds extra resource + cost; native locking is simpler and officially supported since Terraform 1.11. No reason to use DynamoDB for new projects. |
| Raw TF resources | terraform-aws-modules | Only 5-6 resources total; modules add abstraction overhead. Raw resources are simpler and more transparent. (Decision: locked) |
| Separate placeholder Dockerfile | `docker pull` + `docker tag` of base image | User decision: minimal hello-world handler that returns health check, not just a retagged base image. |

## Architecture Patterns

### Recommended Project Structure
```
iac/
  global/
    aws/
      backend/              # S3 state bucket (bootstrapped first)
        providers.tf        # Backend config (initially local, then S3)
        main.tf             # S3 bucket + versioning + encryption + public access block
        variables.tf        # var.bucket_name, var.region
        outputs.tf          # bucket ARN, bucket name
      ecr/                  # ECR repository
        providers.tf        # S3 backend config
        main.tf             # ECR repo + lifecycle policy
        variables.tf        # var.repository_name
        outputs.tf          # repo URL, repo ARN
        placeholder/        # Placeholder image source
          Dockerfile        # Minimal Lambda handler image
          app.py            # Hello-world handler
scripts/
  bootstrap.sh              # Orchestrates full bootstrap sequence
```

### Pattern 1: S3 Backend Bootstrap (Chicken-and-Egg)
**What:** Create the S3 state bucket using Terraform with local state, then migrate that state into S3.
**When to use:** First-time setup of any Terraform project needing remote state.
**Sequence:**
1. Write `iac/global/aws/backend/` TF files with NO backend block (or with backend commented out)
2. `terraform init` (uses local state)
3. `terraform apply -auto-approve` (creates S3 bucket)
4. Add/uncomment the S3 backend block in `providers.tf`
5. `terraform init -migrate-state -force-copy` (migrates local state to S3)

**Example providers.tf (after migration):**
```hcl
terraform {
  required_version = "~> 1.14"

  backend "s3" {
    bucket         = "ferry-terraform-state"
    key            = "global/aws/backend/terraform.tfstate"
    region         = "us-east-1"
    use_lockfile   = true
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

  assume_role {
    role_arn = var.assume_role_arn
  }
}
```

### Pattern 2: S3 State Bucket Resources (Separate Resources)
**What:** Since AWS provider v4+, S3 bucket configuration uses separate resources for versioning, encryption, and public access.
**Why:** Terraform cannot auto-detect changes to inline versioning/encryption blocks. Separate resources are the official recommendation.

**Example main.tf:**
```hcl
resource "aws_s3_bucket" "state" {
  bucket = var.bucket_name

  tags = {
    Name        = var.bucket_name
    ManagedBy   = "terraform"
    Purpose     = "terraform-state"
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

### Pattern 3: ECR with Lifecycle Policy
**What:** ECR repository with a lifecycle policy that expires old images.
**Example main.tf:**
```hcl
resource "aws_ecr_repository" "backend" {
  name                 = var.repository_name
  image_tag_mutability = "MUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name      = var.repository_name
    ManagedBy = "terraform"
  }
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
```

### Pattern 4: Placeholder Container Image
**What:** Minimal Lambda handler image that returns a health check response.
**Why:** Lambda creation in Phase 13 requires a valid ECR image URI. Without a placeholder, you get a circular dependency.

**Example Dockerfile:**
```dockerfile
FROM public.ecr.aws/lambda/python:3.14

COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.handler"]
```

**Example app.py:**
```python
def handler(event, context):
    return {
        "statusCode": 200,
        "body": '{"status": "placeholder", "service": "ferry-backend"}'
    }
```

### Pattern 5: Idempotent Bootstrap Script
**What:** Bash script that orchestrates the full bootstrap, checking state at each step.
**Key techniques:**
- Check if S3 bucket exists: `aws s3api head-bucket --bucket $BUCKET 2>/dev/null`
- Check if ECR repo exists: `aws ecr describe-repositories --repository-names $REPO 2>/dev/null`
- Check if placeholder image exists: `aws ecr describe-images --repository-name $REPO --image-ids imageTag=placeholder 2>/dev/null`
- Check if Terraform state is already remote: look for `.terraform/terraform.tfstate` backend type
- Use `set -euo pipefail` for strict error handling
- Use colored output/logging for step visibility

### Anti-Patterns to Avoid
- **Hardcoding AWS account IDs in Terraform:** Use `data.aws_caller_identity.current.account_id` instead
- **Putting backend block in variables:** Backend configuration cannot use variables, expressions, or references. Values must be literals.
- **Skipping versioning on state bucket:** State corruption without versioning means total loss. Always enable versioning.
- **Using `force_delete = true` on ECR in production:** Only appropriate for dev/test. For staging, keep `false` (default).
- **Building placeholder image for x86_64 when Lambda is arm64:** The placeholder must match the Lambda architecture. Use `--platform linux/arm64` in Docker build.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| S3 state locking | DynamoDB table + custom logic | `use_lockfile = true` | Native Terraform feature since v1.10, zero extra infrastructure |
| ECR lifecycle management | Cron job or Lambda to clean old images | `aws_ecr_lifecycle_policy` | Built-in ECR feature, managed by AWS |
| Docker ECR auth | Manual token management | `aws ecr get-login-password \| docker login` | Standard AWS CLI pattern, handles token refresh |
| Backend config templating | sed/envsubst on .tf files | Terraform partial backend config (`-backend-config`) | Official Terraform feature for dynamic backend values |

**Key insight:** This phase is pure infrastructure plumbing. Every component has a well-established Terraform pattern. The only custom code is the bootstrap script and the trivial placeholder handler.

## Common Pitfalls

### Pitfall 1: Backend Block Cannot Use Variables
**What goes wrong:** Trying to use `var.bucket_name` or `local.region` in the backend block.
**Why it happens:** Terraform processes the backend block before evaluating any variables, locals, or data sources.
**How to avoid:** Use literal strings in the backend block. If you need dynamic values, use `-backend-config` flags or `.tfbackend` files.
**Warning signs:** `Error: Variables not allowed` during `terraform init`.

### Pitfall 2: State Migration Prompts Block Automation
**What goes wrong:** `terraform init -migrate-state` hangs waiting for interactive confirmation.
**Why it happens:** By default, migration asks for confirmation.
**How to avoid:** Use `terraform init -migrate-state -force-copy` which answers "yes" to all prompts.
**Warning signs:** Script hangs at "Do you want to copy existing state to the new backend?"

### Pitfall 3: S3 Bucket Already Exists (Re-Run)
**What goes wrong:** `terraform apply` fails because the S3 bucket name is globally unique and already taken.
**Why it happens:** S3 bucket names are globally unique across all AWS accounts. If bootstrap was partially run, the bucket exists but Terraform doesn't know about it (local state may be lost).
**How to avoid:** The bootstrap script should check if the bucket exists before running apply. If it exists and state is local, use `terraform import` to bring it under management.
**Warning signs:** `BucketAlreadyOwnedByYou` or `BucketAlreadyExists` errors.

### Pitfall 4: ECR Lifecycle Policy Timing
**What goes wrong:** Images don't get cleaned up immediately after policy creation.
**Why it happens:** ECR evaluates lifecycle policies asynchronously. AWS documentation states images become expired "within 24 hours" of meeting criteria.
**How to avoid:** Don't write tests that expect immediate cleanup. The policy is correct if it's attached; cleanup happens on AWS's schedule.
**Warning signs:** None -- this is expected behavior.

### Pitfall 5: Placeholder Image Architecture Mismatch
**What goes wrong:** Lambda fails to start with "exec format error" at runtime.
**Why it happens:** Placeholder image was built for x86_64 but Lambda is configured for arm64 (or vice versa).
**How to avoid:** Explicitly use `--platform linux/arm64` in `docker build` since the Lambda will be arm64 (per INFRA-01 in Phase 13).
**Warning signs:** Lambda invocation returns "Runtime.ExitError" with no useful log output.

### Pitfall 6: Bootstrap Script Assume-Role During Bootstrap
**What goes wrong:** The very first `terraform apply` needs AWS credentials, but assume-role might not be configured yet.
**Why it happens:** The bootstrap is the first operation in a new account. The assume-role target may not exist yet.
**How to avoid:** Bootstrap script can use direct credentials (environment variables or profile) for the initial bootstrap, then all subsequent TF projects use assume-role. Alternatively, the bootstrap assume-role target can be created manually or with CloudFormation first.
**Warning signs:** `AccessDenied` or `AssumeRoleUnauthorizedAccess` errors.

## Code Examples

### S3 Backend Configuration (providers.tf for backend project)
```hcl
# Source: HashiCorp official docs
# https://developer.hashicorp.com/terraform/language/backend/s3
terraform {
  required_version = "~> 1.14"

  # NOTE: During bootstrap, this block is initially commented out.
  # After the S3 bucket is created, uncomment and run:
  #   terraform init -migrate-state -force-copy
  backend "s3" {
    bucket       = "ferry-terraform-state"
    key          = "global/aws/backend/terraform.tfstate"
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
```

### ECR Repository with Lifecycle Policy (main.tf for ECR project)
```hcl
# Source: Terraform Registry
# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecr_repository
resource "aws_ecr_repository" "backend" {
  name                 = "lambda-ferry-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name      = "lambda-ferry-backend"
    ManagedBy = "terraform"
  }
}

# Source: Terraform Registry
# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecr_lifecycle_policy
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
```

### Placeholder Dockerfile
```dockerfile
# Source: AWS Lambda container image docs
# https://docs.aws.amazon.com/lambda/latest/dg/python-image.html
FROM public.ecr.aws/lambda/python:3.14

COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.handler"]
```

### Placeholder Handler (app.py)
```python
import json

def handler(event, context):
    """Placeholder handler -- replaced by real deploy in Phase 14."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": "placeholder", "service": "ferry-backend"}),
    }
```

### Bootstrap Script Skeleton
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BUCKET_NAME="ferry-terraform-state"
ECR_REPO="lambda-ferry-backend"
AWS_REGION="us-east-1"
PLACEHOLDER_TAG="placeholder"

# -- Step 1: Bootstrap S3 state backend --
step_backend() {
  local backend_dir="$REPO_ROOT/iac/global/aws/backend"

  if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
    echo "S3 bucket already exists, skipping creation"
  else
    echo "Creating S3 state bucket..."
    # providers.tf should have backend block commented out initially
    cd "$backend_dir"
    terraform init
    terraform apply -auto-approve
  fi

  # Check if state is already remote
  if terraform -chdir="$backend_dir" show -json 2>/dev/null | grep -q '"backend"'; then
    echo "State already migrated to S3"
  else
    echo "Migrating state to S3..."
    # Uncomment/add backend block, then:
    terraform -chdir="$backend_dir" init -migrate-state -force-copy
  fi
}

# -- Step 2: Create ECR repository --
step_ecr() {
  local ecr_dir="$REPO_ROOT/iac/global/aws/ecr"

  cd "$ecr_dir"
  terraform init
  terraform apply -auto-approve
}

# -- Step 3: Build and push placeholder image --
step_placeholder() {
  local ecr_dir="$REPO_ROOT/iac/global/aws/ecr"
  local account_id
  account_id=$(aws sts get-caller-identity --query Account --output text)
  local ecr_uri="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

  if aws ecr describe-images --repository-name "$ECR_REPO" \
       --image-ids imageTag="$PLACEHOLDER_TAG" 2>/dev/null; then
    echo "Placeholder image already exists, skipping"
    return
  fi

  echo "Building and pushing placeholder image..."
  aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com"

  docker build --platform linux/arm64 \
    -t "${ecr_uri}:${PLACEHOLDER_TAG}" \
    "$ecr_dir/placeholder"

  docker push "${ecr_uri}:${PLACEHOLDER_TAG}"
}

# -- Main --
echo "=== Ferry Bootstrap ==="
step_backend
step_ecr
step_placeholder
echo "=== Bootstrap complete ==="
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| DynamoDB for state locking | `use_lockfile = true` (S3 native) | Terraform 1.10 (experimental), 1.11 (stable) | No DynamoDB table needed, simpler setup |
| S3 bucket with inline config | Separate `aws_s3_bucket_*` resources | AWS provider 4.0+ | Versioning, encryption, ACLs must be separate resources |
| `role_arn` in backend block | `assume_role { role_arn = "..." }` in backend | AWS provider 5.x | Top-level `role_arn` is deprecated in backend config |
| AWS provider ~> 5.0 | AWS provider ~> 6.0 | June 2025 | Multi-region support, deprecation cleanups. No S3/ECR breaking changes. |
| Python 3.12 Lambda base | Python 3.14 Lambda base available | 2025-2026 | Both 3.13 and 3.14 available on `public.ecr.aws/lambda/python` with arm64 |

**Deprecated/outdated:**
- `dynamodb_table` in S3 backend config: Deprecated, will be removed in future minor version
- Top-level `role_arn` in S3 backend: Use `assume_role { role_arn = "..." }` instead
- Inline S3 bucket versioning/encryption: Use separate resources since AWS provider v4+

## Open Questions

1. **Bootstrap assume-role chicken-and-egg**
   - What we know: The user decided "assume-role provider pattern in all TF projects." However, the bootstrap is the very first operation -- the assume-role target may not exist yet.
   - What's unclear: Whether the assume-role target is pre-existing (manually created) or needs to be bootstrapped too.
   - Recommendation: For the bootstrap script, accept an optional `--assume-role-arn` flag. If not provided, use the caller's default credentials (e.g., from `AWS_PROFILE` or environment variables). The bootstrap itself can use direct credentials since it's a one-time local operation. All subsequent TF projects use assume-role.

2. **Backend block commenting strategy**
   - What we know: The backend block must be absent for the initial local-state apply, then present for migration.
   - What's unclear: Whether to use commenting/uncommenting, separate files, or `-backend-config` overrides.
   - Recommendation: Use a `backend.tf.bootstrap` file (no backend block) and a `backend.tf` file (with backend block). The bootstrap script copies the right one into place. Alternatively, use a single `providers.tf` with the backend block present and use `terraform init -backend=false` for the initial apply, then `terraform init -migrate-state -force-copy` for migration. The `-backend=false` approach is cleaner.

3. **Python 3.14 arm64 Lambda base image stability**
   - What we know: `public.ecr.aws/lambda/python:3.14` exists and supports arm64. STATE.md notes this as a concern to verify.
   - What's unclear: Whether the 3.14 image is stable enough for production use (Python 3.14 deprecation date is Jun 30, 2029 per AWS docs).
   - Recommendation: Use 3.14 since it's available and matches the project's Python version. The placeholder image is trivial -- even if 3.14 has issues, the real deploy in Phase 14 will use a proper Dockerfile.

## Sources

### Primary (HIGH confidence)
- [Terraform S3 Backend Documentation](https://developer.hashicorp.com/terraform/language/backend/s3) - `use_lockfile`, backend configuration, IAM permissions
- [AWS Lambda Python Container Images](https://docs.aws.amazon.com/lambda/latest/dg/python-image.html) - Python 3.14 availability, arm64 support, Dockerfile pattern
- [aws_ecr_repository](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecr_repository) - ECR resource configuration
- [aws_ecr_lifecycle_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecr_lifecycle_policy) - Lifecycle policy JSON format
- [ECR lifecycle policy examples](https://docs.aws.amazon.com/AmazonECR/latest/userguide/lifecycle_policy_examples.html) - AWS official examples
- [Terraform init command reference](https://developer.hashicorp.com/terraform/cli/commands/init) - `-migrate-state`, `-force-copy`, `-backend=false` flags

### Secondary (MEDIUM confidence)
- [S3 Native State Locking](https://www.bschaatsbergen.com/s3-native-state-locking) - Verified against official docs: S3 conditional writes for lock files
- [Monterail Terraform Bootstrap Example](https://github.com/monterail/terraform-bootstrap-example) - Bootstrap script pattern verified with official Terraform docs
- [Python 3.14 Lambda announcement](https://aws.amazon.com/blogs/compute/python-3-14-runtime-now-available-in-aws-lambda/) - Runtime availability confirmation
- [AWS Provider 6.0 announcement](https://www.hashicorp.com/en/blog/terraform-aws-provider-6-0-now-generally-available) - Breaking changes analysis

### Tertiary (LOW confidence)
- None -- all findings verified against official sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Terraform and AWS provider versions verified from official releases. S3 backend and ECR are extremely well-documented.
- Architecture: HIGH - Bootstrap pattern is well-established (multiple official examples). Directory structure follows user's locked decisions.
- Pitfalls: HIGH - All pitfalls sourced from official docs, GitHub issues, or widely-reported community patterns.

**Research date:** 2026-02-28
**Valid until:** 2026-03-30 (30 days -- stable domain, slow-moving)
