# Phase 17: End-to-End Loop Validation - Context

**Gathered:** 2026-03-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Prove the full push-to-deploy loop works reliably: a push to the test repo triggers Ferry, which detects changes, dispatches a workflow, builds the container, deploys the Lambda, and the deployed Lambda executes correctly. Fix all bugs encountered. Prove repeatability with multiple push types.

</domain>

<decisions>
## Implementation Decisions

### Validation approach
- Incremental step-by-step: verify each stage independently (webhook delivery → change detection → dispatch → build → deploy) and fix each before moving to the next
- Start with a pre-flight health check: curl the Function URL, check CloudWatch for recent logs, verify GitHub App installation — catch infra issues before blaming code
- Fix-and-self-deploy cycle only: always push fixes through the self-deploy pipeline (no manual `aws lambda update-function-code`). Slower per iteration but keeps Lambda in sync with code
- Proactively fix the known `find_open_prs` 403 bug before starting the E2E loop

### Bug fix workflow
- Primary diagnostics: CloudWatch logs first for webhook processing, change detection, and dispatch failures. GHA workflow logs for build/deploy failures
- No temporary debug logging: trust existing structured logging. If insufficient, improve the permanent logging as part of the fix
- One fix per commit: each bug gets its own atomic commit with a descriptive message (e.g., `fix: handle 403 in find_open_prs`)

### Repeatability proof
- Two successful pushes required to prove repeatability (matches E2E-09)
- Push 1: change handler code in `main.py` (e.g., v1 → v2 greeting) — proves functional code deploys end-to-end
- Push 2: change a dependency/config file like `requirements.txt` — proves non-handler changes also trigger rebuild and deploy
- Invoke the deployed Lambda after each successful deploy to verify the container works in production (matches E2E-07)
- Include a no-op test: push a change to a file outside the Lambda directory (e.g., README), verify Ferry receives the webhook but correctly skips dispatch

### Completion artifacts
- Validation report in `.planning/phases/17-*/` summarizing: steps executed, bugs found and fixed (with commit refs), final proof (invocation results), known limitations
- Include links to actual AWS resources: CloudWatch log groups, GHA run URLs, Lambda ARNs — makes the report a living reference
- Document known limitations: explicitly list what v1.2 proved and what it didn't (Step Functions, API Gateway, multi-resource ferry.yaml, etc.)
- Update setup runbook with inline fixes only — correct any incorrect steps or missing prerequisites found during validation, no new sections
- Do NOT close v1.2 milestone yet — leave open for follow-up fixes that may emerge

### Claude's Discretion
- Whether to use GitHub App webhook redeliver or real git pushes for early verification steps
- Exact order of incremental verification within the step-by-step approach
- What constitutes "sufficient" CloudWatch log evidence for each step

</decisions>

<specifics>
## Specific Ideas

- The two repeatability pushes should test different kinds of changes: core code (main.py handler) AND dependency/config (requirements.txt) — proving both trigger the full rebuild-deploy cycle
- The no-op push (non-Lambda file change) is an important negative test to include in the validation report

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 17-end-to-end-loop-validation*
*Context gathered: 2026-03-07*
