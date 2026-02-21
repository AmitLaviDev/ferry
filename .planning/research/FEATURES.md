# Feature Landscape

**Domain:** Serverless AWS deployment automation (Lambda, Step Functions, API Gateway)
**Researched:** 2026-02-21
**Confidence:** MEDIUM (based on training data for competitor products; web verification unavailable)

## Competitive Landscape Summary

Products analyzed across the serverless deployment automation space:

| Product | Model | Relevance to Ferry |
|---------|-------|-------------------|
| **Digger** | GitHub App + GHA (Terraform) | Direct architectural model -- Ferry adapts this for serverless code deploys |
| **SST (Ion)** | CLI + Console | Full framework approach, different philosophy but feature benchmark |
| **Serverless Framework v4** | CLI + Dashboard | Plugin ecosystem, stage management, packaging |
| **AWS SAM** | CLI (CloudFormation) | AWS-native baseline, local dev focus |
| **Seed.run** | Hosted CI/CD (Serverless Framework) | Closest to Ferry's hosted model for serverless |
| **ArgoCD** | GitOps controller (K8s) | GitOps sync/status model Ferry should emulate |

---

## Table Stakes

Features users expect. Missing any of these means the product feels broken or incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Change detection** | Every competitor detects what changed. Deploying everything on every push is unacceptable for repos with 10+ resources. | Medium | Ferry uses commit diff + ferry.yaml path mappings. Digger does file-path matching for Terraform. Seed.run does incremental deploys. This is non-negotiable. |
| **Container/artifact build** | Users expect the tool to handle building, not just deploying. SAM builds, SST builds, Serverless packages. Ferry's magic Dockerfile IS the build. | Medium | Ferry's key UX win -- one Dockerfile for all Lambdas. Must handle build caching (ECR layer cache) or builds become painfully slow. |
| **Multi-resource deployment** | A single push often changes multiple Lambdas. Deploying one-at-a-time manually is what Ferry replaces. | Medium | Ferry dispatches per resource type, with payload listing all changed resources of that type. Parallel execution within a dispatch is expected. |
| **PR status reporting** | Digger posts plan output on PRs. ArgoCD shows sync status. SST Console shows deploy status. Users need to know what WILL deploy before merging. | Medium | GitHub Checks API -- post which resources are affected, build/deploy status. This is the primary UI since Ferry has no dashboard. |
| **Webhook signature validation** | Security baseline. Any GitHub App that doesn't validate HMAC-SHA256 signatures is a vulnerability. | Low | Standard implementation. Already in Ferry's requirements. |
| **Idempotent delivery** | GitHub sends duplicate webhooks. Processing them twice causes wasted builds or race conditions. | Low | DynamoDB conditional writes for dedup. Already in Ferry's requirements. |
| **OIDC authentication** | Storing AWS credentials as GitHub secrets is the old way. OIDC federation is table stakes in 2026. Digger, AWS's own docs, and GitHub all push OIDC. | Low | User provides role ARN, Ferry Action does OIDC exchange + optional role chaining. |
| **Deployment tagging** | Users need to correlate deployments with code. "Which commit is running in prod?" must be answerable. | Low | Tag ECR images and Lambda versions with git SHA, PR number, or branch. Reference impl uses `pr-{number}` and `{branch}-{commit}`. |
| **Clear error reporting** | When a deploy fails, users need to see the error in the PR/workflow, not hunt through CloudWatch. | Low | Surface build failures, deploy failures, and permission errors in GHA output AND PR status checks. |

## Differentiators

Features that set Ferry apart. Not expected by default, but create competitive advantage.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Magic Dockerfile (zero-config builds)** | One Dockerfile builds ANY Lambda. No per-function build config. This is Ferry's signature feature -- no competitor does this. SAM requires per-function build config. Serverless Framework needs plugins. SST generates build config per function. | Low (already designed) | The glob trick (`COPY system-requirements.tx[t]`) for optional files, build secrets for private repos. This is the single biggest UX differentiator. |
| **GitOps for serverless code** (not IaC) | Ferry deploys CODE, not infrastructure. IaC (Terraform) owns resource creation. Ferry owns code updates. This clean separation doesn't exist in SAM/SST/Serverless which conflate IaC and code deployment. Digger only does IaC. | Low (architectural decision) | The "three connection points" model (code dir + IaC module + ECR repo) is unique. ferry.yaml makes this explicit. |
| **PR preview of affected resources** | Before merge, see exactly which Lambdas, Step Functions, and API Gateways will be deployed. Digger does this for Terraform plans. No serverless tool does this for code deploys. | Medium | Parse commit diff against ferry.yaml, post a summary check. "This PR will deploy: order-processor (Lambda), checkout-flow (Step Function)". Huge confidence-builder. |
| **Digest-based skip** | If the built Docker image digest matches what's already deployed, skip the deployment. Saves deploy time and avoids unnecessary Lambda cold starts. Seed.run does incremental deploys but at the package hash level. | Medium | Compare ECR image digest with currently deployed Lambda image URI. Reference impl already does this via `int128/deploy-lambda-action`. |
| **Thin backend (serverless deploys serverless)** | Ferry's backend is 1-2 Lambdas. Competitors like Seed.run run substantial backend infrastructure. SST Console is a hosted service. This means low operational cost and simple self-hosting path later. | Low (architectural decision) | Marketing differentiator as much as technical. "Your deployment tool costs $0.50/month in AWS bills." |
| **Resource-type-aware dispatching** | One dispatch per resource type (Lambdas, Step Functions, API Gateways). Each type has different build/deploy logic. Cleaner than monolithic "deploy everything" or per-resource dispatching. | Medium | Enables type-specific optimizations: parallel Lambda builds, sequential Step Function updates, API Gateway deployment stages. |

