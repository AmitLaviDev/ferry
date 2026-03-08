# Phase 20 Context: Test Repo Updates

## Decisions

### 1. State Machine Behavior (ASL Definition)

- **Minimal**: Single Task state -> invoke Lambda -> End
- **Invocation mode**: RequestResponse (synchronous) — SF waits for Lambda result
- **Input handling**: Passthrough — whatever the SF execution receives is forwarded to the Lambda as-is
- **No error handling**: No Catch/Retry states. Keep it simple to minimize debug surface.
- **Lambda code**: Use existing hello-world Lambda as-is. If it needs tweaks for the chain, defer to Phase 21.

**ASL structure:**
```json
{
  "StartAt": "InvokeLambda",
  "States": {
    "InvokeLambda": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:ferry-test-hello-world",
      "End": true
    }
  }
}
```

### 2. API Gateway Integration Mapping (OpenAPI Spec)

- **Spec version**: Swagger 2.0 (best AWS API Gateway native support)
- **Path**: `POST /execute` — triggers the chain
- **Request mapping**: HTTP body passed as SF input via `$util.escapeJavaScript($input.body)` in request template
- **Response mapping**: Raw passthrough — return StartExecution response as-is (executionArn, startDate). Phase 21 verifies execution completion separately.
- **Integration type**: AWS (not AWS_PROXY) — uses request/response templates
- **SF ARN in spec**: Constructed from placeholders: `arn:aws:states:${AWS_REGION}:${ACCOUNT_ID}:stateMachine:ferry-test-sf`
- **Credentials**: Use `ferry-test-apgw-invoke` role ARN (also constructed from placeholders)

**Key integration block:**
```yaml
x-amazon-apigateway-integration:
  type: aws
  httpMethod: POST
  uri: "arn:aws:apigateway:${AWS_REGION}:states:action/StartExecution"
  credentials: "arn:aws:iam::${ACCOUNT_ID}:role/ferry-test-apgw-invoke"
  requestTemplates:
    application/json: |
      {
        "stateMachineArn": "arn:aws:states:${AWS_REGION}:${ACCOUNT_ID}:stateMachine:ferry-test-sf",
        "input": "$util.escapeJavaScript($input.body)"
      }
  responses:
    default:
      statusCode: "200"
```

### 3. rest_api_id Dependency in ferry.yaml

- **Approach**: Placeholder + documented manual step
- **Placeholder value**: `REST_API_ID_HERE` in ferry.yaml
- **Manual step**: After terraform apply (Phase 19), run `terraform output rest_api_id`, paste into ferry.yaml before pushing to test repo
- **state_machine_name**: No dependency issue — known value `ferry-test-sf` (from Terraform variables)

### 4. Resource Naming (from Phase 19 CONTEXT.md)

These names are already decided and carry forward:

| ferry.yaml key | Resource type | AWS name / ID |
|----------------|---------------|---------------|
| `hello-chain` (SF) | step_functions | `ferry-test-sf` |
| `hello-chain` (APGW) | api_gateways | `REST_API_ID_HERE` (placeholder) |

### 5. File Paths (from Success Criteria)

| File | Location in test repo |
|------|----------------------|
| ASL definition | `workflows/hello-chain/definition.asl.json` |
| OpenAPI spec | `api/hello-chain/openapi.yaml` |
| ferry.yaml | `ferry.yaml` (root, updated) |
| SF workflow | `.github/workflows/ferry-step_functions.yml` |
| APGW workflow | `.github/workflows/ferry-api_gateways.yml` |

### 6. Workflow Files

- Both workflows are near-identical to the templates in `docs/step-functions.md` and `docs/api-gateways.md`
- Key customization: `aws-region: us-east-1`, `aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}`
- The `uses: ./action/setup` and `uses: ./action/deploy-*` references point to the ferry repo's composite actions
- **Important**: Test repo workflows must reference `AmitLaviDev/ferry@main` (not `./action/`) since the actions live in the ferry repo, not the test repo

## Code Context

### Ferry deploy scripts (what the workflows call)
- `action/src/ferry_action/deploy_stepfunctions.py` — reads `INPUT_SOURCE_DIR/INPUT_DEFINITION_FILE`, envsubst, hash check, `update_state_machine(publish=True)`
- `action/src/ferry_action/deploy_apigw.py` — reads `INPUT_SOURCE_DIR/INPUT_SPEC_FILE`, envsubst, parse YAML/JSON, strip fields, canonical JSON, hash check, `put_rest_api(mode=overwrite)`, `create_deployment`
- `action/src/ferry_action/envsubst.py` — regex `r"\$\{(ACCOUNT_ID|AWS_REGION)\}"` only

### Ferry config schema (what ferry.yaml must match)
- `StepFunctionConfig`: name, source_dir, state_machine_name, definition_file
- `ApiGatewayConfig`: name, source_dir, rest_api_id, stage_name, spec_file
- Both are lists under `step_functions` / `api_gateways` in `FerryConfig`

### Existing test repo structure (from v1.2)
- `ferry.yaml` with `lambdas` section (hello-world Lambda)
- `.github/workflows/ferry-lambdas.yml`
- `services/hello-world/` (Lambda source code)

### Terraform outputs needed (from iac/test-env/)
- `rest_api_id` — required for ferry.yaml
- `rest_api_stage_url` — useful for Phase 21 invocation testing
- `state_machine_name` — already known: `ferry-test-sf`

## Deferred Ideas

- If the hello-world Lambda needs code changes to work well in the chain (e.g., echo input back), handle in Phase 21 during E2E debugging

## Phase Boundary

This phase creates files for the test repo only. It does NOT:
- Run terraform apply (Phase 19 manual step, assumed done)
- Push to the test repo (manual step after file creation)
- Run any deploys or test the chain (Phase 21)
- Modify Ferry application code
