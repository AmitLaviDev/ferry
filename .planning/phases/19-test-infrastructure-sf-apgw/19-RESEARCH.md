# Phase 19: Test Infrastructure for SF + APGW - Research

**Researched:** 2026-03-08
**Domain:** Terraform IaC -- AWS Step Functions + API Gateway REST API + IAM
**Confidence:** HIGH

## Summary

Phase 19 adds Terraform resources to `iac/test-env/` for a Step Functions state machine and an API Gateway REST API, plus the IAM roles and policies required for both runtime execution and Ferry deploy. The existing test-env already has a working pattern (ECR + Lambda + deploy role with OIDC trust) that we extend.

The `terraform-aws-modules/step-functions/aws` module (v5.1.0) supports creating Standard state machines with externally managed IAM roles via `use_existing_role = true` + `create_role = false`. For API Gateway REST API, there is NO community module -- `terraform-aws-modules/apigateway-v2` only supports HTTP/WebSocket APIs (v2). We must use native `aws_api_gateway_rest_api` + `aws_api_gateway_deployment` + `aws_api_gateway_stage` resources.

**Primary recommendation:** Use the community module for Step Functions (v5.1.0), native resources for API Gateway REST API, and follow the existing IAM pattern (policy document + policy + attachment) for all new permissions.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
1. **Resource Naming:** `ferry-test-sf` (state machine), `ferry-test-api` (REST API), `ferry-test-sf-execution` (SF role), `ferry-test-apgw-invoke` (APGW role), `chain-sf` / `chain-api` (ferry.yaml keys)
2. **SF Execution Role Scope:** `lambda:InvokeFunction` on `ferry-test-hello-world`, CloudWatch Logs permissions, no X-Ray
3. **APGW Invocation Role:** Dedicated `ferry-test-apgw-invoke`, trust `apigateway.amazonaws.com`, permission `states:StartExecution` on `ferry-test-sf`
4. **Terraform Organization:** `step_function.tf` and `api_gateway.tf` as new files; IAM policy documents in `data.tf`; deploy role extensions in `main.tf`
5. **Deploy Role Permissions (ferry-test-deploy):** SF deploy: `states:UpdateStateMachine`, `states:DescribeStateMachine`, `states:TagResource`, `states:ListTagsForResource`. APGW deploy: `apigateway:PutRestApi`, `apigateway:CreateDeployment`, `apigateway:GetRestApi`, `apigateway:GetTags`, `apigateway:TagResource`
6. **API Gateway Config:** REGIONAL endpoint, `test` stage, placeholder body (overwritten by Ferry deploy)
7. **Community modules:** Use `terraform-aws-modules/step-functions` and `terraform-aws-modules/apigateway`

### Claude's Discretion
(none specified)

### Deferred Ideas (OUT OF SCOPE)
(none -- scope held tight)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | Step Functions state machine exists (Standard type, placeholder definition) | SF module v5.1.0 with `type = "STANDARD"`, `use_existing_role = true`, placeholder definition |
| INFRA-02 | API Gateway REST API exists with `test` stage | Native `aws_api_gateway_rest_api` + deployment + stage resources (no community module for REST API) |
| INFRA-03 | IAM execution role for SF with Lambda invoke permission | Trust policy for `states.amazonaws.com`, scoped `lambda:InvokeFunction` + CloudWatch Logs |
| INFRA-04 | API Gateway has IAM permissions to call `states:StartExecution` | Dedicated role `ferry-test-apgw-invoke` with trust for `apigateway.amazonaws.com` |
| INFRA-05 | Deploy role has SF deploy permissions | New policy + attachment on existing `ferry-test-deploy` role |
| INFRA-06 | Deploy role has APGW deploy permissions | New policy + attachment on existing `ferry-test-deploy` role |
</phase_requirements>

## Standard Stack

