# Phase 1: Foundation and Shared Contract - Context

**Gathered:** 2026-02-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Monorepo structure with uv workspace, shared Pydantic data contract (dispatch payload models, constants, enums, error types), webhook receiver (HMAC-SHA256 validation + DynamoDB deduplication), and GitHub App authentication (JWT + installation token). This is the foundation that Phases 2-5 build on. Only push event handling is implemented — PR events are Phase 2.

</domain>

<decisions>
## Implementation Decisions

### Dispatch payload contract
- Schema version field in the payload (e.g., `"v": 1`) — Action checks version and handles accordingly
- Minimal payload — only ORCH-02 required fields: resource_type, resources[], trigger_sha, deployment_tag, pr_number. Action fetches anything else it needs from GitHub/AWS
- Typed union (Pydantic discriminated union) for resource models — LambdaResource, StepFunctionResource, ApiGatewayResource as separate models with strong validation

### Webhook error behavior
- Push events only in Phase 1 — Phase 2 adds PR event routing
- Keep it minimal for Phase 1, refactor to router pattern when Phase 2 adds PR handlers

### Package boundaries (monorepo layout)
- `utils/` — shared Pydantic models, constants, enums, error types (the contract layer)
- `backend/` — Ferry App Lambda (webhook handler, GitHub API wrapper, orchestration)
- `action/` — Ferry Action composite action and Python scripts
- `iac/` — SAM templates and infrastructure definitions
- GitHub API wrapper lives in `backend/` only, not shared

### DynamoDB data model
- 24-hour TTL on dedup records — GitHub retries within hours, no need for longer retention

### Claude's Discretion
- Resource list structure within dispatch payload (flat vs grouped) — Claude picks what works best with per-type dispatch model
- uv workspace configuration — separate packages vs single package with directories
- Webhook error responses — security-minimal vs debugging-friendly (Claude picks standard approach)
- Internal logging strategy — structured JSON vs errors-only
- DynamoDB table design — single-table vs table-per-concern
- Dedup record metadata — minimal vs observability-rich
- Dedup key hashing strategy — full payload hash vs key fields only

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation-and-shared-contract*
*Context gathered: 2026-02-22*
