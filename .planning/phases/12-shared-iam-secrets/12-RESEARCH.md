# Phase 12: Shared IAM + Secrets - Research

**Researched:** 2026-03-01
**Domain:** AWS IAM (OIDC, roles, policies) + Secrets Manager via Terraform
**Confidence:** HIGH

## Summary

Phase 12 creates the identity and secrets foundation that all subsequent phases depend on. There are four distinct Terraform resource groups: (1) an account-wide OIDC identity provider for GitHub Actions, (2) a Lambda execution role with least-privilege policies, (3) two GHA deploy roles (self-deploy and dispatch) with ECR push and Lambda update permissions, and (4) Secrets Manager containers for GitHub App credentials.

The implementation is straightforward raw Terraform -- no modules needed. All IAM policies use `data.aws_iam_policy_document` blocks (type-safe HCL, not inline JSON). The OIDC provider is a single resource in its own TF project (`iac/global/aws/oidc/`), while roles, policies, and secrets live in `iac/staging/aws/shared/`. Wildcard-scoped resource ARNs are used now (Phase 13 tightens to exact ARNs once DynamoDB/logs exist).

**Primary recommendation:** Implement as two separate `terraform apply` targets -- first OIDC provider (global), then shared IAM+secrets (staging) -- following the existing Phase 11 pattern of small, focused TF projects.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Account-wide OIDC provider for `token.actions.githubusercontent.com` -- lives in `iac/global/aws/oidc/`
- GHA deploy role trust: repo-only scope (any workflow in the ferry repo can assume)
- Lambda execution role: standard `lambda.amazonaws.com` service trust (not OIDC)
- **Two separate GHA roles**: one for self-deploy (ferry repo), one for dispatch-triggered workflows (customer repos). Clean separation now avoids entangling permissions later
- **Separate secrets per credential** -- not a single JSON blob
- Naming convention: `ferry/github-app/{name}` -- three secrets: `ferry/github-app/app-id`, `ferry/github-app/private-key`, `ferry/github-app/webhook-secret`
- Standard tags on all secrets: `Project=ferry`, `ManagedBy=terraform`, `Component=github-app`
- OIDC provider: `iac/global/aws/oidc/` (account-wide, follows iac-tf pattern)
- IAM roles + secrets + OIDC role bindings: `iac/staging/aws/shared/` (account/env-specific, not global)
- TF state keys match directory paths: e.g., `staging/aws/shared/terraform.tfstate`, `global/aws/oidc/terraform.tfstate`
- File split follows iac-tf convention: `iam.tf`, `secrets.tf`, `oidc.tf` (role bindings), `data.tf`, `providers.tf`, `variables.tf`, `outputs.tf`
- HCL `data.aws_iam_policy_document` blocks (type-safe, composable) -- no inline JSON
- **Wildcard-scoped now, tighten to exact ARNs in Phase 13** -- avoids circular dependency since DynamoDB table and log groups don't exist yet
- Lambda execution role needs: DynamoDB (ferry-*), Secrets Manager (ferry/*), CloudWatch Logs (ferry-*)
- GHA self-deploy role: ECR push (ferry/backend) + Lambda update-function-code
- GHA dispatch role: ECR push (ferry/*) + Lambda update (ferry-*) -- broader scope for future customer-repo dispatches

### Claude's Discretion
- Secret initial values approach (empty string vs no initial version)
- Exact IAM policy document structure and data source organization
- Whether to use `locals` for policy attachment maps (like iac-tf) or direct attachments
- Role and policy naming convention (PascalCase like iac-tf vs kebab-case)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| IAM-01 | Lambda execution role with least-privilege policies (DynamoDB, Secrets Manager, CloudWatch Logs) | Lambda trust policy pattern, `data.aws_iam_policy_document` for DynamoDB/SecretsManager/Logs actions, wildcard scoping for now |
| IAM-02 | OIDC identity provider for GitHub Actions in Ferry AWS account | `aws_iam_openid_connect_provider` with `url` and `client_id_list` -- thumbprint_list optional since provider v5.81.0 (we use v6.34.0) |
| IAM-03 | GHA deploy role with ECR push + Lambda update permissions, scoped to ferry repo | OIDC assume-role trust policy with `sub` claim scoping, ECR push actions (7 total), Lambda update actions |
| IAM-04 | Secrets Manager secret containers for GitHub App credentials (app ID, private key, webhook secret) | `aws_secretsmanager_secret` without `aws_secretsmanager_secret_version` creates empty container; values populated via CLI in Phase 14 |
</phase_requirements>

## Standard Stack

### Core
| Library/Resource | Version | Purpose | Why Standard |
|------------------|---------|---------|--------------|
| hashicorp/aws provider | ~> 6.0 (locked at 6.34.0) | All AWS resources | Already in use from Phase 11 |
| Terraform | ~> 1.12.0 | IaC engine | Already in use from Phase 11 |
| `aws_iam_openid_connect_provider` | N/A | Register GitHub OIDC provider | AWS-native OIDC federation |
| `aws_iam_role` | N/A | IAM roles (Lambda exec, GHA deploy) | Standard IAM resource |
| `data.aws_iam_policy_document` | N/A | Type-safe HCL policy definitions | Compile-time validation, composability |
| `aws_iam_policy` + `aws_iam_role_policy_attachment` | N/A | Named policies attached to roles | Clean separation of policies from roles |
| `aws_secretsmanager_secret` | N/A | Secret containers | Standard Secrets Manager resource |

### Supporting
| Library/Resource | Version | Purpose | When to Use |
|------------------|---------|---------|-------------|
| `data.aws_caller_identity` | N/A | Get account ID for ARN construction | Already used in ECR project |
| `data.aws_region` | N/A | Get current region for ARN construction | Avoid hardcoding region in ARNs |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `aws_iam_*` resources | terraform-aws-modules/iam | Modules add abstraction for only ~6 resources; project decision is raw resources |
| `data.aws_iam_policy_document` | Inline JSON strings | JSON is error-prone, no compile-time validation, no composition |
| Separate OIDC modules (unfunco, philips-labs) | Raw `aws_iam_openid_connect_provider` | Module wraps a single resource; unnecessary abstraction |

## Architecture Patterns

### Recommended Project Structure
```
iac/
├── global/aws/
│   ├── backend/          # Phase 11 (exists)
│   ├── ecr/              # Phase 11 (exists)
│   └── oidc/             # Phase 12 - NEW
│       ├── providers.tf
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
└── staging/aws/
    └── shared/           # Phase 12 - NEW
        ├── providers.tf
        ├── data.tf       # aws_caller_identity, aws_region, policy documents
        ├── iam.tf        # roles + policy attachments
        ├── oidc.tf       # GHA role OIDC trust bindings (assume role policies)
        ├── secrets.tf    # Secrets Manager secrets
        ├── variables.tf
        └── outputs.tf
```

### Pattern 1: OIDC Provider (Global)
**What:** Account-wide GitHub Actions OIDC identity provider
**When to use:** Once per AWS account, referenced by all GHA roles

```hcl
# iac/global/aws/oidc/main.tf
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  # thumbprint_list is optional since AWS provider v5.81.0
  # AWS validates GitHub OIDC via its root CA library (since July 2023)
}
```

### Pattern 2: Lambda Execution Role Trust Policy
**What:** IAM role that Lambda service assumes to execute function code
**When to use:** Every Lambda function needs an execution role

```hcl
# data.tf - trust policy
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# iam.tf - role
resource "aws_iam_role" "lambda_execution" {
  name               = "ferry-lambda-execution"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}
```

### Pattern 3: GHA OIDC Assume Role Trust Policy
**What:** IAM role that GitHub Actions workflows assume via OIDC federation
**When to use:** Any GHA workflow needing AWS access without static credentials

```hcl
# data.tf - trust policy for self-deploy role (ferry repo only)
data "aws_iam_policy_document" "gha_self_deploy_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.terraform_remote_state.oidc.outputs.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:*"]
    }
  }
}
```

### Pattern 4: Secrets Manager Empty Container
**What:** Create secret metadata without a secret version (value populated manually later)
**When to use:** When TF owns structure but values are populated out-of-band

```hcl
# secrets.tf
resource "aws_secretsmanager_secret" "github_app_id" {
  name        = "ferry/github-app/app-id"
  description = "GitHub App ID for Ferry"

  tags = {
    Component = "github-app"
  }
}

# No aws_secretsmanager_secret_version resource -- values set via CLI:
# aws secretsmanager put-secret-value --secret-id ferry/github-app/app-id --secret-string "12345"
```

### Pattern 5: Remote State References
**What:** Use `terraform_remote_state` to reference outputs from other TF projects
**When to use:** The shared project needs the OIDC provider ARN from the global/oidc project

```hcl
# data.tf in staging/aws/shared/
data "terraform_remote_state" "oidc" {
  backend = "s3"

  config = {
    bucket = "ferry-global-terraform-state"
    key    = "global/aws/oidc/terraform.tfstate"
    region = "us-east-1"
  }
}
```

### Anti-Patterns to Avoid
- **Inline JSON for IAM policies:** Use `data.aws_iam_policy_document` instead -- it catches syntax errors at plan time, supports merging, and is more readable
- **Single monolithic policy document:** Split into separate named policies per concern (DynamoDB access, Secrets Manager access, CloudWatch Logs). Easier to audit and modify independently
- **Hardcoded account IDs in ARNs:** Use `data.aws_caller_identity.current.account_id` and `data.aws_region.current.name`
- **Storing secret values in Terraform:** Never put actual credentials in TF state. Create containers only, populate via CLI
- **Overly broad OIDC trust (org-wide wildcard):** Scope `sub` claim to specific repo at minimum; never use bare `*`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OIDC thumbprint generation | Custom scripts to fetch/compute thumbprints | Omit `thumbprint_list` entirely | AWS provider v5.81.0+ makes it optional; AWS uses root CA library since July 2023 |
| IAM policy JSON | String interpolation / heredocs | `data.aws_iam_policy_document` | Type-safe, composable, catches errors at plan time |
| Account ID lookup | Hardcoded values or shell scripts | `data.aws_caller_identity` | Already in use from Phase 11 ECR project |
| ARN construction | Manual string formatting | `"arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/ferry-*"` | Terraform interpolation with data sources is reliable |

**Key insight:** For ~10 Terraform resources with well-understood patterns, raw resources are the right choice. Every IAM module evaluated wraps the same primitives we'd use directly, adding indirection without value.

## Common Pitfalls

### Pitfall 1: OIDC Sub Claim Scoping
**What goes wrong:** Trust policy uses `StringEquals` for the `sub` claim but actual token value doesn't match exactly due to event-type variations
**Why it happens:** The sub claim format varies by trigger type:
- Push: `repo:ORG/REPO:ref:refs/heads/BRANCH`
- Pull request: `repo:ORG/REPO:pull_request`
- Environment: `repo:ORG/REPO:environment:ENV_NAME`
- The sub claim value is **case-sensitive**
**How to avoid:** Use `StringLike` with `repo:ORG/REPO:*` for repo-scoped access (matches all event types). Only use `StringEquals` when restricting to a specific branch or environment
**Warning signs:** `AccessDenied` errors when assuming role from GHA; the `sub` claim in the error message doesn't match the trust policy condition

### Pitfall 2: ECR GetAuthorizationToken Requires Resource "*"
**What goes wrong:** ECR push fails with auth errors despite having push permissions on the repository
**Why it happens:** `ecr:GetAuthorizationToken` is an account-level action that cannot be scoped to a specific repository -- it requires `Resource: "*"`. All other ECR push actions can be scoped to specific repository ARNs
**How to avoid:** Split ECR policy into two statements: one for `GetAuthorizationToken` with `Resource = "*"`, another for push actions scoped to repository ARNs
**Warning signs:** `Unable to locate credentials` or `no basic auth credentials` during `docker login`

### Pitfall 3: Circular Dependency with Exact ARNs
**What goes wrong:** Lambda role needs DynamoDB table ARN, but DynamoDB table needs Lambda role ARN (for encryption/access), creating a plan-time cycle
**Why it happens:** Resources that reference each other's ARNs during creation
**How to avoid:** Use wildcard patterns now (`arn:aws:dynamodb:*:*:table/ferry-*`) -- this is the explicit decision from CONTEXT.md. Phase 13 tightens to exact ARNs after resources exist
**Warning signs:** Terraform circular dependency errors at plan time

### Pitfall 4: Secrets Manager Without Initial Version
**What goes wrong:** `aws_secretsmanager_secret` without `aws_secretsmanager_secret_version` creates a secret with no versions. Attempting to read it returns an error until a version is created
**Why it happens:** Secrets Manager treats the secret and its value as separate API objects. A secret with no versions is valid but not readable
**How to avoid:** This is the **intended behavior** for Phase 12 -- we create empty containers. Document clearly that values must be populated via CLI before the Lambda can start. Consider adding a `# MANUAL STEP` comment in the secret resource blocks
**Warning signs:** Lambda fails at cold start with "secret has no versions" error (expected until Phase 14 CLI population)

### Pitfall 5: Missing permissions.id-token in GHA Workflow
**What goes wrong:** OIDC assume-role fails from GitHub Actions even though IAM trust policy is correct
**Why it happens:** The GHA workflow must explicitly declare `permissions: id-token: write` for the OIDC token to be generated
**How to avoid:** This is a Phase 14 concern but roles must be designed knowing this. The trust policy `aud` claim matches `sts.amazonaws.com` which is the default audience when using `aws-actions/configure-aws-credentials`
**Warning signs:** 403/Forbidden when attempting to get OIDC token in the workflow

## Code Examples

### Complete OIDC Provider (`iac/global/aws/oidc/main.tf`)

```hcl
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  tags = {
    Name = "github-actions"
  }
}
```

### Lambda Execution Role Permission Policy

```hcl
# data.tf
data "aws_iam_policy_document" "lambda_dynamodb" {
  statement {
    sid    = "DynamoDBAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
    ]
    resources = [
      "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/ferry-*",
    ]
  }
}

data "aws_iam_policy_document" "lambda_secrets" {
  statement {
    sid    = "SecretsManagerRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:ferry/*",
    ]
  }
}

data "aws_iam_policy_document" "lambda_logs" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/ferry-*:*",
    ]
  }
}
```

### GHA Self-Deploy Role -- ECR Push + Lambda Update Permissions

```hcl
# data.tf
data "aws_iam_policy_document" "gha_self_deploy_ecr" {
  statement {
    sid    = "ECRAuth"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ECRPush"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [
      "arn:aws:ecr:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:repository/lambda-ferry-backend",
    ]
  }
}

data "aws_iam_policy_document" "gha_self_deploy_lambda" {
  statement {
    sid    = "LambdaUpdate"
    effect = "Allow"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
    ]
    resources = [
      "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:ferry-backend",
    ]
  }
}
```

### Secrets Manager Containers

```hcl
# secrets.tf
locals {
  github_app_secrets = {
    "app-id"         = "GitHub App ID for Ferry"
    "private-key"    = "GitHub App private key (PEM format) for Ferry"
    "webhook-secret" = "GitHub App webhook secret for Ferry"
  }
}

resource "aws_secretsmanager_secret" "github_app" {
  for_each = local.github_app_secrets

  name        = "ferry/github-app/${each.key}"
  description = each.value

  tags = {
    Component = "github-app"
  }
}
# No aws_secretsmanager_secret_version -- values populated via CLI in Phase 14
```

### GHA Workflow Usage (for reference -- implemented in Phase 14)

```yaml
# .github/workflows/deploy.yml (Phase 14)
permissions:
  id-token: write
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::ACCOUNT_ID:role/ferry-gha-self-deploy
      aws-region: us-east-1
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| OIDC thumbprint pinning | AWS root CA validation (thumbprint optional) | July 2023 (AWS), Dec 2024 (TF provider v5.81.0) | Can omit `thumbprint_list` entirely in TF |
| Static AWS access keys in GHA secrets | OIDC federation with short-lived tokens | 2022+ | No long-lived credentials; automatic rotation |
| Single JSON blob for secrets | Separate secrets per credential | Current best practice | Independent rotation, granular IAM access |
| `aws_iam_role_policy` (inline) | `aws_iam_policy` + `aws_iam_role_policy_attachment` | Best practice | Named policies are auditable, reusable |

**Deprecated/outdated:**
- Thumbprint-based OIDC validation: Still works but unnecessary for GitHub; AWS validates via root CA
- `aws-actions/configure-aws-credentials@v1`: Use v4 (latest stable)

## Discretion Recommendations

### Secret Initial Values: No Secret Version (Recommended)
**Recommendation:** Create `aws_secretsmanager_secret` resources only, with no `aws_secretsmanager_secret_version`. This means the secret exists in Secrets Manager but has zero versions until populated via CLI.

**Rationale:**
- Cleaner than setting an empty string (which creates a version containing `""` that could be mistakenly treated as valid)
- The AWS API allows this -- it creates the secret metadata without any secret data
- Forces explicit CLI population in Phase 14, which is the documented manual step
- The Lambda will fail clearly with "secret has no versions" until values are set, making the dependency obvious

### Policy Attachment Style: Direct (Not Locals Map)
**Recommendation:** Use direct `aws_iam_role_policy_attachment` resources rather than the `for_each` + `locals` map pattern from iac-tf.

**Rationale:**
- Only 3 roles with ~2-3 policies each (6-9 attachments total)
- Direct attachments are more readable at this scale
- The locals map pattern adds value when you have many roles with many overlapping policies; here it's overhead
- Each attachment is explicitly named and easy to find in `terraform state list`

### Naming Convention: kebab-case (Recommended)
**Recommendation:** Use kebab-case for role and policy names: `ferry-lambda-execution`, `ferry-gha-self-deploy`, `ferry-gha-dispatch`.

**Rationale:**
- Consistent with the `ferry-*` naming used throughout the project (S3 bucket, DynamoDB table prefix, Lambda function names)
- AWS IAM names are case-sensitive and kebab-case is more common in CLI-heavy workflows
- PascalCase in iac-tf is a legacy convention from that specific project, not a universal standard

## Open Questions

1. **Dispatch role `sub` claim scoping**
   - What we know: The dispatch role is for customer repos that run workflow_dispatch. The sub claim format is `repo:ORG/REPO:ref:refs/heads/BRANCH` for push but varies by event type
   - What's unclear: Which repos will trigger dispatch? If unknown at deploy time, the trust policy needs a broader pattern (e.g., `repo:ORG/*:*`) or needs updating when customer repos are onboarded
   - Recommendation: For v1, scope to the ferry repo org with `StringLike` and `repo:${var.github_org}/*:*`. This allows any repo in the org to assume the role. Can be tightened later when customer repo patterns are known

2. **Lambda execution role `logs:CreateLogGroup` permission**
   - What we know: Phase 13 creates the log group via Terraform. The Lambda role needs `CreateLogStream` and `PutLogEvents`
   - What's unclear: Should the Lambda role also have `logs:CreateLogGroup` as a safety net if the TF-managed log group doesn't exist yet?
   - Recommendation: Omit `CreateLogGroup` -- if the log group doesn't exist, that's a Terraform apply ordering issue to fix, not a permissions issue to paper over

## Sources

### Primary (HIGH confidence)
- AWS IAM docs: OIDC trust policy structure for GitHub Actions -- condition keys (`aud`, `sub`), `sts:AssumeRoleWithWebIdentity` action
- AWS ECR docs: Required IAM permissions for image push (7 actions, `GetAuthorizationToken` requires `Resource: *`)
- Terraform AWS provider v5.81.0 release: `thumbprint_list` made optional (verified via [GitHub issue #35112](https://github.com/hashicorp/terraform-provider-aws/issues/35112), resolved Dec 2024)
- GitHub OIDC reference docs: Sub claim formats by event type (`ref:refs/heads/BRANCH`, `pull_request`, `environment:NAME`)
- Existing Phase 11 code (`iac/global/aws/backend/`, `iac/global/aws/ecr/`): Provider version 6.34.0, S3 backend pattern, tagging convention

### Secondary (MEDIUM confidence)
- [Colin Barker blog (Jan 2025)](https://colinbarker.me.uk/blog/2025-01-12-github-actions-oidc-update/) -- Confirmed thumbprint_list omission works in practice
- [AWS Security Blog](https://aws.amazon.com/blogs/security/use-iam-roles-to-connect-github-actions-to-actions-in-aws/) -- GHA OIDC architecture reference
- [AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/secure-sensitive-data-secrets-manager-terraform/using-secrets-manager-and-terraform.html) -- Secrets Manager + Terraform patterns
- [GitHub Actions OIDC docs](https://docs.github.com/en/actions/concepts/security/openid-connect) -- Sub claim format specifications

### Tertiary (LOW confidence)
- None -- all claims verified with at least two sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all resources are well-documented AWS primitives used in the existing codebase
- Architecture: HIGH -- follows established patterns from Phase 11 and iac-tf conventions
- Pitfalls: HIGH -- OIDC sub claim, ECR GetAuthorizationToken, and empty secrets patterns are well-documented failure modes
- Discretion recommendations: MEDIUM -- naming and attachment style are preference-driven; recommendations are defensible but alternatives are valid

**Research date:** 2026-03-01
**Valid until:** 2026-04-01 (stable domain, 30-day validity)
