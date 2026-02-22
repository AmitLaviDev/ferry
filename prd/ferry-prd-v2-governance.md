# Ferry — Product Requirements Document
## Version 2: Security & Governance First

**Document status:** Draft v2.0
**Author:** Ferry Product Team
**Date:** 2026-02-22
**Strategic angle:** Audit trail, ACLs, compliance, and drift prevention — "Every serverless change tracked, controlled, and reversible — without the overhead of a platform team."

---

# Problem Alignment

## Problem & Opportunity

Serverless teams running AWS Lambda, Step Functions, and API Gateway have no reliable, automated way to keep their deployed infrastructure synchronized with code — leaving them exposed to silent configuration drift, zero audit trail, and no recoverable state when production breaks. This is not a niche edge case: 1.8 million AWS customers run Lambda monthly (AWS re:Invent 2025), 70% of AWS customers use serverless (Datadog), and fewer than 50% of organizations can detect and fix drift within 24 hours (Firefly 2024). The consequence is both operational (outages caused by untracked console changes) and legal: ClickOps deployments directly violate SOC 2 and ISO 27001 by bypassing version control, audit trails, and peer review. The governance problem is worsening as serverless scales — Capital One now runs tens of thousands of Lambda functions and built a dedicated Serverless Center of Excellence specifically because external tooling could not meet their needs. The window to establish a category-defining open-core GitOps platform for serverless is open now: Kubernetes solved this exact problem with ArgoCD (60% cluster adoption, NPS 79), the mental model exists in the market, and no equivalent tool exists for serverless.

## High Level Approach

Ferry is a continuously-running GitOps operator for AWS serverless infrastructure. It treats a Git repository as the single source of truth for the desired state of Lambda functions, Step Functions, and API Gateway, and continuously reconciles actual deployed state against that desired state — automatically detecting drift, alerting teams through GitHub Issues, enforcing team-level ACLs at the deployment action level, and producing a structured, immutable audit trail. The operator pattern follows the proven ArgoCD model applied to serverless: a GitHub App backend watches repos, runs reconciliation on PR events and on a scheduled loop, and applies changes through a controlled pipeline that requires peer review before production.

**Alternatives considered:**

- **Wrapping Terraform/Pulumi:** Both tools have partial drift detection but require Kubernetes to run continuous reconciliation — ironic overhead for serverless teams. Neither understands Lambda-specific semantics (aliases, canary weights, version ARNs, provisioned concurrency). Terraform is generic IaC, not a serverless operator.
- **Extending Serverless Framework or SST:** Both are push-only deploy tools with no reconciliation loop. Serverless Framework's v4 pricing controversy ($2M+ revenue companies pay per credit) creates adoption risk. SST's audit trail lives in their SaaS, not in the customer's Git history. Neither has a workable ACL model.
- **Building on AWS CodeDeploy:** Provides Lambda canary/blue-green with CloudWatch alarm rollback but is not GitOps-native — there is no concept of Git as desired state, no drift detection, and no cross-service reconciliation.
- **Digger/Atlantis model applied to serverless:** PR-based GitOps for Terraform requires a long-running server or Kubernetes. The architecture is right (PR automation + plan/apply loop) but the engine underneath must be serverless-aware.

The chosen approach — a Git-native, continuously-running operator that understands serverless primitives — is the only architecture that can deliver continuous reconciliation, structured audit trail, and ACL enforcement simultaneously. No shortcut through existing tooling gets there.

### Narrative

**Before Ferry — The Compliance Audit**

It is 11 PM on a Tuesday. Your SOC 2 auditor has asked for a complete deployment history for the past 90 days across all Lambda functions in production. Your lead engineer opens the AWS Console and sees 47 functions in eu-west-1 alone. She opens CloudTrail — the logs are there but unstructured, tied to IAM principals rather than GitHub users, and contain no mapping to business features or git commits. She opens Slack and tries to reconstruct which engineer deployed what and when from a mix of informal messages, CloudFormation stack events, and CI pipeline logs spread across three different GitHub Actions workflows. Two functions show memory configurations that don't match the `serverless.yml` in the repository. Nobody knows when those changed or why. The audit takes three engineers four days to prepare. The auditor flags two findings. You do not get the certification on schedule.

**After Ferry — The Same Audit**

The auditor sends the same request. Your lead engineer opens the Ferry audit dashboard and runs a 90-day export for the production environment. Every deployment event is stored: timestamp, deployer (GitHub username), commit SHA, changeset diff, approval chain (which PR reviewer approved it), and the resulting deployed configuration. The two functions with memory drift were flagged by Ferry twelve days ago — a GitHub Issue was automatically created, assigned to the owning team, and the configuration was reverted to Git state within two hours. The audit response is a single export. The auditor has no findings. You get the certification.

---

**Before Ferry — The 3 AM Incident**

An engineer is on-call. A Lambda processing payment webhooks starts throwing 502s from API Gateway. The engineer checks the function in the console. Memory is 512MB — but the git repository says 256MB. Someone changed it in the console three weeks ago, nobody knows who, and a subsequent deploy from CI partially overwrote the change but left the API Gateway integration config in a broken intermediate state. There is no rollback button. Rollback via Serverless Framework requires reinstalling all plugins and re-running the full deploy from source — in a panicked 3 AM incident, that is a 25-minute gamble on a broken toolchain. The engineer manually patches the console. The incident resolution is undocumented. The drift is not tracked. It will happen again.

