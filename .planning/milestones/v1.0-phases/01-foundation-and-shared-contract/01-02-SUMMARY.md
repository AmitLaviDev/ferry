---
phase: 01-foundation-and-shared-contract
plan: 02
subsystem: webhook
tags: [hmac-sha256, dynamodb, dedup, lambda-handler, webhook, moto, tdd]

# Dependency graph
requires:
  - phase: 01-foundation-and-shared-contract
    provides: "uv workspace, Settings class, structlog logging, DynamoDB test fixture"
provides:
  - "HMAC-SHA256 webhook signature validation (verify_signature)"
  - "DynamoDB dual-key deduplication: delivery-level + event-level (is_duplicate)"
  - "Lambda Function URL webhook handler wiring signature + dedup + event parsing"
  - "18 tests: 5 signature, 6 dedup, 7 handler integration"
affects: [01-03, 02-app-core, 05-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [hmac-constant-time-comparison, dynamodb-conditional-write-dedup, lambda-function-url-handler, base64-body-decoding, header-normalization, structlog-contextvars]

key-files:
  created:
    - backend/src/ferry_backend/webhook/signature.py
    - backend/src/ferry_backend/webhook/dedup.py
    - backend/src/ferry_backend/webhook/handler.py
    - tests/test_backend/test_signature.py
    - tests/test_backend/test_dedup.py
    - tests/test_backend/test_handler.py
  modified: []

key-decisions:
  - "DynamoDB client injected as parameter to is_duplicate for testability with moto (not module-level)"
  - "Handler returns _response helper for consistent Lambda Function URL format"
  - "Signature validation happens before delivery ID check (reject invalid requests as early as possible)"
  - "Dedup tests use local fixture instead of conftest.py fixture for isolation"

patterns-established:
  - "TDD red-green-refactor: failing test committed before implementation for each feature"
  - "DynamoDB dual-key dedup: DELIVERY#{id} for retries, EVENT#push#{repo}#{sha} for re-queued events"
  - "Lambda Function URL response: {statusCode, headers, body} with JSON Content-Type"
  - "Header normalization: lowercase all headers immediately on entry"
  - "Module-level Settings + DynamoDB client for Lambda cold start optimization"

requirements-completed: [WHOOK-01, WHOOK-02]

# Metrics
duration: 4min
completed: 2026-02-22
---

# Phase 1 Plan 2: Webhook Receiver Summary

**Lambda webhook handler with HMAC-SHA256 signature validation and DynamoDB dual-key deduplication (delivery-level + event-level), all TDD with 18 tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-22T19:46:53Z
- **Completed:** 2026-02-22T19:50:41Z
- **Tasks:** 3 features (6 TDD phases + 1 lint fix)
- **Files modified:** 6

## Accomplishments
- HMAC-SHA256 webhook signature validation using stdlib hmac + hashlib with constant-time comparison
- DynamoDB dual-key deduplication catching both GitHub retries (same delivery ID) and re-queued events (new delivery ID, same repo+SHA)
- Lambda Function URL handler wiring signature validation, dedup, and push event filtering with structured logging
- Full TDD discipline: all 3 features started with failing tests before implementation

## Task Commits

Each TDD feature committed as test (RED) then implementation (GREEN):

1. **Feature 1 RED: Signature validation tests** - `1b09a92` (test)
2. **Feature 1 GREEN: Signature validation implementation** - `ba10dc6` (feat)
3. **Feature 2 RED: Dedup tests** - `2995d3e` (test)
4. **Feature 2 GREEN: Dedup implementation** - `872573a` (feat)
5. **Feature 3 RED: Handler integration tests** - `eb5eba5` (test)
6. **Feature 3 GREEN: Handler implementation** - `1ba5469` (feat)
7. **Lint fixes** - `c1ab335` (fix)

## Files Created/Modified
- `backend/src/ferry_backend/webhook/signature.py` - HMAC-SHA256 verify_signature with constant-time comparison
- `backend/src/ferry_backend/webhook/dedup.py` - DynamoDB dual-key dedup (delivery-level + event-level)
- `backend/src/ferry_backend/webhook/handler.py` - Lambda Function URL handler wiring signature + dedup + event parsing
- `tests/test_backend/test_signature.py` - 5 tests: valid, tampered, missing, no prefix, wrong secret
- `tests/test_backend/test_dedup.py` - 6 tests: first delivery, same ID, re-queued, missing fields, different event, TTL
- `tests/test_backend/test_handler.py` - 7 tests: accepted, duplicate, invalid sig, missing sig, non-push, base64, missing delivery

## Decisions Made
- DynamoDB client injected as parameter to `is_duplicate` for testability with moto (module-level client in handler for production Lambda cold start optimization)
- Signature validation happens before delivery ID check -- reject invalid requests as early as possible
- Handler tests use local DynamoDB fixture (not shared conftest.py) for test isolation
- `_response()` helper in handler for consistent Lambda Function URL response format

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff lint errors in dedup.py and test_handler.py**
- **Found during:** Verification (post all features)
- **Issue:** SIM103 (simplifiable return) in dedup.py, F401 (unused import os) in test_handler.py
- **Fix:** Simplified return expression with `bool()`, removed unused `import os`
- **Files modified:** `backend/src/ferry_backend/webhook/dedup.py`, `tests/test_backend/test_handler.py`
- **Verification:** `ruff check` passes on all plan files, all 18 tests still pass
- **Committed in:** `c1ab335`

---

**Total deviations:** 1 auto-fixed (lint cleanup)
**Impact on plan:** Trivial formatting fix. No scope creep.

**Out-of-scope lint issues:** Pre-existing lint errors in `backend/src/ferry_backend/github/client.py`, `tests/test_backend/test_jwt.py`, `tests/test_backend/test_tokens.py` (from Plan 01-03) were not fixed per scope boundary rules.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Webhook handler complete and tested, ready for Phase 2 to add config reading, change detection, and dispatch after the "accepted" response point
- Signature validation module ready for use by any webhook endpoint
- Dedup module accepts any DynamoDB client, ready for integration testing
- Handler follows Phase 1 push-only filter; Phase 2 refactors to router pattern for PR events

## Self-Check: PASSED

All 7 created files verified present. All 7 commits (1b09a92, ba10dc6, 2995d3e, 872573a, eb5eba5, 1ba5469, c1ab335) verified in git log.

---
*Phase: 01-foundation-and-shared-contract*
*Completed: 2026-02-22*
