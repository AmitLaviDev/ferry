# Phase 12: Shared IAM + Secrets - Context

**Gathered:** 2026-03-01
**Status:** Ready for planning

<domain>
## Phase Boundary

IAM roles and secrets infrastructure exist so the Lambda can assume its execution role and the GHA workflow can authenticate via OIDC. This phase creates: Lambda execution role, OIDC provider, GHA deploy roles (self-deploy + dispatch), and Secrets Manager containers for GitHub App credentials. No secret values are populated (that's Phase 14).

</domain>

<decisions>
## Implementation Decisions

### OIDC Trust Scope
- Account-wide OIDC provider for `token.actions.githubusercontent.com` — lives in `iac/global/aws/oidc/`
- GHA deploy role trust: repo-only scope (any workflow in the ferry repo can assume)
- Lambda execution role: standard `lambda.amazonaws.com` service trust (not OIDC)
- **Two separate GHA roles**: one for self-deploy (ferry repo), one for dispatch-triggered workflows (customer repos). Clean separation now avoids entangling permissions later

### Secrets Structure
- **Separate secrets per credential** — not a single JSON blob
- Naming convention: `ferry/github-app/{name}` — three secrets:
  - `ferry/github-app/app-id`
  - `ferry/github-app/private-key`
  - `ferry/github-app/webhook-secret`
- Standard tags on all secrets: `Project=ferry`, `ManagedBy=terraform`, `Component=github-app`

### TF Project Layout
- OIDC provider: `iac/global/aws/oidc/` (account-wide, follows iac-tf pattern)
- IAM roles + secrets + OIDC role bindings: `iac/staging/aws/shared/` (account/env-specific, not global)
- TF state keys match directory paths: e.g., `staging/aws/shared/terraform.tfstate`, `global/aws/oidc/terraform.tfstate`
- File split follows iac-tf convention: `iam.tf`, `secrets.tf`, `oidc.tf` (role bindings), `data.tf`, `providers.tf`, `variables.tf`, `outputs.tf`

### Policy Granularity
- HCL `data.aws_iam_policy_document` blocks (type-safe, composable) — no inline JSON
- **Wildcard-scoped now, tighten to exact ARNs in Phase 13** — avoids circular dependency since DynamoDB table and log groups don't exist yet
- Lambda execution role needs: DynamoDB (ferry-*), Secrets Manager (ferry/*), CloudWatch Logs (ferry-*)
- GHA self-deploy role: ECR push (ferry/backend) + Lambda update-function-code
- GHA dispatch role: ECR push (ferry/*) + Lambda update (ferry-*) — broader scope for future customer-repo dispatches

### Claude's Discretion
- Secret initial values approach (empty string vs no initial version)
- Exact IAM policy document structure and data source organization
- Whether to use `locals` for policy attachment maps (like iac-tf) or direct attachments
- Role and policy naming convention (PascalCase like iac-tf vs kebab-case)

</decisions>

<specifics>
## Specific Ideas

- Follow iac-tf `teams/platform/aws/prod/shared/` pattern for file organization — iam.tf with policies + roles + attachments, data.tf with policy documents
- iac-tf uses `for_each` with `local.*_policy_attachments` maps for role-policy attachments — clean pattern to follow
- Reference repo: `ConvergeBio/iac-tf` at `teams/platform/aws/prod/shared/` for the exact conventions

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 12-shared-iam-secrets*
*Context gathered: 2026-03-01*
