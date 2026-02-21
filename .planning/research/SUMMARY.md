# Project Research Summary

**Project:** Ferry
**Domain:** GitHub App + GitHub Action serverless AWS deployment automation
**Researched:** 2026-02-21
**Confidence:** MEDIUM-HIGH

## Executive Summary

Ferry is a GitOps deployment tool for serverless AWS infrastructure — Lambda functions, Step Functions, and API Gateways — following the "thin backend orchestrator + GHA runner executor" model pioneered by Digger for Terraform. The architecture is deliberately split: a Ferry App (1-2 AWS Lambdas + DynamoDB) receives GitHub webhooks, reads `ferry.yaml` to detect which resources changed, and triggers `workflow_dispatch` on the user's GitHub Actions workflow. The Ferry Action (composite GHA action) then runs in the user's own runner, handling OIDC auth, Docker builds via the Magic Dockerfile, ECR pushes, and direct AWS API deployments. This means Ferry never touches the user's AWS account directly — the user's runner, the user's credentials, the user's compute.

The recommended approach centers on three decisive choices validated by research. First, use a composite GHA action (not Docker), because the Magic Dockerfile requires host Docker daemon access that Docker-in-Docker cannot reliably provide. Second, call GitHub's six required API endpoints directly via a thin `GitHubClient` wrapper around httpx, rather than any GitHub SDK — the endpoints are well-understood and a ~150-line wrapper gives full control with zero dependency overhead. Third, deploy Lambda/StepFunctions/APIGateway via direct boto3 calls instead of third-party GHA actions, enabling custom digest-based skip logic and eliminating supply-chain risk. The shared Pydantic models package (`ferry-shared`) is the contract between App and Action — defining the dispatch payload schema that both sides must agree on from day one, and enabling parallel development of the two components.

The top risks are operational, not architectural. Webhook delivery is not guaranteed — GitHub's 10-second response timeout and at-least-once delivery semantics mean a slow Lambda or a GitHub infra hiccup silently drops a deploy with no visible indication. `workflow_dispatch` returns `204 No Content` before verifying the workflow actually ran, creating a fire-and-forget gap. Lambda deployment races (two rapid pushes to the same function) require GHA concurrency groups and `RevisionId` optimistic locking. These pitfalls have clear mitigations and must be designed in from the start, not retrofitted.

## Key Findings

### Recommended Stack

The stack is entirely settled on established, low-risk libraries. The Ferry App Lambda is pure Python 3.14 with Pydantic v2 (data contracts), PyJWT+cryptography (GitHub App auth), httpx (GitHub API calls), PyYAML (ferry.yaml parsing), boto3 (DynamoDB), structlog (structured logging), and tenacity (retry logic). The Ferry Action shares most of these libraries and uses boto3 for AWS deployments. A `ferry-shared` package contains only Pydantic and PyYAML — the minimal surface for shared models. The uv workspace manages all three packages in a monorepo. Ferry's own backend infrastructure is defined in a SAM template (~50 lines): Lambda + Function URL + DynamoDB, all in one deployable unit.

**Core technologies:**
- **Python 3.14 + uv workspace**: Runtime and package manager — already decided; uv workspace supports the three-package monorepo cleanly
- **Pydantic v2**: Data contracts between App and Action — the dispatch payload schema is the architectural spine; Pydantic defines it with type safety and validation
- **httpx (direct API calls)**: Six GitHub endpoints — a ~150-line `GitHubClient` wrapper gives full control with zero SDK overhead
- **PyJWT + cryptography**: GitHub App auth — RS256 JWT generation in ~5 lines; installation token exchange in ~10 lines
- **boto3 (direct calls)**: All AWS operations — Lambda/SFN/APIGW deployment logic is 10-25 lines per resource type; no third-party deploy actions
- **Composite GHA action**: Action type — mandatory because the Magic Dockerfile needs host Docker daemon; Docker-in-Docker is not viable on standard runners
- **AWS SAM**: Ferry's own backend infrastructure — Lambda + Function URL + DynamoDB in ~50 lines; simpler than CDK or Terraform for two resources
- **moto + pytest-httpx**: Testing — mock all AWS services and GitHub API calls; enables full unit testing without real credentials

**Version verification needed before implementation:** Python 3.14 Lambda runtime availability (may require container-based Lambda, not zip deployment), moto Python 3.14 compatibility, and the exact buildx version on ubuntu-latest runners (affects Magic Dockerfile glob behavior).

