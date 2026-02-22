# Ferry — MVP PRD

**Product:** Ferry
**Version:** MVP
**Date:** 2026-02-22
**Status:** Working Draft

---

# Problem Alignment

## Problem & Opportunity

Serverless teams deploy Lambda functions the same way engineers did in 2012: manually, from a local machine, with no continuous record of what's actually running in production. Every existing tool — Serverless Framework, SAM, SST, CDK — is push-only. The relationship between what's in git and what's deployed is severed the moment someone edits a timeout in the AWS Console or runs `sls deploy` from a laptop. Less than 33% of organizations continuously monitor for drift; less than 50% can fix it within 24 hours. The gap is real, well-documented, and completely unfilled: no tool does for serverless what ArgoCD did for Kubernetes.

## High Level Approach

Ferry is a GitHub App that watches a git repo as the authoritative desired state for AWS Lambda, Step Functions, and API Gateway. When a PR is opened, Ferry posts a plan. When it's merged, Ferry deploys. On a recurring loop, Ferry compares what's in git to what's running in AWS and opens a GitHub Issue when they diverge. Git revert is rollback.

That's the whole shape. A reconciliation loop with git as the source of truth, surfaced entirely through GitHub's native interfaces.

**Alternatives considered:**
- **Terraform + Atlantis/Digger:** Terraform treats Lambda as a generic resource — no alias semantics, no version ARNs, no canary weights. Atlantis requires a long-running server. Wrong tool, wrong model.
- **Wrapping Serverless Framework or SAM:** Both are push-only. You'd be building a reconciliation loop on a foundation that has no concept of desired vs. actual state. You'd fight the abstraction at every layer.
- **Pure SaaS CI/CD (Seed model):** Still push-based. Adds managed deployment orchestration but doesn't eliminate the gap between git state and production state.

The GitHub App model (OpenTaco/Digger for Terraform, now Ferry for serverless) gives us PR automation, drift notifications, and deploy triggers without requiring customers to run any infrastructure. No cluster. No long-running agent to babysit.

### Narrative

Minh is the de-facto infra person at a 40-person B2B SaaS company. No dedicated DevOps engineer. The team runs 23 Lambda functions and a Step Functions state machine.

**Before Ferry:** Monday 9 AM, billing job failed at 2 AM. Customers emailed at 8:45. Minh digs through the AWS Console and finds the billing Lambda's memory is 128MB in prod but 512MB in `serverless.yml`. Someone raised it in the Console during a Friday incident and never pushed the change back to code. A Thursday deploy silently reset it. He tries `sls rollback` — fails because plugin state changed. He has no record of who deployed what or when. Three hours gone. He knows it'll happen again.

**After Ferry:** At 2:12 AM, a GitHub Issue opens automatically: "Drift detected — billing-job: memory 128MB (git) vs 512MB (live). Auto-reconcile in 15 minutes." Minh is asleep. The reconcile runs. Billing job at 2:30 AM completes. Monday morning, Minh opens GitHub: drift issue closed, tagged auto-resolved, audit trail shows who changed it and when. His day is normal. He ships a feature.

## Goals

1. **The GitOps loop works reliably.** PR opens → plan comment posted. PR merges → deploy happens. Console change → GitHub Issue created. This is the entire product. It must work every time.

2. **Drift is caught before it causes incidents.** A configuration change made outside of git creates a GitHub Issue within one poll cycle. Auto-reconcile resets it to desired state unless explicitly overridden.

3. **Rollback is a git operation.** `git revert` + PR merge restores previous infrastructure state. No source code required, no plugin reinstall, no guessing.

4. **Safe by default.** Auto-reconcile never fires without a grace period. Destructive changes (function deletion) require explicit opt-in. If Ferry is down, nothing breaks — it fails closed.

5. **Zero new infrastructure for the customer to operate.** The GitHub App model means customers install Ferry like any other GitHub App. No cluster, no server, no ops burden.

## Non-Goals

Everything not in the 5 MVP features is deferred. Specifically:

