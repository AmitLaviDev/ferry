---
phase: 01-foundation-and-shared-contract
verified: 2026-02-22T20:00:00Z
status: passed
score: 4/4 success criteria verified
re_verification: false
---

# Phase 1: Foundation and Shared Contract Verification Report

**Phase Goal:** Both components (App and Action) can be developed independently against a shared, validated data contract, with the webhook receiver accepting and deduplicating GitHub events
**Verified:** 2026-02-22T20:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A GitHub push webhook sent to the Ferry App endpoint is validated (HMAC-SHA256) and returns 200; tampered request rejected with 401 | VERIFIED | `signature.py` uses `hmac.compare_digest`; `handler.py` returns 401 on failure; 5 signature tests + 7 handler tests all pass |
| 2 | Sending the same webhook delivery twice results in exactly one processing — duplicate returns 200 but is not processed again | VERIFIED | `dedup.py` implements dual-key DynamoDB conditional write; handler returns `{"status": "duplicate"}` on repeat; 6 dedup tests all pass |
| 3 | Ferry App can generate a valid GitHub App JWT and exchange it for a scoped installation token | VERIFIED | `jwt.py` generates RS256 JWT with correct iss/iat/exp claims; `tokens.py` POSTs to `/app/installations/{id}/access_tokens` with scoped permissions; 8 JWT tests + 13 token tests all pass |
| 4 | Monorepo contains three packages managed by uv workspace, with shared Pydantic models importable by both app and action | VERIFIED | `pyproject.toml` has `[tool.uv.workspace] members = ["utils", "backend", "action"]`; `ferry_utils` declared as `{ workspace = true }` in both `backend/pyproject.toml` and `action/pyproject.toml`; `uv run python -c "import ferry_utils; import ferry_backend; import ferry_action"` exits 0; 25 model validation tests pass |

**Score:** 4/4 truths verified

---

### Required Artifacts

All artifacts verified at all three levels: exists, substantive, wired.

| Artifact | Provides | Level 1: Exists | Level 2: Substantive | Level 3: Wired | Status |
|----------|----------|-----------------|----------------------|----------------|--------|
| `pyproject.toml` | Workspace root with uv workspace config | PRESENT | Contains `[tool.uv.workspace]` with 3 members, full dev deps, ruff/mypy/pytest config | Used by uv directly | VERIFIED |
| `utils/src/ferry_utils/models/dispatch.py` | DispatchPayload with discriminated union | PRESENT | `DispatchPayload`, `LambdaResource`, `StepFunctionResource`, `ApiGatewayResource`, `Resource` annotated union with discriminator | Imported by `ferry_utils/__init__.py`; re-exported for both backend and action | VERIFIED |
| `utils/src/ferry_utils/models/webhook.py` | PushEvent and webhook header models | PRESENT | `PushEvent`, `WebhookHeaders`, `Repository`, `Pusher` — all frozen Pydantic models | Imported by `ferry_utils/models/__init__.py`; re-exported from package root | VERIFIED |
| `backend/src/ferry_backend/settings.py` | pydantic-settings config loading FERRY_* env vars | PRESENT | `Settings(BaseSettings)` with `env_prefix="FERRY_"`, 6 fields, private_key whitespace validator | Used at module level in `handler.py` via `settings = Settings()` | VERIFIED |
| `backend/src/ferry_backend/webhook/signature.py` | HMAC-SHA256 webhook signature validation | PRESENT | `verify_signature` using `hmac.new` + `hmac.compare_digest`, sha256 prefix check, utf-8 encoding | Called in `handler.py` at line 57 | VERIFIED |
| `backend/src/ferry_backend/webhook/dedup.py` | DynamoDB dual-key deduplication | PRESENT | `is_duplicate` with delivery-level + event-level keys, `_try_record` with `ConditionExpression="attribute_not_exists(pk)"`, 24h TTL | Called in `handler.py` at line 88 | VERIFIED |
| `backend/src/ferry_backend/webhook/handler.py` | Lambda Function URL entry point | PRESENT | Full handler: base64 decode, header normalization, signature validation, delivery ID check, event type filter, dedup, structured logging | Entry point wired to `verify_signature` and `is_duplicate` | VERIFIED |
| `backend/src/ferry_backend/auth/jwt.py` | GitHub App JWT generation with RS256 | PRESENT | `generate_app_jwt` with `iat-60`, `exp+540`, RS256 via PyJWT | Tested by 8 tests; available for import in token exchange flow | VERIFIED |
| `backend/src/ferry_backend/auth/tokens.py` | Installation token exchange | PRESENT | `get_installation_token` POSTs to `/app/installations/{id}/access_tokens` with scoped permissions dict; raises `GitHubAuthError` on 401/404 | Calls `client.post(...)` on `GitHubClient` | VERIFIED |
| `backend/src/ferry_backend/github/client.py` | Thin httpx wrapper for GitHub API | PRESENT | `GitHubClient` with `app_auth`, `installation_auth`, `get`, `post`; adds standard GitHub headers; ~90 lines | Used by `tokens.py` via `client.post` | VERIFIED |
| `tests/test_backend/test_signature.py` | Signature validation tests | PRESENT | 5 tests: valid, tampered body, missing, no prefix, wrong secret | All 5 pass | VERIFIED |
| `tests/test_backend/test_dedup.py` | Dedup tests with moto DynamoDB | PRESENT | 6 tests: first delivery, same delivery ID, re-queued event, missing fields, different repo, TTL | All 6 pass | VERIFIED |
| `tests/test_backend/test_handler.py` | Integration test for full handler flow | PRESENT | 7 tests: accepted, duplicate, invalid sig, missing sig, non-push, base64 body, missing delivery header | All 7 pass | VERIFIED |
| `tests/test_backend/test_jwt.py` | JWT generation tests | PRESENT | 8 tests: string return, RS256 algorithm, iss claim, iat backdated 60s, exp at 9 min, decodable with public key, invalid key error, different app IDs | All 8 pass | VERIFIED |
| `tests/test_backend/test_tokens.py` | Token exchange tests with httpx mocking | PRESENT | 13 tests: client auth headers, URL construction, token exchange endpoint, permissions, error handling | All 13 pass | VERIFIED |

