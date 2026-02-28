"""HMAC-SHA256 webhook signature validation.

Validates GitHub webhook signatures using constant-time comparison
to prevent timing attacks. Signature format: "sha256=" + hex digest.

Reference: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
"""

import hashlib
import hmac


def verify_signature(body: str, signature_header: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature of a webhook payload.

    Args:
        body: Raw request body string (before JSON parsing).
        signature_header: Value of X-Hub-Signature-256 header (e.g., "sha256=abc123...").
        secret: Webhook secret shared with GitHub.

    Returns:
        True if signature is valid, False otherwise.
    """
    if not signature_header.startswith("sha256="):
        return False

    expected = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )

    return hmac.compare_digest(expected, signature_header)