- **No web UI.** GitHub PR comments and Issues are the interface. A UI gets built after the reconciler is proven, not before.
- **No health-signal rollback.** CloudWatch-triggered auto-rollback is real and valuable. It's also v2. MVP rollback is git revert → merge → deploy.
- **No import wizard.** `ferry init` to introspect an existing AWS account and generate `ferry.yml` is a meaningful adoption accelerator. It's not the MVP. Teams write their manifest manually or adapt from examples.
- **No ACLs or RBAC.** Deployment access controls come after the core loop is proven. MVP relies on GitHub's built-in branch protection and PR review requirements.
- **No audit export.** Structured compliance export (JSON/CSV for SOC 2 evidence) is a governance feature. The git history is the audit trail in MVP.
- **No multi-cloud.** AWS only. Lambda + Step Functions + API Gateway. That's it.
- **No self-hosted operator option.** Ferry Cloud (GitHub App model, Ferry runs the backend) is the only deployment model for MVP.
- **No Slack/PagerDuty integration.** GitHub Issues are the notification surface.
- **No cost estimation in plan output.** Nice to have, deferred.
- **No support for EventBridge, SQS, DynamoDB, or other AWS resources.** Scope is Lambda + Step Functions + API Gateway and nothing else.

---

# Solution Alignment

## Key Features

### F1 — GitHub App + PR Automation

The Ferry GitHub App watches the configured branch. On PR open or update, Ferry posts a plan comment: what will change, what's being added, what's being removed. The plan is read-only — no AWS calls happen. On merge to the target branch, Ferry applies.

Plan comment includes:
- Resource diff (added / changed / removed)
- Field-level changes (memory 128 → 512, timeout 30 → 60)
- Any destructive changes flagged explicitly
- Confirmation of no changes when the PR doesn't touch `ferry.yml`

Apply posts a follow-up comment on the merged PR: deployed at, commit SHA, Lambda version published.

### F2 — Declarative Config (`ferry.yml`)

One file in the repo root declares the desired state. Human-writable. Diff-friendly. Version-controlled.

```yaml
version: "1"
app: billing-service
provider:
  name: aws
  region: us-east-1
  role: arn:aws:iam::123456789012:role/ferry-deploy-role

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

apiGateway:
  payments-api:
    type: http
    stage: prod
```

SSM and Secrets Manager references (`${ssm:...}`, `${secretsmanager:...}`) are resolved at deploy time. Raw secret values in `environment:` blocks generate a lint warning. Schema is validated on every PR — bad config blocks the plan and posts a clear error.

### F3 — Reliable Deploy Loop

Ferry deploys Lambda functions, Step Functions state machines, and API Gateway configurations via AWS APIs directly. No CloudFormation. No framework dependency.

What "reliable" means here:
- Lambda code + config updates publish a new version and update the managed alias
- Step Functions state machine definitions are updated atomically
- API Gateway route changes are applied after function updates, not before
- Concurrent merges to the same branch are queued, not run in parallel
- A deploy in progress locks the resource group — second merge waits, doesn't conflict
- Partial failures do not leave resources in an unknown intermediate state; pre-apply state is snapshotted

Supported runtimes at MVP: Python 3.11+, Node 18+, Go 1.x. Container image functions are supported; rollback is image-digest-based.

### F4 — Drift Detection

Ferry polls AWS state on a configurable interval (default: 15 minutes). On every poll, it compares actual resource configuration to desired state in `ferry.yml` on the default branch.

On drift detected:
1. GitHub Issue opened with: resource name, field, expected value (git), actual value (AWS), detected timestamp
2. Grace period begins (default: 15 minutes, configurable)
3. If no human action by end of grace period, Ferry auto-reconciles by re-applying desired state
4. Issue closed automatically when actual state matches desired state again

Suppressing auto-reconcile: label the drift issue `ferry:skip-reconcile`. Ferry will not touch it.

Drift is not detected on excluded fields: `last_modified`, `code_sha_256`, Lambda numeric version numbers, AWS-managed metadata. These would produce false positives.

Blast radius cap: if more than 20% of managed resources show drift simultaneously, Ferry pauses auto-reconcile and requires a human to review before resuming. This prevents a bad `ferry.yml` commit from triggering a mass reconciliation cascade.

### F5 — Rollback

Ferry maintains a deployment state log: every apply records the commit SHA, changed resources, pre-apply configuration snapshot, timestamp, and actor (GitHub username or Ferry App for automated reconciles).