### Core
| Resource/Module | Version | Purpose | Why Standard |
|-----------------|---------|---------|--------------|
| `terraform-aws-modules/step-functions/aws` | 5.1.0 | Create Standard state machine | Blessed community module, handles resource lifecycle cleanly |
| `aws_api_gateway_rest_api` (native) | AWS provider ~> 6.0 | Create REST API | Community module only supports HTTP APIs (v2); must use native |
| `aws_api_gateway_deployment` (native) | AWS provider ~> 6.0 | Create initial deployment | Required to activate the REST API |
| `aws_api_gateway_stage` (native) | AWS provider ~> 6.0 | Create `test` stage | Provides the invoke URL |

### Supporting
| Resource | Purpose | When to Use |
|----------|---------|-------------|
| `aws_iam_role` | Service execution/invocation roles | SF execution, APGW invocation |
| `aws_iam_policy` + `aws_iam_policy_document` | Scoped permission policies | All IAM policies |
| `aws_iam_role_policy_attachment` | Attach policies to roles | Every policy-to-role binding |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SF community module | Native `aws_sfn_state_machine` | Module adds role management, tags, logging config -- worth the abstraction even if we skip role creation |
| Native APGW resources | `terraform-aws-modules/apigateway-v2` | **Not viable** -- that module only supports HTTP/WebSocket APIs, not REST APIs. Must use native resources. |

**IMPORTANT CORRECTION to CONTEXT.md Decision #4:** The CONTEXT.md says to use `terraform-aws-modules/apigateway` community module, but this module (`terraform-aws-modules/apigateway-v2`) only supports API Gateway v2 (HTTP/WebSocket APIs). It does NOT support REST APIs (v1). Native Terraform resources must be used instead. The README explicitly states it creates "API Gateway v2 resources with HTTP/Websocket capabilities."

## Architecture Patterns

### New File Structure
```
iac/test-env/
├── providers.tf          # (existing) Backend + AWS provider
├── variables.tf          # (existing + new vars) Add SF/APGW names
├── data.tf               # (existing + new) Add trust policies + permission docs
├── main.tf               # (existing + extend) Add deploy role SF/APGW policies
├── outputs.tf            # (existing + new) Add SF/APGW outputs
├── step_function.tf      # (NEW) SF module + execution role + IAM
└── api_gateway.tf        # (NEW) REST API + deployment + stage + invocation role + IAM
```

### Pattern 1: Step Functions Module with External Role
**What:** Create a Standard state machine using the community module but manage the IAM role ourselves.
**When to use:** When you need fine-grained IAM control (our case: specific Lambda invoke + CloudWatch Logs).
**Example:**
```hcl
# Source: terraform-aws-modules/step-functions/aws v5.1.0 README
module "step_function" {
  source  = "terraform-aws-modules/step-functions/aws"
  version = "5.1.0"

  name       = "ferry-test-sf"
  type       = "STANDARD"
  definition = jsonencode({
    Comment = "Placeholder -- overwritten by Ferry deploy"
    StartAt = "Placeholder"
    States = {
      Placeholder = {
        Type = "Pass"
        End  = true
      }
    }
  })

  create_role      = false
  use_existing_role = true
  role_arn         = aws_iam_role.test_sf_execution.arn

  tags = {
    Name = "ferry-test-sf"
  }
}
```

**Key inputs:**
- `name` (string): State machine name
- `definition` (string): ASL JSON definition -- use `jsonencode()` for the placeholder
- `type` (string, default "STANDARD"): "STANDARD" or "EXPRESS"
- `create_role` (bool, default true): Set to `false` to skip module role creation
- `use_existing_role` (bool, default false): Set to `true` to use external role
- `role_arn` (string): ARN of the external role (used when `use_existing_role = true`)

**Key outputs:**
- `state_machine_arn`: The ARN of the state machine
- `state_machine_name`: The name of the state machine
- `state_machine_id`: The ID (same as ARN for SF)

### Pattern 2: Native API Gateway REST API (No Body)
**What:** Create a REST API shell without an OpenAPI body, avoiding Terraform drift when Ferry overwrites the spec.
**When to use:** When the API spec is managed externally (Ferry deploy uses `put_rest_api` mode=overwrite).

**CRITICAL GOTCHA:** If you provide a `body` argument in the `aws_api_gateway_rest_api` resource AND Ferry later overwrites the spec via `put_rest_api`, Terraform will detect drift and try to restore the original body on next `terraform apply`. This would undo Ferry's deploy.

