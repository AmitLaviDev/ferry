# Phase 19 Context: Test Infrastructure for SF + APGW

## Decisions

### 1. Resource Naming

| Resource | Name | Notes |
|----------|------|-------|
| Step Functions state machine | `ferry-test-sf` | Standard type |
| REST API | `ferry-test-api` | REGIONAL endpoint |
| SF execution role | `ferry-test-sf-execution` | Trusted by states.amazonaws.com |
| APGW invocation role | `ferry-test-apgw-invoke` | Trusted by apigateway.amazonaws.com |
| ferry.yaml SF key | `chain-sf` | `step_functions.chain-sf` |
| ferry.yaml APGW key | `chain-api` | `api_gateways.chain-api` |
| ferry.yaml iac fields | `module.chain_sf` / `module.chain_api` | Convention labels, not functional |

### 2. SF Execution Role Scope

- `lambda:InvokeFunction` on `ferry-test-hello-world` Lambda
- CloudWatch Logs permissions (`logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`)
- No X-Ray tracing

### 3. APGW Invocation Role

- Dedicated role `ferry-test-apgw-invoke`
- Trust policy: `apigateway.amazonaws.com`
- Permission: `states:StartExecution` on the `ferry-test-sf` state machine
- Referenced in Phase 20's OpenAPI spec `credentials` field

### 4. Terraform Organization

- New files in `iac/test-env/`:
  - `step_function.tf` — state machine resource + SF execution role + IAM
  - `api_gateway.tf` — REST API resource + stage + APGW invocation role + IAM
- Use **community modules**: `terraform-aws-modules/step-functions` and `terraform-aws-modules/apigateway`
- IAM policy documents added to `data.tf` (existing pattern)
- Deploy role policies (`ferry-test-deploy`) extended with SF + APGW permissions in `main.tf`

### 5. Deploy Role Permissions (ferry-test-deploy)

**Step Functions deploy policy:**
- `states:UpdateStateMachine`
- `states:DescribeStateMachine`
- `states:TagResource`
- `states:ListTagsForResource`

**API Gateway deploy policy:**
- `apigateway:PutRestApi`
- `apigateway:CreateDeployment`
- `apigateway:GetRestApi`
- `apigateway:GetTags`
- `apigateway:TagResource`

### 6. API Gateway Configuration

- Endpoint type: REGIONAL
- Stage name: `test`
- Placeholder body: minimal OpenAPI spec (will be overwritten by Ferry deploy)

## Code Context

### Existing test-env IaC (`iac/test-env/`)
- `main.tf` — ECR repo, deploy role (`ferry-test-deploy`), Lambda execution role, test Lambda module
- `data.tf` — OIDC remote state, trust policies, permission policy documents
- `variables.tf` — region, github_owner/repo, ECR name, Lambda name, placeholder image URI
- `outputs.tf` — deploy role ARN, ECR URL, Lambda name/ARN
- `providers.tf` — S3 backend (`test-env/terraform.tfstate`), AWS provider us-east-1

### Deploy code AWS API calls (from ferry-action)
- **SF deploy** (`deploy_stepfunctions.py`): `list_tags_for_resource`, `update_state_machine(publish=True)`, `tag_resource`
- **APGW deploy** (`deploy_apigw.py`): `get_tags`, `put_rest_api(mode=overwrite)`, `create_deployment(stageName)`, `tag_resource`
- Both use `sts:GetCallerIdentity` (always allowed, no explicit policy needed)

## Deferred Ideas

- (none — scope held tight)

## Phase Boundary

This phase creates AWS resources via Terraform only. It does NOT:
- Create test repo files (Phase 20)
- Run any deploys (Phase 21)
- Modify Ferry application code