## Anti-Features

Features to explicitly NOT build. These are tempting but wrong for Ferry v1.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Web dashboard** | Ferry's UI is the GitHub PR. Building a dashboard means maintaining a frontend, auth system, and state sync. Digger spent years building theirs and it's mediocre. SST Console is good but required massive investment. | Post everything to GitHub Checks API and PR comments. The PR IS the dashboard. |
| **AI/automatic resource discovery** | Scanning repos to auto-detect Lambdas sounds smart but is fragile, inaccurate, and removes user control. Explicit config (ferry.yaml) is more reliable and debuggable. | ferry.yaml is the source of truth. Users declare resources explicitly. |
| **Infrastructure provisioning** | Creating Lambda functions, ECR repos, Step Functions, or API Gateways. This is Terraform/CloudFormation territory. Ferry deploys code to EXISTING resources. Mixing IaC and code deployment is how SAM/SST/Serverless become complex. | Require pre-existing resources. ferry.yaml maps code to existing infra. IaC creates resources, Ferry updates them. |
| **Automatic rollback** | Sounds essential but is dangerous for serverless. Rolling back a Lambda might break a Step Function that depends on the new version. Rolling back an API Gateway spec might orphan Lambda integrations. Cross-resource rollback is an unsolved problem. | User re-deploys previous commit. Git is the rollback mechanism. Clear deployment tagging makes "which commit to revert to" obvious. |
| **Environment/branch mapping** | Mapping branches to environments (main=prod, develop=staging) adds complexity around promotion, environment-specific config, and multi-account AWS. Digger supports this but it's their most complex feature. | v1 deploys to one target account per workflow run. Environment management is a v2 feature. |
| **Local development/testing** | SAM has `sam local invoke`. SST has live Lambda dev. These are huge features that don't fit Ferry's model. Ferry runs in GHA, not locally. | Users test Lambdas locally with their own tools (pytest, docker run). Ferry is a CI/CD tool, not a dev tool. |
| **Plugin/extension system** | Serverless Framework's plugin ecosystem is powerful but created a maintenance nightmare. Plugins break across versions, have inconsistent quality, and fragment the community. | Opinionated defaults. If a deployment type isn't supported, add it as a first-class resource type in ferry.yaml, not as a plugin. |
| **Multi-account deployment** | Deploying to staging AND prod from one push. Requires environment promotion logic, approval gates, account-specific role ARNs. Significantly increases complexity. | One target account per workflow run. Users can set up separate workflows for staging/prod if needed. |
| **SQS/async event processing** | Adding a queue between webhook receipt and dispatch adds latency, complexity (DLQ, retry logic, ordering), and infra. The reference implementation processes synchronously and it works fine. | Process webhook synchronously. Lambda timeout is 15 minutes -- plenty for reading ferry.yaml, computing diffs, and triggering dispatches. |
| **ECR repository creation** | Auto-creating ECR repos conflates infrastructure management with code deployment. What permissions should the repo have? What lifecycle policy? These are IaC decisions. | Require pre-existing ECR repos. ferry.yaml's `ecr` field points to repos that already exist. |
| **Drift detection** | Detecting when deployed Lambda code doesn't match the expected version. ArgoCD does this for K8s. But for serverless, "drift" mostly means someone manually updated a Lambda in the console, which is a process problem not a tooling problem. | Out of scope for v1. If needed later, compare deployed image digest against expected digest from last Ferry deployment. |

## Feature Dependencies

```
Webhook validation ──> Change detection ──> PR status reporting
                                        ──> Workflow dispatch ──> Container build ──> Lambda deploy
                                                              ──> Step Function deploy
                                                              ──> API Gateway deploy

ferry.yaml parsing ──> Change detection (path mapping)
                   ──> Workflow dispatch (resource list payload)
                   ──> PR status reporting (resource names)

OIDC auth ──> ECR push
          ──> Lambda deploy
          ──> Step Function deploy
          ──> API Gateway deploy

Container build (ECR push) ──> Lambda deploy (image URI)
                           ──> Digest-based skip (compare digests)

Deployment tagging ──> Digest-based skip (tag lookup)
                   ──> PR status reporting (deployed version)
```

**Critical path:** Webhook validation -> ferry.yaml parsing -> change detection -> workflow dispatch -> container build -> Lambda deploy. Everything else branches off this spine.

## Detailed Feature Analysis by Competitor

### Change Detection