**Solution:** Do NOT provide a `body` argument. Create a minimal empty REST API with just `name` and `endpoint_configuration`. The first Ferry deploy will populate the spec.

```hcl
# REST API -- no body, Ferry manages the spec via put_rest_api
resource "aws_api_gateway_rest_api" "test" {
  name        = "ferry-test-api"
  description = "Ferry test API -- spec managed by Ferry deploy"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = {
    Name = "ferry-test-api"
  }
}
```

**However**, there is a secondary issue: we need a deployment + stage, and `aws_api_gateway_deployment` requires something deployable. An empty REST API with no methods cannot be deployed. Options:

1. **Skip initial deployment in Terraform** -- just create the REST API and stage. The first Ferry deploy via `create_deployment` will create the initial deployment. BUT: `aws_api_gateway_stage` requires a `deployment_id`.
2. **Provide a minimal body** with `lifecycle { ignore_changes = [body] }` -- create the initial spec, deploy it, and then ignore future changes since Ferry manages it.

**Recommended approach:** Provide a minimal placeholder OpenAPI body AND use `lifecycle { ignore_changes = [body] }` to prevent Terraform from reverting Ferry's deploys.

```hcl
resource "aws_api_gateway_rest_api" "test" {
  name        = "ferry-test-api"
  description = "Ferry test API -- spec managed by Ferry deploy"

  body = jsonencode({
    openapi = "3.0.1"
    info = {
      title   = "ferry-test-api"
      version = "1.0"
    }
    paths = {}
  })

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  lifecycle {
    ignore_changes = [body]
  }

  tags = {
    Name = "ferry-test-api"
  }
}

resource "aws_api_gateway_deployment" "test" {
  rest_api_id = aws_api_gateway_rest_api.test.id
  description = "Initial placeholder deployment"

  triggers = {
    redeployment = sha1(jsonencode(aws_api_gateway_rest_api.test.body))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "test" {
  deployment_id = aws_api_gateway_deployment.test.id
  rest_api_id   = aws_api_gateway_rest_api.test.id
  stage_name    = "test"

  tags = {
    Name = "ferry-test-api-test"
  }
}
```

### Pattern 3: IAM Role with Service Trust Policy
**What:** Create IAM roles that AWS services can assume.
**When to use:** For SF execution role (trusted by `states.amazonaws.com`) and APGW invocation role (trusted by `apigateway.amazonaws.com`).
**Example:**
```hcl
# Trust policy for Step Functions
data "aws_iam_policy_document" "test_sf_assume_role" {
  statement {
    sid     = "StepFunctionsAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "test_sf_execution" {
  name               = "ferry-test-sf-execution"
  assume_role_policy = data.aws_iam_policy_document.test_sf_assume_role.json

  tags = {
    Name = "ferry-test-sf-execution"
  }
}
```

### Pattern 4: Deploy Role Extension
**What:** Add new IAM policies to the existing `ferry-test-deploy` role.
**When to use:** Extending deploy permissions without modifying existing policies.
**Example:**
```hcl
# In data.tf -- new policy document
data "aws_iam_policy_document" "test_sf_deploy" {
  statement {
    sid    = "StepFunctionsDeploy"
    effect = "Allow"
    actions = [
      "states:UpdateStateMachine",
      "states:DescribeStateMachine",
      "states:TagResource",
      "states:ListTagsForResource",
    ]
    resources = [
      module.step_function.state_machine_arn,
    ]
  }
}

# In main.tf -- policy + attachment (matches existing pattern)
resource "aws_iam_policy" "test_sf_deploy" {
  name   = "ferry-test-sf-deploy"
  policy = data.aws_iam_policy_document.test_sf_deploy.json

  tags = {
    Name = "ferry-test-sf-deploy"
  }
}

resource "aws_iam_role_policy_attachment" "test_sf_deploy" {
  role       = aws_iam_role.test_deploy.name
  policy_arn = aws_iam_policy.test_sf_deploy.arn
}
```

