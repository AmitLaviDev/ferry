# Phase 7: Tech Debt Cleanup - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Resolve low-severity tech debt items identified by the milestone audit: inconsistent runtime defaults, missing workflow documentation, and incomplete SUMMARY frontmatter. Also wire runtime end-to-end through the dispatch pipeline, and perform a quick sweep for other trivial inconsistencies.

</domain>

<decisions>
## Implementation Decisions

### Workflow documentation
- Standalone `docs/` directory, not embedded in README
- One document per resource type (lambdas, step_functions, api_gateways) plus a shared page for common concepts
- Full setup guide with annotated copy-paste example workflow files (inline YAML comments explaining each field)
- Cover the naming convention (`ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`) and why it matters

### Runtime default resolution
- Canonical default: `python3.14`
- Wire runtime end-to-end: ferry.yaml `LambdaConfig.runtime` flows through dispatch payload to build action
- Default lives in `LambdaConfig` schema only (single source of truth) — `parse_payload.py` receives it from dispatch, no hardcoded fallback
- Documentation should explain the default is overridable at the workflow level

### SUMMARY frontmatter
- Backfill `requirements-completed` field in ALL existing SUMMARY.md files
- Cross-validate against VERIFICATION.md and REQUIREMENTS.md — fix any mismatches found
- Format for plans with no requirements: Claude's discretion (empty array or omit)

### Scope of cleanup
- Core: 3 audit items + runtime end-to-end wiring
- Quick sweep of entire codebase (production code, tests, docs) for trivial inconsistencies
- Fix trivial issues silently (one-liner fixes: stale comments, wrong defaults, mismatched types)
- Flag non-trivial issues that need design decisions

### Claude's Discretion
- How to handle SUMMARY files for plans that don't map to specific requirements (empty array vs omit)
- Organization of shared vs per-type documentation pages
- What counts as "trivial" vs "non-trivial" during the sweep
- Exact runtime wiring approach through dispatch models

</decisions>

<specifics>
## Specific Ideas

- "python3.14 but explain that it's overridable" — docs should make the override mechanism clear
- One doc per resource type with cross-references to shared content — not a monolithic guide
- Annotated examples: users should be able to copy-paste and understand every field

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-tech-debt-cleanup*
*Context gathered: 2026-02-27*