### Expected Features

Research across Digger, SST, Serverless Framework, SAM, Seed.run, and ArgoCD establishes what Ferry must do to feel complete and where it can genuinely differentiate.

**Must have (table stakes):**
- **Change detection** — every competitor does this; deploying all resources on every push is unacceptable for multi-resource repos
- **Container/artifact build** — users expect the tool to handle building; the Magic Dockerfile IS the build
- **Multi-resource deployment** — one push often changes multiple Lambdas; manual per-resource deployment is what Ferry replaces
- **PR status reporting** — users need to know what will deploy before merging; GitHub Checks API is the primary UI since Ferry has no dashboard
- **Webhook signature validation** — security baseline; HMAC-SHA256 against raw body bytes, constant-time compare
- **Idempotent delivery** — DynamoDB dedup on delivery ID plus event-content composite key
- **OIDC authentication** — storing AWS credentials as GitHub Secrets is the 2020 way; OIDC federation is table stakes in 2026
- **Deployment tagging** — ECR images and Lambda versions tagged with git SHA for "which commit is running" traceability
- **Clear error reporting** — surface build/deploy failures in GHA output and PR status; no hunting through CloudWatch

**Should have (differentiators):**
- **Magic Dockerfile (zero-config builds)** — one Dockerfile for all Lambdas; no competitor does this; the single biggest UX differentiator
- **GitOps for code, not IaC** — Ferry deploys code to existing infrastructure; IaC creates resources; a clean separation that SAM/SST/Serverless conflate
- **PR preview of affected resources** — before merge, show exactly which Lambda/SFN/APIGW will deploy; Digger does this for Terraform; no serverless code-deploy tool does this
- **Digest-based deploy skip** — if the built image digest matches the deployed image, skip deployment; saves time and avoids unnecessary cold starts
- **Resource-type-aware dispatching** — one dispatch per type (Lambda/SFN/APIGW); different build/deploy logic per type; cleaner than monolithic dispatch

**Defer (v2+):**
- Environment/branch mapping (main=prod, develop=staging) — Digger's most complex feature; out of scope for v1
- Multi-account deployment — requires promotion logic and approval gates
- Automatic rollback — cross-resource rollback is an unsolved problem for serverless; git revert is the v1 answer
- Drift detection — out of scope; process problem not a tooling problem
- Web dashboard — the PR is the dashboard; avoid the investment Digger and SST made
- Plugin/extension system — caused Serverless Framework's maintenance nightmare; first-class resource types instead

### Architecture Approach

Ferry follows the Digger model: thin stateless backend for decision-making, user's GHA runner for execution. The Ferry App Lambda handles webhook ingestion, validates HMAC-SHA256 signature against raw body bytes, deduplicates via DynamoDB conditional write, generates a fresh GitHub App JWT per request, exchanges it for a scoped installation token, fetches `ferry.yaml` at the exact pushed commit SHA (not branch HEAD), computes file diff via GitHub Compare API, matches changed paths against ferry.yaml resource definitions, triggers one `workflow_dispatch` per affected resource type, and posts a GitHub Check Run showing what will deploy. The entire cycle completes in ~700ms-1s — well within GitHub's 10-second webhook response window. The dispatch payload is a versioned JSON contract (7 string inputs) that fully specifies what the Action needs to build and deploy.

**Major components:**
1. **Ferry App Lambda** — webhook ingestion, GitHub App auth, ferry.yaml parsing, change detection, dispatch triggering, PR status checks; communicates with GitHub API and DynamoDB; stateless per-request
2. **DynamoDB Table (ferry-state)** — webhook dedup (delivery ID + event content composite key), optional state tracking; single-table design with TTL for auto-cleanup
3. **Ferry Action (composite)** — OIDC auth, Magic Dockerfile builds, ECR push, Lambda/StepFunctions/APIGateway deployment; runs in user's GHA runner with user's credentials; Ferry never accesses the user's AWS account directly
4. **ferry-shared package** — Pydantic models for ferry.yaml schema, dispatch payload, and webhook events; the versioned contract between App and Action; enables parallel development
5. **ferry.yaml** — source of truth for resource mappings (code directory to IaC resource to ECR repo name); read by App at pushed commit SHA via GitHub Contents API

### Critical Pitfalls