### Anti-Patterns to Avoid
- **Providing `body` without `ignore_changes`:** Terraform will revert Ferry's spec on every `terraform apply`, undoing the deploy.
- **Using `terraform-aws-modules/apigateway-v2` for REST APIs:** It only supports HTTP/WebSocket APIs (v2). Will not work.
- **Inline IAM policies:** Use managed policies (policy + attachment), matching the existing codebase pattern. Inline policies are harder to audit and debug.
- **Wildcard resource ARNs in deploy policies:** Always scope to the specific state machine or REST API ARN.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| State machine resource | Raw `aws_sfn_state_machine` | `terraform-aws-modules/step-functions/aws` v5.1.0 | Module handles tags, lifecycle, optional logging/encryption consistently |
| REST API (v1) | Community module | Native `aws_api_gateway_rest_api` + deployment + stage | No community module supports REST APIs; native resources are the standard approach |
| IAM policy JSON strings | Raw JSON strings | `aws_iam_policy_document` data source | Type-safe, composable, validates at plan time |

## Common Pitfalls

### Pitfall 1: API Gateway Body Drift
**What goes wrong:** Terraform provides an initial OpenAPI body. Ferry deploys a new spec via `put_rest_api`. Next `terraform apply` reverts the spec to the Terraform-defined body.
**Why it happens:** Terraform tracks the `body` attribute as desired state.
**How to avoid:** Use `lifecycle { ignore_changes = [body] }` on the `aws_api_gateway_rest_api` resource.
**Warning signs:** `terraform plan` shows changes to the REST API body after a successful Ferry deploy.

### Pitfall 2: Deployment Ordering
**What goes wrong:** `aws_api_gateway_deployment` is created before the REST API has any routes/methods. Deployment fails or creates an empty stage.
**Why it happens:** Empty REST APIs can technically be deployed but have no callable endpoints.
**How to avoid:** Provide a minimal placeholder body (even with empty `paths: {}`) to ensure a valid deployment. The first Ferry deploy will replace it.
**Warning signs:** Stage exists but returns 403/404 for all paths before Ferry deploys.

### Pitfall 3: Deployment Not Updating
**What goes wrong:** Changes to the REST API body don't trigger a new deployment. The stage still serves the old spec.
**Why it happens:** `aws_api_gateway_deployment` has no implicit dependency on the REST API body changes.
**How to avoid:** Use `triggers = { redeployment = sha1(jsonencode(aws_api_gateway_rest_api.test.body)) }` on the deployment resource. But since we use `ignore_changes = [body]`, the trigger won't fire after initial creation -- which is correct because Ferry handles subsequent deployments via `create_deployment`.
**Warning signs:** N/A for our use case since Ferry manages deployments.

### Pitfall 4: SF Module create_role vs use_existing_role
**What goes wrong:** Setting `create_role = false` but forgetting `use_existing_role = true`. The module tries to reference a role it didn't create.
**Why it happens:** These are two separate flags. `create_role = false` stops creation, but `use_existing_role = true` is what tells the module to use `role_arn`.
**How to avoid:** Always set both: `create_role = false` AND `use_existing_role = true`.
**Warning signs:** Error like "index on aws_iam_role.this is out of range" during plan.

### Pitfall 5: Missing iam:PassRole for Deploy Role
**What goes wrong:** The deploy role (used by Ferry Action in GHA) may need `iam:PassRole` if it creates or updates resources that assume other roles.
**Why it happens:** Step Functions `update_state_machine` with a `roleArn` parameter requires the caller to have `iam:PassRole` on that role.
**How to avoid:** Check whether `update_state_machine` in our deploy code passes a `roleArn`. Looking at `deploy_stepfunctions.py`: it does NOT pass `roleArn` -- it only passes `definition` and `publish`. The role was set at creation time by Terraform and won't change. So **iam:PassRole is NOT needed** for our deploy pattern.
**Warning signs:** `AccessDeniedException` mentioning `iam:PassRole` during SF deploy.