| Product | How | Granularity | Notes |
|---------|-----|-------------|-------|
| **Digger** | File path matching in digger.yaml | Per Terraform project | Closest to Ferry's model |
| **SST** | Framework tracks constructs | Per construct | Automatic, no config needed |
| **Serverless Framework** | Package hash comparison | Per service | Only detects at deploy time |
| **SAM** | CloudFormation changeset | Per stack | Infrastructure-level, not file-level |
| **Seed.run** | Package fingerprinting | Per service | Incremental -- only deploys changed services |
| **Ferry** | Commit diff + ferry.yaml path mapping | Per resource | Git-native, pre-deploy detection. Posts affected resources to PR BEFORE deploy. |

**Ferry's edge:** Detection happens at PR time (pre-merge), not at deploy time. Users see what will deploy before they merge. No other serverless tool does this.

### Deployment Model

| Product | Build Where | Deploy How | Multi-resource |
|---------|-------------|------------|----------------|
| **Digger** | GHA runner | Terraform apply | Yes, per project |
| **SST** | Local/CI | CloudFormation | Yes, per stack |
| **Serverless Framework** | Local/CI | CloudFormation | Yes, per service |
| **SAM** | Local/CI | CloudFormation | Yes, per stack |
| **Seed.run** | Seed's infra | CloudFormation | Yes, per service |
| **Ferry** | GHA runner | Direct API calls | Yes, per resource type dispatch |

**Ferry's edge:** Direct API calls (no CloudFormation) means deploys are FAST. Updating a Lambda image via API takes 5-10 seconds. CloudFormation stack updates take 1-5 minutes.

### Status Reporting

| Product | Where | What |
|---------|-------|------|
| **Digger** | PR comment + Check | Terraform plan output |
| **SST** | Console (web) | Stack status, resource list |
| **Serverless Framework** | Dashboard (web) | Deploy history, alerts |
| **SAM** | CLI output | Stack events |
| **Seed.run** | Web console | Build/deploy logs, alerts |
| **ArgoCD** | Web UI + K8s status | Sync status, health, diff |
| **Ferry** | PR check + GHA logs | Affected resources, build/deploy status |

**Ferry's edge:** Everything in GitHub. No second tool, no separate login, no context switching.

## MVP Recommendation

**Phase 1 -- Core pipeline (must ship together):**
1. Webhook validation + dedup (table stakes, low complexity)
2. ferry.yaml parsing (foundation for everything)
3. Change detection via commit diff (table stakes, medium complexity)
4. Workflow dispatch triggering (core mechanism)
5. PR status check -- affected resources preview (differentiator, medium complexity)

**Phase 2 -- Build and deploy (must ship together):**
1. Magic Dockerfile container build (differentiator, already designed)
2. ECR push with deployment tagging (table stakes, low complexity)
3. Lambda deployment (table stakes, medium complexity)
4. Step Function deployment (table stakes, low complexity)
5. API Gateway deployment (table stakes, low complexity)
6. OIDC authentication in Ferry Action (table stakes, low complexity)

**Phase 3 -- Polish:**
1. Digest-based deploy skip (differentiator, medium complexity)
2. Error reporting improvements (table stakes, low complexity)
3. Build caching optimization (performance, medium complexity)

**Defer to v2:**
- Environment/branch mapping
- Multi-account deployment
- Drift detection
- Approval gates / deployment policies

## Confidence Notes

| Finding | Confidence | Reason |
|---------|------------|--------|
| Competitor feature sets | MEDIUM | Based on training data (up to early 2025). SST Ion, Serverless v4 may have added features since. |
| Change detection as table stakes | HIGH | Universal across all products studied. Fundamental to multi-resource repos. |
| PR preview as differentiator | HIGH | Verified no serverless code deploy tool does this (Digger does for IaC plans, not code). |
| Magic Dockerfile as differentiator | HIGH | No competitor offers a single Dockerfile for all functions. SAM/SST/Serverless all require per-function build config. |
| Direct API deploys being faster than CloudFormation | HIGH | Well-established. CloudFormation overhead is a known pain point. |
| Anti-rollback stance | MEDIUM | Reasonable for v1 but some users will push back. Git-based rollback is defensible. |
| Dashboard as anti-feature | MEDIUM | Bold stance. Seed.run and SST Console users value dashboards. But GitHub-native is a valid positioning choice. |

## Sources

- Digger architecture and GitHub App model (training data, docs.digger.dev)
- SST Ion documentation and Console features (training data, sst.dev)
- Serverless Framework v4 and Dashboard (training data, serverless.com)
- AWS SAM CLI and documentation (training data, docs.aws.amazon.com)
- Seed.run feature set and pricing (training data, seed.run)
- ArgoCD GitOps patterns (training data, argo-cd.readthedocs.io)
- ConvergeBio/pipelines-hub reference implementation (project memory)

**Note:** Web search and verification tools were unavailable during this research session. All competitor analysis is based on training data (cutoff early 2025). Recommend verifying SST Ion and Serverless Framework v4 feature sets before finalizing roadmap, as these products evolve quickly.