---

### Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|-----|--------|----------|
| `backend/pyproject.toml` | `utils/pyproject.toml` | workspace dependency | WIRED | `ferry-utils = { workspace = true }` at line 16 |
| `action/pyproject.toml` | `utils/pyproject.toml` | workspace dependency | WIRED | `ferry-utils = { workspace = true }` at line 10 |
| `webhook/handler.py` | `webhook/signature.py` | import and call verify_signature | WIRED | `from ferry_backend.webhook.signature import verify_signature` (line 19); called at line 57 |
| `webhook/handler.py` | `webhook/dedup.py` | import and call is_duplicate | WIRED | `from ferry_backend.webhook.dedup import is_duplicate` (line 18); called at line 88 |
| `webhook/dedup.py` | DynamoDB | boto3 put_item with ConditionExpression | WIRED | `ConditionExpression="attribute_not_exists(pk)"` at line 74 |
| `auth/tokens.py` | `github/client.py` | uses GitHubClient for API calls | WIRED | `resp = client.post(...)` at line 41 |
| `auth/jwt.py` | PyJWT library | jwt.encode with RS256 | WIRED | `pyjwt.encode(payload, private_key, algorithm="RS256")` at line 33 |
| `auth/tokens.py` | GitHub App installations API | POST /app/installations/{id}/access_tokens | WIRED | `f"/app/installations/{installation_id}/access_tokens"` at line 42 |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| WHOOK-01 | 01-02-PLAN.md | Ferry App validates webhook signature (HMAC-SHA256) against raw body bytes before any JSON parsing | SATISFIED | `signature.py` uses `hmac.new`+`hmac.compare_digest`; `handler.py` validates signature before `json.loads`; 5 signature tests pass |
| WHOOK-02 | 01-02-PLAN.md | Ferry App deduplicates webhook deliveries via DynamoDB conditional write (delivery ID + event content composite key) | SATISFIED | `dedup.py` implements `DELIVERY#{id}` + `EVENT#push#{repo}#{sha}` dual-key dedup with `attribute_not_exists` conditional write; 6 dedup tests pass |
| AUTH-01 | 01-03-PLAN.md | Ferry App authenticates as GitHub App (JWT generation + installation token exchange) to read repos and trigger dispatches | SATISFIED | `jwt.py` generates RS256 JWT (iss/iat-60/exp+540); `tokens.py` exchanges JWT for scoped installation token; 21 auth tests pass |
| ACT-02 | 01-01-PLAN.md | Ferry Action, Ferry App, and shared models live in one monorepo managed by uv workspace | SATISFIED | Root `pyproject.toml` has `[tool.uv.workspace] members = ["utils", "backend", "action"]`; all packages cross-importable |

**No orphaned requirements.** REQUIREMENTS.md maps WHOOK-01, WHOOK-02, AUTH-01, and ACT-02 to Phase 1 — all four are claimed in plan frontmatter and verified above.

---

### Anti-Patterns Found

None found. No TODOs, FIXMEs, placeholder returns, or empty implementations in any source file.

Note: The comment `# 8. Phase 1 stub: accept and return` in `handler.py` is accurate documentation of intentional design scope (Phase 2 adds dispatch logic). The handler correctly performs all Phase 1 behaviors — signature validation, dedup, structured logging, and HTTP responses — before returning `{"status": "accepted"}`. This is not a stub; it is the complete Phase 1 behavior for accepted events.

---

### Human Verification Required

None. All behaviors are fully verifiable programmatically:
- Signature validation: verified by test suite
- Dedup logic: verified by moto-backed test suite
- JWT claims: verified by decode-with-public-key tests
- Package imports: verified by direct Python invocation
- Lint: verified by ruff

---

### Verification Summary

Phase 1 goal is fully achieved. All four Success Criteria from ROADMAP.md are verified:

1. Webhook signature validation is implemented with HMAC-SHA256 constant-time comparison, rejecting tampered requests before any JSON parsing.
2. DynamoDB dual-key deduplication catches both direct GitHub retries (same delivery ID) and re-queued events (new delivery ID, same repo+SHA). The handler correctly returns `{"status": "duplicate"}` without re-processing.
3. GitHub App authentication is complete: RS256 JWT generation with correct iss/iat/exp claims and installation token exchange posting scoped permissions to the correct GitHub API endpoint.
4. The uv workspace monorepo with three packages (ferry-utils, ferry-backend, ferry-action) is working. ferry-utils is a workspace dependency in both backend and action packages. Shared Pydantic models (DispatchPayload with discriminated union, PushEvent, WebhookHeaders) are importable from both components.

Full test suite: **64 tests, 0 failures, 0 lint errors.**

---

_Verified: 2026-02-22T20:00:00Z_
_Verifier: Claude (gsd-verifier)_