### Pitfall 6: API Gateway Deployment lifecycle
**What goes wrong:** Redeployment fails with `BadRequestException: Active stages pointing to this deployment must be moved or deleted`.
**Why it happens:** The old deployment is destroyed before the new one is created, but the stage still references it.
**How to avoid:** Use `lifecycle { create_before_destroy = true }` on the `aws_api_gateway_deployment` resource. This is explicitly recommended in the Terraform AWS provider docs.
**Warning signs:** Error during `terraform apply` when the deployment resource is replaced.

## Code Examples

### Complete step_function.tf
```hcl
# Source: terraform-aws-modules/step-functions/aws v5.1.0 + existing codebase patterns

# -----------------------------------------------------------------------------
# IAM Role: Step Functions execution
# -----------------------------------------------------------------------------

resource "aws_iam_role" "test_sf_execution" {
  name               = "ferry-test-sf-execution"
  assume_role_policy = data.aws_iam_policy_document.test_sf_assume_role.json

  tags = {
    Name = "ferry-test-sf-execution"
  }
}

resource "aws_iam_policy" "test_sf_invoke_lambda" {
  name   = "ferry-test-sf-invoke-lambda"
  policy = data.aws_iam_policy_document.test_sf_invoke_lambda.json

  tags = {
    Name = "ferry-test-sf-invoke-lambda"
  }
}

resource "aws_iam_role_policy_attachment" "test_sf_invoke_lambda" {
  role       = aws_iam_role.test_sf_execution.name
  policy_arn = aws_iam_policy.test_sf_invoke_lambda.arn
}

resource "aws_iam_policy" "test_sf_logs" {
  name   = "ferry-test-sf-logs"
  policy = data.aws_iam_policy_document.test_sf_logs.json

  tags = {
    Name = "ferry-test-sf-logs"
  }
}

resource "aws_iam_role_policy_attachment" "test_sf_logs" {
  role       = aws_iam_role.test_sf_execution.name
  policy_arn = aws_iam_policy.test_sf_logs.arn
}

# -----------------------------------------------------------------------------
# Step Functions State Machine
# -----------------------------------------------------------------------------

module "step_function" {
  source  = "terraform-aws-modules/step-functions/aws"
  version = "5.1.0"

  name = var.sf_name
  type = "STANDARD"

  definition = jsonencode({
    Comment = "Placeholder -- overwritten by Ferry deploy"
    StartAt = "Placeholder"
    States = {
      Placeholder = {
        Type = "Pass"
        End  = true
      }
    }
  })

  create_role       = false
  use_existing_role = true
  role_arn          = aws_iam_role.test_sf_execution.arn

  tags = {
    Name = var.sf_name
  }
}
```

### Complete api_gateway.tf
```hcl
# Source: Terraform AWS provider docs for aws_api_gateway_rest_api/deployment/stage

# -----------------------------------------------------------------------------
# IAM Role: API Gateway invocation (StartExecution)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "test_apgw_invoke" {
  name               = "ferry-test-apgw-invoke"
  assume_role_policy = data.aws_iam_policy_document.test_apgw_assume_role.json

  tags = {
    Name = "ferry-test-apgw-invoke"
  }
}

resource "aws_iam_policy" "test_apgw_start_execution" {
  name   = "ferry-test-apgw-start-execution"
  policy = data.aws_iam_policy_document.test_apgw_start_execution.json

  tags = {
    Name = "ferry-test-apgw-start-execution"
  }
}

resource "aws_iam_role_policy_attachment" "test_apgw_start_execution" {
  role       = aws_iam_role.test_apgw_invoke.name
  policy_arn = aws_iam_policy.test_apgw_start_execution.arn
}

# -----------------------------------------------------------------------------
# API Gateway REST API
# -----------------------------------------------------------------------------

resource "aws_api_gateway_rest_api" "test" {
  name        = var.apigw_name
  description = "Ferry test API -- spec managed by Ferry deploy"

  body = jsonencode({
    openapi = "3.0.1"
    info = {
      title   = var.apigw_name
      version = "1.0"
    }
    paths = {}
  })

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  lifecycle {
    ignore_changes = [body]
  }

  tags = {
    Name = var.apigw_name
  }
}

resource "aws_api_gateway_deployment" "test" {
  rest_api_id = aws_api_gateway_rest_api.test.id
  description = "Initial placeholder deployment"

  triggers = {
    redeployment = sha1(jsonencode(aws_api_gateway_rest_api.test.body))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "test" {
  deployment_id = aws_api_gateway_deployment.test.id
  rest_api_id   = aws_api_gateway_rest_api.test.id
  stage_name    = "test"

  tags = {
    Name = "${var.apigw_name}-test"
  }
}
```

