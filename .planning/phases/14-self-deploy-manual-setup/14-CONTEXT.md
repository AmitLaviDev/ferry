# Phase 14: Self-Deploy + Manual Setup - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Ferry can deploy itself on every push to main, the GitHub App is registered and receiving webhooks, and anyone can reproduce the full setup from the runbook. Covers: backend Dockerfile, self-deploy GHA workflow, Secrets Manager resolution in settings.py, GitHub App registration, secrets population, and setup runbook.

Requirements: DEPLOY-01, DEPLOY-02, DEPLOY-03, SETUP-01, SETUP-02, SETUP-03

</domain>

<decisions>
## Implementation Decisions

### Self-deploy behavior
- Triggers on **every push to main** — no path filtering. Simple and predictable.
- **Fail loudly, no rollback** — workflow fails with red X, Lambda keeps running previous image, user investigates manually.
- **Run Ferry's own pytest suite before building** — test job runs first, build+deploy job depends on it passing.

### Secrets resolution in settings.py
- **Separate ARN env vars** — Lambda env vars like `FERRY_APP_ID_ARN`, `FERRY_PRIVATE_KEY_ARN`, `FERRY_WEBHOOK_SECRET_ARN` hold Secrets Manager ARNs. At cold start, settings.py resolves ARNs to actual values and populates the corresponding fields.
- **Only sensitive values from Secrets Manager** — `app_id`, `private_key`, `webhook_secret` resolved from SM. Non-secrets (`table_name`, `installation_id`, `log_level`) stay as plain `FERRY_*` env vars.
- **Individual secrets** — Three separate secrets already created by Phase 12: `ferry/github-app/app-id`, `ferry/github-app/private-key`, `ferry/github-app/webhook-secret`. One SM API call per secret at cold start.
- **Local dev uses plain env vars** — If `FERRY_*_ARN` vars are absent, settings.py uses `FERRY_*` values directly. SM resolution only activates when ARN vars are present. No LocalStack needed.

### Runbook scope & location
- Lives at **`docs/setup-runbook.md`**
- Audience: **us / future contributors** — assumes AWS access and Terraform familiarity, focuses on Ferry-specific steps and order.
- Scope: **Phase 14 manual steps only** — GitHub App registration, secrets population, triggering first deploy. Does not cover Phases 11-13 apply order.
- **Includes verification steps** at the end — curl the Function URL, send a test webhook from GitHub App settings, check CloudWatch logs.

### Claude's Discretion
- Backend Dockerfile structure (multi-stage, base image, layer caching)
- GHA workflow job structure and step ordering
- How settings.py internally organizes the SM resolution (validator, factory, etc.)
- Exact runbook formatting and section headers

</decisions>

<specifics>
## Specific Ideas

- Phase 12 already created the three individual Secrets Manager secrets at `ferry/github-app/{app-id,private-key,webhook-secret}` — implementation must align with these exact names.
- The existing `action/Dockerfile` is the "Magic Dockerfile" for user apps — the backend Dockerfile is a separate file for Ferry's own Lambda container.
- The placeholder image from Phase 11 (`iac/resources/placeholders/ecr_image/Dockerfile`) is what the Lambda currently runs — the self-deploy replaces it with the real backend.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 14-self-deploy-manual-setup*
*Context gathered: 2026-03-02*
