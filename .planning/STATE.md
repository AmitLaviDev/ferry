# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-21)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** Phase 7: Tech Debt Cleanup

## Current Position

Phase: 7 of 7 (Tech Debt Cleanup)
Plan: 2 of 3 in current phase
Status: In Progress
Last activity: 2026-02-27 -- Completed 07-02 (Workflow documentation)

Progress: [##########] 99%

## Performance Metrics

**Velocity:**
- Total plans completed: 14
- Average duration: 4min
- Total execution time: 0.96 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 3 | 12min | 4min |
| 02-app-core | 3 | 17min | 6min |
| 03-build-and-lambda-deploy | 3 | 8min | 2.7min |
| 04-extended-resource-types | 3 | 14min | 4.7min |
| 06-fix-lambda-function-name-pipeline | 1 | 4min | 4min |
| 07-tech-debt-cleanup | 1 | 3min | 3min |

**Recent Trend:**
- Last 5 plans: 6min, 3min, 5min, 4min, 3min
- Trend: stable

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
- 03-01: Default runtime python3.12 in matrix (dispatch payload intentionally lean, runtime is a build concern)
- 03-01: Each composite action installs ferry-action via uv (matrix jobs run on separate runners)
- 03-01: gha.py uses file-based GITHUB_OUTPUT with stdout fallback for local testing
- 03-02: Dockerfile path resolved relative to build.py module (Path(__file__).parent.parent.parent / Dockerfile)
- 03-02: ECR registry domain extracted from URI by splitting on first slash for docker login
- 03-02: Error handling with common failure hints (missing docker, bad requirements, ECR auth)
- 03-03: Fixture-based mock_aws instead of per-test decorator (avoids fixture-outside-mock-context issue)
- 03-03: Digest normalization strips URI prefix before comparison (handles both raw sha256: and full URI@sha256: formats)
- 03-03: Alias fallback: try update_alias first, catch ResourceNotFoundException, fall back to create_alias
- 04-01: Strict regex pattern for envsubst: only matches ${ACCOUNT_ID} and ${AWS_REGION}, safe for JSONPath
- 04-01: get_content_hash_tag handles both SF list-of-dicts and APIGW flat-dict tag formats via isinstance check
- 04-01: _MATRIX_BUILDERS dispatch dict pattern for type-based matrix construction in parse_payload
- 04-02: ARN constructed from STS GetCallerIdentity account_id + AWS_REGION env var + state_machine_name
- 04-02: update_state_machine called with publish=True and versionDescription for deployment traceability
- 04-02: Content-hash skip reads ferry:content-hash tag via list_tags_for_resource before deploying
- 04-03: pyyaml added to ferry-action deps for YAML spec parsing; moto[apigateway] added to dev deps
- 04-03: Canonical JSON (sort_keys=True, compact separators) for deterministic hashing regardless of input format
- 04-03: Moto requires x-amazon-apigateway-integration in spec for create_deployment; tests use valid integration specs
- 06-01: function_name added as required str (not Optional) on LambdaResource -- backend resolves defaults before constructing dispatch model
- 06-01: deploy.py uses os.environ.get with explicit fail-fast for INPUT_FUNCTION_NAME instead of bare KeyError
- 07-02: Workflow YAML examples use real action paths and real input names from composite action YAML files
- 07-02: Documentation structure: shared setup.md + one file per resource type in docs/ directory

### Pending Todos

None yet.

### Blockers/Concerns

- Research flag: Phase 3 needs validation of Magic Dockerfile COPY glob behavior on ubuntu-latest BuildKit version and Python 3.14 Lambda container runtime availability
- Research flag: Phase 4 needs verification of validate-state-machine-definition API semantic coverage
- Research flag: Phase 5 requires GitHub App registration (manual process) with correct permission scopes

## Session Continuity

Last session: 2026-02-27
Stopped at: Completed 07-02-PLAN.md (Workflow documentation)
Resume file: None
