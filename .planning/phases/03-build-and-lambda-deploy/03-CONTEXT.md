# Phase 3: Build and Lambda Deploy - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

The Ferry Action receives a workflow_dispatch from the Ferry App, authenticates to AWS via OIDC, builds Lambda containers with the Magic Dockerfile, pushes to ECR, and deploys Lambda functions with version and alias management. This phase covers only Lambda deployments triggered by merge to main. Step Functions, API Gateway, and PR comment triggers are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Lambda directory convention
- Minimal structure: `main.py` + `requirements.txt` in the source_dir — nothing else required
- Entire source_dir contents copied into the container (not just .py files). User's directory = their container.
- Fixed handler: `main.handler` — every Lambda exports a `handler` function from `main.py`. Zero config.
- No excludes or ignore patterns — if it's in source_dir, it ships. Users organize their repo accordingly.

### Action workflow interface
- User creates their workflow file manually from docs/README template (like Digger)
- Minimal action inputs: just `aws-role-arn` (and optionally `aws-region`). Dispatch payload comes via workflow_dispatch inputs automatically.
- Matrix strategy: workflow fans out one job per Lambda resource for parallel builds
- Separate `ferry-action/setup` composite step parses the dispatch payload and outputs `matrix` as JSON — clean separation between setup (parse) and action (build/deploy)

### Deploy trigger & ECR tagging
- Deploy only on merge to main — no branch deploys in v1
- ECR image tag for merge deploys: `pr-{pr_number}`
- Code-only deploys: Ferry updates the function code image and publishes a version. Terraform owns all Lambda configuration (memory, timeout, env vars, VPC).
- Digest-based skip: log message ("Skipping deploy for X — image unchanged") + action output `skipped=true`

### Build & deploy logging
- Summary with collapsible detail: key milestones (building, pushing, deploying) as top-level log lines, Docker build output in GHA collapsible groups
- Common failure hints: catch known patterns (bad requirements, missing main.py, ECR auth failure) and add a one-liner remediation hint. Raw error for uncommon failures.
- Per-resource GHA job summary: each matrix job writes a markdown summary panel (resource name, ECR tag, Lambda version, deploy status, duration)
- Log masking: mask AWS account ID and role ARN via `::add-mask::`. ECR repo URIs and Lambda names stay visible.

### Claude's Discretion
- Lambda alias naming strategy (e.g., `live`, `current`, etc.)
- Docker build optimization (layer caching, multi-stage)
- OIDC token exchange implementation details
- Python script organization within the composite action

</decisions>

<specifics>
## Specific Ideas

- PR comment trigger ("ferry deploy") for manual deploys with `{branch_name}+{sha_4chars}` ECR tagging — user wants this but it's a separate phase
- User wants the workflow template to be copy-paste simple from docs, not auto-generated
- Matrix strategy was specifically chosen over sequential loop for parallel resource builds

</specifics>

<deferred>
## Deferred Ideas

- **PR comment trigger** ("ferry deploy") for manual/branch deploys — new capability, separate phase. Would use ECR tag `{branch_name}+{sha_4chars}`
- **Branch-based deploys** — deploying to staging from non-main branches
- **Configurable deploy branch** — letting users specify which branch triggers deploys in ferry.yaml

</deferred>

---

*Phase: 03-build-and-lambda-deploy*
*Context gathered: 2026-02-25*