Rollback is a git operation at the workflow level: `git revert <commit>` → open PR → merge → Ferry deploys the reverted state. This is the canonical rollback path.

For emergency rollback without a PR cycle, the CLI supports:

```bash
# Roll back to previous deployment
ferry rollback --steps 1

# Roll back to a specific commit
ferry rollback --to-commit abc123f

# Preview without applying
ferry rollback --steps 1 --dry-run
```

Rollback uses Lambda's native versioning system — it swaps the managed alias pointer to the previous published version. No source code required. No re-running a build pipeline. Target: single-function rollback completes in under 30 seconds.

Rollback is recorded in the state log as a first-class deployment event.

---

### Future Considerations

In rough priority order after MVP:

- `ferry import` — scan existing AWS account, generate `ferry.yml` from live state
- Health-signal rollback — CloudWatch error rate triggers auto-rollback after deploy
- Deployment RBAC — GitHub team → resource group permission mapping
- Audit export — structured JSON/CSV for SOC 2 evidence
- Web UI — visual sync status, drift map, deployment history
- Slack/PagerDuty integration for drift alerts
- Multi-environment promotion workflows
- EventBridge, SQS, DynamoDB as managed resource types
- Multi-cloud (GCP Cloud Run, Azure Functions)
- Self-hosted operator option

---

## Key Flows

### Flow 1: PR Deploy

```
Developer edits ferry.yml (increases billing-job memory 256 → 512)
  → Opens PR
  → Ferry posts plan comment within 60 seconds:
      "~ billing-job: memory 256MB → 512MB
       No destructive changes. IAM: no new permissions required."
  → Teammate reviews and approves PR
  → Developer merges to main
  → Ferry begins apply within 30 seconds of merge event
  → Ferry updates Lambda configuration, publishes v14, updates $LIVE alias
  → Ferry posts on merged PR:
      "Applied. billing-job v14 live. Commit: abc123f. 2026-02-22T09:14Z."
  → State log entry written
  → Reconciler baseline updated
```

No human runs a deployment command. The merge is the deploy.

### Flow 2: Drift Detection and Auto-Reconcile

```
Engineer opens AWS Console, increases billing-job timeout 300s → 900s during incident
  → Does not update ferry.yml

15 minutes later, Ferry reconciler runs:
  → Fetches actual Lambda config via AWS API
  → Detects: billing-job timeout 900s (actual) vs 300s (desired in git)
  → Opens GitHub Issue:
      "Drift: billing-job — timeout 900s (live) vs 300s (git)"
      Labels: ferry:drift, ferry:auto-reconcile-pending
  → 15-minute grace period starts

Engineer options:
  A: Updates ferry.yml to match (timeout: 900), opens PR, merges
     → Reconciler sees desired now matches actual, closes issue
  B: Labels issue ferry:skip-reconcile
     → Ferry leaves it alone, issue stays open as documented exception
  C: No action
     → After 15 min, Ferry resets timeout to 300s
     → Issue closed: "Auto-reconciled."
```

### Flow 3: Rollback

```
Ferry applies deploy at 14:32 (commit abc123f, billing-job v14 live)
  → Engineer notices billing job errors spiking
  → Engineer runs: ferry rollback --steps 1 --dry-run
  → Ferry shows: "Will revert billing-job: v14 → v13 (commit xyz789a)"
  → Engineer confirms: ferry rollback --steps 1
  → Ferry swaps $LIVE alias: v14 → v13
  → Rollback complete in ~15 seconds
  → State log records rollback event: actor, from-version, to-version, timestamp
  → Engineer opens git revert PR to keep ferry.yml in sync with what's running
```

---

## Key Logic

**Desired state authority.** `ferry.yml` on the configured deploy branch is always authoritative. Actual AWS state that diverges from it is drift, not the new desired state.

**Dry-run before every apply.** Every apply (whether PR merge or CLI) runs a plan phase first. Plan output is logged. Apply aborts if the plan contains a function deletion unless `--allow-destroy` is explicitly passed.

**Concurrent deploy lock.** Ferry uses a DynamoDB conditional write to lock a resource group during deploy. Concurrent merges queue rather than conflict. A deploy that exceeds 15 minutes releases the lock and opens a GitHub Issue.

