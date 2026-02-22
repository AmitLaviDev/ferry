# Ferry PRD — v3: Migration Path
**Product:** Ferry — GitOps for Serverless
**Version:** 3.0 (Migration Path Edition)
**Date:** 2026-02-22
**Status:** Draft for Review
**Author:** Product Team

---

# Problem Alignment

## Problem & Opportunity

Teams running production workloads on AWS Lambda are operating blind: functions are deployed manually from laptops, environment variables are edited live in the AWS Console, and there is no authoritative record of what version is actually running in production — only what someone *thought* they deployed last Thursday. When something breaks, the recovery path is "rebuild from memory." This is not a workflow problem. It is a governance and reliability crisis, and it is happening at scale: 1.8 million customers invoke Lambda functions 15+ trillion times per month, while fewer than 33% of organizations continuously monitor their infrastructure for drift, and fewer than 50% can remediate a drift incident within 24 hours.

The opportunity is structurally clear. ArgoCD solved this exact problem for Kubernetes in 2018 — manual, drift-prone, unauditable deployments — and now holds 60% cluster adoption with an NPS of 79. The GitOps mental model is proven and mainstream (64% enterprise adoption per CNCF 2024). No tool has applied continuous reconciliation to serverless. That gap is Ferry's founding premise.

**Why now:** Serverless is past early adopter but not yet fully tooled. The Forrester Wave created a dedicated Serverless Dev Platforms category in Q2 2025, signaling analyst category formation. The dominant framework (Serverless Framework) triggered a pricing controversy that is pushing teams to evaluate alternatives. AWS itself published a "Operating Serverless at Scale: Governance" series — acknowledging the gap without filling it. The window to define this category is open.

**Which customers:** Backend engineers, data engineers, and full-stack developers at companies with 10–500 engineers who have adopted Lambda but have not hired a dedicated platform or DevOps team. They are building with serverless for velocity, but the operational debt is accumulating in silence. Capital One's Serverless Center of Excellence is the enterprise tip; the real mass market is the thousands of teams below that scale who are one bad Console edit away from a production incident they cannot explain.

---

## High Level Approach

Ferry is a continuously-running GitOps operator for serverless infrastructure. It watches a Git repository as the authoritative desired state for AWS Lambda functions, Step Functions, and API Gateway, and continuously reconciles actual deployed state against that spec. When drift is detected — whether from a Console change, a partial deploy, or a misconfigured CI job — Ferry creates an actionable GitHub issue and, where configured, auto-reconciles. When a deployment is merged to the target branch, Ferry deploys it. When a deployment degrades health metrics, Ferry rolls back automatically. Git history becomes the audit trail. Git revert becomes the rollback primitive.

This is the ArgoCD model applied to serverless: operator pattern, declarative config, continuous reconciliation, Git-native RBAC, structured audit log. The technical implementation follows the OpenTaco/Digger open-core model — a GitHub App that runs in the customer's cloud account (no SaaS data plane), with PR automation, drift detection as a background process, and declarative workflow config stored in the repo itself.

**Alternatives considered:**

- *Extend an existing IaC tool (Terraform/Pulumi):* Both have GitOps wrappers, but they require Kubernetes to run their reconciliation loops (Pulumi Operator, Atlantis), are not serverless-aware (Lambda is just a generic resource with no alias, canary, or weighted routing semantics), and have no Lambda-specific health signal integration. We'd be building on a foundation that fights us at every layer.
- *Build a SaaS CI/CD orchestrator (Seed model):* Faster initial adoption but architecturally push-only. Seed.run shows the ceiling — good CI/CD orchestration, no reconciliation, no drift detection, audit gated behind $600/mo enterprise plans. We would be building into a dead end.
- *Wrapper around Serverless Framework:* Serverless Framework's push-only model and the v4 pricing controversy ($2M+ revenue companies must pay per credit) make it a risky dependency. We also inherit its lack of reconciliation semantics.

