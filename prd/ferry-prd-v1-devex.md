# Ferry — PRD v1: Developer Experience First

**Product:** Ferry
**Version:** v1.0 (Developer Experience Edition)
**Author:** [Product]
**Date:** 2026-02-22
**Status:** Draft
**Strategic Theme:** "You don't need a DevOps team anymore — Ferry gives every developer GitOps superpowers for serverless."

---

# Problem Alignment

## Problem & Opportunity

Serverless teams — 1.8M monthly active AWS Lambda customers generating over 15 trillion monthly invocations — deploy their infrastructure the same way engineers did in 2012: manually, from a local machine, with no audit trail and no way to recover if it breaks. Every existing deployment tool (Serverless Framework, SAM, SST, CDK, Terraform) is push-based: a human runs a command, the code goes out, and the relationship between what is in git and what is actually running in production is permanently severed. No tool continuously watches for drift, reconciles mismatches, or enforces git as authoritative state. The operational model is fragile by design, and the governance and compliance gaps it creates are substantial. The window to own this category is open now: GitOps adoption has hit 64% of engineering organizations (CNCF 2024), ArgoCD proved the reconciliation-loop model works at scale (60% K8s cluster adoption, NPS 79), and Forrester formally created a Serverless Dev Platforms Wave category in Q2 2025 — but no one has applied the ArgoCD pattern to serverless.

## High Level Approach