**Fail closed.** If Ferry's backend is unavailable, no automated deploys occur. Webhook events queue in GitHub. Drift detection pauses. Nothing breaks. Manual `ferry apply` from the CLI still works. State corruption on partial failure is not acceptable — pre-apply snapshots exist for this reason.

**Grace period is not optional in production.** The 15-minute default grace period before auto-reconcile exists to protect teams making emergency Console changes during incidents. Auto-reconcile during an active incident would be catastrophic. Teams can extend the grace period per environment (e.g., `grace_period_minutes: 60` for prod).

**Blast radius cap.** If >20% of managed resources drift simultaneously, auto-reconcile pauses entirely. This is the safety net against a bad `ferry.yml` commit or a mis-scoped reconcile run.

**No secrets stored.** Environment variable values using `${ssm:...}` or `${secretsmanager:...}` references are resolved at deploy time by Ferry and never stored in state. Raw string values in `environment:` blocks log a lint warning. Ferry never stores customer source code or credentials.

**IAM via OIDC, not stored keys.** Ferry never holds customer AWS credentials. Authentication is via OIDC trust between the Ferry GitHub App and a customer-managed IAM role. Customers create the role (Ferry provides a CloudFormation template), review the permissions, and own it. Ferry assumes it per-deployment.

**Manifest validation on every PR.** Validation errors (invalid runtime, memory outside 128MB–10240MB range, bad ARN format, missing required fields) block the plan and post a clear error comment. Schema version is pinned in `ferry.yml` — upgrades are explicit.

---

# Development and Launch Planning

## Milestones

### M0 — Core Infrastructure (Weeks 1–4)
- GitHub App registered and receiving webhooks
- OIDC auth flow end-to-end
- AWS provider: Lambda, Step Functions, API Gateway read/write adapters
- `ferry.yml` schema v1 with validation
- `ferry plan` computes field-level diff against live AWS state
- Plan comment posted on PR open

Exit: a developer can install Ferry, write a `ferry.yml`, open a PR, and see an accurate plan comment. No apply yet.

### M1 — GitOps Deploy Loop (Weeks 5–10)
- PR merge triggers apply
- Lambda: code + config update, version publish, alias management
- Step Functions state machine updates
- API Gateway route and stage management
- DynamoDB deployment lock (concurrent deploy queuing)
- State log: per-apply record (commit SHA, resources changed, pre-apply snapshot)
- Deploy success comment posted on merged PR
- Ferry CLI: `ferry plan`, `ferry apply`, `ferry status`

Exit: a developer can manage a Lambda function through the full PR → plan → merge → deploy cycle. Manual `sls deploy` is no longer needed for the happy path.

### M2 — Drift Detection (Weeks 11–16)
- Reconciler polling loop (AWS API → `ferry.yml` desired state)
- GitHub Issue creation on drift (structured format: resource, field, expected, actual)
- Grace period + auto-reconcile
- `ferry:skip-reconcile` label support
- Blast radius cap (>20% drift → pause, require human review)
- `ferry drift` CLI command (manual trigger)

Exit: a console-level change to a managed resource produces a GitHub Issue within 15 minutes and auto-reconciles within 30 minutes.

### M3 — Rollback + Hardening (Weeks 17–22)
- `ferry rollback` CLI (steps-based and commit-based)
- Rollback via Lambda alias pointer swap
- Destructive change guard (`--allow-destroy` required for function deletion)
- Concurrent deploy queuing under load
- SSM/Secrets Manager env var reference resolution
- Failure mode testing: partial apply, backend unavailable, AWS API rate limits

Exit: rollback of a single function completes in under 30 seconds. No state corruption on partial failure.

### M4 — Private Beta (Weeks 23–26)
- 5–10 design partners running Ferry in production
- Error message quality pass: every failure has a human-readable explanation and a next action
- Documentation: quickstart, `ferry.yml` reference, IAM role setup guide
- Telemetry (opt-in): deploy counts, drift frequency, rollback frequency

Exit: 5 design partners have Ferry managing at least one production resource group for 4+ weeks with zero Ferry-caused incidents.

