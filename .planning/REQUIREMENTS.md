# Requirements: Ferry

**Defined:** 2026-02-21
**Core Value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed — with full visibility on the PR before merge.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Webhook & Security

- [x] **WHOOK-01**: Ferry App validates webhook signature (HMAC-SHA256) against raw body bytes before any JSON parsing
- [x] **WHOOK-02**: Ferry App deduplicates webhook deliveries via DynamoDB conditional write (delivery ID + event content composite key)
- [ ] **WHOOK-03**: Build and deploy failures are surfaced in GitHub PR status checks and GHA workflow logs

### Configuration

- [x] **CONF-01**: Ferry App reads and validates ferry.yaml from user's repo at the pushed commit SHA via GitHub Contents API
- [x] **CONF-02**: ferry.yaml supports lambdas, step_functions, and api_gateways as top-level resource types with type-specific fields

### Change Detection

- [x] **DETECT-01**: Ferry App compares commit diff (via GitHub Compare API) against ferry.yaml path mappings to identify changed resources
- [ ] **DETECT-02**: Ferry App posts a GitHub Check Run on PRs showing which resources will be affected before merge

### Orchestration

- [ ] **ORCH-01**: Ferry App triggers one workflow_dispatch per affected resource type with a versioned payload contract
- [ ] **ORCH-02**: Dispatch payload includes resource type, resource list, trigger SHA, deployment tag, and PR number

### Authentication

- [x] **AUTH-01**: Ferry App authenticates as GitHub App (JWT generation + installation token exchange) to read repos and trigger dispatches
- [ ] **AUTH-02**: Ferry Action authenticates to AWS via OIDC (user provides role ARN as action input, action handles the exchange)

### Build

- [ ] **BUILD-01**: Ferry Action builds Lambda containers using the Magic Dockerfile pattern (one generic Dockerfile for all Lambda functions)
- [ ] **BUILD-02**: Magic Dockerfile supports configurable Python runtime versions via ferry.yaml (not hardcoded to one version)
- [ ] **BUILD-03**: Magic Dockerfile supports private GitHub repo dependencies via Docker build secrets (user provides token)
- [ ] **BUILD-04**: Magic Dockerfile handles optional system-requirements.txt and system-config.sh without failing when absent
- [ ] **BUILD-05**: Ferry Action pushes built images to pre-existing ECR repos with deployment tags (git SHA, PR number)

### Deploy

- [ ] **DEPLOY-01**: Ferry Action deploys Lambda functions (update-function-code, wait for LastUpdateStatus: Successful, publish version, update alias)
- [ ] **DEPLOY-02**: Ferry Action deploys Step Functions (update state machine definition with variable substitution for account ID and region)
- [ ] **DEPLOY-03**: Ferry Action deploys API Gateways (put-rest-api with OpenAPI spec, create-deployment to push to stage)
- [ ] **DEPLOY-04**: Ferry Action skips deployment when built image digest matches currently deployed image (digest-based skip)
- [ ] **DEPLOY-05**: Ferry Action tags deployments with git SHA and PR number for traceability

### Action Structure

- [ ] **ACT-01**: Ferry Action is a composite GitHub Action with Python scripts for build/deploy logic (not inline bash)
- [x] **ACT-02**: Ferry Action, Ferry App, and shared models live in one monorepo managed by uv workspace

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Environment Management

- **ENV-01**: Branch-to-environment mapping (main=prod, develop=staging)
- **ENV-02**: Environment-specific ferry.yaml overrides
- **ENV-03**: Promotion flow between environments with approval gates

### Multi-Account

- **MACCT-01**: Deploy to different AWS accounts per environment
- **MACCT-02**: Account-specific role ARN configuration in ferry.yaml

### Reliability

- **REL-01**: Dispatch watchdog (detect dispatches that never spawned a workflow run)
- **REL-02**: Reconciliation polling (compare DynamoDB delivery records against recent commits)

### Observability

- **OBS-01**: Deployment history tracking in DynamoDB (what was deployed, when, by which commit)
- **OBS-02**: Post-deployment Check Run updates (success/failure status after deploy completes)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Web dashboard | The PR is the dashboard. Avoid frontend/auth investment. |
| AI/automatic resource discovery | Explicit config (ferry.yaml) is more reliable and debuggable |
| Infrastructure provisioning | IaC (Terraform) creates resources. Ferry deploys code to existing resources. |
| Automatic rollback | Cross-resource rollback is unsolved for serverless. Git revert is the v1 answer. |
| SageMaker model deployment | Different workflow, not serverless compute |
| Multi-account AWS | Single target account per workflow run for v1 |
| RBAC / permissions | Relies on GitHub App installation permissions |
| SQS / async event processing | Process synchronously. Keep backend thin. |
| ECR repo creation | IaC creates ECR repos, Ferry pushes to them |
| Drift detection | Process problem, not a tooling problem for v1 |
| Local dev/testing | Ferry is a CI/CD tool, not a dev tool |
| Plugin/extension system | First-class resource types, not plugins |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| WHOOK-01 | Phase 1 | Complete |
| WHOOK-02 | Phase 1 | Complete |
| WHOOK-03 | Phase 5 | Pending |
| CONF-01 | Phase 2 | Complete |
| CONF-02 | Phase 2 | Complete |
| DETECT-01 | Phase 2 | Complete |
| DETECT-02 | Phase 2 | Pending |
| ORCH-01 | Phase 2 | Pending |
| ORCH-02 | Phase 2 | Pending |
| AUTH-01 | Phase 1 | Complete |
| AUTH-02 | Phase 3 | Pending |
| BUILD-01 | Phase 3 | Pending |
| BUILD-02 | Phase 3 | Pending |
| BUILD-03 | Phase 3 | Pending |
| BUILD-04 | Phase 3 | Pending |
| BUILD-05 | Phase 3 | Pending |
| DEPLOY-01 | Phase 3 | Pending |
| DEPLOY-02 | Phase 4 | Pending |
| DEPLOY-03 | Phase 4 | Pending |
| DEPLOY-04 | Phase 3 | Pending |
| DEPLOY-05 | Phase 3 | Pending |
| ACT-01 | Phase 3 | Pending |
| ACT-02 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

---
*Requirements defined: 2026-02-21*
*Last updated: 2026-02-21 after roadmap creation*
