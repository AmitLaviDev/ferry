# Phase 15: Deploy Ferry Infrastructure - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Apply all Ferry AWS infrastructure, register the GitHub App, populate secrets, and verify the full system is live. This phase executes the runbook from Phase 14 (`docs/setup-runbook.md`) — no new IaC code is written, no new features are added. The deliverable is a running system, not code.

</domain>

<decisions>
## Implementation Decisions

### Plan structure
- Plans should be **operational checklists with verification gates**, not code-writing tasks
- Each plan covers a logical group of steps from the runbook
- Plans must clearly separate automated steps (terraform, AWS CLI) from manual steps (GitHub App registration in browser)
- Plans should include the exact commands from the runbook, not reinvent them

### Terraform apply strategy
- Apply projects in dependency order: bootstrap → ECR → OIDC → shared IAM/secrets → backend
- Run `terraform plan` before each apply and verify no unexpected changes
- Validate each project succeeded before moving to the next (check outputs, resource existence)
- If a plan shows unexpected drift or resources, stop and investigate — don't blindly apply

### GitHub App configuration
- App name: user decides at registration time (runbook suggests "Ferry" or "Ferry-Staging")
- Install scope: "Only select repositories" — install on the ferry repo only for now
- Permissions and events: exactly as documented in the runbook (Contents:Read, PRs:RW, Checks:RW, Actions:Write, Push events)
- Installation ID: use Option B (Terraform variable) for permanence, not the quick CLI hack

### Verification approach
- Verify against all 5 success criteria from the roadmap — not just a quick curl
- Verification is sequential: each criterion builds on the previous
- For the self-deploy test (criterion 5): push a trivial commit to trigger the pipeline rather than waiting for a real change

### Claude's Discretion
- Exact plan split (how many plans, how steps are grouped)
- Whether to create a small verification script vs manual command-by-command checks
- Terraform workspace naming if relevant

</decisions>

<specifics>
## Specific Ideas

- The runbook at `docs/setup-runbook.md` is the primary reference — plans should point to it, not duplicate it
- Known issue: `find_open_prs` in checks/runs.py crashes on 403 response — this may surface during webhook testing
- The existing self-deploy workflow is at `.github/workflows/self-deploy.yml`
- Four Terraform projects to apply, in this layout:
  - `iac/global/cloud/aws/backend/` (S3 state backend)
  - `iac/global/cloud/aws/ecr/` (ECR repo)
  - `iac/global/cloud/aws/oidc/` (GitHub OIDC provider)
  - `iac/aws/staging/shared/` (IAM roles, secrets)
  - `iac/aws/staging/us-east-1/ferry_backend/` (Lambda, DynamoDB, Function URL)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 15-deploy-ferry-infrastructure*
*Context gathered: 2026-03-03*