**Why this approach:** The operator pattern is the correct abstraction. Infrastructure desired state lives in Git. A continuously-running process (the Ferry operator, deployed to the customer's AWS account as a Lambda or ECS task) compares desired vs. actual state on a configurable interval and on every Git push. This gives us continuous reconciliation without requiring Kubernetes. The customer's cloud account is the data plane; Ferry is the control plane. No serverless infra passes through our servers.

**The migration-first angle:** The critical insight for V1 is that most target customers already have Lambda functions deployed. Ferry cannot require a greenfield setup. The product must meet teams where they are: import existing resources, enter read-only discovery mode first, then gradually take over deployment ownership. The migration path is not a feature — it is the product strategy.

---

### Narrative

**Story 1: The 3am Configuration Mystery**

Elena is a senior backend engineer at a 40-person fintech startup. Her team runs 60 Lambda functions. There is no DevOps team. Last quarter, a production incident traced back to a Lambda function's memory limit being 128MB in CloudFormation and 512MB in the Console — an engineer had raised it manually during an outage six months ago and nobody remembered. Elena spent three hours during the incident working backward through Slack logs and CloudWatch to understand what was actually running. There was no deployment record linking the Console change to a commit or a person.

She discovers Ferry. She runs `ferry import --region us-east-1` against her AWS account. In twelve minutes, Ferry has scanned all 60 functions, generated declarative config files for each, and opened a pull request showing the delta between what the code says and what is actually deployed. She reviews the PR, merges it, and for the first time has a Git-backed snapshot of production. She enables read-only mode — Ferry watches for drift but does not deploy yet. For two weeks, Ferry creates GitHub issues every time someone touches the Console. The team reviews the issues, turns the Console changes into PRs, and merges them. Nobody is blocked. Nothing breaks. The Console is still available as an escape hatch.

Six weeks later, Elena enables deploy mode for two non-critical functions. PR merged → Ferry deploys. She watches the GitHub Actions output, sees the deployment record link to the exact commit SHA, and realizes she now has what she wanted all along: a deployment log that is also version history. She rolls out Ferry to all 60 functions over the next month, function group by function group. The 3am incident cannot happen again — the Console change would appear as a drift issue in GitHub within 15 minutes.

---

**Story 2: The Handoff That Didn't Break Everything**

Marcus is the lead engineer at a Series A startup that recently lost its one serverless-expert engineer. That engineer had built a complex Step Functions workflow that orchestrates nightly data pipelines. The workflow definition lives partially in the Console and partially in a half-maintained `serverless.yml`. Nobody remaining on the team knows how to deploy it safely. They are afraid to touch it.

Marcus runs `ferry import --resource-type step-functions --name nightly-pipeline`. Ferry exports the current state definition from AWS, creates a version-controlled spec file, and attaches a deployment history reconstructed from CloudTrail events. Marcus now has a readable record of every state machine change for the past 90 days. He enables Ferry in dry-run mode — every push to the config file runs a `ferry plan` that shows the diff between current and desired state, posted as a PR comment. His team can review changes to the Step Functions workflow in a code review, catch logic errors before apply, and merge with confidence. Nobody needs to be a Step Functions expert to sanity-check a plan output.

---

**Story 3: The Audit That Didn't Panic**

Priya's team is a data engineering group at a healthcare company that just entered SOC 2 Type II audit preparation. Their auditors ask for evidence of change control for all production infrastructure. Priya's current answer is a combination of CI/CD logs, Slack messages, and a shared spreadsheet her team has maintained inconsistently. The auditors are not pleased.

Ferry's audit trail is Git history. Every deployment is linked to a commit, a PR, a reviewer, and a merge timestamp. Ferry exports a structured deployment log — committer, commit SHA, timestamp, resource changed, pre-deployment state hash, post-deployment state hash — in a format that maps directly to SOC 2 CC6.1 (logical access) and CC7.2 (system monitoring) controls. Priya runs `ferry audit export --from 2025-01-01 --to 2025-12-31 --format csv` and hands the file to her auditor. What would have been a two-week evidence-gathering scramble becomes a ten-minute export. SOC 2 passes. Priya's team adopts Ferry across all environments.

---

## Goals

**Priority order:**

1. **Time-to-first-value under 30 minutes.** A developer with existing Lambda functions in AWS should be able to run `ferry import`, generate a Git-backed config for their existing resources, and see their first drift detection issue in GitHub — all in under 30 minutes. This is the adoption funnel. If the first session requires a complete migration, we will lose every team with existing infrastructure.

2. **Zero production incidents caused by Ferry.** Ferry must be safe to run alongside existing workflows. Read-only mode and dry-run mode must be real, functional, and the default. Ferry should never modify a resource the user has not explicitly authorized it to manage. The escape hatch (direct AWS Console or CLI) must remain operational at all times. Violating this goal destroys trust and creates a category-level story that will follow us for years.

3. **Full GitOps loop operational for a production service within 30 days of onboarding.** Teams that complete import and pass through read-only mode should be deploying via Ferry by day 30. This is the activation metric — import is not adoption, deployment is adoption.

4. **Measurable drift reduction.** Teams using Ferry for 60+ days should see a measurable reduction in unplanned Console-originated changes. Target: fewer than 5% of deployed configuration changes originate outside Git for fully-managed resources.

5. **Compliance-ready audit export.** Any team on Ferry for 90+ days should be able to produce a SOC 2–mappable deployment audit log in under 10 minutes.

**Immeasurable but essential:**

- Developers feel confident merging infra changes because they can read the plan output before it applies.
- The on-call experience improves: rollback is `git revert`, not "who deployed last and do they have the source?"
- New team members can understand the deployed state of the system by reading the repo — no AWS Console archaeology.

**Guardrail metrics (if these move the wrong direction, we stop and investigate):**

- Ferry-caused production incidents: target 0, alarm at 1.
- Opt-out rate after read-only period: alarm if >40% of teams that complete import never enable deploy mode.
- Time-to-import p95: alarm if >45 minutes for accounts with <200 functions.
- Support tickets citing "Ferry modified something I didn't authorize": target 0.

---

## Non-Goals

**V1 does not address:**

- **Multi-cloud support (GCP Cloud Functions, Azure Functions, Cloudflare Workers).** AWS Lambda is where 1.8M monthly active customers are. Multi-cloud dilutes the operator's ability to model Lambda-specific semantics (aliases, versions, canary weighted routing, Lambda layers). We will define the category on AWS first and revisit multi-cloud at V2 or when there is explicit pull.

- **A UI (web dashboard or console).** CLI-first is a deliberate choice, not a cost shortcut. The ArgoCD web UI was added after the operator model was proven. Ferry V1 ships with `ferry` CLI, GitHub PR comments as the review interface, and GitHub Issues as the drift notification surface. A UI is Future Considerations.

- **Application-layer deployment strategies beyond Lambda's native mechanisms.** Blue/green and canary are in scope through Lambda aliases and weighted routing. A/B testing, feature flags, and progressive delivery at the application layer are not.

- **Serverless frameworks other than the resource types we define.** Ferry V1 manages Lambda functions, Step Functions state machines, and API Gateway REST/HTTP APIs as first-class resources. EventBridge rules, SQS queues, and DynamoDB tables that support these resources are modeled as dependencies, not primary managed resources. They are visible in import but not actively reconciled in V1.

- **Secret management.** Ferry does not store, rotate, or manage secrets. It integrates with AWS Secrets Manager and Parameter Store by reference — the config file points to a secret ARN, not the secret value. Secrets management is a separate product category.

- **Automated remediation of all drift types.** Some drift (IAM policy changes, VPC configuration) is high-risk to auto-remediate. In V1, all drift creates a GitHub Issue with a recommended action. Auto-remediation is opt-in per resource group and is scoped to non-destructive configuration changes (memory, timeout, environment variables, concurrency limits) only.

- **Replacing existing CI/CD pipelines.** Ferry integrates with GitHub Actions, not replaces it. Teams can continue to run their test suites, build steps, and other pipeline stages. Ferry handles the deploy step and the reconciliation loop. It is not a build system.

---

# Solution Alignment

## Key Features

### Plan of Record (priority order)

---

**1. `ferry import` — Resource Discovery and Config Generation**

*Why first:* Import is the zero-to-value moment for every existing team. Without a safe, accurate, non-destructive import, the product does not exist for the 1.8M customers who already have Lambda functions running.

- Scan an AWS account (or specified region, or specific ARNs) for Lambda functions, Step Functions state machines, and API Gateway resources.
- Generate declarative Ferry config files (`ferry.yaml` or per-resource HCL equivalent) from the live resource state.
- Reconstruct a partial deployment history from CloudTrail events (90-day lookback where CloudTrail is enabled).
- Open a GitHub PR with the generated config files and a diff showing any gaps between discovered state and any pre-existing IaC definitions detected in the repo.
- Default mode: read-only. Import does not grant Ferry deploy permissions. A separate, explicit `ferry grant --resource-group <name>` step is required before Ferry manages any resource.
- Handle partial imports gracefully — unsupported resource types are flagged in an `UNMANAGED.md` file, not silently skipped.

**Acceptance criteria:** `ferry import` on an account with 50 Lambda functions completes in under 10 minutes, generates valid config for 100% of supported resource types, and creates a PR with a human-readable diff against any existing `serverless.yml` or `template.yaml` found in the repo root.

---

**2. Read-Only / Drift Watch Mode**

*Why second:* Trust must be established before Ferry takes any action. Drift watch is the proof-of-value layer before the team commits to deploy mode. It is also a standalone product for teams that cannot or will not hand over deploy control (regulated industries, security-sensitive environments).

- Ferry operator polls AWS resource state on a configurable interval (default: 15 minutes, configurable to 1 minute for high-sensitivity environments).
- On every poll, compare live AWS state to the Git-committed desired state (the Ferry config files in the repo's default branch or configured deployment branch).
- On drift detection: open a GitHub Issue with the resource name, the attribute that drifted, the expected value (Git), the actual value (AWS), and the CloudTrail event that caused it (if available).
- Issues are labeled `ferry/drift`, linked to the resource config file, and include a suggested remediation PR command.
- Drift issues auto-close when the live state matches Git state again (either because someone fixed it in the Console or Ferry applied the correct state in deploy mode).
- Drift report available as `ferry status` output — shows all managed resources, their current drift status, and when they were last reconciled.

**Acceptance criteria:** Drift is detected and a GitHub Issue is opened within 2 poll intervals of a Console change to a managed resource. False positive rate is less than 1% (measured on controlled test accounts during internal testing).

---

**3. GitOps Deployment Loop (PR Automation and Auto-Deploy)**

*Why third:* This is the core product. After import and trust-building, teams graduate to having Ferry own the deploy step.

- GitHub App watches for pushes to the configured deployment branch (configurable, default: `main`).
- On PR open: run `ferry plan` — generate a diff of what would change if this PR were merged. Post the plan output as a PR comment, including resource names, attribute changes, and estimated deploy time. Surface any destructive changes (function deletion, API Gateway stage deletion) with a required manual approval step.
- On PR merge to deployment branch: auto-run `ferry apply`. The deployment is linked to the commit SHA, the PR number, and the GitHub username of the merger.
- Deployment lock: if a deploy is in progress for a resource group, queue subsequent deploys rather than failing. Concurrent deploy protection is a first-class feature, not a workaround. (This addresses the pain point: "Two devs deploying to same environment simultaneously → CloudFormation resource conflicts.")
- Post-deploy: update the GitHub PR with deployment status, Lambda version number deployed, and a link to the deployment record.
- All deployment records stored in Ferry state backend (S3 + DynamoDB by default, customer-managed). Each record: commit SHA, PR number, deployer GitHub username, timestamp, resources changed, pre-deploy state hash, post-deploy state hash.

**Acceptance criteria:** A PR merge results in a completed deployment within 5 minutes for stacks with fewer than 20 Lambda functions. The deployment record is queryable by commit SHA and by resource ARN.

---

**4. Health-Signal Rollback**

*Why fourth:* Rollback is the most frequently requested feature in developer forums and the most frequently broken in existing tools. ("Serverless Framework artifacts are not immutable — making traditional rollback strategies completely ineffective." — Seed.run) This is a meaningful differentiator.

- After every deploy, Ferry monitors CloudWatch metrics for the deployed functions for a configurable health window (default: 10 minutes).
- Monitored signals: error rate (Lambda errors / invocations), p99 latency, throttle rate. Thresholds are configurable per function or per resource group.
- On threshold breach within the health window: automatically roll back to the previous deployed version using Lambda's native versioning and alias swapping (no re-deploy from source required — this is immutable artifact rollback, the thing Serverless Framework cannot do).
- Rollback event is recorded in the state backend, linked to the original commit SHA and the CloudWatch alarm that triggered it.
- Rollback creates a GitHub Issue with the breach data, the rolled-back-to version, and a suggested `git revert` command for the offending commit.
- Manual rollback: `ferry rollback --resource-group <name> --to-commit <sha>` or `ferry rollback --resource-group <name> --steps 1`. Both forms are supported. (This directly addresses GitHub Issue #3894 — numeric rollback syntax.)

**Acceptance criteria:** A Lambda function with a failing deployment (error rate > threshold within health window) is rolled back automatically within 3 minutes of threshold breach. Manual rollback via CLI completes in under 2 minutes for a single function.

---

**5. Audit Trail and Compliance Export**

*Why fifth:* Compliance is a top-of-funnel driver for enterprise buyers and a retention driver for teams that go through SOC 2 or ISO 27001. The audit trail is largely a byproduct of the deployment loop, but the export tooling must be explicit.

- `ferry audit export` — generate a structured deployment history export (JSON, CSV, or PDF) filterable by date range, resource, deployer, and deployment status.
- Export fields map to SOC 2 CC6.1 (logical access control) and CC7.2 (system monitoring and detection) controls, with column names that match common audit questionnaire terminology.
- Audit log is immutable: records are append-only in the state backend. Ferry does not provide a delete or edit API for audit records.
- `ferry audit export --format pdf` generates a formatted report suitable for direct submission to auditors.

---

**6. Deployment RBAC via Git**

*Why sixth:* ACL enforcement through Git is a core GitOps value proposition — no direct AWS console permissions needed for developers, no shared deploy credentials. This is a strong enterprise selling point.

- Resource groups defined in Ferry config (`ferry.yaml`) map to GitHub teams. A PR that modifies resources in a group requires approval from a member of the mapped team before Ferry will apply.
- Developers push code; they never need AWS credentials for deploy actions. Ferry's GitHub App (running with a scoped IAM role in the customer's account) performs all AWS API calls.
- `ferry grant` and `ferry revoke` commands manage which resource groups Ferry actively manages. Requires admin-level GitHub token scoped to the repo.
- Emergency override: a console admin can break-glass by directly applying via `ferry apply --emergency --reason "P0 incident"`, which creates a mandatory GitHub Issue and Slack notification.

---

### Future Considerations

The following features are explicitly out of scope for V1 but are tracked for future prioritization based on adoption signal:

- **Web UI / Dashboard** — visual resource map, deployment history timeline, drift status board. Targeted for V2 after the operator model is validated.
- **Slack / PagerDuty Integration** — drift alerts and deployment notifications piped to communication channels rather than only GitHub Issues.
- **Multi-environment promotion workflows** — `ferry promote --from staging --to prod` with configurable approval gates. Requires multi-environment state management that adds complexity before the core loop is hardened.
- **EventBridge, SQS, DynamoDB as first-class managed resources** — supporting event sources and data dependencies, not just compute and orchestration.
- **Terraform/CDK config import** — parse existing `main.tf` or CDK app output and generate Ferry config from it, rather than scanning live AWS state. Reduces the need for a "ground truth scan" when teams already have partial IaC.
- **Multi-cloud support** — GCP Cloud Functions, Azure Functions. Evaluate after AWS market share is established.
- **Policy-as-code integration** — OPA/Rego policies that block PR merges if the ferry plan violates defined rules (e.g., "no function may exceed 3GB memory without VP approval").
- **Lambda cost anomaly integration** — flag deployments that cause >20% cost increase in CloudWatch cost metrics.

---

### Key Flows

#### Flow 1: Discovery and Import (Day 1)

```
Developer installs Ferry GitHub App on their repo
  → Runs: ferry init --repo <org/repo> --aws-region us-east-1
  → Ferry requests read-only AWS permissions (IAM role with Lambda:List*, Lambda:Get*,
    StepFunctions:List*, ApiGateway:GET) — never write permissions at this stage
  → Runs: ferry import --region us-east-1 [--filter tag:Environment=prod]
  → Ferry scans all matching resources
  → Ferry generates:
      /ferry/
        functions/
          payment-processor.yaml
          user-auth.yaml
          notification-sender.yaml
        workflows/
          nightly-pipeline.yaml
        apis/
          v2-rest-api.yaml
        ferry.yaml  (root config: resource groups, deploy branch, health thresholds)
        UNMANAGED.md  (any resource types Ferry cannot model yet)
  → Ferry opens GitHub PR: "ferry/import: discovered 47 resources (2026-02-22)"
  → PR includes:
      - Summary table: resource count by type
      - Delta table: attributes that differ between live AWS state and any existing IaC
      - CloudTrail-reconstructed change history for the last 90 days per resource
      - Instructions for next steps (review, merge, then optionally enable drift watch)
Developer reviews, edits if needed, merges PR
  → Ferry enters READ-ONLY mode automatically (no deploy permissions granted)
```

---

#### Flow 2: Drift Watch (Days 2–30, Gradual Trust Building)

```
Ferry operator (running as Lambda or ECS task in customer account) polls every 15 min
  → Fetches live state for all resources in ferry.yaml
  → Compares to Git committed state (default branch)
  → On drift detected:
      → Opens GitHub Issue:
          Title: "Drift detected: payment-processor — MemorySize changed"
          Body:
            Resource: arn:aws:lambda:us-east-1:123:function:payment-processor
            Attribute: MemorySize
            Expected (Git): 128
            Actual (AWS): 512
            Changed by: arn:aws:iam::123:user/john.smith (via CloudTrail)
            Changed at: 2026-02-19T14:32:11Z

            Suggested fix:
              Option A: Update Git to match Console → `ferry sync --from-aws payment-processor`
              Option B: Revert Console to match Git → Enable deploy mode and re-apply
          Labels: ferry/drift, resource:payment-processor, severity:medium
  → Drift issue auto-closes when live state matches Git again
Developer reviews issues → either raises a PR to update the config or
  reverts the Console change manually
  → Team builds habit: Console changes become PRs
  → After 2 weeks, team sees drift frequency decreasing
```

---

#### Flow 3: First Deployment via Ferry (Enabling Deploy Mode)

```
Team decides to enable deploy mode for one resource group
  → Runs: ferry grant --resource-group non-critical-functions
  → Ferry prompts:
      "This will allow Ferry to deploy to: [user-auth, notification-sender]
       Ferry will request additional IAM permissions: Lambda:UpdateFunctionCode,
       Lambda:UpdateFunctionConfiguration, Lambda:PublishVersion, Lambda:UpdateAlias
       Confirm? [y/N]"
  → On confirm: Ferry creates scoped IAM role, stores ARN in state backend
  → Team creates a branch, edits notification-sender.yaml (increases timeout from 30s → 60s)
  → Opens PR → Ferry GitHub App posts plan comment:
      ## Ferry Plan

      Resource Group: non-critical-functions
      Triggered by: @elena on PR #42

      ~ aws_lambda_function.notification-sender
          timeout: 30 → 60

      Estimated deploy time: ~45 seconds
      No destructive changes. Safe to merge.
  → Team reviews, approves, merges
  → Ferry deploys: updates function configuration
  → Posts to PR:
      ## Ferry Apply — Succeeded

      Deployed at: 2026-02-22T09:14:33Z
      Commit: abc123f
      Lambda version published: 14
      Alias $LIVE updated: v13 → v14

      Health window: monitoring for 10 minutes
      CloudWatch link: [View metrics]
  → Health window passes cleanly → deployment record finalized
  → Team repeats for next resource group
```

---

#### Flow 4: Health-Signal Rollback (When Things Go Wrong)

```
Team merges a PR that increases payment-processor concurrency limit
  → Ferry deploys: publishes v27, updates alias $LIVE to v27
  → Health monitoring begins (10-minute window)
  → At 4 minutes post-deploy: Lambda error rate spikes to 12% (threshold: 5%)
  → Ferry triggers automatic rollback:
      → Alias $LIVE → v26 (previous version, already published, immutable)
      → Rollback completes in ~8 seconds (alias swap, not a re-deploy)
  → Ferry opens GitHub Issue:
      Title: "Rollback triggered: payment-processor — error rate 12% (threshold 5%)"
      Body:
        Rolled back: v27 → v26
        Trigger: ErrorRate = 12% at 2026-02-22T11:23:44Z
        Alarm: payment-processor-error-rate-high
        CloudWatch dashboard: [link]

        Suggested action:
          git revert abc123f  # the commit that introduced v27
          → Open a PR with this revert to keep Git state synchronized

        Deployment record: ferry-state://deployments/payment-processor/v27
  → On-call engineer sees the issue, investigates, creates a revert PR
  → Ferry detects revert PR, shows plan confirming state will match rollback
  → Revert merged → Ferry re-deploys with the rollback config →
    Git and AWS state synchronized again
```

---

#### Flow 5: Escape Hatch — Bypassing Ferry in an Emergency

```
P0 incident: production function is broken, on-call needs to deploy a hotfix NOW
  → Engineer pushes directly to deployment branch (force-push allowed with admin token)
  → OR: runs ferry apply --emergency --reason "P0: payment processor down #INC-4421"
  → Ferry applies immediately, bypassing PR requirement
  → Emergency apply creates:
      → GitHub Issue with reason, deployer, timestamp, commit SHA
      → Slack notification to #deploys and #incidents channels (if integration configured)
      → Audit record flagged as EMERGENCY_OVERRIDE
  → After incident resolved: team opens a retrospective PR linking the emergency commit
    to a proper config PR that "ratifies" the change in Git
  → Ferry drift watch surfaces any unratified emergency changes as drift issues
    until they are formally committed to config
```

---

### Key Logic

**Backward Compatibility and Safe Migration Rules:**

1. **Import never writes to AWS.** `ferry import` is strictly a read operation. It writes to the local filesystem (config files) and opens a GitHub PR. It does not create IAM roles, does not modify Lambda configuration, and does not register any webhooks that could trigger deployments. This is a hard architectural constraint, enforced at the CLI layer.

2. **Deploy permissions are per-resource-group and opt-in.** Ferry cannot deploy to any resource until `ferry grant` is explicitly run for that resource group by a user with repo admin rights. Default state after import is zero deploy permissions. The IAM role created by `ferry grant` is scoped to the minimum permissions for the specific functions in the resource group — not account-wide Lambda write access.

3. **Dry-run is always available.** `ferry plan` can be run at any time without deploying. PR automation defaults to plan-only until deploy mode is enabled. Dry-run mode must be equivalent to what apply would do — plans that are inaccurate undermine the entire model.

4. **Console access is never revoked.** Ferry does not modify or restrict AWS Console access. Teams can always make changes directly via Console or CLI. The governance mechanism is detection (drift watch → GitHub Issue), not prevention. Preventing Console access would require IAM changes that are out of scope and create safety risks. The social mechanism (drift issues in GitHub) is the control.

5. **State is customer-owned.** Ferry state (deployment records, drift history, resource group config) is stored in S3 and DynamoDB in the customer's own AWS account. Ferry's backend never holds customer infrastructure state. This is a security and vendor lock-in concern addressed architecturally. If a customer stops using Ferry, their state is fully in their own account — readable, exportable, not held hostage.

6. **Rollback uses Lambda native versioning, not re-deploy.** Rollback does not require the source code, the original developer, or the CI environment that produced the original artifact. Ferry records the Lambda version ARN at deploy time. Rollback is an alias pointer swap — it takes seconds, not minutes, and is not subject to transient build environment failures.

7. **Concurrent deployment safety.** Ferry maintains a per-resource-group deployment lock in DynamoDB (conditional write). If a deploy is in progress, subsequent triggers are queued (configurable queue depth, default 3) and processed in order. A deploy that exceeds a timeout (default 15 minutes) releases the lock and creates a GitHub Issue. No concurrent deploys to the same resource group. This directly addresses the "Two devs deploying simultaneously → CloudFormation conflicts" pain point.

8. **Destructive change guard.** Any ferry plan that includes a resource deletion (Lambda function, API Gateway resource, Step Functions state machine) requires an explicit `# ferry:allow-destroy` annotation in the config file and a separate PR comment from a repo admin (`/ferry approve-destroy`). Without both, ferry apply will skip the destructive change and create an Issue describing what was blocked and why.

9. **Unsupported resource passthrough.** Resources that Ferry cannot model (EventBridge rules, SQS, SNS, DynamoDB) are listed in `UNMANAGED.md` and ignored by the reconciliation loop. Ferry does not touch them, does not flag them as drift, and does not block deployments because of them. Partial management is explicitly supported.

10. **Config format stability.** Ferry config files (`ferry.yaml`, per-resource files) follow a versioned schema. Breaking changes to the schema require a major version bump and a migration tool (`ferry migrate --from-schema v1 --to-schema v2`). Teams must not be surprised by a Ferry upgrade changing the meaning of their config.

**Edge cases:**

- *Lambda function deleted from AWS but present in Git:* Ferry creates a drift Issue (type: MISSING_RESOURCE) rather than attempting to re-create it automatically. Recreation is a destructive change in the opposite direction and requires explicit apply.
- *Lambda function present in AWS but deleted from ferry config:* Treated as an unmanaged resource — Ferry stops reconciling it and removes it from drift watch. Does not delete the function. Creating the deletion requires explicit `ferry destroy` with the `allow-destroy` guard.
- *Ferry operator loses connectivity to AWS:* Ferry enters a "stale" state after 3 missed poll cycles and creates a GitHub Issue. It does not fail open (taking action) or fail in a way that blocks the CI pipeline. Deployments triggered by PR merges still attempt to run.
- *AWS API rate limiting:* Ferry uses exponential backoff with jitter for all AWS API calls. Import and poll operations respect Lambda's ListFunctions pagination. For accounts with >1000 functions, import is batched and estimated time is surfaced to the user before the scan begins.
- *Two Ferry instances running against the same account:* The deployment lock in DynamoDB prevents concurrent applies. Import from two instances produces two PRs — the Git conflict is visible and resolvable through normal PR workflow.

**Non-functional requirements:**

- *Import performance:* p95 import time for 100 Lambda functions in a single region must be under 5 minutes.
- *Drift poll latency:* Drift must be detected within 2 poll intervals (default: 30 minutes maximum). For high-sensitivity environments with 1-minute polling, drift is detected within 2 minutes.
- *Rollback speed:* Alias-swap rollback must complete within 30 seconds of the triggering event for any single Lambda function.
- *GitHub App availability:* PR automation (plan comments) must succeed within 60 seconds of PR open for stacks with fewer than 20 functions. Failure to post a plan comment does not block the PR — it creates an error annotation.
- *State backend durability:* Deployment records in S3 must be versioned. Accidental deletion of a record must be recoverable from S3 versioning.
- *IAM principle of least privilege:* Ferry's IAM role in the customer account must be documented and auditable. Every permission must be justified in the documentation. Wildcard resource permissions (`*`) are prohibited.

---

# Development and Launch Planning

## Key Milestones

### Milestone 0: Foundation (Weeks 1–6)
- Ferry CLI scaffold — `ferry init`, `ferry import`, `ferry plan`, `ferry apply`, `ferry status`
- AWS provider layer — Lambda, Step Functions, API Gateway read/write adapters
- State backend — S3 + DynamoDB schema, deployment record format, lock mechanism
- Config schema v1 — `ferry.yaml` root config, per-function schema, resource group model
- GitHub App scaffold — webhook receiver, PR comment posting, Issue creation
- Internal testing environment — two isolated AWS accounts (source-of-truth and drift target)

### Milestone 1: Private Alpha — Import and Drift Watch (Weeks 7–12)
- `ferry import` complete with CloudTrail history reconstruction
- Drift detection poll loop operational
- GitHub Issue creation for drift events with CloudTrail attribution
- `ferry status` output
- 3–5 design partners onboarded (teams with existing Lambda functions, no existing GitOps)
- Success criteria: all design partners complete import in under 30 minutes; drift detection catches 100% of Console changes in controlled tests

### Milestone 2: Private Beta — GitOps Deploy Loop (Weeks 13–20)
- PR automation: plan comment on PR open, apply on merge
- Deployment lock (DynamoDB conditional write)
- Health-signal monitoring and alias-swap rollback
- `ferry rollback` CLI command (commit SHA and step-count forms)
- Audit record export (`ferry audit export`)
- 15–30 beta users, mix of startup and mid-market
- Success criteria: 5+ beta teams have Ferry owning at least one production resource group; zero Ferry-caused incidents

### Milestone 3: Public Launch — Open Core (Weeks 21–30)
- Open-source core operator (Apache 2.0) — import, drift watch, deploy loop, rollback, CLI
- Ferry Cloud (managed operator hosting, SaaS state backend, team management) — paid
- Documentation site: installation guide, migration playbook, resource type reference, security model
- Deployment RBAC (GitHub team → resource group mapping)
- Emergency override flow with audit annotation
- `ferry audit export --format pdf`
- Blog post: "GitOps for Serverless — the gap ArgoCD didn't fill"
- Launch targets: Hacker News Show HN, AWS community channels, serverless-focused newsletters

### Milestone 4: Growth (Weeks 31–52)
- Slack and PagerDuty integration for drift notifications
- Multi-environment promotion (`ferry promote`)
- Terraform config import (parse `main.tf` → generate ferry config without live scan)
- EventBridge and SQS as first-class resource types
- Ferry Analytics — fleet-level drift rate, deployment frequency, rollback rate dashboards
- Enterprise tier: SSO, SCIM, advanced audit export, SLA

---

## Operational Checklist

**Pre-launch:**
- [ ] Security review of Ferry IAM role — every permission documented and scoped
- [ ] Penetration test of GitHub App webhook receiver (signature validation, replay protection)
- [ ] AWS Service Quotas analysis — ferry import must handle accounts at Lambda quota limits
- [ ] Load test — 1000-function import, 500-function drift poll, 50 concurrent PR events
- [ ] Rollback reliability test — 100 consecutive alias-swap rollbacks in test environment
- [ ] State backend recovery test — simulate S3 and DynamoDB partial failures
- [ ] CloudTrail dependency documentation — ferry import degrades gracefully if CloudTrail is disabled
- [ ] Legal review of open-source license (Apache 2.0) and CLA for contributors
- [ ] Data residency documentation — all state in customer's account, no data leaves

**Launch support:**
- [ ] Runbook: "Ferry deployed something I didn't expect" — investigation and mitigation steps
- [ ] Runbook: "ferry import found resources I don't recognize" — disambiguation guide
- [ ] Runbook: "Drift detected in a resource I don't want Ferry to manage" — opt-out procedure
- [ ] Public status page for Ferry Cloud (managed tier)
- [ ] On-call rotation for Ferry Cloud during launch week

---

## Other

### Appendix

**A. Ferry Config Schema (v1 example)**

```yaml
# ferry.yaml — root config, committed to repo root or /ferry/ directory
version: 1
state_backend:
  type: aws_s3_dynamodb
  bucket: my-org-ferry-state
  table: my-org-ferry-locks
  region: us-east-1

deploy_branch: main
operator:
  poll_interval_minutes: 15
  health_window_minutes: 10

resource_groups:
  critical-payments:
    resources:
      - functions/payment-processor.yaml
      - functions/payment-webhook.yaml
      - apis/payments-api.yaml
    github_team: backend-leads   # required approver for deploys to this group
    managed: false               # read-only until ferry grant is run
    health_thresholds:
      error_rate_percent: 2
      p99_latency_ms: 3000
      throttle_rate_percent: 5

  non-critical:
    resources:
      - functions/notification-sender.yaml
      - functions/user-auth.yaml
    managed: true
    health_thresholds:
      error_rate_percent: 5
      p99_latency_ms: 10000
```

**B. Competitive Moat Summary**

The gap in the market is not feature-level — it is architectural. Every existing tool is push-only. Ferry's continuous reconciliation loop is an operator pattern, not a CI/CD pipeline enhancement. The table below shows the capability gap:

| Capability | Serverless Framework | SAM | SST | Terraform+Atlantis | Ferry V1 |
|---|---|---|---|---|---|
| Continuous reconciliation | No | No | No | No | Yes |
| Drift detection | No | No | No | Scheduled | Continuous |
| Git-native rollback | No | No | No | No | Yes (alias swap) |
| Audit trail | CI logs only | CI logs only | SaaS only | CI logs only | Git + state backend |
| Deployment RBAC | No | No | No | Workspace-level | Git team → resource group |
| Import existing resources | No | No | No | Partial (import block) | Yes (first-class) |
| Serverless-native semantics | Yes | Yes | Yes | No | Yes |

**C. Open-Core Model**

Ferry follows the ArgoCD/Akuity model: open-source operator, commercial managed service. The open-source tier (Apache 2.0) includes all core functionality — import, drift watch, deploy loop, rollback, CLI, self-hosted operator. Ferry Cloud (paid) adds: managed operator hosting (no infra to run), SaaS state backend, team management UI, SSO/SCIM, advanced audit export, and SLA. This avoids the Serverless Framework v4 pricing mistake — the tool that drives adoption is free and open forever.

---

### Risks

**R1: AWS builds a native GitOps offering**
*Likelihood:* Medium. AWS CodePipeline and CodeDeploy are CI/CD-centric, not reconciliation-based. AWS has shown no signs of building an ArgoCD-equivalent. Their governance series acknowledges the gap without filling it.
*Mitigation:* Win with developer experience and ecosystem before AWS can react. ArgoCD won 60% K8s market share against GKE's built-in deployment tools. OSS community adoption creates switching cost.

**R2: Teams don't trust Ferry with production deployments**
*Likelihood:* High in the early market. The "read-only first" model exists specifically to address this. The escape hatch (Console always works, emergency override always available) is a trust-building mechanism, not a technical compromise.
*Mitigation:* Design partner program with white-glove onboarding. Public incident post-mortems when Ferry makes mistakes. Zero-incident track record through M2 before broad launch.

**R3: The import step produces inaccurate config, causing a bad deploy**
*Likelihood:* Medium. AWS resource state APIs are occasionally inconsistent. CloudTrail history is incomplete for pre-existing resources.
*Mitigation:* Import produces config + requires human review via PR before any managed state is established. Ferry never auto-applies imported config. The PR review step is mandatory, not optional.

**R4: Lambda alias/versioning complexity creates rollback failures**
*Likelihood:* Low-medium. Lambda aliases and versions are well-documented, but edge cases exist (functions with no published versions, functions using $LATEST, container image functions).
*Mitigation:* Ferry requires alias-based deployment (publishes a version on every deploy, manages a named alias like `$LIVE`). Functions using `$LATEST` are flagged during import with a migration suggestion. Container image functions are supported in V1 but rollback is image-digest-based rather than version-number-based.

**R5: Category education cost is high — "GitOps for Serverless" doesn't resonate**
*Likelihood:* Medium. The framing works for engineers who know ArgoCD. For teams who don't, "continuous reconciliation" needs translation.
*Mitigation:* Dual messaging track: technical track ("ArgoCD for serverless") and business track ("Git is your source of truth — Ferry keeps AWS matching it"). The migration narrative (meet teams where they are) is the accessible entry point.

**R6: Open-source fork undermines commercial tier**
*Likelihood:* Low. The managed hosting value prop is operational, not feature-gated. Teams that want to run the operator themselves can. Teams that don't want to manage another piece of infrastructure pay for Ferry Cloud. This is the Grafana/HashiCorp model before BSL — done correctly with Apache 2.0, the community is a growth driver, not a threat.

---

### FAQ

**Q: Why not build on top of Terraform or Pulumi instead of a custom operator?**
A: Terraform is not Lambda-aware. Lambda's alias/version system, weighted routing for canary deploys, and health-signal rollback cannot be modeled as generic Terraform resources without significant custom provider work. More importantly, Terraform's reconciliation loop requires Kubernetes (Pulumi Operator, Atlantis) — which is ironic for a serverless team. We would be building for the use case Terraform was not designed for, fighting the abstraction at every layer. A purpose-built operator that speaks Lambda natively is the right foundation.

**Q: What if a team uses Serverless Framework today — do they have to rewrite everything?**
A: No. `ferry import` scans the live AWS state, not the Serverless Framework YAML. The import generates Ferry config from what is actually deployed. Teams can deprecate their `serverless.yml` incrementally — Ferry takes over one resource group at a time. The two tools can coexist during migration as long as they are not managing the same resource simultaneously (Ferry will flag the conflict as drift if Serverless Framework deploys over a Ferry-managed function).

**Q: How does Ferry handle functions deployed from multiple repos (monorepo vs. multi-repo)?**
A: Each Ferry installation is scoped to a GitHub repository. For multi-repo setups, each repo runs its own Ferry instance with its own resource groups. The state backends can be separate (recommended) or shared (supported, with explicit resource group scoping to prevent cross-repo conflicts). A cross-repo dependency graph is a V2 feature.

**Q: What happens if Ferry's operator goes down?**
A: Deployments triggered by PR merges are event-driven (GitHub App webhook). If the operator is down, webhook events are queued by GitHub for up to 30 seconds and retried. For longer outages, a `ferry apply` command can be run manually from the CLI with the same IAM role. Drift detection pauses during operator downtime. Ferry Cloud's managed tier has a 99.9% SLA.

**Q: Is there a risk that Ferry's IAM role is a security liability?**
A: The IAM role is the primary security surface and is treated as such. Read-mode IAM role: Lambda:List*, Lambda:Get*, StepFunctions:List*, ApiGateway:GET — no write permissions. Deploy-mode IAM role: per-resource-group, scoped to specific function ARNs, not account-wide. The role definition is generated by Ferry, published as open-source CloudFormation/CDK, and is auditable by the customer before creation. No wildcard resource permissions. The emergency override audit trail exists specifically to detect role misuse.

**Q: How does Ferry handle multi-account AWS setups?**
A: V1 supports single-account, single-region. Multi-account (via AWS Organizations and cross-account IAM role assumption) is on the V2 roadmap. Enterprise teams with multi-account setups can run separate Ferry instances per account in V1 — the GitHub App can be installed org-wide and each repo can target a different account.

**Q: What's the pricing model for Ferry Cloud?**
A: Not finalized for V1 launch. Working assumption: per-managed-function pricing (similar to Datadog's Lambda monitoring tier), with a free tier covering up to 10 functions and unlimited drift watch. Enterprise tier adds SSO, SCIM, and SLA. Open-source self-hosted remains free with no function limit.

---

*This document represents the V3 product direction for Ferry. It supersedes the V1 and V2 PRDs. Key changes from V2: migration-first positioning, import flow elevated to feature #1, read-only mode formalized as a trust-building phase, escape hatch flow made explicit, and guardrail metrics added to prevent over-engineering the GitOps loop at the expense of adoption friction.*

*Next review: 2026-03-07*