1. **Webhook delivery is not guaranteed** — GitHub's 10-second timeout and at-least-once semantics mean a slow cold start or GitHub infra issue silently drops a deploy; respond to GitHub quickly (within 1-2s, after dedup write), keep the Lambda lean, and implement periodic reconciliation against recent commits as a safety net
2. **workflow_dispatch is fire-and-forget** — the 204 response confirms GitHub accepted the request, not that a workflow run was created; poll for the run after dispatch (wait 5-10s, then check recent runs), track dispatch-to-run correlation in DynamoDB, build a watchdog that flags dispatches with no corresponding run after N minutes
3. **Lambda deployment races** — two rapid pushes trigger concurrent deploys to the same function; use GHA concurrency groups in queue mode (not cancel-in-progress) and `RevisionId` optimistic locking on `update-function-code`
4. **Lambda `update-function-code` is async** — the API returns before the update completes; calling `publish-version` immediately publishes old code; always wait for `LastUpdateStatus: Successful` using the `function_updated_v2` waiter before publishing
5. **OIDC role chain 1-hour cap** — chained `AssumeRole` sessions are hard-capped at 1 hour by AWS STS regardless of role `MaxSessionDuration`; design Ferry Action workflows to complete well under 60 minutes; prefer direct OIDC trust on the target account role to eliminate chaining overhead

## Implications for Roadmap

Based on the dependency graph in ARCHITECTURE.md and the phase-specific pitfall warnings in PITFALLS.md, research suggests a 5-phase structure. A critical insight: after Phase 1 establishes shared models, the App (Phase 2) and Action (Phases 3-4) can be developed in parallel because they communicate only through the dispatch payload contract.

### Phase 1: Foundation and Shared Contract

**Rationale:** The `ferry-shared` Pydantic models are the contract both sides must agree on before either side can be built confidently. Webhook infrastructure (HMAC validation, DynamoDB dedup) and GitHub App auth (JWT, installation tokens) are also foundational — no App logic works without them. Building these first unblocks parallel development.

**Delivers:** ferry-shared models (ferry.yaml schema, dispatch payload, webhook events), webhook receiver with HMAC-SHA256 validation, DynamoDB dedup module, GitHub App JWT generation and installation token exchange, SAM template skeleton (Lambda + Function URL + DynamoDB table)

**Addresses:** Webhook signature validation (table stakes), idempotent delivery (table stakes)

**Avoids:** Raw body HMAC pitfall (validate before JSON parse, use `hmac.compare_digest`), ConditionalCheckFailedException mishandling (catch explicitly, return 200), dedup key fragility (use delivery ID + `{repo}#{event_type}#{sha}` composite key, not delivery ID alone), JWT clock skew (`iat` backdated 60s, `exp` set to 9 minutes)

**Research flag:** Not needed — webhook HMAC, DynamoDB conditional writes, and GitHub App auth are all exhaustively documented stable patterns

### Phase 2: Core App Logic (Ferry Backend)

**Rationale:** With auth and models in place, the App's core loop can be built. This is the decision-making brain: read ferry.yaml from the pushed commit SHA, compute changed files via GitHub Compare API, match against resource definitions, trigger one workflow_dispatch per resource type, post Check Run showing what will deploy.

**Delivers:** ferry.yaml parser and Pydantic validator, change detection engine (diff + config matching), dispatch payload builder, workflow_dispatch trigger, PR Check Run (pending state showing affected resources), ferry.yaml cache by commit SHA in DynamoDB

**Addresses:** Change detection (table stakes), PR preview of affected resources (differentiator), PR status reporting (table stakes)

**Avoids:** Reading ferry.yaml from wrong ref (always use `after` SHA from push event, not branch HEAD), workflow_dispatch fire-and-forget (poll for run ID after dispatch, track in DynamoDB), rate limit pressure (cache ferry.yaml by commit SHA, batch Check Run updates, track `X-RateLimit-Remaining`), post-merge check invisibility (post pre-merge for preview; use PR comments for post-merge deployment results)

**Research flag:** Not needed — GitHub Compare API, Contents API, Checks API, and workflow_dispatch are all stable REST endpoints with clear documented semantics

### Phase 3: Ferry Action — Build and Lambda Deploy

**Rationale:** The Magic Dockerfile and Lambda deployment logic are independent of App Phases 1-2 and can be developed in parallel (both sides depend only on the ferry-shared models from Phase 1). This phase ports the pipelines-hub reference implementation into the composite action structure. Lambda is the most complex resource type: it requires Docker build + ECR push + async function update + version publish + alias update.

