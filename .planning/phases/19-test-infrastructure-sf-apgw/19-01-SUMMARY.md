---
phase: 19-test-infrastructure-sf-apgw
plan: 01
subsystem: iac/test-env
tags: [terraform, step-functions, api-gateway, iam, infrastructure]
dependency-graph:
  requires: []
  provides: [sf-state-machine, apgw-rest-api, sf-execution-role, apgw-invoke-role, sf-deploy-perms, apgw-deploy-perms]
  affects: [ferry-test-deploy-role, test-env-outputs]
tech-stack:
  added: [terraform-aws-modules/step-functions/aws@5.1.0]
  patterns: [external-role-for-module, lifecycle-ignore-changes, create-before-destroy]
key-files:
  created:
    - iac/test-env/step_function.tf
    - iac/test-env/api_gateway.tf
  modified:
    - iac/test-env/variables.tf
    - iac/test-env/data.tf
    - iac/test-env/main.tf
    - iac/test-env/outputs.tf
    - iac/test-env/README.md
decisions:
  - Used terraform-aws-modules/step-functions/aws v5.1.0 with external execution role (create_role=false, use_existing_role=true)
  - Used native aws_api_gateway_rest_api resources (community module only supports HTTP/WebSocket, not REST)
  - APGW REST API body uses lifecycle ignore_changes to prevent Terraform from reverting Ferry deploys
  - APGW deployment uses create_before_destroy to avoid "active stages" error
metrics:
  duration: 195s
  completed: 2026-03-08
  tasks: 4/4
---

# Phase 19 Plan 01: SF + APGW Test Infrastructure Terraform Summary

Standard Step Functions state machine (v5.1.0 module, placeholder Pass state) and REGIONAL REST API (placeholder OpenAPI body) with full IAM: SF execution role (lambda:InvokeFunction + CloudWatch Logs), APGW invocation role (states:StartExecution), and ferry-test-deploy role extended with SF + APGW deploy permissions.

## Tasks Completed

| Task | Name | Commit | Key Changes |
|------|------|--------|-------------|
| 1 | Add variables and IAM policy documents | 700c0db | variables.tf (+2 vars), data.tf (+7 policy documents) |
| 2 | Create step_function.tf and api_gateway.tf | 700c0db | 2 new files: SF module + execution role, REST API + invoke role |
| 3 | Extend deploy role and add outputs | 700c0db | main.tf (+2 policy attachments), outputs.tf (+5 outputs) |
| 4 | Validate Terraform configuration | 700c0db | terraform fmt + validate pass, pre-commit hooks pass |

## What Was Built

### Step Functions (step_function.tf)
- **IAM Role** `ferry-test-sf-execution` with states.amazonaws.com trust
- **Policies**: lambda:InvokeFunction (scoped to test Lambda ARN + :*), CloudWatch Logs (CreateLogGroup, CreateLogStream, PutLogEvents)
- **Module** `step_function` (terraform-aws-modules/step-functions/aws v5.1.0): STANDARD type, placeholder Pass state definition, external execution role

### API Gateway (api_gateway.tf)
- **IAM Role** `ferry-test-apgw-invoke` with apigateway.amazonaws.com trust
- **Policy**: states:StartExecution (scoped to state machine ARN)
- **REST API** `ferry-test-api`: REGIONAL endpoint, placeholder OpenAPI 3.0.1 body, lifecycle ignore_changes=[body]
- **Deployment**: create_before_destroy=true, triggers on body SHA1
- **Stage**: "test"

### Deploy Role Extensions (main.tf)
- **SF deploy policy** `ferry-test-sf-deploy`: UpdateStateMachine, DescribeStateMachine, TagResource, ListTagsForResource
- **APGW deploy policy** `ferry-test-apgw-deploy`: PutRestApi, CreateDeployment, GetRestApi, GetTags, TagResource (double-colon ARN format)

### New Outputs (outputs.tf)
- `state_machine_name`, `state_machine_arn` (from SF module)
- `rest_api_id`, `rest_api_stage_url` (from APGW resources)
- `apgw_invoke_role_arn` (needed by Phase 20 OpenAPI spec)

### Data Sources (data.tf)
- 7 new IAM policy documents: 2 trust (SF, APGW), 2 SF execution (invoke lambda, logs), 1 APGW invocation (start execution), 2 deploy role (SF deploy, APGW deploy)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] terraform_docs pre-commit hook modified README.md**
- **Found during:** Commit
- **Issue:** Pre-commit hook `terraform_docs` auto-generated updated README.md with new resources/outputs
- **Fix:** Added iac/test-env/README.md to the commit and re-ran
- **Files modified:** iac/test-env/README.md
- **Commit:** 700c0db

## Decisions Made

1. **External execution role for SF module** -- Set both `create_role=false` and `use_existing_role=true` to avoid module-managed role and use our explicitly defined IAM role with scoped permissions.
2. **Native REST API resources** -- Used aws_api_gateway_rest_api/deployment/stage instead of community module because terraform-aws-modules/apigateway only supports HTTP and WebSocket APIs, not REST APIs.
3. **lifecycle ignore_changes=[body]** -- Prevents `terraform apply` from reverting Ferry's deployed OpenAPI spec back to the placeholder.
4. **create_before_destroy on deployment** -- Required to avoid "Active stages pointing to this deployment must be moved or deleted" error during replacement.

## Verification Results

- `terraform fmt -check`: PASSED (all 7 files)
- `terraform validate`: PASSED (Success! The configuration is valid.)
- Pre-commit hooks: All passed (Terraform format, validate, tflint, trivy, terraform_docs)
- Policy document count in data.tf: 13 (6 existing + 7 new)
- Policy attachment count in main.tf: 7 (5 existing + 2 new)
- Output count in outputs.tf: 9 (4 existing + 5 new)

## Next Steps

- Run `terraform apply` in `iac/test-env/` to create the AWS resources (manual step)
- Phase 20 will add ASL definition, OpenAPI spec, and ferry.yaml entries referencing these resources
- Phase 21 will exercise the full APGW -> SF -> Lambda chain via Ferry deploy
