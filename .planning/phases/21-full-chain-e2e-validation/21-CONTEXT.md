# Phase 21: Full-Chain E2E Validation - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Prove the full integrated chain works: API Gateway → Step Function → Lambda, all deployed via Ferry. Verify independent SF and APGW deploy paths via Ferry dispatch, no-op skip detection via content-hash, and multi-type dispatch in a single push. Fix all bugs encountered. Produce a validation report.

This phase does NOT close the v1.3 milestone — that's a separate step after validation.

</domain>

<decisions>
## Implementation Decisions

### Chain verification approach (E2E-05)
- **Full data trace**: Call APGW endpoint with test payload, verify SF execution reaches SUCCEEDED status, AND verify Lambda output in SF execution history shows the payload flowed through
- **Test payload**: Simple JSON marker `{"source": "ferry-e2e-test", "timestamp": "..."}` — enough to trace through the chain
- **APGW invocation**: Use AWS CLI (`aws apigateway test-invoke-method` or equivalent SigV4-signed call). No additional setup needed since we have AWS credentials
- **SF verification**: Use `aws stepfunctions describe-execution --execution-arn <arn>` in a poll loop until status is SUCCEEDED, then check the output field for Lambda's response

### Hello-world Lambda modification
- **Echo input back**: Modify handler to return `{"source": event.get("source"), "message": "hello from ferry"}` so we can verify the payload flowed APGW → SF → Lambda and back
- **Timing**: Push Lambda code change as a **separate pre-push** before starting the SF/APGW E2E sequence. Get the Lambda deployed and stable first
- **Don't reconfirm Lambda deploy path**: Trust v1.2 — just push the change and let Ferry deploy it. If something breaks, we catch it anyway
- **Direct invoke after pre-push**: Run `aws lambda invoke` with the test payload to confirm the echo response works before testing through the chain. Isolates Lambda issues from chain issues

### Test sequence
1. Pre-push: Lambda code change (echo input) → wait for Ferry deploy → direct invoke to verify echo
2. E2E-01/02: Push SF definition change → verify Ferry detects, dispatches, deploys state machine
3. E2E-03/04: Push APGW spec change → verify Ferry detects, dispatches, deploys REST API
4. E2E-05: Invoke APGW POST endpoint → verify SF execution SUCCEEDED with Lambda output
5. E2E-06: No-op push → verify SF and APGW deploys skipped via content-hash
6. E2E-07: Push changing all three resource types → verify 3 separate dispatches all succeed

### Bug fix workflow (carried from Phase 17)
- Primary diagnostics: CloudWatch logs for webhook/dispatch, GHA logs for build/deploy
- No temporary debug logging — trust existing structured logging, improve permanently if insufficient
- One fix per commit, descriptive message
- SF + APGW deploys were individually proven in Phase 20 debugging — expect fewer bugs here, but iterate if needed

### Validation report
- Same format as Phase 17: steps executed, bugs found+fixed (with commit refs), final proof (invocation results), known limitations
- Include AWS resource links (CloudWatch log groups, GHA run URLs, Lambda/SF/APGW ARNs)
- Include a brief **v1.3 Summary** section at the end: what the full milestone proved (all 3 resource types deployed via Ferry, chain works, no-op skip works)
- Report lives in `.planning/phases/21-full-chain-e2e-validation/`

### Milestone closure
- Phase 21 is validation only. v1.3 milestone closure (archive, PROJECT.md/STATE.md updates) handled separately via `/gsd:complete-milestone`

### Claude's Discretion
- Exact polling interval/timeout for SF execution status check
- Whether to use `test-invoke-method` or `awscurl` for APGW invocation
- What constitutes meaningful "changes" for each push test (code change vs. comment/whitespace)
- Order of E2E-06 vs E2E-07 if dependencies suggest a different sequence

</decisions>

<specifics>
## Specific Ideas

- The Lambda echo response should include the `source` field from the input payload — this proves data flowed through all 3 layers (APGW → SF → Lambda → SF output)
- For the multi-type push (E2E-07), change something meaningful in each: Lambda handler tweak, SF definition tweak, APGW spec tweak — not just whitespace
- The no-op test (E2E-06) should push a change to a file outside all resource directories (e.g., README) to verify Ferry receives the webhook but correctly skips dispatch

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

<code_context>
## Code Context

### Test repo (AmitLaviDev/ferry-test-app)
- `services/hello-world/main.py` — Lambda handler to modify (add echo input)
- `workflows/hello-chain/definition.asl.json` — SF definition (from Phase 20)
- `api/hello-chain/openapi.yaml` — APGW spec (from Phase 20)
- `ferry.yaml` — all 3 resource types configured
- `.github/workflows/ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`

### Ferry deploy scripts (what the workflows call)
- `action/src/ferry_action/deploy_stepfunctions.py` — envsubst, hash check, `update_state_machine(publish=True)`
- `action/src/ferry_action/deploy_apigw.py` — envsubst, hash check, `put_rest_api(mode=overwrite)`, `create_deployment`
- `action/src/ferry_action/deploy.py` — Lambda deploy (update code, publish version, point alias)

### AWS resources (from test-env Terraform)
- Lambda: `ferry-test-hello-world`
- Step Function: `ferry-test-sf`
- REST API: ID from `terraform output rest_api_id`, stage: `test`
- Deploy role: `ferry-test-deploy` (has all 3 resource type permissions)

### Verification commands
- APGW invoke: `aws apigateway test-invoke-method` or SigV4-signed request
- SF status: `aws stepfunctions describe-execution --execution-arn <arn>`
- Lambda direct: `aws lambda invoke --function-name ferry-test-hello-world --payload '{"source":"ferry-e2e-test"}' /dev/stdout`

</code_context>

---

*Phase: 21-full-chain-e2e-validation*
*Context gathered: 2026-03-09*