**Delivers:** action.yml composite action scaffolding, Magic Dockerfile port from pipelines-hub, ECR build+push with deployment tagging (git SHA, PR number), Lambda deployment (update-function-code + wait for `LastUpdateStatus: Successful` + publish-version + update-alias), OIDC auth integration (aws-actions/configure-aws-credentials + amazon-ecr-login), digest-based skip logic

**Addresses:** Container/artifact build (table stakes), Lambda deployment (table stakes), OIDC authentication (table stakes), deployment tagging (table stakes), digest-based deploy skip (differentiator)

**Avoids:** Docker action vs composite (composite is mandatory — need host Docker daemon for `docker build`), ECR auth mid-build expiry (re-authenticate immediately before each `docker push`, not once at workflow start), Lambda async update (wait for `LastUpdateStatus: Successful` before publishing), deployment races (GHA concurrency groups in queue mode + RevisionId optimistic locking), Magic Dockerfile glob trick fragility (pin buildx version, test with and without optional files in CI), OIDC 1-hour chain cap (design for sub-60-minute runs; document parallel build option for large batches), image size monitoring (warn at 5 GB, error at 10 GB)

**Research flag:** Needs validation — pin Docker/buildx version on ubuntu-latest runner and test Magic Dockerfile COPY glob behavior on that exact version; verify Python 3.14 container Lambda runtime availability before writing SAM template

### Phase 4: Ferry Action — Extended Resource Types

**Rationale:** Step Functions and API Gateway deployments share the OIDC auth foundation from Phase 3 but have distinct deployment logic and pitfalls. They are lower risk than Lambda (no Docker involved) but require careful handling of ASL envsubst fragility and API Gateway's destructive all-or-nothing overwrite behavior.

**Delivers:** Step Functions deployment (validate-state-machine-definition pre-flight + selective variable substitution + update-state-machine + preserve previous definition), API Gateway deployment (put-rest-api overwrite mode + mandatory create-deployment call)

**Addresses:** Step Functions deployment (table stakes), API Gateway deployment (table stakes)

**Avoids:** Step Functions envsubst over-replacement (selective substitution by explicit variable list, not blanket `envsubst`; JSONPath `$.variable` expressions must survive substitution), Step Function deploy-then-fail-at-runtime (use `validate-state-machine-definition` API before update), API Gateway endpoints disappearing (spec is single source of truth; never manually edit the console; always call `create-deployment` after `put-rest-api`)

**Research flag:** Verify `validate-state-machine-definition` API semantic coverage — does it catch invalid state references and incorrect resource ARNs, or only schema-level errors?

### Phase 5: Integration, Reliability, and Observability

**Rationale:** End-to-end integration testing requires both the App (Phases 1-2) and Action (Phases 3-4) to be complete. This phase also hardens the reliability gaps that cannot be validated until a full flow exists: the dispatch watchdog, webhook reconciliation, and post-deployment status reporting back to GitHub.

**Delivers:** End-to-end integration test against a real GitHub App installation, GitHub App registration with correct permissions, AWS infrastructure deployment via SAM (`sam build && sam deploy`), dispatch-to-run correlation tracking in DynamoDB, dispatch watchdog (scheduled check for dispatches with no corresponding run after N minutes), post-deployment Check Run update (success/failure), deployment results as PR comments on merged PRs

**Addresses:** Clear error reporting (table stakes), deployment result visibility (build/deploy success/failure surfaced in GitHub without CloudWatch hunting)

**Avoids:** Silent deploy drops (reconciliation: periodically compare DynamoDB delivery records against recent commits via GitHub API; flag gaps), invisible dispatch failures (watchdog that detects 204 responses that never spawned a workflow run)

**Research flag:** Needs hands-on validation — GitHub App registration requires navigating the App creation UI, configuring webhook URLs, setting permissions, and generating the private key; the exact required permission set should be verified against the full API call surface used by both App and Action

### Phase Ordering Rationale

- **Phase 1 must come first:** ferry-shared Pydantic models are the interface contract. Building them first allows Phases 2 and 3 to develop independently without integration risk.
- **Phases 2 and 3 can be parallel:** The App reads ferry.yaml and constructs a dispatch payload; the Action receives a dispatch payload and deploys. These are fully decoupled until Phase 5. Teams can split here.
- **Phase 4 after Phase 3:** Step Functions and API Gateway deploy on the same OIDC + composite action foundation as Lambda. Build Lambda first (most complex, most pitfalls), then extend the pattern.
- **Phase 5 last:** Integration and reliability hardening require a full working system. The dispatch watchdog and reconciliation mechanism are only meaningful once the happy path is validated.