### M5 — Open Source Launch (Weeks 27–30)
- Core reconciler open-sourced (Apache 2.0)
- Public documentation site
- GitHub repository with contribution guide and issue templates
- Show HN post, AWS/serverless community channels
- Ferry Cloud (managed SaaS, paid) for teams that don't want to run their own backend

---

## Other

### Risks

**R1 — Auto-reconcile causes a production incident.**
If Ferry's desired state has a bug and auto-reconcile fires aggressively, it could degrade production. This is the highest-trust risk. Mitigations: blast radius cap (>20% drift → pause), 15-minute grace period, dry-run gate before every apply, `ferry:skip-reconcile` escape hatch, explicit `--allow-destroy` for deletions. Treat this as the most important safety property in the system. Test it constantly.

**R2 — AWS builds native GitOps.**
AWS has acknowledged the gap (their "Operating Serverless at Scale: Governance" series) but current offerings are push-based CI/CD, not reconciliation operators. AWS historically acquires or integrates winning OSS rather than building from scratch. Mitigation: get into production use fast, build the community standard, make Ferry the obvious open-source answer before AWS ships anything comparable.

**R3 — Framework lock-in makes adoption too hard.**
Most target users already have Serverless Framework, SAM, or SST. Asking them to replace their IaC tool is high friction. This is the core adoption risk. Mitigation: `ferry.yml` is intentionally familiar (similar syntax to Serverless Framework). Position Ferry as the layer that adds reconciliation on top of existing tooling, not a full replacement. The `ferry import` wizard (post-MVP) accelerates this further.

**R4 — The deploy loop is unreliable enough to damage trust.**
A tool that deploys inconsistently or produces inaccurate plans is worse than no tool. If a plan says "no changes" and a deploy makes changes, trust is gone. Every plan must be accurate. Every apply must be idempotent. Mitigation: invest disproportionately in correctness over features during M0–M2. Don't ship M3 features until M1 is solid with design partners.

### FAQ

**Q: How is this different from just using GitHub Actions to run `sam deploy`?**
GitHub Actions is push-based. It deploys when triggered. It doesn't verify that what deployed still matches what was intended. An engineer making a Console change after a deployment leaves no trace in the Actions pipeline. Ferry's reconciliation loop watches deployed state continuously, not just at deploy time. The plan/apply model also gives you a preview of changes before they happen — `sam deploy` gives you none of that.

**Q: How is this different from Seed.run?**
Seed is a managed CI/CD orchestrator for Serverless Framework and SST. It's still push-based: a human action triggers a deployment. Seed doesn't detect drift. It doesn't auto-reconcile. Rollback requires the original source. Seed is a better deployment pipeline; Ferry is a reconciliation operator. They solve different problems, and Ferry doesn't require you to be on Serverless Framework or SST.

**Q: What if we make a console change intentionally during an incident?**
Ferry detects it as drift and opens a GitHub Issue. You have three options: (1) update `ferry.yml` to capture the intent via PR — the right answer; (2) label the issue `ferry:skip-reconcile` to tell Ferry to leave it alone; (3) do nothing and Ferry auto-reconciles after the grace period. The grace period (default 15 min, configurable) exists precisely for incident response windows.

**Q: Does Ferry replace our CI/CD pipeline?**
No. Your CI pipeline runs tests, builds artifacts, and validates code. Ferry handles the deploy step and the continuous reconciliation. They work alongside each other. Ferry is triggered by the same PR merge that your existing CI responds to — it just takes ownership of the AWS deploy step.

**Q: What permissions does Ferry's IAM role need?**
Ferry provides a CloudFormation template that creates a scoped IAM role: `lambda:*` (function management), `states:*` (Step Functions), `apigateway:*` (API Gateway), `dynamodb:*` on the Ferry state table only. No wildcards on resource ARNs except where Lambda's API requires it. Customers review and own this role. Ferry never stores credentials.

**Q: What happens if Ferry is down?**
Nothing breaks. PRs still merge to git. Ferry processes the apply backlog when it recovers. Drift detection resumes from the last checkpoint. No state corruption. Teams can run `ferry apply` manually from the CLI for critical deploys during an outage. Ferry's backend targets 99.9% uptime. It fails closed — unavailability means no automated deploys, not bad deploys.
