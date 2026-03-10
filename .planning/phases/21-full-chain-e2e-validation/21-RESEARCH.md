# Phase 21: Full-Chain E2E Validation - Research

**Researched:** 2026-03-09

## Current State

### Infrastructure (all verified deployed)
- **Lambda:** `ferry-test-hello-world` (image-based, `live` alias, us-east-1)
- **Step Function:** `ferry-test-sf` (STANDARD type, `ferry-test-sf-execution` role)
- **REST API:** ID `v1h1ch5rqk`, stage `test`, REGIONAL endpoint
- **Deploy role:** `ferry-test-deploy` (OIDC trust for `AmitLaviDev/ferry-test-app`)
- **APGW invoke role:** `ferry-test-apgw-invoke` (allows `states:StartExecution`)
- **SF execution role:** `ferry-test-sf-execution` (allows `lambda:InvokeFunction`)

### Deploy Scripts (content-hash skip logic)
- **Lambda** (`deploy.py`): Compares ECR image digest. Skip if digest matches.
- **Step Functions** (`deploy_stepfunctions.py`): SHA-256 of envsubst'd definition. Reads `ferry:content-hash` tag. Skip if hash matches.
- **API Gateway** (`deploy_apigw.py`): SHA-256 of canonical JSON (sorted keys, stripped fields). Reads `ferry:content-hash` tag. Skip if hash matches.

### Multi-Type Dispatch (handler.py)
- `match_resources(config, changed_files)` returns all affected resources across all types
- `trigger_dispatches()` groups by type, sends ONE `workflow_dispatch` per resource type
- Example: push touching Lambda + SF + APGW files → 3 parallel dispatches

### Phase 20 State
- Test repo files created and pushed (SF definition, APGW spec, ferry.yaml, workflow files)
- SF + APGW deploys individually proven working during debugging (5 bugs fixed)
- Lambda deploy path proven in v1.2

### AWS Details
- **Account:** 050068574410
- **Region:** us-east-1
- **Ferry Function URL:** `https://6dtb47ahdfi4hywuclwhwl7x5q0wizqz.lambda-url.us-east-1.on.aws/`
- **SF ARN:** `arn:aws:states:us-east-1:050068574410:stateMachine:ferry-test-sf`
- **REST API stage URL:** `https://v1h1ch5rqk.execute-api.us-east-1.amazonaws.com/test`
- **CloudWatch log group:** `/aws/lambda/ferry-backend`

## Key Verification Commands

```bash
# Lambda direct invoke
aws lambda invoke --function-name ferry-test-hello-world --qualifier live \
  --payload '{"source":"ferry-e2e-test"}' /dev/stdout

# APGW test invoke (IAM auth, POST /execute)
aws apigateway test-invoke-method \
  --rest-api-id v1h1ch5rqk \
  --resource-id <resource-id> \
  --http-method POST \
  --body '{"source":"ferry-e2e-test","timestamp":"..."}'

# SF execution status
aws stepfunctions describe-execution --execution-arn <arn>

# GHA workflow runs
gh run list -R AmitLaviDev/ferry-test-app --limit 5

# CloudWatch logs
aws logs tail /aws/lambda/ferry-backend --since 5m --format short
```

## Plan Structure Decision

**3 plans** following Phase 17 pattern:
1. **21-01:** Pre-push Lambda echo + individual SF/APGW deploy verification (wave 1, interactive)
2. **21-02:** Full chain invocation + no-op skip + multi-type push (wave 2, interactive)
3. **21-03:** Validation report (wave 3, autonomous)

All E2E tasks are `checkpoint:human-verify` since they require real AWS infrastructure interaction and manual push/verification cycles.

---

*Phase: 21-full-chain-e2e-validation*
*Research completed: 2026-03-09*