### Research Flags

Phases needing deeper research during planning:
- **Phase 3:** Validate Magic Dockerfile COPY glob behavior against the exact BuildKit version on ubuntu-latest; verify Python 3.14 Lambda container runtime availability; confirm docker/build-push-action secret passing syntax for current version
- **Phase 4:** Verify `validate-state-machine-definition` API semantic coverage beyond JSON schema validation
- **Phase 5:** GitHub App registration is a manual multi-step process; verify required permission scopes against the actual API calls in Phases 1-4 before registering

Phases with standard patterns (skip research-phase):
- **Phase 1:** GitHub App HMAC webhook validation, DynamoDB conditional writes, and GitHub App JWT auth are exhaustively documented stable patterns
- **Phase 2:** GitHub Compare API, Contents API, Checks API, and workflow_dispatch are stable REST endpoints with clear semantics; no research needed

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Core library choices are settled and well-justified; version numbers need pre-implementation verification (especially Python 3.14 Lambda runtime and moto compatibility) |
| Features | HIGH | Table stakes and differentiators are well-established from competitive analysis; anti-feature list is opinionated but grounded in specific competitor failures |
| Architecture | HIGH | GitHub App auth flow, composite action constraint, and Digger model are all documented stable patterns; dispatch payload design is Ferry-specific but straightforward |
| Pitfalls | HIGH | GitHub webhook behavior, Lambda async updates, and OIDC chain cap are officially documented; envsubst selective substitution and Docker glob fragility are MEDIUM (observed behavior vs documented guarantee) |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Python 3.14 Lambda runtime:** As of early 2025 training data, AWS Lambda supported through Python 3.12/3.13. If 3.14 requires container-based Lambda deployment, the SAM template changes slightly but the architecture does not. Verify this before writing the template.
- **Magic Dockerfile BuildKit glob behavior:** The `COPY file.tx[t]` glob trick works in pipelines-hub but is an implementation detail, not a documented guarantee. Pin the buildx version and add an explicit CI test covering both "file present" and "file absent" paths before shipping.
- **Dispatch watchdog design:** The fire-and-forget pitfall requires a correlation mechanism between dispatches and workflow runs. The exact polling strategy (poll immediately after dispatch vs scheduled reconciliation Lambda) needs a design decision during Phase 2 planning — both are valid, with different latency/complexity tradeoffs.
- **GitHub App minimum permissions:** The required GitHub App permission set needs verification against the actual endpoints called. Requesting more permissions than needed will be scrutinized by users. Map each API call to its required permission before registering the App.
- **moto coverage for newer AWS features:** The Step Functions `validate-state-machine-definition` API may not be mocked in current moto. Verify before building the Phase 4 test suite; if not mocked, test with real AWS in integration tests.

## Sources

### Primary (HIGH confidence)
- GitHub Docs: Webhooks security, App authentication, REST API (training data — core behavior is stable and well-documented)
- GitHub Docs: workflow_dispatch API, composite actions vs Docker actions (training data — stable)
- AWS Docs: Lambda container images, STS AssumeRole session duration, ECR auth, DynamoDB conditional writes, Step Functions API, API Gateway REST API import (training data — stable)
- AWS SAM documentation (training data — stable)
- ConvergeBio/pipelines-hub reference implementation (project memory — first-party, HIGH confidence on patterns)
- Ferry project MEMORY.md and architecture decisions (first-party — HIGH confidence)

### Secondary (MEDIUM confidence)
- Digger open-source codebase architecture (training data — patterns are well-established but Digger may have evolved since training cutoff)
- SST Ion, Serverless Framework v4, Seed.run feature sets (training data — competitive landscape may have shifted)
- Python ecosystem library versions (training data — all version numbers need pre-implementation verification)
- BuildKit COPY glob behavior (observed from pipelines-hub reference — not a documented guarantee; behavior may vary by version)

### Tertiary (LOW confidence)
- GitHub webhook re-queue behavior with new delivery IDs during outages (observed behavior — not officially documented; drives the composite dedup key recommendation)
- Lambda SnapStart availability for Python runtime (training data — may have expanded since cutoff; check before assuming unavailable)

---
*Research completed: 2026-02-21*
*Ready for roadmap: yes*
