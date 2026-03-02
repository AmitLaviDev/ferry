# Phase 13: Backend Core - Context

**Gathered:** 2026-03-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Deploy Ferry's Lambda backend with Function URL, DynamoDB dedup table, and CloudWatch log group via Terraform. Wire environment variables to reference Secrets Manager secret names and DynamoDB table name. All IAM roles and secrets infrastructure already exist from Phase 12.

**Pre-requisite:** Phase 12.1 (IaC directory restructure + state migration) must complete first — Phase 13 builds in the new directory layout.

</domain>

<decisions>
## Implementation Decisions

### Lambda Configuration
- Memory: 256 MB
- Timeout: 30 seconds
- Architecture: arm64 (container image)
- Reserved concurrency: none (unreserved account pool)
- Ephemeral storage: 512 MB (default)
- Function URL: auth=NONE (HMAC validation handled in app code)

### TF Project Layout
- Phase 13 project lives at: `iac/aws/staging/us-east-1/ferry_backend/`
- Follows ConvergeBio/iac-tf conventions
- Phase 12.1 (separate phase) restructures the entire iac directory first:
  - Global: `iac/global/cloud/aws/{backend,ecr,oidc}`
  - Staging shared (non-regional): `iac/aws/staging/shared/` — single project, NOT split (iam.tf + secrets.tf stay together)
  - Staging regional: `iac/aws/staging/us-east-1/ferry_backend/`
- State migration required for all existing TF projects during Phase 12.1

### DynamoDB Table
- Table name: `ferry-webhook-dedup`
- Partition key: `pk` (String, HASH)
- Sort key: `sk` (String, RANGE)
- TTL attribute: `expires_at`
- Billing mode: PAY_PER_REQUEST
- Schema matches existing app code in `dedup.py` exactly

### Environment Variable Contract
- Individual secret name env vars (not ARNs, not a prefix):
  - `FERRY_APP_ID_SECRET` → Secrets Manager secret name for GitHub App ID
  - `FERRY_PRIVATE_KEY_SECRET` → Secrets Manager secret name for private key
  - `FERRY_WEBHOOK_SECRET_SECRET` → Secrets Manager secret name for webhook secret
- Direct value env vars:
  - `FERRY_TABLE_NAME` → DynamoDB table name (`ferry-webhook-dedup`)
  - `FERRY_LOG_LEVEL` → set explicitly in TF (default: `INFO`)
- Note: settings.py will need updating (Phase 14 scope) to resolve secrets from names at cold start

### Claude's Discretion
- `FERRY_INSTALLATION_ID` handling — TF variable or Secrets Manager secret, whichever fits the pattern better
- CloudWatch log group naming convention
- Terraform file organization within the ferry_backend project (providers.tf, main.tf, variables.tf, outputs.tf pattern)
- How to reference remote state from shared IAM and ECR projects

</decisions>

<specifics>
## Specific Ideas

- Directory structure should mirror ConvergeBio/iac-tf conventions exactly
- "us-east-1" is the region directory name (not us_east_1)
- The shared project stays as one project during the restructure (Phase 12.1) — iam.tf + secrets.tf together, just directory move

</specifics>

<deferred>
## Deferred Ideas

- IaC directory restructure + state migration — captured as Phase 12.1 (must execute before Phase 13)
- settings.py modification to resolve secrets from names at cold start — Phase 14 (DEPLOY-03)

</deferred>

---

*Phase: 13-backend-core*
*Context gathered: 2026-03-01*
