---
phase: 01-foundation-and-shared-contract
plan: 03
subsystem: auth
tags: [jwt, rs256, pyjwt, httpx, github-app, installation-token, tdd]

# Dependency graph
requires:
  - phase: 01-foundation-and-shared-contract
    provides: "uv workspace, ferry-utils errors (GitHubAuthError), backend package scaffolding"
provides:
  - "generate_app_jwt: RS256 JWT generation with correct iss/iat/exp claims"
  - "get_installation_token: JWT-to-installation-token exchange via GitHub API"
  - "GitHubClient: thin httpx wrapper with app_auth and installation_auth"
affects: [02-foundation, 03-build-deploy]

# Tech tracking
tech-stack:
  added: []
  patterns: [tdd-red-green-refactor, type-checking-imports, github-api-client-pattern]

key-files:
  created:
    - backend/src/ferry_backend/auth/jwt.py
    - backend/src/ferry_backend/auth/tokens.py
    - backend/src/ferry_backend/github/client.py
    - tests/test_backend/test_jwt.py
    - tests/test_backend/test_tokens.py
  modified: []

key-decisions:
  - "GitHubClient uses mutable _headers dict for auth switching (app_auth vs installation_auth)"
  - "get_installation_token takes GitHubClient (not raw httpx.Client) for consistent header management"
  - "TYPE_CHECKING import for GitHubClient in tokens.py to satisfy ruff TC001"

patterns-established:
  - "TDD red-green-refactor: failing test commit, then implementation commit per feature"
  - "GitHubClient auth pattern: call app_auth(jwt) or installation_auth(token) before API calls"
  - "GitHub API error handling: catch httpx.HTTPStatusError, wrap in GitHubAuthError with status detail"

requirements-completed: [AUTH-01]

# Metrics
duration: 4min
completed: 2026-02-22
---

# Phase 1 Plan 3: GitHub App Auth Summary

**RS256 JWT generation with PyJWT (iss/iat-60s/exp+540s claims) and installation token exchange via thin httpx GitHubClient wrapper, fully TDD**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-22T19:47:12Z
- **Completed:** 2026-02-22T19:51:18Z
- **Tasks:** 2 features (4 TDD commits: 2 RED + 2 GREEN)
- **Files modified:** 5

## Accomplishments
- GitHub App JWT generation produces valid RS256 tokens with correct claims (iss=app_id, iat backdated 60s, exp at 9 minutes)
- Installation token exchange calls correct GitHub API endpoint with scoped permissions (contents:read, checks:write, actions:write)
- Thin GitHubClient wrapper (~85 lines) provides authenticated get/post with standard GitHub headers
- 21 tests covering JWT generation (8) and token exchange + client (13), all passing with zero lint errors

## Task Commits

Each feature was committed via TDD red-green-refactor:

1. **Feature 1 RED: JWT generation tests** - `a5e9653` (test)
2. **Feature 1 GREEN: JWT generation implementation** - `7a6cca1` (feat)
3. **Feature 2 RED: Token exchange + client tests** - `918770c` (test)
4. **Feature 2 GREEN: Token exchange + client implementation** - `c5ce1a6` (feat)

_No REFACTOR commits needed -- implementations were clean and minimal._

## Files Created/Modified
- `backend/src/ferry_backend/auth/jwt.py` - generate_app_jwt(app_id, private_key) -> RS256 JWT string
- `backend/src/ferry_backend/auth/tokens.py` - get_installation_token(client, jwt, installation_id) -> token string
- `backend/src/ferry_backend/github/client.py` - GitHubClient with app_auth, installation_auth, get, post
- `tests/test_backend/test_jwt.py` - 8 tests: RS256 signing, claims, clock drift, invalid key
- `tests/test_backend/test_tokens.py` - 13 tests: client auth, headers, token exchange, error handling

## Decisions Made
- GitHubClient uses mutable `_headers` dict rather than per-request header merging -- simpler for the auth switching pattern (app JWT -> installation token within same webhook cycle)
- `get_installation_token` takes `GitHubClient` (not raw `httpx.Client`) to ensure standard GitHub headers are always present
- Used `TYPE_CHECKING` import for `GitHubClient` in `tokens.py` to satisfy ruff TC001 (type-checking-only imports)
- Used `from __future__ import annotations` for forward reference support in both client.py and tokens.py

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pytest-httpx URL mismatch in 404 test**
- **Found during:** Feature 2 GREEN phase (token exchange tests)
- **Issue:** Test mocked URL `/installations/00000/` but actual request used `/installations/0/` (Python int formatting)
- **Fix:** Changed test to use installation_id=99998 matching both mock URL and actual request
- **Files modified:** tests/test_backend/test_tokens.py
- **Verification:** All 13 tests pass
- **Committed in:** c5ce1a6 (Feature 2 GREEN commit)

**2. [Rule 1 - Bug] Fixed ruff lint errors in new files**
- **Found during:** Overall verification
- **Issue:** TC001 (type-checking import), UP037 (quoted type annotation), B017 (bare Exception), F401 (unused import), F841 (unused variables)
- **Fix:** Moved GitHubClient import to TYPE_CHECKING block, removed quotes from __enter__ return type, used specific PyJWT exception, removed unused imports and variables
- **Files modified:** backend/src/ferry_backend/auth/tokens.py, backend/src/ferry_backend/github/client.py, tests/test_backend/test_jwt.py, tests/test_backend/test_tokens.py
- **Verification:** `ruff check` passes on all modified files
- **Committed in:** c5ce1a6 (Feature 2 GREEN commit)

---

**Total deviations:** 2 auto-fixed (2 bugs/lint)
**Impact on plan:** Minor test and lint fixes. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- GitHub App auth module complete and tested: JWT generation + installation token exchange
- GitHubClient ready for use by Phase 2 (ferry.yaml reading, change detection, dispatch) and future phases
- Auth flow: generate_app_jwt -> client.app_auth(jwt) -> get_installation_token -> client.installation_auth(token) -> API calls
- All Phase 1 foundation is now in place (workspace, shared contract, webhook handler, dedup, auth)

## Self-Check: PASSED

All 5 created files verified present. All 4 commits (a5e9653, 7a6cca1, 918770c, c5ce1a6) verified in git log.

---
*Phase: 01-foundation-and-shared-contract*
*Completed: 2026-02-22*
