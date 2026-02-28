# Phase 4: Extended Resource Types - Context

**Gathered:** 2026-02-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Ferry Action deploys Step Functions and API Gateways using the same dispatch and auth foundation as Lambda. This phase adds two new deploy modules (step_functions, api_gateway) with variable substitution, content-hash skip logic, and GHA summaries. The dispatch payload and OIDC auth are already in place from Phase 3. No new resource types beyond these two.

</domain>

<decisions>
## Implementation Decisions

### Step Functions definition file
- Configurable filename via `definition_file` field in ferry.yaml (required, no default)
- File lives relative to `source_dir` (e.g., `source_dir: pipelines/foo/definitions`, `definition_file: stepfunction.json`)
- envsubst-style variable substitution: replace `${ACCOUNT_ID}` and `${AWS_REGION}` in the definition
- Only these two variables — no custom variables or full env passthrough
- JSONPath expressions (`$.path`) are safe because substitution only targets `${}` patterns
- Target state machine identified by `state_machine_name` in ferry.yaml (required, no default)
- Ferry constructs the full ARN via STS GetCallerIdentity after OIDC auth: `arn:aws:states:{region}:{account_id}:stateMachine:{name}`

### API Gateway spec & staging
- Configurable spec file via `spec_file` field in ferry.yaml (required, no default)
- Support both YAML and JSON format — detect from file extension
- Same envsubst-style substitution: `${ACCOUNT_ID}` and `${AWS_REGION}`
- Strip known problematic OpenAPI fields before put-rest-api: `host`, `schemes`, `basePath`
- **Must clearly document which fields are stripped and why** in Ferry docs
- Target API Gateway identified by `rest_api_id` in ferry.yaml (required, no default)
- Target stage identified by `stage_name` in ferry.yaml (required, no default)
- Deploy via `put-rest-api` (upload spec) + `create-deployment` (push to stage)

### ferry.yaml config fields
- **StepFunctionConfig** new required fields: `state_machine_name`, `definition_file`
- **ApiGatewayConfig** new required fields: `rest_api_id`, `stage_name`, `spec_file`
- All fields required, no defaults — explicit over magical
- Name-based identification for state machines (ARN resolved at deploy time via STS)
- Consistent with Lambda's approach: `function_name` is just a name, not an ARN

### Deploy skip logic
- Content hash comparison: hash the substituted definition/spec content (after envsubst, after field stripping for APIGW)
- Store hash in AWS resource tags: `ferry:content-hash` tag on the Step Function and API Gateway
- Skip deploy if hash matches — same philosophy as Lambda's digest-based skip
- Log "Skipping deploy for X — definition unchanged" when skipped

### Deploy logging & summaries
- Same GHA job summary table format as Lambda, with type-specific fields:
  - Step Functions: state machine name, definition file, version ARN, deploy status
  - API Gateway: REST API ID, stage, deployment ID, deploy status
- Same error hint pattern: catch known AWS errors, add one-liner remediation hints
  - SF examples: StateMachineDoesNotExist, AccessDenied, InvalidDefinition
  - APIGW examples: NotFoundException, BadRequestException (invalid spec)
- Collapsible groups for detailed output, key milestones as top-level log lines

### Claude's Discretion
- envsubst implementation approach (regex, string replace, or actual envsubst)
- Exact content hashing algorithm (SHA256 likely)
- How to handle the STS call (cache account ID across resources or call per resource)
- Python module organization for the new deploy modules
- Which additional OpenAPI fields (if any) need stripping beyond host/schemes/basePath

</decisions>

<specifics>
## Specific Ideas

- Follow the same patterns as the ref repo (pipelines-hub): envsubst for variable substitution, field stripping for APIGW specs
- Keep deploy modules consistent with the existing Lambda deploy module structure (deploy.py pattern)
- Documentation requirement: clearly document which OpenAPI fields are stripped and why — users should not be surprised

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-extended-resource-types*
*Context gathered: 2026-02-26*
