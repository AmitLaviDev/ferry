# Phase 11: Bootstrap + Global Resources - Context

**Gathered:** 2026-02-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Terraform state management and container registry exist so all subsequent IaC projects can initialize and the Lambda has an image to reference. Delivers: S3 state bucket, ECR repo with lifecycle policy, placeholder container image, and a bootstrap script to orchestrate the setup.

</domain>

<decisions>
## Implementation Decisions

### IaC directory layout
- Follow ConvergeBio pattern: `global/aws/` for account-wide resources, `environments/staging/{region}/` for per-environment
- Global resources: `iac/global/aws/backend/` (S3 state bucket), `iac/global/aws/ecr/` (ECR repo)
- Per-environment resources (future phases): `iac/environments/staging/us-east-1/iam/`, `iac/environments/staging/us-east-1/app/`
- Include region level in environment path (`us-east-1`) per ConvergeBio convention
- Each TF project has standard file split: providers.tf, main.tf, variables.tf, outputs.tf, data.tf, locals.tf

### Resource naming
- S3 state bucket: `ferry-terraform-state`
- ECR repo: `lambda-ferry-backend` (one ECR repo per Lambda, naming pattern: `lambda-ferry-{lambda-name}`)
- State keys mirror directory structure: e.g., `global/aws/ecr/terraform.tfstate`

### AWS region + account
- Region: us-east-1
- Dedicated AWS account for Ferry (no project prefixes needed for uniqueness)
- Assume-role provider pattern in all TF projects (not bare credentials)
- No DynamoDB lock table — use Terraform native `use_lockfile = true`

### Bootstrap automation
- Idempotent `scripts/bootstrap.sh` handles full sequence:
  1. S3 state bucket: init with local state → apply → add backend config → init -migrate-state
  2. ECR: terraform apply for ECR project
  3. Placeholder image: build minimal hello-world Dockerfile, tag, push to ECR
- Script checks state at each step, skips what's already done — safe to re-run
- Minimal hello-world placeholder image (not just a base image pull) — returns health check response

### Claude's Discretion
- Exact Terraform resource configurations (encryption, versioning, tags)
- Hello-world Dockerfile implementation details
- Bootstrap script error handling and logging
- ECR lifecycle policy specifics (keep last 10 per requirements)

</decisions>

<specifics>
## Specific Ideas

- Bootstrap script should be one command to go from zero AWS to ready-for-next-phase
- `use_lockfile = true` instead of DynamoDB — Terraform native locking, no extra infrastructure
- Each Lambda gets its own ECR repo (pattern: `lambda-ferry-{name}`) even though there's currently only one

</specifics>

<deferred>
## Deferred Ideas

- Python package restructuring (ferry_backend → ferry.backend namespace package) — potential future tech debt phase

</deferred>

---

*Phase: 11-bootstrap-global-resources*
*Context gathered: 2026-02-28*
