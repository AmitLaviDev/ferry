# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-21)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** Phase 2: App Core Logic

## Current Position

Phase: 2 of 5 (App Core Logic)
Plan: 3 of 3 in current phase
Status: Phase Complete
Last activity: 2026-02-24 -- Completed 02-03 (Dispatch & orchestration)

Progress: [########--] 80%

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: 5min
- Total execution time: 0.48 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 3 | 12min | 4min |
| 02-app-core | 3 | 17min | 6min |

**Recent Trend:**
- Last 5 plans: 4min, 4min, 3min, 5min, 9min
- Trend: stable (9min for complex orchestration plan with 100 tests)

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: 5 phases derived from requirements; Phases 2 and 3 can be developed in parallel (both depend only on Phase 1 shared contract)
- 01-01: Used `uv sync --all-packages` for workspace member installation; all Pydantic models frozen with ConfigDict(frozen=True)
- 01-01: Mixed resource types allowed at model layer; application logic enforces single-type-per-payload
- 01-02: DynamoDB client injected as parameter to is_duplicate for moto testability; module-level client in handler for Lambda cold start
- 01-02: Signature validation before delivery ID check (reject invalid requests earliest possible)
- 01-02: Dedup tests use local fixture for isolation instead of shared conftest.py
- 01-03: GitHubClient uses mutable _headers dict for auth switching (app_auth vs installation_auth)
- 01-03: get_installation_token takes GitHubClient (not raw httpx.Client) for consistent header management
- 01-03: TYPE_CHECKING import for GitHubClient in tokens.py to satisfy ruff TC001
- 02-01: object.__setattr__ for frozen model validator default (function_name defaults to name)
- 02-01: ConfigError wraps both HTTP errors and ValidationError for uniform fail-fast behavior
- 02-02: AffectedResource uses frozen dataclass (not Pydantic) with tuple[str, ...] for immutable changed_files
- 02-02: Trailing slash normalization on source_dir prevents partial-prefix false matches
- 02-02: detect_config_changes uses model_dump() dict comparison for field-level diffing
- 02-02: TYPE_CHECKING import for FerryConfig and GitHubClient to avoid circular imports
- 02-03: GitHubClient at module level for Lambda cold start; auth methods called per-invocation
- 02-03: Merge-base comparison (default_branch...head) for PR branches; before...after for default branch
- 02-03: find_open_prs used for both PR identification and merged-PR number lookup on default branch
- 02-03: Config diff triggered only when ferry.yaml is in changed_files list
- 02-03: Payload size check (65535) with skip-and-log-error behavior

### Pending Todos

None yet.

### Blockers/Concerns

- Research flag: Phase 3 needs validation of Magic Dockerfile COPY glob behavior on ubuntu-latest BuildKit version and Python 3.14 Lambda container runtime availability
- Research flag: Phase 4 needs verification of validate-state-machine-definition API semantic coverage
- Research flag: Phase 5 requires GitHub App registration (manual process) with correct permission scopes

## Session Continuity

Last session: 2026-02-24
Stopped at: Completed 02-03-PLAN.md (Dispatch & orchestration) -- Phase 2 complete
Resume file: None
