# Phase 8: Error Surfacing and Failure Reporting - Context

**Gathered:** 2026-02-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Build and deploy failures are clearly surfaced to developers in PR status checks and GHA workflow logs. No silent failures, no need to check CloudWatch. Covers both backend errors (auth, config) and action errors (build, deploy). Does not add new deployment capabilities or change existing deploy logic.

</domain>

<decisions>
## Implementation Decisions

### Check Run presentation
- Resource-specific titles: e.g., "Ferry: my-api-lambda build failed"
- Summary body contains error message only — terse and scannable
- Check Runs created for both success and failure (not failure-only)
- Pre-merge vs post-merge Check Run relationship: Claude's discretion

### Log output format
- Use both GHA annotations (::error::) and structured log blocks — annotations for summary view, blocks for detail
- Step-by-step progress on success: show building, pushing, deploying, done
- Collapsible ::group:: sections per resource
- Explicit skip messages when deploy skipped due to unchanged image digest

### Error detail level
- AWS identifiers: partial masking — show last 4 of account ID, use logical names primarily
- Actionable hints for recognizable errors (e.g., "ECR repo not found — ensure repo exists in your IaC")
- Hints appear in GHA logs only, NOT in Check Run summary (keep PR view terse)
- Stack traces hidden by default, shown when debug flag/env var is set

### Backend error visibility
- Config errors (invalid ferry.yaml): surface as PR comment, not Check Run
- Auth errors (bad JWT, expired token): backend logs only — system-level, not developer-actionable
- Separate handling: config errors → PR-visible, auth errors → infra-visible

### Claude's Discretion
- Backend HTTP response format (structured JSON vs status codes)
- Backend logging format (structured JSON vs human-readable)
- Pre-merge vs post-merge Check Run relationship (separate vs update existing)
- Debug flag mechanism (env var name, enabling pattern)

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

*Phase: 08-error-surfacing*
*Context gathered: 2026-02-28*
