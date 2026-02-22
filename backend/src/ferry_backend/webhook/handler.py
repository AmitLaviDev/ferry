"""Lambda Function URL entry point for GitHub webhook processing.

Wires together signature validation, deduplication, and event parsing.
Phase 1: Only processes push events. Phase 2 adds PR event routing.

Response format follows Lambda Function URL payload format v2:
{statusCode: int, headers: dict, body: str (JSON)}
"""

import base64
import json

import boto3
import structlog

from ferry_backend.logging import configure_logging
from ferry_backend.settings import Settings
from ferry_backend.webhook.dedup import is_duplicate
from ferry_backend.webhook.signature import verify_signature

# Module-level initialization for Lambda cold start optimization
settings = Settings()
configure_logging(settings.log_level)
log = structlog.get_logger()
dynamodb_client = boto3.client("dynamodb", region_name="us-east-1")


def handler(event: dict, context: object) -> dict:
    """Lambda Function URL handler for GitHub webhooks.

    Processing order:
    1. Extract and decode body (handle base64)
    2. Normalize headers to lowercase
    3. Validate HMAC-SHA256 signature (before JSON parsing)
    4. Check for required headers
    5. Filter non-push events
    6. Deduplicate
    7. Return accepted (Phase 1 stub)

    Args:
        event: Lambda Function URL event (payload format v2).
        context: Lambda context object (unused in Phase 1).

    Returns:
        Lambda Function URL response dict with statusCode, headers, body.
    """
    # 1. Extract body - handle possible base64 encoding (Pitfall 1)
    body = event.get("body", "")
    if event.get("isBase64Encoded", False):
        body = base64.b64decode(body).decode("utf-8")

    # 2. Normalize headers to lowercase (Pitfall 5)
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}

    # 3. Validate signature BEFORE any JSON parsing (anti-pattern from RESEARCH.md)
    signature = headers.get("x-hub-signature-256", "")
    if not verify_signature(body, signature, settings.webhook_secret):
        log.warning("webhook_signature_invalid")
        return _response(401, {"error": "invalid signature"})

    # 4. Check for required delivery ID header
    delivery_id = headers.get("x-github-delivery", "")
    if not delivery_id:
        log.warning("webhook_missing_delivery_id")
        return _response(400, {"error": "missing delivery id"})

    event_type = headers.get("x-github-event", "")

    # Bind context for structured logging
    structlog.contextvars.bind_contextvars(
        delivery_id=delivery_id,
        event_type=event_type,
    )

    # 5. Filter non-push events (Phase 1: push only)
    if event_type != "push":
        log.info("webhook_event_ignored", reason="non-push event")
        return _response(200, {"status": "ignored"})

    # 6. Parse payload (after signature validation)
    payload = json.loads(body)

    # Bind repo to log context
    repo = payload.get("repository", {}).get("full_name", "unknown")
    structlog.contextvars.bind_contextvars(repo=repo)

    # 7. Deduplicate
    if is_duplicate(delivery_id, payload, settings.table_name, dynamodb_client):
        log.info("webhook_duplicate_delivery")
        return _response(200, {"status": "duplicate"})

    # 8. Phase 1 stub: accept and return
    # Phase 2 adds: config read, change detection, dispatch
    log.info("webhook_accepted")
    return _response(200, {"status": "accepted"})


def _response(status_code: int, body: dict) -> dict:
    """Build Lambda Function URL response.

    Args:
        status_code: HTTP status code.
        body: Response body dict (will be JSON-serialized).

    Returns:
        Lambda Function URL response format.
    """
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