### IAM Policy Documents (additions to data.tf)
```hcl
# --- Trust policies ---

data "aws_iam_policy_document" "test_sf_assume_role" {
  statement {
    sid     = "StepFunctionsAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "test_apgw_assume_role" {
  statement {
    sid     = "APIGatewayAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }
  }
}

# --- SF execution permissions ---

data "aws_iam_policy_document" "test_sf_invoke_lambda" {
  statement {
    sid    = "InvokeLambda"
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction",
    ]
    resources = [
      module.test_lambda.lambda_function_arn,
      "${module.test_lambda.lambda_function_arn}:*",
    ]
  }
}

data "aws_iam_policy_document" "test_sf_logs" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["*"]
  }
}

# --- APGW invocation permissions ---

data "aws_iam_policy_document" "test_apgw_start_execution" {
  statement {
    sid    = "StartExecution"
    effect = "Allow"
    actions = [
      "states:StartExecution",
    ]
    resources = [
      module.step_function.state_machine_arn,
    ]
  }
}

# --- Deploy role: SF permissions ---

data "aws_iam_policy_document" "test_sf_deploy" {
  statement {
    sid    = "StepFunctionsDeploy"
    effect = "Allow"
    actions = [
      "states:UpdateStateMachine",
      "states:DescribeStateMachine",
      "states:TagResource",
      "states:ListTagsForResource",
    ]
    resources = [
      module.step_function.state_machine_arn,
    ]
  }
}

# --- Deploy role: APGW permissions ---

data "aws_iam_policy_document" "test_apgw_deploy" {
  statement {
    sid    = "APIGatewayDeploy"
    effect = "Allow"
    actions = [
      "apigateway:PutRestApi",
      "apigateway:CreateDeployment",
      "apigateway:GetRestApi",
      "apigateway:GetTags",
      "apigateway:TagResource",
    ]
    resources = [
      "arn:aws:apigateway:${data.aws_region.current.id}::/restapis/${aws_api_gateway_rest_api.test.id}",
      "arn:aws:apigateway:${data.aws_region.current.id}::/restapis/${aws_api_gateway_rest_api.test.id}/*",
    ]
  }
}
```

### Deploy Role Extensions (additions to main.tf)
```hcl
# --- SF deploy policy ---

resource "aws_iam_policy" "test_sf_deploy" {
  name   = "ferry-test-sf-deploy"
  policy = data.aws_iam_policy_document.test_sf_deploy.json

  tags = {
    Name = "ferry-test-sf-deploy"
  }
}

resource "aws_iam_role_policy_attachment" "test_sf_deploy" {
  role       = aws_iam_role.test_deploy.name
  policy_arn = aws_iam_policy.test_sf_deploy.arn
}

# --- APGW deploy policy ---

resource "aws_iam_policy" "test_apgw_deploy" {
  name   = "ferry-test-apgw-deploy"
  policy = data.aws_iam_policy_document.test_apgw_deploy.json

  tags = {
    Name = "ferry-test-apgw-deploy"
  }
}

resource "aws_iam_role_policy_attachment" "test_apgw_deploy" {
  role       = aws_iam_role.test_deploy.name
  policy_arn = aws_iam_policy.test_apgw_deploy.arn
}
```

### New Variables (additions to variables.tf)
```hcl
variable "sf_name" {
  description = "Step Functions state machine name"
  type        = string
  default     = "ferry-test-sf"
}

variable "apigw_name" {
  description = "API Gateway REST API name"
  type        = string
  default     = "ferry-test-api"
}
```

