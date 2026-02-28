# Phase 10: Docs and Dead Code Cleanup - Context

**Gathered:** 2026-02-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix workflow documentation to include all necessary permissions and inputs for Check Run reporting (Phase 8 feature), and remove unused error classes. Pure doc fixes + dead code cleanup — no new capabilities.

</domain>

<decisions>
## Implementation Decisions

### Error class disposition
- Remove `BuildError` and `DeployError` entirely from `ferry_utils/errors.py`
- Full cleanup: remove class definitions, re-exports from `__init__.py`, and `__all__` entries
- Rationale: action scripts are terminal error handlers — no upstream caller differentiates `BuildError` vs `DeployError`. Errors are communicated via exit codes and GHA annotations, not exception types.

### Doc permission updates
- Add `checks: write` permission to all three workflow docs (`lambdas.md`, `step-functions.md`, `api-gateways.md`)
- Include explanatory comment on each permission line (per-line inline comments)
- Example style: `checks: write     # Check Run status reporting`

### Claude's Discretion
- Comment formatting: whether to convert existing block comments above permissions to inline, or blend styles — pick the cleanest approach
- Exact wording of inline permission comments

### Deploy action inputs in docs
- Add `trigger-sha` and `github-token` as active (uncommented) inputs to the Lambda deploy step in `docs/lambdas.md`
- Also add `github-token` to Step Functions and API Gateway deploy docs for consistency — all three deploy actions support Check Run reporting
- `github-token` uses `${{ github.token }}` (auto-granted), NOT a PAT — different from build's `github-token` which is for private repo deps

</decisions>

<specifics>
## Specific Ideas

- Per-line comments on permissions rather than block comments above — each permission self-documents its purpose
- `github-token` in deploy steps should clearly indicate it's for Check Run reporting (contrast with build step where it's for private repo deps)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-docs-and-dead-code-cleanup*
*Context gathered: 2026-02-28*