**After Ferry — The Same Incident**

The 502s trigger an alert. The on-call engineer opens the Ferry CLI: `ferry rollback --function payment-webhook --env prod --n 2`. Ferry identifies the last two known-good deployment states from its version history, shows a diff, and rolls back to the previous committed configuration in 90 seconds. The rollback itself is recorded as a deployment event in the audit trail — who triggered it, from which terminal, at what time, reverting to which commit. A post-incident issue is automatically opened in GitHub with full context. The root drift that caused the incident was already flagged by Ferry's reconciliation loop 21 days earlier but was dismissed — that dismissal is also in the audit trail.

---

**Before Ferry — The New Joiner**

A new backend engineer joins the team. She is told to deploy a fix to the user-notification Lambda. She has AWS Console access because "everyone has Console access." She makes the change directly in the console — it's faster. No PR. No review. No record. Three months later, a security audit reveals that the Lambda's execution role was broadened in that session to include `s3:*` on all buckets. Nobody knows who did it. The blast radius analysis takes a week.

**After Ferry — The Same Scenario**

The new engineer joins. She is told to make changes through the repository. Ferry's ACL configuration — defined in YAML in the repo itself — specifies that the `notifications` service requires a PR approval from a `senior-backend` team member before merge to main triggers a production deployment. She opens a PR. A senior engineer reviews it. The merge triggers Ferry's reconciliation loop. The deployment is attributed to her GitHub username in the audit trail. She never needs direct AWS Console access for deployments. Her IAM role has no deploy permissions — Ferry's service account handles the actual API calls. The blast radius of a compromised developer credential is near zero.

---

## Goals

**In priority order:**

**1. Make serverless deployments auditable and traceable (Primary)**
- Every production deployment records: deployer identity (GitHub username), commit SHA, environment, changeset diff, approval chain, and outcome
- Audit export covers 90-day window required for SOC 2 Type II evidence collection in under 5 minutes
- Zero "orphan" deployments — no production change goes unrecorded, including rollbacks and drift remediations
- Guardrail: Ferry must not introduce audit gaps. If the Ferry system itself fails to record a deployment event, that failure is itself logged and surfaced

**2. Detect and remediate configuration drift before it causes incidents (High)**
- Reconciliation loop runs at minimum every 15 minutes, event-driven on push within 60 seconds
- Drift detected and a GitHub Issue opened with full context (function name, expected vs. actual, diff) within 5 minutes of detection
- Remediation available in two modes: auto-revert (for pre-approved drift policies) and manual-approve via PR
- Guardrail: Auto-revert must never overwrite intentional emergency console changes made during active incidents — a "drift freeze" flag must exist