### New Outputs (additions to outputs.tf)
```hcl
output "state_machine_name" {
  description = "Step Functions state machine name"
  value       = module.step_function.state_machine_name
}

output "state_machine_arn" {
  description = "Step Functions state machine ARN"
  value       = module.step_function.state_machine_arn
}

output "rest_api_id" {
  description = "API Gateway REST API ID"
  value       = aws_api_gateway_rest_api.test.id
}

output "rest_api_stage_url" {
  description = "API Gateway stage invoke URL"
  value       = aws_api_gateway_stage.test.invoke_url
}

output "apgw_invoke_role_arn" {
  description = "API Gateway invocation role ARN (for OpenAPI spec credentials)"
  value       = aws_iam_role.test_apgw_invoke.arn
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SF module v4.x (AWS provider ~>5.0) | SF module v5.x (AWS provider >=6.28) | v5.0.0, 2025-06-26 | Breaking: requires AWS provider 6.28+, our ~>6.0 satisfies this |
| `stage_name` on `aws_api_gateway_deployment` | Separate `aws_api_gateway_stage` resource | Provider v2+ | `stage_name` on deployment is deprecated; use dedicated stage resource |
| Monolithic API Gateway module | No REST API community module | Always | REST APIs never had a widely-adopted community module; native resources are standard |

**Deprecated/outdated:**
- `aws_api_gateway_deployment.stage_name`: Deprecated in favor of `aws_api_gateway_stage` resource. Do not use.
- SF module v4.x: Incompatible with AWS provider v6.x. Must use v5.0+.

## Open Questions

1. **API Gateway ARN format for deploy permissions**
   - What we know: API Gateway uses a non-standard ARN format for IAM: `arn:aws:apigateway:{region}::/restapis/{id}` (note double colon -- no account ID). The `create_deployment` action needs `arn:aws:apigateway:{region}::/restapis/{id}/*` to cover sub-resources.
   - What's unclear: Whether `apigateway:GetTags` and `apigateway:TagResource` need the `/tags/*` sub-resource path or just the REST API ARN.
   - Recommendation: Use both `arn:aws:apigateway:{region}::/restapis/{id}` and `arn:aws:apigateway:{region}::/restapis/{id}/*` in the resource list. This is standard practice and covers all sub-resource operations.

2. **Lambda InvokeFunction ARN with qualifier**
   - What we know: The SF execution role needs `lambda:InvokeFunction`. The Lambda module outputs `lambda_function_arn` which is the unqualified ARN.
   - What's unclear: Whether SF invocations may include a qualifier (version/alias) in the function ARN.
   - Recommendation: Include both the unqualified ARN and `${arn}:*` (qualified wildcard), matching the pattern already used in `test_lambda_deploy` policy. This is the pattern used in the existing codebase.

## Sources

### Primary (HIGH confidence)
- `terraform-aws-modules/step-functions/aws` GitHub repo -- README.md, variables.tf, outputs.tf, main.tf, CHANGELOG.md (v5.1.0, released 2026-01-08)
- `terraform-aws-modules/apigateway-v2/aws` GitHub repo -- README.md (confirmed HTTP/WebSocket only, NOT REST API)
- Terraform AWS provider docs -- `aws_api_gateway_rest_api`, `aws_api_gateway_deployment`, `aws_api_gateway_stage` resource docs (from hashicorp/terraform-provider-aws GitHub)
- Existing codebase -- `iac/test-env/` files (main.tf, data.tf, variables.tf, outputs.tf, providers.tf)
- Deploy code -- `deploy_stepfunctions.py`, `deploy_apigw.py` (for exact API calls and permission requirements)

### Secondary (MEDIUM confidence)
- SF module versions.tf -- confirms AWS provider >= 6.28 requirement (compatible with our ~> 6.0)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Verified module version, capabilities, and limitations via GitHub source code
- Architecture: HIGH - Patterns directly match existing codebase and are verified against official Terraform docs
- Pitfalls: HIGH - Body drift issue verified via official Terraform docs; `create_before_destroy` recommended in official docs
- IAM: HIGH - Trust policies follow standard AWS service principal patterns; deploy permissions derived from actual deploy code API calls

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (stable -- Terraform modules change slowly)