Ferry is a GitOps operator for serverless infrastructure. It runs as a GitHub App (no long-lived server required on the customer's end), watches declared desired state in a git repo, compares it to what is actually deployed in AWS, and continuously reconciles any difference. The core loop: define your Lambda functions, Step Functions, and API Gateway config in a Ferry manifest file; open a PR and Ferry posts a plan; merge and Ferry applies; drift in production triggers a GitHub Issue and an auto-reconcile. The git repo is the single source of truth. Always.

**Alternatives considered and rejected:**

- **Pure CLI wrapper (like Serverless Framework):** Solves the deploy problem, not the reconciliation problem. Leaves drift, traceability, and rollback completely unsolved. This is exactly what every competitor already does.
- **SaaS CI/CD platform (like Seed.run):** Still push-based. Adds managed deployment but does not eliminate the gap between what git says and what runs in production. Audit trail requires enterprise tier.
- **Terraform wrapper (like Atlantis):** Terraform is not serverless-aware. Lambda is "just a resource" — no alias semantics, no weighted routing, no health-signal rollback. Requires a long-running Kubernetes cluster, which is ironic for a serverless team.
- **Build on top of existing frameworks:** Ferry's value is the reconciliation loop, not the deployment primitive. Framework lock-in would force users to adopt Ferry's opinions about IaC syntax on top of existing opinions. A thin manifest layer that calls AWS APIs directly gives Ferry full control over deployment semantics.

**Why a GitHub App specifically:** The OpenTaco/Digger model — a git application backend, PR automation, and periodic reconciliation jobs — gives Ferry the right architecture without requiring customers to run infrastructure. The GitHub App model means a five-minute setup path. No cluster. No long-running agent. No DevOps team required to operate Ferry itself.

### Narrative

**Before Ferry — Minh's Monday**

Minh is a backend engineer at a 40-person B2B SaaS company. The team runs 23 Lambda functions and a Step Functions state machine. There is no dedicated DevOps engineer; Minh is the de-facto infra person because he "knows the most AWS."

It is 9:07 AM on Monday. The nightly billing job failed at 2 AM. Nobody noticed until customers emailed at 8:45 AM. Minh opens the AWS Console and starts investigating. He finds that the billing Lambda's memory is set to 128MB in the console but 512MB in the `serverless.yml` in git. Last Friday, someone — he has no idea who — increased the memory in the console during a different incident. That override never made it back to code. The deployment on Thursday reduced it silently back to 128MB, and the billing job timed out.

Minh tries to roll back to Thursday's deployment. `sls rollback --timestamp 1706870400` fails because the plugin state has changed. He digs through CloudWatch logs manually. He cannot find a clean record of who deployed what, when. After three hours he has a fix. He has also lost half his day, and he knows this will happen again.

There is no audit trail. There is no way to know what actually runs in production without clicking through the AWS Console. The git repo lies.

**After Ferry — Minh's Monday (alternate timeline)**

Minh's phone buzzes at 2:12 AM. A GitHub Issue opened automatically: "Drift detected — billing-job Lambda: memory 512MB (live) vs 128MB (desired). Auto-reconcile scheduled in 15 minutes. Review to override." Minh is asleep. The reconcile runs. Memory is restored to 512MB. The billing job at 2:30 AM completes successfully.

At 9:07 AM Minh opens GitHub. The drift issue is closed, tagged `auto-resolved`. The audit trail shows: the memory override was made via the AWS Console by an IAM user attached to a colleague's session at 11:43 PM Friday. The reconciliation log shows exactly what changed and when Ferry corrected it. The git history shows what the desired state always was.

Minh's Monday is normal. He ships a feature by noon.

---

**Before Ferry — the engineering manager's compliance review**

Priya is the engineering manager at a fintech startup preparing for SOC 2 Type II. The auditor asks for evidence of change control: who deployed what, when, and with whose approval. Priya's team uses Serverless Framework deployed from GitHub Actions. She pulls the CI/CD logs. They show that a deployment ran. They do not show what changed in the deployment. They do not show whether the deployed code matches what is in git. They do not show who approved the change (there is no approval gate). Three engineers have production AWS credentials on their laptops. The auditor notes four findings. The audit timeline slips by six weeks.

**After Ferry — Priya's compliance review**

Every deployment is a git merge, and every git merge has a PR, a reviewer, and a commit SHA. Ferry attaches the commit SHA to every deployed Lambda version as a tag. The Ferry audit log exports a full history: `who → what changed → why (PR link) → when → outcome`. No engineer has production AWS credentials on their laptop — Ferry's IAM role does the deploying. Priya exports the Ferry audit log, attaches the git history, and closes the finding in two hours.

---

## Goals

Goals are listed in priority order. Primary goals are measurable; secondary goals include immeasurable but strategically important outcomes.

**G1 — Time-to-first-deploy under 10 minutes (primary)**
A developer with an existing AWS account and a GitHub repo should be able to install the Ferry GitHub App, add a `ferry.yml` manifest, open a PR, and see a plan comment posted — all within 10 minutes. This is the single most important metric for v1. Adoption is impossible if the setup is harder than the tools Ferry replaces.

**G2 — Zero manual deployments in participating repos within 30 days of adoption (primary)**
Measure by: repos where Ferry is installed show no `sls deploy` or `sam deploy` invocations in CI logs after day 30. This is the behavioral signal that Ferry has replaced the old workflow, not just augmented it.

**G3 — Drift detection latency under 15 minutes (primary)**
From the moment a console-level change is made to a watched resource, a drift GitHub Issue must be created within 15 minutes. This is the headline operational guarantee of the reconciler.

**G4 — Rollback completes in under 60 seconds (primary)**
`ferry rollback --steps 1` must identify the previous good state and invoke a redeployment that completes within 60 seconds for a standard Lambda function. Measured from CLI invocation to Lambda version live.

**G5 — Achieve developer NPS > 50 at 90 days (primary)**
ArgoCD's NPS of 79 is the benchmark. A v1 score above 50 signals product-market fit with the developer persona and justifies the open-core commercial build.

**G6 — Become the reference implementation for serverless GitOps (secondary)**
Be cited in AWS documentation, blog posts, and conference talks as the canonical answer to "how do I do GitOps for Lambda?" This is the ArgoCD playbook: win through community ownership of the category before the enterprise layer is built.

**G7 — Build the trust infrastructure for future enterprise features (secondary)**
RBAC, audit export, SSO, and multi-account management are not v1 features. But v1 must not make them impossible. Every design decision must leave these doors open. The compliance narrative must be directionally present even if the enterprise controls are deferred.

**Guardrail metrics — things Ferry must NOT do:**

- G-RAIL-1: Ferry must not be the cause of a production outage. Auto-reconcile must have a dry-run gate. Any reconciliation that changes more than a configurable threshold of resources must require human approval via PR.
- G-RAIL-2: Ferry must not store customer secrets or source code. AWS credentials are assumed via OIDC. Source code never leaves the customer's GitHub environment.
- G-RAIL-3: Ferry must not introduce deploy latency greater than 30 seconds over a baseline `aws lambda update-function-code` call. GitOps must not mean slower deploys.
- G-RAIL-4: Ferry's own infrastructure must not cost customers more than $50/month for a standard 10-function deployment at any scale tier.

## Non-Goals

**Out of scope for v1:**

- **UI/dashboard.** Ferry v1 is CLI-first, GitHub-native. A web UI is a future milestone. Rationale: ArgoCD's UI was built after the core reconciler was proven. Building a UI before the reconciliation model is solid is premature. The GitHub PR interface is a sufficient UI for the core GitOps loop.
- **Multi-cloud support (GCP Cloud Run, Azure Functions).** AWS Lambda + Step Functions + API Gateway is the v1 surface area. Rationale: 70% of AWS customers use serverless; the Lambda ecosystem is the deepest. Multi-cloud dilutes focus and complicates the state model. It is explicitly planned for v2.
- **Full IaC coverage (DynamoDB, S3, VPCs, etc.).** Ferry is not Terraform. It manages the serverless compute and API layer, not all AWS resources. Rationale: teams already have Terraform for foundational infra. Ferry plugs in above that layer. Scope expansion to stateful resources significantly increases the blast radius of auto-reconcile and must be gated on a mature safety model.
- **Enterprise access controls (RBAC, SSO, SAML, multi-account delegation).** These are commercial tier features. Rationale: v1 must win on developer experience to build the community and the usage data. Enterprise controls that add friction before the core loop is proven will hurt adoption.
- **Self-hosted Ferry operator.** v1 is SaaS/GitHub App only. Self-hosted is a future commercial tier feature for enterprises that cannot use SaaS. Rationale: self-hosted adds operational complexity (upgrades, availability SLAs, support burden) before product-market fit is established.
- **Custom workflow engines (replace GitHub Actions).** Ferry works with GitHub Actions, not instead of it. Rationale: integrating into existing CI/CD pipelines lowers the adoption barrier. Replacing the pipeline entirely is a much higher-friction ask.

---

# Solution Alignment

## Key Features

### Plan of Record — v1 Features (priority order)

**F1 — Ferry Manifest (`ferry.yml`)** *(P0)*
A declarative YAML manifest that lives in the repository and defines the desired state of Lambda functions, Step Functions state machines, and API Gateway APIs. The manifest is the single source of truth. Ferry reads and acts on this file. It must be human-writable from scratch (no code generation required), compatible with existing naming conventions, and support environment-specific overrides via profile blocks.

```yaml
# Example ferry.yml
version: "1"
app: billing-service
provider:
  name: aws
  region: us-east-1
  role: arn:aws:iam::123456789:role/ferry-deploy-role

functions:
  billing-job:
    runtime: python3.12
    handler: src/billing.handler
    memory: 512
    timeout: 300
    environment:
      DB_HOST: ${ssm:/prod/db/host}
    events:
      - schedule: rate(1 day)

  webhook-receiver:
    runtime: python3.12
    handler: src/webhook.handler
    memory: 256
    timeout: 30
    events:
      - http:
          method: POST
          path: /webhook

stepFunctions:
  billing-pipeline:
    definition: infra/billing-pipeline.asl.json
```

**F2 — GitHub App + PR Plan Automation** *(P0)*
The core GitOps trigger. When a PR is opened or updated, Ferry posts a plan comment showing exactly what will change (new functions, updated memory, changed environment variables, removed resources). The plan is deterministic and safe to read — it does not make any changes. On merge to the configured target branch, Ferry automatically applies the plan. No human needs to run a CLI command to deploy.

Plan comment format includes:
- Resource diff (what is being added, changed, removed)
- Estimated IAM permissions required (new permissions highlighted)
- Dependency graph if multiple resources change
- "Apply" and "Skip" buttons for manual override

**F3 — Reconciliation Loop + Drift Detection** *(P0)*
The continuous operator. Ferry polls the actual state of all managed resources every 10 minutes using AWS APIs. When actual state diverges from the desired state defined in `ferry.yml`, Ferry:
1. Opens a GitHub Issue in the repository with a structured drift report (resource, field, desired value, actual value, detected timestamp)
2. Waits a configurable grace period (default: 15 minutes) for human acknowledgment
3. Auto-reconciles by re-applying the desired state unless the issue is labeled `ferry:skip-reconcile`

Drift sources detected:
- Console-level changes (memory, timeout, environment variables, IAM role)
- Partial deployment failures (some resources updated, others not)
- Out-of-band CLI deployments (someone ran `sls deploy` without Ferry)
- Resource deletion in console
- Alias or version pointer drift

**F4 — Git-Native Rollback** *(P0)*
Ferry maintains a deployment state log — a record of every apply operation including: commit SHA, changed resources, pre-apply state snapshot, apply timestamp, and operator identity. Rollback is a first-class operation:

```bash
# Roll back to the previous deployment
ferry rollback --steps 1

# Roll back to the state at a specific commit
ferry rollback --to-commit abc123f

# Preview a rollback without applying
ferry rollback --steps 1 --dry-run
```

Under the hood, rollback re-invokes the previous state snapshot via AWS Lambda's versioning system. Rollback does not require re-running a deployment pipeline. Target: rollback completes in under 60 seconds.

**F5 — Ferry CLI** *(P0)*
A single installable binary (`ferry`) that provides:
- `ferry init` — scaffolds a `ferry.yml` from existing deployed resources (introspects AWS account, generates manifest)
- `ferry plan` — shows what would change, locally, without a PR
- `ferry apply` — applies desired state (used in CI without the GitHub App)
- `ferry rollback` — rolls back to a previous state
- `ferry status` — shows current state of all managed resources vs. desired state
- `ferry drift` — manually triggers a drift check
- `ferry logs` — structured deployment audit log

The CLI must work independently of the GitHub App. Teams that cannot use a GitHub App (GitHub Enterprise, other VCS) can use Ferry via CLI + CI script alone.

**F6 — AWS Authentication via OIDC** *(P0)*
Ferry never stores or handles customer AWS credentials. Authentication is via OIDC trust between the Ferry GitHub App and a customer-managed IAM role. The customer creates the IAM role (Ferry provides a CloudFormation template for this), grants it the minimum permissions Ferry needs, and configures the OIDC trust relationship. Ferry's backend assumes this role per-deployment. This is the same model used by GitHub Actions OIDC and is already familiar to the target audience.

**F7 — Deployment State Store** *(P1)*
Ferry maintains a versioned record of every deployment state. This is what makes rollback, drift detection, and audit work. The state store is:
- Encrypted at rest (AES-256)
- Versioned (every apply creates a new version)
- Queryable via CLI (`ferry state list`, `ferry state show <version>`)
- Exportable (JSON) for compliance purposes

State is stored in Ferry's managed backend. Future commercial tier: state stored in customer's own S3 bucket (self-managed state, same model as Terraform remote backend).

**F8 — Structured Audit Log** *(P1)*
Every Ferry operation (plan, apply, rollback, drift detect, drift reconcile) is logged with: timestamp, operator identity (GitHub user or Ferry App), changed resources, commit SHA, outcome, and duration. The audit log is:
- Queryable via `ferry logs --since 30d --resource billing-job`
- Exportable to JSON/CSV
- Immutable (append-only)

This is the compliance artifact. It answers the SOC 2 question: "who deployed what, when, and with whose approval?"

**F9 — Health-Signal Rollback (Auto-Rollback)** *(P1)*
After a Ferry apply, the reconciler enters a configurable watch period (default: 10 minutes). During this window, Ferry monitors CloudWatch metrics for the deployed functions:
- Error rate: if error rate exceeds threshold (default: >5% over 5 minutes), auto-rollback is triggered
- Latency P99: if p99 latency exceeds threshold, flag for review
- Throttles: if throttle rate exceeds threshold, alert

Auto-rollback is explicitly opt-in in v1 with a clear warning in the manifest:

```yaml
deploy:
  autoRollback:
    enabled: true
    errorRateThreshold: 5   # percent
    watchWindowMinutes: 10
```

**F10 — `ferry init` Import Wizard** *(P1)*
For teams with existing Lambda deployments (the majority of the market), `ferry init` introspects the AWS account and generates a `ferry.yml` that represents current state. This is the critical adoption bridge. Engineers do not need to rewrite their infrastructure definition from scratch; Ferry generates it from what already exists.

---

### Future Considerations (explicitly deferred)

- **Web UI / application dashboard** — visual sync status, drift map, deployment history graph. Post-v1.
- **Multi-cloud (GCP Cloud Run, Azure Functions)** — v2 strategic priority.
- **Enterprise RBAC** — per-team deployment permissions, environment promotion gates, approval workflows. Commercial tier, post-v1.
- **SSO / SAML / SCIM** — enterprise identity integration. Commercial tier.
- **Multi-account management** — AWS Organizations integration, cross-account deployment orchestration. Commercial tier.
- **Policy-as-code (Ferry Policies)** — define rules like "no function may have memory > 1GB without approval." Post-v1.
- **Slack / PagerDuty integration** — route drift alerts and deployment notifications to ops channels. Post-v1.
- **Self-hosted Ferry operator** — for enterprises that cannot use SaaS. Commercial tier.
- **Stateful resource management** — DynamoDB tables, S3 buckets, SQS queues as Ferry-managed resources. Requires significant safety modeling; v3+.
- **Cost tracking and optimization** — per-function cost attribution and right-sizing recommendations. Post-v1.

---

## Key Flows

### Flow 1 — First-Time Setup (Target: < 10 minutes)

```
Developer installs Ferry GitHub App (2 min)
  → Selects repository
  → Ferry guides through IAM role creation via CloudFormation one-click template (3 min)
  → Developer runs `ferry init` in their repo (2 min)
      → Ferry introspects AWS account, discovers existing Lambda functions
      → Generates ferry.yml with current state as desired state
  → Developer commits ferry.yml, opens a PR (1 min)
  → Ferry posts plan comment: "No changes — current state matches desired state"
  → Developer merges
  → Ferry is live. All future changes flow through git.
```

First deploy complete. The developer has not run a single `aws` CLI command.

---

### Flow 2 — Standard Development Cycle (PR-driven deploy)

```
Developer updates billing-job memory from 512MB → 1024MB in ferry.yml
  → Opens PR
  → Ferry posts plan comment within 60 seconds:
      "~ billing-job: memory 512 → 1024 MB
       Estimated monthly cost delta: +$8.20
       IAM: no new permissions required
       [Apply] [Skip]"
  → Teammate reviews PR, approves
  → Developer merges to main
  → Ferry applies within 2 minutes:
      - Updates Lambda configuration
      - Creates new Lambda version (v14)
      - Tags version with commit SHA abc123f
      - Posts deploy success comment: "Applied. billing-job v14 live. Commit: abc123f."
  → Audit log entry written
  → Reconciler baseline updated to new desired state
```

No human runs a deployment command. The PR is the deployment.

---

### Flow 3 — Drift Detection and Auto-Reconcile

```
Engineer opens AWS Console
  → Increases billing-job timeout from 300s → 900s (investigating an incident)
  → Does not update ferry.yml

10 minutes later — Ferry reconciler runs:
  → Fetches actual Lambda configuration via AWS API
  → Compares to desired state in ferry.yml
  → Detects: billing-job timeout 900s (actual) vs 300s (desired)
  → Opens GitHub Issue:
      Title: "Drift: billing-job — timeout 900s (actual) vs 300s (desired)"
      Body: resource, field, values, detected timestamp, IAM user who made change
      Labels: ferry:drift, ferry:auto-reconcile-pending
  → 15-minute grace period begins

Engineer sees the issue:
  Option A: Engineer closes issue, comments "intentional — needs to go in code"
    → Engineer updates ferry.yml, opens PR, merges
    → Ferry reconciler sees desired state now matches actual state, closes drift issue
  Option B: Engineer labels issue `ferry:skip-reconcile`
    → Ferry will not auto-reconcile this drift
    → Issue remains open as an intentional exception
  Option C: Engineer takes no action
    → After 15 minutes, Ferry auto-reconciles: resets timeout to 300s
    → Drift issue closed automatically: "Auto-reconciled. timeout reset to 300s."
```

---

### Flow 4 — Rollback

```
Ferry applied a deploy at 14:32 (commit abc123f)
  → Error rate on billing-job spikes to 18% within 3 minutes (health-signal rollback enabled)
  → Ferry auto-rollback triggers:
      - Rolls back billing-job to previous Lambda version (v13, commit xyz789a)
      - Posts GitHub comment on the originating PR: "Auto-rollback triggered. Error rate 18%. Rolled back to v13."
      - Opens GitHub Issue: "Rollback: billing-job — error rate threshold exceeded"
      - Audit log entry written

Alternatively, manual rollback:
  → Developer runs `ferry rollback --steps 1`
  → Ferry shows what will be rolled back (dry-run preview)
  → Developer confirms
  → Rollback completes in < 60 seconds
  → Audit log records: rollback, operator, from version, to version, timestamp
```

---

### Flow 5 — Import Existing Infrastructure

```
Developer runs `ferry init`:
  → Ferry authenticates to AWS via current session
  → Discovers 23 Lambda functions, 2 Step Functions, 4 API Gateway APIs
  → Generates ferry.yml representing current state:
      - Runtime, handler, memory, timeout, environment variable keys (not values)
      - Attached event sources (schedules, API GW routes, SQS triggers)
      - IAM role ARNs
  → Warns: "3 functions have environment variables with inline values.
             Recommend migrating to SSM Parameter Store references."
  → Developer reviews, adjusts, commits
  → Opens PR — Ferry plan comment: "No changes (import baseline)"
  → Merges — Ferry takes over management of all 23 functions
```

---

## Key Logic

### Reconciliation Rules

- **Desired state authority:** `ferry.yml` in the default branch is always authoritative. Actual AWS state that diverges from it is drift, not the new desired state.
- **Auto-reconcile scope:** Auto-reconcile is enabled by default. It can be disabled globally (`reconcile: enabled: false`) or per-resource (`ferry:skip-reconcile` issue label).
- **Blast radius cap:** If a drift check finds more than 20% of managed resources have drifted simultaneously, Ferry pauses auto-reconcile and requires human review via a PR. This prevents a bad ferry.yml commit from silently destroying production.
- **Grace period:** Default 15 minutes between drift detection and auto-reconcile. Configurable per environment (e.g., prod grace period: 60 minutes).
- **Console-change provenance:** Ferry records the IAM identity that made an out-of-band change when available via CloudTrail. This is included in the drift GitHub Issue body.

### Deployment Safety Rules

- **Dry-run before apply:** Every apply operation (whether triggered by PR merge or CLI) runs a plan phase first. The plan output is logged. Apply is aborted if the plan contains a destructive action (function deletion) unless `--allow-destroy` is explicitly passed.
- **Deployment ordering:** If multiple functions share an API Gateway, Ferry deploys functions first, then updates the API Gateway stage. Order is deterministic and documented.
- **Concurrent deploy prevention:** Ferry locks a repository's deploy queue. If two PRs merge within seconds of each other, their applies are queued, not run in parallel. This prevents CloudFormation-style resource conflicts.
- **Canary/weighted routing (F9 dependency):** For functions with auto-rollback enabled, Ferry deploys to a new Lambda version and shifts traffic via weighted alias: 10% for 2 minutes, then 100% if error rate is acceptable. Rollback shifts traffic back to the previous alias target.
- **Environment variable handling:** Values prefixed `${ssm:...}` or `${secretsmanager:...}` are resolved at deploy time by Ferry, not stored in the manifest. Raw string values in `environment:` blocks generate a lint warning recommending migration to SSM.

### Manifest Validation

- Ferry validates `ferry.yml` on every PR. Validation errors block the plan from running and post a clear error comment.
- Validated fields: runtime validity, handler path format, memory within Lambda limits (128MB–10,240MB), timeout within limits (1s–900s), event source syntax, IAM role ARN format.
- Ferry does NOT validate that the IAM role has the required permissions (this would require making an AWS API call, which is done during the plan phase instead).

### State Management Rules

- State is versioned on every successful apply.
- State versions are retained for 90 days by default (configurable).
- State cannot be manually edited. It is the output of a successful apply, not an input.
- Rollback targets must be state versions within the retention window.
- State export (`ferry state export --format json`) produces a document Ferry can use to re-bootstrap from scratch (disaster recovery).

### Non-Functional Requirements

- **Plan latency:** Ferry must post a plan comment within 60 seconds of a PR open/update event.
- **Apply latency:** Apply (after merge) must begin within 30 seconds of the merge event. Deploy time itself is gated by AWS API speed, not Ferry overhead.
- **Reconciler polling:** Default 10-minute poll interval. Configurable down to 5 minutes (minimum to avoid AWS API rate limiting at scale).
- **Availability:** Ferry backend must maintain 99.9% uptime. Drift detection and deployment must degrade gracefully if Ferry is temporarily unavailable — no partial deploys, no state corruption.
- **Security:** Ferry's GitHub App has read-only access to repository contents and write access to issues and PR comments. It does not receive webhook payloads containing secrets. AWS credentials are never transmitted to Ferry's backend.
- **Scale:** v1 must handle a single organization with up to 500 managed Lambda functions without performance degradation.

---

# Development and Launch Planning

## Milestones

### M0 — Foundation (Weeks 1–4)
- Ferry GitHub App registered and functional
- OIDC authentication flow working end-to-end
- `ferry init` introspects a real AWS account and produces a valid `ferry.yml`
- Basic plan computation (diff desired vs. actual for Lambda function configuration)
- Plan comment posted on PR open

Milestone exit criteria: A developer can install Ferry, run `ferry init`, open a PR, and see a plan comment. No apply yet.

### M1 — Core GitOps Loop (Weeks 5–10)
- PR merge triggers apply
- Apply updates Lambda function configuration, code, and event sources
- Lambda versioning and alias management
- Deployment state store (v1 — Ferry-managed)
- Audit log (append-only, queryable via CLI)
- `ferry status` and `ferry logs` CLI commands

Milestone exit criteria: A developer can manage an existing Lambda function through the full PR-plan-apply cycle. Manual deploys (`sls deploy`) are no longer needed for the happy path.

### M2 — Drift Detection (Weeks 11–16)
- Reconciler polling loop (AWS API → desired state comparison)
- GitHub Issue creation for detected drift (structured format)
- Grace period + auto-reconcile
- `ferry drift` manual trigger
- `ferry:skip-reconcile` label support
- CloudTrail integration for out-of-band change attribution

Milestone exit criteria: A console-level change to a managed resource produces a GitHub Issue within 15 minutes and auto-reconciles within 30 minutes.

### M3 — Rollback and Health Signals (Weeks 17–22)
- `ferry rollback` CLI (steps-based and commit-based)
- Health-signal monitoring (error rate, latency) via CloudWatch
- Auto-rollback (opt-in, canary traffic shifting)
- Step Functions state machine management
- API Gateway management (routes, stages, authorizers)

Milestone exit criteria: A deployment that causes error rate spike triggers automatic rollback within 5 minutes. Manual rollback via CLI completes within 60 seconds.

### M4 — Polish and Launch (Weeks 23–28)
- `ferry init` import wizard (full discovery: Lambda + Step Functions + API Gateway)
- Blast radius protection (>20% drift pause)
- Concurrent deploy queuing
- SSM / Secrets Manager environment variable references
- Public documentation site
- Quickstart tutorial (10-minute setup walkthrough)
- Telemetry and error tracking (opt-in)
- Private beta with 10 design partners

Milestone exit criteria: 10 design partners using Ferry in production, time-to-first-deploy under 10 minutes verified with new users, NPS survey baseline established.

### M5 — General Availability (Week 30+)
- Public launch (open-core, free tier)
- Open source core reconciler on GitHub
- Ferry Cloud (managed SaaS, paid tier)
- SOM target: 100 active repos in first 60 days post-launch

---

## Operational Checklist

**Before M4 private beta:**
- [ ] Penetration test on GitHub App webhook handler
- [ ] IAM role minimum-permissions audit (principle of least privilege verified)
- [ ] Chaos test: Ferry backend unavailable mid-apply — verify no partial state corruption
- [ ] Rate limiting test: 500 Lambda functions, reconciler polling — verify no AWS API throttling
- [ ] Data deletion: customer can delete all Ferry state for their org (GDPR/data portability)
- [ ] Incident response runbook: what happens if Ferry posts an incorrect plan and a user merges it

**Before GA:**
- [ ] SLA definition published (99.9% uptime, plan comment latency SLO)
- [ ] Status page live
- [ ] Security disclosure policy published
- [ ] Pricing published (free tier limits, paid tier features)
- [ ] AWS ISV Partner Program application (for co-sell and Marketplace listing)

---

## Other

### Appendix

**A1 — Competitive Gap Summary**

The following table summarizes the capability gap Ferry fills. Every cell with "No" in the competitor row is a gap Ferry addresses natively in v1.

| Capability | Serverless Framework | SAM | SST | Terraform | Pulumi | CDK | Seed | **Ferry v1** |
|---|---|---|---|---|---|---|---|---|
| Continuous reconciliation | No | No | No | No | No* | No | No | **Yes** |
| Drift detection | No | No | No | Partial | Partial* | No | No | **Yes** |
| Git-native rollback | No | No | No | No | No | No | No | **Yes** |
| Structured audit trail | No | No | No | No | No | No | Enterprise | **Yes** |
| Health-signal rollback | No | No | No | No | No | No | No | **Yes** |
| Lambda-aware semantics | Yes | Yes | Yes | No | No | Partial | Yes | **Yes** |
| No long-running infra required | Yes | Yes | Yes | No | No* | Yes | Yes | **Yes** |

*Pulumi continuous reconciliation requires Kubernetes to run — which is ironic for a serverless team.

**A2 — Market Data Summary**

- Serverless market: $22–28B (2024), 14–15% CAGR
- AWS Lambda: 1.8M monthly active customers, 15+ trillion monthly invocations
- 70% of AWS customers use serverless (Datadog)
- GitOps adoption: 64% of engineering organizations (CNCF 2024)
- ArgoCD: 60% of K8s clusters, NPS 79, 97% production use rate
- GitOps platforms market: $1.62B (2024), 22.4% CAGR
- Akuity (ArgoCD commercial): $24M Series A (2023) — direct analog for Ferry's commercial path
- <50% of orgs can fix infrastructure drift within 24 hours (Firefly 2024)
- <33% of orgs continuously monitor for drift (Firefly 2024)

**A3 — Design Partner Target Profile**

Ferry is looking for design partners matching this profile:
- 5–100 engineers
- No dedicated DevOps/platform team
- Currently running 5+ Lambda functions in production
- Using Serverless Framework, SAM, SST, or CDK
- Expressed pain around: drift, audit, rollback, or concurrent deployments
- Willing to use Ferry in production during M4 private beta

---

### Risks

**R1 — AWS builds native GitOps (HIGH IMPACT / LOW-MEDIUM PROBABILITY)**
AWS has published a "Serverless at Scale: Governance" series acknowledging the gap. AWS CodeDeploy handles Lambda canary/blue-green. But AWS's current offerings are CI/CD-centric (push-based), not reconciliation-based. AWS historically acquires or open-sources winning community patterns rather than building from scratch. Mitigation: Win fast, build the community standard, make Ferry the obvious open-source answer before AWS ships a native solution.

**R2 — Adoption friction: existing framework lock-in (HIGH IMPACT / HIGH PROBABILITY)**
Most target users are already using Serverless Framework, SAM, or SST. Asking them to replace their IaC tool is high friction. Mitigation: `ferry init` generates `ferry.yml` from existing deployments without requiring a rewrite. Ferry's manifest is intentionally familiar to Serverless Framework users. Position Ferry as a layer on top, not a replacement — the reconciler, not the IaC.

**R3 — Auto-reconcile causes an outage (HIGH IMPACT / LOW PROBABILITY)**
If Ferry's desired state contains a bug and auto-reconcile applies it aggressively across production, it could cause widespread service degradation. Mitigation: blast radius cap (>20% drift triggers human review), dry-run gate before every apply, health-signal rollback, configurable grace periods, and explicit auto-reconcile opt-in for aggressive settings. This is the product's single biggest trust risk and must be treated as such in design, testing, and communication.

**R4 — Open-source expectation vs. commercial viability (MEDIUM IMPACT / HIGH PROBABILITY)**
ArgoCD won as an open-source project; Akuity built the commercial layer after. If Ferry launches as closed-source, it will face adoption headwinds from the developer community. If it launches as fully open-source, the commercial model is unclear. Mitigation: open-core model. Core reconciler is open-source (Apache 2.0). Ferry Cloud (managed SaaS, RBAC, multi-account, audit export, enterprise SLAs) is the commercial product. This is the Grafana/Gitlab/HashiCorp model applied to GitOps.

**R5 — "Serverless is dying" narrative (LOW IMPACT / MEDIUM PROBABILITY)**
CNCF data shows adoption is "split" — some teams are moving back to containers. The Unkey case study (an API platform that abandoned Cloudflare Workers in Dec 2025) is frequently cited. But the root cause of serverless abandonment is operational overhead, which is exactly what Ferry solves. Mitigation: lean into the narrative. "Teams abandon serverless because the tooling is broken. Ferry fixes the tooling." The case against serverless is the case for Ferry.

---

### FAQ

**Q: Why not just use Terraform with Atlantis or Spacelift?**
Terraform is not serverless-aware. Lambda is "just a resource" with no understanding of versions, aliases, weighted routing, or health-signal rollback. Atlantis and Spacelift require a long-running Kubernetes cluster or server, which is ironic for a serverless team. Ferry is built for the Lambda mental model from the ground up.

**Q: How is Ferry different from Seed.run?**
Seed is a managed CI/CD platform for Serverless Framework and SST. It is still push-based — a human action triggers a deployment, and the relationship between git state and production state is not continuously maintained. Seed does not detect drift. It does not auto-reconcile. It does not provide git-native rollback. Seed is a better deployment pipeline; Ferry is a reconciliation operator. They solve different problems.

**Q: Does Ferry replace our CI/CD pipeline?**
No. Ferry works alongside your existing CI/CD pipeline. GitHub Actions runs tests, builds artifacts, and validates code. Ferry handles the deployment and reconciliation. The PR merge is the deploy trigger. You do not need to change your CI pipeline to use Ferry.

**Q: What if we make a console change intentionally?**
Ferry detects it as drift and opens a GitHub Issue. If it was intentional, you have two options: (1) update `ferry.yml` to reflect the change and merge it via PR — the canonical right answer; or (2) label the drift issue `ferry:skip-reconcile` to tell Ferry to leave it alone. Option 2 is the escape hatch, not the workflow.

**Q: What permissions does Ferry's IAM role need?**
Ferry provides a CloudFormation template that creates an IAM role with least-privilege permissions covering: `lambda:*` (function management), `states:*` (Step Functions), `apigateway:*` (API Gateway), `cloudwatch:GetMetricStatistics` (health signals), and `cloudtrail:LookupEvents` (drift attribution). Customers review and own this role; Ferry never stores the credentials.

**Q: What happens if Ferry is down?**
PRs can still be merged; Ferry will process the apply backlog when it recovers. Drift detection will resume from the last checkpoint. No deploys will be lost — they are queued, not dropped. Ferry's availability SLA is 99.9%. If Ferry is down for an extended period, teams can fall back to manual deploys via the Ferry CLI, which operates independently of the Ferry backend.

**Q: Is the state stored securely?**
Yes. State is encrypted at rest (AES-256) and in transit (TLS 1.3). Ferry's backend does not store source code or secrets. Environment variable values are resolved from SSM/Secrets Manager at deploy time and never stored in Ferry's state. State can be exported and deleted by the customer at any time.

**Q: How does pricing work?**
v1 launches with a free tier covering: 1 GitHub App installation, up to 10 managed functions, 90-day audit log retention, and community support. Paid tiers add: unlimited functions, extended audit log retention, priority support, and (eventually) RBAC, multi-account management, and self-hosted options. Detailed pricing is to be determined during M4 based on design partner feedback.

**Q: Why AWS only in v1?**
70% of AWS customers use serverless. Lambda has 1.8M monthly active customers. The Lambda ecosystem (versioning, aliases, weighted routing, CloudWatch integration) is the deepest and most mature serverless compute platform. AWS is the right first wedge. Multi-cloud (GCP Cloud Run, Azure Functions) is explicitly planned for v2, and the Ferry manifest format is designed to be provider-extensible.