**3. Enforce access controls at the deployment action level (High)**
- ACL model defined declaratively in YAML in the repo, version-controlled alongside the infrastructure code it governs
- No developer requires direct AWS Console deploy permissions — Ferry's service account is the only principal with deploy rights in production
- Role-based model: Developer, Reviewer, Service Owner, Admin — each with scoped permissions per environment
- Guardrail: ACL model cannot be bypassed by modifying Ferry config files without going through the same PR review process (bootstrapped from Ferry's own config ACLs)

**4. Enable one-command rollback from Git history (Medium)**
- `ferry rollback --n <N>` restores a function or service group to its Nth-previous deployed state
- Rollback completes in under 3 minutes for a single-function rollback
- Rollback is a first-class deployment event — recorded, auditable, attributable
- Guardrail: Rollback must not bypass the ACL model — production rollbacks still require appropriate role

**5. Establish Git as the single, recoverable source of truth (Medium)**
- Ferry state includes full configuration snapshots — teams can rebuild from zero using `ferry apply --env prod --from-git`
- Recovery time objective (RTO) from total infrastructure loss: under 30 minutes for a 20-function service group
- Guardrail: Ferry state store is itself backed up and versioned — the tool that manages your disaster recovery must not be a single point of failure

**Immeasurable goals:**
- Engineers who join a Ferry-managed team should feel immediate confidence that they understand what is deployed and who deployed it
- Compliance officers should be able to answer "who changed that Lambda and when?" without involving an engineer
- On-call engineers should never have to guess whether what is in Git matches what is running in production

## Non-Goals

**V1 explicitly does not address:**

- **Multi-cloud support (Azure Functions, GCP Cloud Run, Cloudflare Workers):** AWS Lambda is the dominant platform (1.8M monthly active customers) and the right first wedge. Multi-cloud adds complexity before the core pattern is proven. Designed for extensibility, not built for it in V1.

- **UI/Dashboard:** V1 is CLI-first. A web UI adds significant frontend engineering and authentication surface area before the core value is proven. The GitHub Issues integration provides sufficient human-readable output at launch. UI is a Phase 2 priority.

- **Lambda code deployment (the application layer):** Ferry manages infrastructure configuration — runtime, memory, environment variables, IAM roles, triggers, API Gateway config, Step Function definitions. It does not replace your CI/CD pipeline for building and pushing application code artifacts. It orchestrates the infrastructure wrapping that code, not the code itself.

- **Automatic IAM policy generation:** Ferry enforces ACLs for who can deploy via Ferry. It does not auto-generate least-privilege IAM policies for Lambda execution roles. This is a Phase 2 security feature.

- **SaaS managed service:** V1 is self-hosted. Teams run the Ferry operator in their own AWS account. A SaaS hosted version is a revenue-generating Phase 2 offering.

- **Pricing/metering infrastructure:** V1 is free open-source. Commercial licensing and usage metering are Phase 2.

- **Support for frameworks beyond AWS native (Lambda, Step Functions, API Gateway):** No EventBridge Pipes, AppSync, SNS, SQS trigger management in V1 beyond what is required to describe a complete Lambda function. These are Phase 2 scope expansions.

---

# Solution Alignment

## Key Features

### Plan of Record (Priority Order)

**Feature 1: Git-Sync Operator (Core Reconciliation Loop)**
The heart of Ferry. A continuously-running process (deployed as a Lambda itself, or as an ECS task — ironically appropriate) that:
- Reads desired state from the connected Git repository (declarative YAML manifests)
- Reads actual state from AWS APIs (Lambda GetFunction, GetFunctionConfiguration, API Gateway GET, GetStateMachine)
- Computes a diff (desired vs. actual)
- When in sync: records a heartbeat, no action
- When drift detected: emits a drift event, creates a GitHub Issue, optionally auto-remediates per policy
- Runs on a 15-minute scheduled poll AND is event-triggered on every push to the watched branch

Acceptance criteria: Drift detection latency under 5 minutes from console change to GitHub Issue created. False positive rate under 1% (known-safe transient state changes, like Lambda cold-start metadata, must not trigger false drift alerts).

**Feature 2: GitHub App Integration**
Ferry operates as a GitHub App installed on the customer's org or repo. The App:
- Watches push events on configured branches (typically `main` for production, `develop` for staging)
- Posts plan output as PR comments when a PR is opened against a watched branch
- Applies on merge — no separate "trigger deploy" step
- Creates GitHub Issues for drift events, tagging the relevant service owner
- Posts deployment completion summaries with commit SHA, diff summary, and audit event link

Acceptance criteria: PR comment posted within 60 seconds of PR open. Apply triggered within 60 seconds of merge. All GitHub interactions use structured data (not freeform text) so they are parseable by other tooling.

**Feature 3: Declarative Manifest Format**
Teams define their serverless infrastructure in `ferry.yaml` files in their repo. Format:

```yaml
# ferry.yaml
service: payment-processor
environment: production
region: us-east-1

functions:
  process-webhook:
    runtime: python3.12
    memory: 512
    timeout: 30
    handler: src/handler.process
    role: arn:aws:iam::123456789:role/payment-processor-exec
    environment_variables:
      DB_SECRET: "{{ssm:/prod/payment/db-secret}}"
    triggers:
      - type: api_gateway
        path: /webhooks/payment
        method: POST

step_functions:
  payment-flow:
    definition: ./state-machines/payment-flow.json

acls:
  production:
    deploy: [senior-backend, platform-lead]
    review_required: true
    min_approvals: 1
```

Acceptance criteria: All configuration is valid YAML, version-controlled, diff-friendly, human-readable. SSM Parameter Store references are resolved at apply time, never stored in plain text. Schema is validated on PR with clear error messages.

**Feature 4: Structured Audit Trail**
Every deployment action Ferry takes or records is written to a structured audit log stored in the customer's own AWS account (DynamoDB or S3 + Athena):

Each audit record contains:
- `event_id` — UUID
- `event_type` — DEPLOY | ROLLBACK | DRIFT_DETECTED | DRIFT_REMEDIATED | DRIFT_DISMISSED | PLAN_RUN | ACL_DENIED
- `timestamp` — ISO 8601 UTC
- `actor` — GitHub username (or `ferry-operator` for automated actions)
- `commit_sha` — Git commit that triggered the action
- `environment` — staging | production
- `service` — service identifier
- `function_name` — specific function affected
- `change_summary` — structured diff of configuration fields changed
- `approval_chain` — array of {reviewer, approved_at, pr_url}
- `outcome` — SUCCESS | FAILURE | PARTIAL
- `failure_reason` — if applicable
- `aws_request_ids` — array of AWS API call IDs for cross-referencing CloudTrail

Audit records are write-once and immutable after creation. Audit export produces a JSON file or CSV suitable for auditor submission.

Acceptance criteria: 100% of Ferry-mediated deployment actions produce an audit record. Export for a 90-day window completes under 5 minutes. Audit records survive Ferry operator restarts — they are durable before the action is acknowledged as complete.

**Feature 5: CLI (`ferry`)**
A single binary CLI for human interaction with Ferry:

```
ferry plan [--env <env>] [--service <service>]     # Show what Ferry would change
ferry apply [--env <env>] [--service <service>]    # Apply changes from current Git state
ferry rollback [--env <env>] --function <fn> --n <N>  # Roll back N deployments
ferry drift [--env <env>]                          # Show current drift status across all services
ferry audit export [--days 90] [--format json|csv] # Export audit trail
ferry status                                        # Show reconciliation loop health
ferry init                                          # Bootstrap a new repo with Ferry
```

Acceptance criteria: All commands exit with machine-readable JSON when `--json` flag is passed. `ferry plan` produces output format consistent with `terraform plan` — engineers already know how to read it. `ferry rollback` completes under 3 minutes for a single function.

**Feature 6: ACL Enforcement Engine**
Ferry reads the `acls:` block from `ferry.yaml` and enforces it at the apply stage:
- If the PR that triggered the apply does not have the required number of approvals from users in the required roles, Ferry refuses to apply and posts a comment explaining the denial
- ACL denials are recorded in the audit trail as `ACL_DENIED` events
- Role membership is defined in a separate `ferry-teams.yaml` in the repo root — also version-controlled
- Ferry's own config files (`ferry.yaml`, `ferry-teams.yaml`) are protected by a `meta` ACL that requires admin role for changes — preventing privilege escalation via config modification

Acceptance criteria: An unauthorized deploy attempt (wrong role, insufficient approvals) results in an `ACL_DENIED` audit event and no AWS API calls. Role membership changes are also audit-logged. ACL enforcement cannot be disabled without an admin-role PR.

**Feature 7: Drift Detection with Auto-Remediation Policy**
Beyond just detecting drift, Ferry allows teams to define remediation policy per environment:

```yaml
drift_policy:
  staging:
    action: auto_revert    # Immediately revert to Git state
    notify: slack          # Also post to Slack
  production:
    action: alert_and_hold # Create GitHub Issue, do not auto-revert
    require_ack: true      # Issue must be acknowledged before next deploy
    drift_freeze: true     # Allow incident commander to pause drift checks
```

The `drift_freeze` flag is critical for production safety: during active incidents, on-call engineers make console changes to stop the bleeding. Auto-revert during an incident would be catastrophic. Ferry provides a `ferry drift freeze --duration 2h` command that suspends auto-remediation while still recording drift events.

Acceptance criteria: Auto-revert on staging completes within 5 minutes of drift detection. Production drift creates a GitHub Issue within 5 minutes. Drift freeze can be set from CLI without internet access to Ferry's config repo (uses a flag stored in AWS SSM, not Git). All drift events, remediations, dismissals, and freeze events are auditable.

**Feature 8: State Management with Versioning**
Ferry maintains its own state store, separate from and complementary to Terraform/CloudFormation state:
- Stores a full snapshot of the deployed configuration at each deployment
- Each snapshot is linked to a Git commit SHA
- Enables rollback without requiring the original source commit to be checked out
- State is stored in customer's DynamoDB (versioned item per function per deployment)
- State is not a substitute for infrastructure-as-code — it is the bridge between Git and AWS APIs

Acceptance criteria: `ferry rollback --n 2` resolves state without accessing the Git repo (uses state store snapshot). State store is not corrupted by a failed partial deployment — each state write is transactional. State can be exported and used to reconstruct infrastructure from zero.

---

### Future Considerations (Phase 2+)

- **Web UI / Dashboard** — Visual deployment history, drift status board, approval queue, audit trail explorer
- **SaaS hosted offering** — Managed Ferry backend, multi-tenant, metered pricing
- **Slack integration** — Rich deployment notifications, approval requests, drift alerts in Slack channels
- **Health-signal rollback** — Integrate with CloudWatch alarms; auto-rollback if error rate exceeds threshold post-deploy
- **IAM least-privilege advisor** — Analyze Lambda execution roles, surface over-permissioned roles, suggest minimums
- **Multi-cloud (Azure Functions, GCP Cloud Run)** — After proving the pattern on AWS
- **Policy-as-code (OPA integration)** — Custom compliance rules enforced at plan time (e.g., "no Lambda with more than X memory in production without admin approval")
- **Environment promotion flows** — Promote staging configuration to production through a governed, auditable promotion event
- **EventBridge, SQS, SNS trigger management** — Expand resource scope beyond V1
- **Secret scanning at plan time** — Detect hardcoded secrets in `ferry.yaml` before apply
- **Cost estimation** — Show projected cost delta at plan time

---

## Key Flows

### Flow 1: Standard Deployment (PR → Deploy)

```
Developer pushes code changes
        ↓
Opens PR against `main` (production branch)
        ↓
Ferry GitHub App receives PR opened event
        ↓
Ferry runs `plan` — computes diff between PR branch state and current deployed state
        ↓
Ferry posts PR comment: structured plan output (added/changed/deleted resources, estimated impact)
        ↓
Team reviews PR + plan comment
        ↓
Required approvers (per ACL config) approve the PR
        ↓
Developer merges PR
        ↓
Ferry GitHub App receives push event on `main`
        ↓
Ferry checks ACL: Did this PR have required approvals from required roles?
   → NO: Record ACL_DENIED audit event, post failure comment, stop. No AWS calls made.
   → YES: Proceed
        ↓
Ferry applies changes via AWS APIs (Lambda UpdateFunctionConfiguration, UpdateFunctionCode, etc.)
        ↓
Ferry writes DEPLOY audit record (actor, commit SHA, diff, approval chain, outcome)
        ↓
Ferry writes state snapshot to DynamoDB
        ↓
Ferry posts deployment completion comment on the (now merged) PR
        ↓
Ferry reconciliation loop validates deployed state matches desired state within 5 min
```

### Flow 2: Drift Detection → Alert → Remediation

```
[Scheduled: every 15 minutes | Event-triggered: any AWS Console change via CloudTrail]
        ↓
Ferry reads desired state from Git (latest commit on watched branch)
Ferry reads actual state from AWS APIs
        ↓
Ferry computes diff
        ↓
No diff detected → heartbeat recorded, no action
        ↓
Diff detected (example: Lambda memory changed from 256MB to 512MB in Console)
        ↓
Ferry records DRIFT_DETECTED audit event
        ↓
Ferry checks `drift_policy` for the affected environment
        ↓
  [staging — action: auto_revert]
        ↓
Ferry calls Lambda UpdateFunctionConfiguration to revert memory to 256MB
Ferry records DRIFT_REMEDIATED audit event
Ferry posts GitHub Issue with: function, field, old value, new value, when detected, remediation taken
        ↓
  [production — action: alert_and_hold]
        ↓
Ferry creates GitHub Issue: title "Drift detected: payment-webhook [memory]", body contains full diff,
  expected vs actual values, timestamp, "Acknowledge this issue to unblock next deployment"
Ferry records DRIFT_DETECTED audit event (no AWS change made)
Next `ferry apply` is blocked until the issue is acknowledged (or drift freeze is set)
```

### Flow 3: Audit Trail Export for Compliance

```
Compliance officer or auditor requests 90-day deployment history
        ↓
Engineer runs: `ferry audit export --days 90 --env production --format csv`
        ↓
Ferry queries DynamoDB audit table (indexed by environment + timestamp range)
        ↓
Returns structured records: event_type, timestamp, actor, commit_sha, function,
  change_summary, approval_chain, outcome
        ↓
Export file generated locally (JSON or CSV)
        ↓
Engineer delivers to auditor
        ↓
Auditor can cross-reference any event_id against CloudTrail using aws_request_ids field
```

### Flow 4: Emergency Rollback

```
Production incident — 502s from API Gateway on payment-webhook
        ↓
On-call engineer runs: `ferry rollback --env prod --function payment-webhook --n 1`
        ↓
Ferry queries state store for Nth-previous deployment snapshot for this function
Ferry shows diff: "This will revert memory from 512MB → 256MB, timeout from 60s → 30s. Proceed? [y/N]"
        ↓
Engineer confirms
        ↓
Ferry checks ACL: Does this engineer have rollback permission for production?
   → NO: ACL_DENIED audit event, abort
   → YES: Proceed
        ↓
Ferry applies rollback via AWS APIs (no source code required — uses state snapshot)
        ↓
Ferry records ROLLBACK audit event: actor, rolled-back-from commit SHA, rolled-back-to commit SHA,
  timestamp, outcome
        ↓
Ferry posts GitHub Issue: "Rollback performed in production — [function] — [timestamp]"
  with link to audit record and prompt to open incident review
        ↓
Rollback complete in under 3 minutes from command invocation
```

### Flow 5: ACL Enforcement — Unauthorized Deploy Attempt

```
Junior developer merges PR to main without required senior-backend approval
        ↓
Ferry GitHub App receives push event
        ↓
Ferry ACL engine checks: PR approval chain against `acls.production.deploy` role requirements
  → PR was approved only by another junior developer (not in senior-backend role)
        ↓
Ferry records ACL_DENIED audit event: {actor, commit_sha, environment, reason: "insufficient approvals",
  required_role: "senior-backend", approvers_found: ["junior-dev-alice"], approvers_required: 1}
        ↓
Ferry posts comment on the commit: "Deployment blocked: ACL requirement not met.
  Required: 1 approval from [senior-backend]. Found: 0. No changes were deployed."
        ↓
Zero AWS API calls are made. Deployed state is unchanged.
        ↓
ACL_DENIED event is visible in audit trail export.
```

---

## Key Logic

### Reconciliation Logic

- Desired state is always the latest commit on the configured watched branch (typically `main` for production, not the PR branch)
- Actual state is read directly from AWS APIs, not from AWS CloudFormation (to catch Console changes that bypass CloudFormation)
- Diff computation is field-level, not resource-level: Ferry detects that `memory_size` changed, not just that a function was "modified"
- Fields excluded from drift detection (to prevent false positives):
  - `last_modified` timestamp
  - `code_sha_256` (managed by CI/CD, not Ferry)
  - `version` ARN (Ferry tracks aliases, not numeric versions)
  - AWS-managed metadata fields
- Drift on excluded fields is silently ignored but logged at debug level

### State Snapshot Logic

- A state snapshot is written at the start of `apply` (captures pre-apply state) and at the end (captures post-apply state)
- If an apply fails mid-way (partial deployment), the pre-apply snapshot remains the "last known good" state
- State snapshots are stored with: commit SHA, timestamp, full function configuration, applied-by identity, environment
- Rollback resolves to a snapshot, not to a Git commit — ensuring rollback works even if the Git history has been rebased (though Ferry records the original commit SHA for auditability)

### ACL Enforcement Logic

- ACL check happens at apply time, not at merge time (merge is a git operation outside Ferry's control)
- Ferry reads the `acls` block from the `ferry.yaml` at the watched branch tip, not from the PR branch (prevents privilege escalation via ACL modification in the same PR)
- Role membership is resolved at apply time from the current `ferry-teams.yaml` on the watched branch
- An emergency override exists: `ferry apply --emergency --reason "P0 incident"` bypasses ACL but requires the actor to have `admin` role AND records an `ACL_OVERRIDE` event with mandatory reason field
- ACL override events are flagged in audit exports for immediate auditor attention

### Drift Freeze Logic

- `ferry drift freeze --duration <N>h` sets a flag in AWS SSM Parameter Store (not in Git) — intentional, so it works during internet outages or when Git is unavailable
- Drift freeze does not suppress detection — drift is still recorded in the audit trail. It suppresses auto-remediation only.
- Drift freeze automatically expires after the configured duration. Manual extension requires re-running the command.
- Drift freeze events (set, extended, expired) are recorded in the audit trail with actor and duration.

### Non-Functional Requirements

**Security:**
- Ferry's service account IAM role follows least-privilege: only the specific Lambda, API Gateway, and Step Functions API actions required for reconciliation
- No secrets are stored in the Ferry state store or audit trail. Environment variable values are references only (SSM paths, Secrets Manager ARNs)
- Ferry operator runs in the customer's own AWS account — no customer data transits Ferry's infrastructure
- GitHub App uses minimal scopes: read access to repo contents, write access to issues and PR comments
- All Ferry-to-AWS communication is over HTTPS; all credentials are short-lived via IAM roles, never static keys

**Reliability:**
- Reconciliation loop failure (e.g., operator crash) must not cause a deployment. Fail-closed on uncertainty.
- Operator recovery: on restart, Ferry re-reads desired state from Git and actual state from AWS before taking any action
- GitHub API rate limits: Ferry implements exponential backoff and does not fail silently on rate limit errors

**Observability:**
- Ferry emits structured logs (JSON) to CloudWatch Logs
- Ferry emits CloudWatch metrics: `ferry.drift.detected`, `ferry.deploy.success`, `ferry.deploy.failure`, `ferry.acl.denied`, `ferry.reconcile.duration`
- Customers can build CloudWatch alarms on these metrics (e.g., alert if drift is detected more than N times per day)

**Performance:**
- Plan computation for a 20-function service: under 30 seconds
- Apply for a 20-function service (sequential): under 5 minutes
- Rollback for a single function: under 3 minutes
- Audit export for 90 days: under 5 minutes

**Compatibility:**
- V1 target: AWS Lambda (runtimes: Python 3.11+, Node 18+, Java 17+, Go 1.x), API Gateway (REST and HTTP APIs), Step Functions (Standard and Express workflows)
- AWS regions: all commercial regions
- GitHub: GitHub.com and GitHub Enterprise Server 3.x+
- CI/CD: Ferry is agnostic — it operates on Git state, not on your CI pipeline. Works alongside any CI system.

---

# Development and Launch Planning

## Key Milestones

### Phase 0: Foundation (Weeks 1-6)
**Goal:** Core operator running locally, reconciliation loop working against a test AWS account.

- [ ] Define manifest schema (`ferry.yaml`) — finalized and documented
- [ ] Build state reader: AWS Lambda, API Gateway, Step Functions API clients
- [ ] Build diff engine: desired state vs actual state, field-level diff
- [ ] Build state writer: apply changes via AWS APIs
- [ ] CLI skeleton: `ferry plan`, `ferry apply`, `ferry status`
- [ ] DynamoDB state store schema + write/read
- [ ] Basic audit record write on each apply

Milestone exit: `ferry plan` shows accurate diff against a live AWS account. `ferry apply` successfully deploys a Lambda from a `ferry.yaml`.

### Phase 1: GitOps Loop (Weeks 7-12)
**Goal:** GitHub App connected, PR automation working, reconciliation running on schedule.

- [ ] GitHub App: OAuth app creation, webhook handling (push, PR events)
- [ ] PR comment: post plan output as structured PR comment
- [ ] Merge handler: trigger apply on push to watched branch
- [ ] Scheduled reconciliation: Lambda-based scheduler, 15-minute polling loop
- [ ] Drift detection: compare scheduled reads to Git desired state, emit drift events
- [ ] GitHub Issue creation on drift detection
- [ ] `ferry drift` CLI command
- [ ] Deployment summary comment posted on merged PR

Milestone exit: Full GitOps loop running. Open PR → plan comment. Merge → auto-deploy. Console change → GitHub Issue opened within 15 minutes.

### Phase 2: Security & Governance Layer (Weeks 13-18)
**Goal:** ACL enforcement, audit trail completeness, rollback, compliance export. This is the V1 ship milestone.

- [ ] ACL engine: parse `ferry-teams.yaml` and `acls` block, check PR approval chain
- [ ] ACL enforcement at apply time: ACL_DENIED audit events and blocked deploys
- [ ] Admin role and meta-ACL for Ferry config files
- [ ] Rollback: `ferry rollback --n N`, state snapshot resolution, rollback audit events
- [ ] Drift freeze: `ferry drift freeze`, SSM-based flag, auto-expiry
- [ ] Auto-remediation policy (`drift_policy` block): staging auto-revert, production hold
- [ ] Audit trail completeness: all event types covered, all fields populated
- [ ] `ferry audit export` CLI command: JSON and CSV
- [ ] Emergency ACL override with mandatory reason
- [ ] CloudWatch metrics emission
- [ ] Documentation: setup guide, `ferry.yaml` reference, ACL configuration guide, compliance guide (SOC 2 evidence map)

Milestone exit: All Key Features implemented. A complete 90-day audit export can be generated. ACL denial blocks a deploy with zero AWS API calls. Rollback completes in under 3 minutes.

### Phase 3: Alpha (Weeks 19-22)
**Goal:** 5 design partners using Ferry in staging environments. Real-world validation.

- [ ] Recruit 5 alpha teams: target backend teams at companies with active SOC 2 or ISO 27001 compliance programs
- [ ] Ferry `init` command: bootstrap a new repo from zero
- [ ] Alpha feedback integration: schema changes, CLI UX improvements
- [ ] Error message quality pass: every failure mode has a human-readable explanation and a suggested next action
- [ ] Security review: penetration test of GitHub App and AWS service account IAM roles

Milestone exit: 5 alpha teams have run Ferry in staging for 4+ weeks. At least 3 report that Ferry would replace or significantly reduce their current deployment tooling.

### Phase 4: Open Source Launch (Weeks 23-28)
**Goal:** Public GitHub release, community traction, first production users.

- [ ] Repository setup: MIT or Apache 2.0 license, contribution guide, issue templates
- [ ] Documentation site (Docusaurus or similar): getting started in under 30 minutes
- [ ] Launch: Hacker News Show HN, GitHub trending targeting, relevant Slack communities (Serverless, AWS Heroes, DevOps)
- [ ] Blog post series: "ArgoCD for Serverless — How Ferry Works", "The Audit Trail Gap in Serverless", "ClickOps: The Hidden SOC 2 Risk"
- [ ] Ferry Operator available as: Docker image, AWS CDK Construct (deploy to your own account in minutes)

---

## Operational Checklist (Pre-Launch)

- [ ] Security: Ferry GitHub App permissions reviewed and minimized
- [ ] Security: Ferry service account IAM policy reviewed by AWS IAM specialist
- [ ] Security: No secrets in state store, audit trail, or logs — verified by automated test
- [ ] Reliability: Operator crash and recovery tested — confirm no partial-apply state corruption
- [ ] Reliability: DynamoDB state store TTL and capacity configured for sustained load
- [ ] Compliance: `ferry audit export` output reviewed by an actual SOC 2 auditor — confirm fields satisfy evidence requirements
- [ ] Docs: Getting started guide tested by someone who has never seen Ferry
- [ ] Docs: SOC 2 / ISO 27001 compliance guide maps Ferry audit fields to specific control requirements
- [ ] Support: GitHub Discussions enabled on repo, response SLA defined for alpha users

---

## Other

### Appendix A: Compliance Control Mapping

| SOC 2 Control | Ferry Feature | Evidence |
|---|---|---|
| CC6.1 — Logical access controls | ACL Enforcement Engine | ACL_DENIED audit records; no direct AWS deploy access for developers |
| CC6.2 — New user access requests | ACL model via PR review | `ferry-teams.yaml` changes require admin PR approval; audit trail |
| CC7.2 — System monitoring | Drift Detection | DRIFT_DETECTED audit events; CloudWatch metrics |
| CC8.1 — Change management | PR-based deployment flow | Full approval chain in audit record; all changes via Ferry |
| A1.2 — Availability | Rollback + Disaster Recovery | `ferry rollback`, `ferry apply --from-git`, state snapshots |

| ISO 27001 Control | Ferry Feature | Evidence |
|---|---|---|
| A.9.4.1 — Information access restriction | ACL enforcement | ACL_DENIED events; IAM role minimization |
| A.12.4.1 — Event logging | Audit trail | Structured, immutable audit records for all deployment events |
| A.12.4.3 — Administrator and operator logs | Actor attribution | All automated actions attributed to `ferry-operator`; human actions to GitHub username |
| A.14.2.2 — System change control procedures | PR-gated deployments | Approval chain in audit record |

### Appendix B: Competitive Differentiation Summary

| Capability | Serverless Framework | SAM | SST | Terraform | Ferry V1 |
|---|---|---|---|---|---|
| Continuous reconciliation | No | No | No | No | Yes |
| Drift detection | No | No | No | Partial | Yes (event-driven) |
| Structured audit trail | No | No | SaaS-only | No | Yes (customer-owned) |
| Deployment ACLs | No | No | No | No | Yes (Git-native) |
| Git-native rollback | No | No | No | No | Yes |
| Lambda-aware semantics | Yes | Yes | Yes | No | Yes |
| Self-hosted | Yes | Yes | Yes | Yes | Yes |

### Appendix C: Why Open-Source First

ArgoCD's trajectory is the clearest precedent in adjacent markets: 20,000+ GitHub stars, CNCF Graduated, 97% production use, enterprise users including Adobe, BlackRock, Capital One. The commercial entity (Akuity) raised a $24M Series A in 2023. ArgoCD won its 60% market share versus Flux's 11% not on features alone, but on developer experience and product completeness — achieved through open-source community investment. Ferry must follow this path: open-core from day one, with enterprise features (SaaS, SSO, advanced policy-as-code, priority support) gating the commercial offering.

---

### Risks

**Risk 1: AWS builds this natively**
- *Likelihood:* Medium. AWS has published a "Operating Serverless at Scale: Governance" blog series — acknowledging the gap — but current AWS offerings (CodePipeline, CodeDeploy) remain CI/CD-centric and push-based. No AWS-native continuous reconciliation exists today.
- *Mitigation:* Speed to market. Establish community and production usage before AWS can ship a comparable native offering. AWS typically acquires or integrates popular OSS (see EKS and Karpenter).

**Risk 2: Category education cost**
- *Likelihood:* High. "ArgoCD for Serverless" resonates immediately with K8s-experienced engineers but requires education for teams that have never used a GitOps tool.
- *Mitigation:* `ferry init` makes the zero-to-working path under 30 minutes. Documentation leads with the "before / after" compliance story, not with architecture. Blog content targets both K8s-aware engineers and compliance-focused engineering leaders.

**Risk 3: Serverless adoption plateau**
- *Likelihood:* Low-Medium. CNCF 2024 data shows serverless adoption is "split." Unkey's public exodus (Dec 2025) became a narrative. However, the split is driven by exactly the operational overhead that Ferry reduces. The Unkey case is an argument for Ferry, not against serverless.
- *Mitigation:* Position Ferry as what makes serverless viable at scale, not as a bet on serverless growth.

**Risk 4: Drift freeze misuse — operator leans on it as a crutch**
- *Likelihood:* Medium. If drift freeze becomes permanent, Ferry's governance guarantees degrade.
- *Mitigation:* Drift freeze events are prominently flagged in audit exports. Maximum drift freeze duration is configurable per team (default: 4 hours). Consecutive freeze extensions (within 24h) trigger an alert.

**Risk 5: ACL bypass via Ferry config modification**
- *Likelihood:* Low if meta-ACL is implemented correctly. High if not.
- *Mitigation:* Meta-ACL protecting `ferry.yaml` and `ferry-teams.yaml` is a V1 requirement, not Phase 2. Bootstrapping is documented carefully: the first Ferry setup requires admin credentials, after which the meta-ACL governs itself.

---

### FAQ

**Q: How is Ferry different from just using Terraform with Atlantis?**
A: Terraform with Atlantis is the closest existing approximation, and it is not a bad answer for teams that already know Terraform. Ferry differs in three ways: (1) Ferry understands Lambda-specific semantics — aliases, canary weights, function URLs, Step Function definitions — that Terraform treats as opaque resources. (2) Ferry's reconciliation is event-driven from CloudTrail, not just on-push — it catches Console changes within minutes. (3) Ferry's audit trail is structured and designed for compliance export from day one, not reconstructed from Terraform plan logs.

**Q: Why not just enforce Git discipline through CI/CD?**
A: CI/CD pipelines are push-based. They deploy when triggered. They do not continuously verify that what was deployed still matches what was intended. An engineer bypassing CI and making a Console change after a deployment leaves no trace in the CI system. Ferry's reconciliation loop closes this gap — it watches the deployed state continuously, not just at deploy time.

**Q: We already have CloudTrail. Why do we need Ferry's audit trail?**
A: CloudTrail captures all AWS API calls by IAM principal. What it does not provide: mapping from an AWS API call to a Git commit, a PR, an approver, and a business intent. Ferry's audit record is the layer that connects CloudTrail events to your engineering workflow. The `aws_request_ids` field in every Ferry audit record allows cross-referencing into CloudTrail for forensic depth.

**Q: Does Ferry manage the application code (ZIP artifacts) or just the configuration?**
A: V1 manages configuration — runtime, memory, timeout, environment variable references, triggers, IAM role ARN, API Gateway routing, Step Function definitions. Application code artifacts (ZIP/container images) are managed by your existing CI/CD pipeline. Ferry declares where the artifact lives (ECR URI or S3 key), but does not build or push it.

**Q: What happens if Ferry goes down?**
A: Ferry fails closed. If the operator is unavailable, no automated deploys occur — PRs merge to Git but changes are not applied to AWS. Developers can run `ferry apply` manually from the CLI using their own credentials (subject to ACL enforcement). The reconciliation loop resumes from the current Git state when the operator recovers, with no accumulated backlog to process.

**Q: Is Ferry SOC 2 compliant itself?**
A: Ferry is infrastructure that helps your team achieve SOC 2 compliance. The Ferry operator runs in your own AWS account — there is no third-party data processor in V1 (self-hosted). The open-source codebase is available for your security team to review. A SaaS hosted offering in Phase 2 will have its own SOC 2 program.
