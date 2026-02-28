"""Tests for webhook HMAC-SHA256 signature validation.

Tests cover:
- Valid signature accepted
- Tampered body rejected
- Missing signature rejected
- Signature without sha256= prefix rejected
- Wrong secret rejected
"""

import hashlib
import hmac

from ferry_backend.webhook.signature import verify_signature

SECRET = "test-webhook-secret"
BODY = '{"action": "push", "ref": "refs/heads/main"}'


def _make_signature(body: str, secret: str) -> str:
    """Helper to compute a valid HMAC-SHA256 signature."""
    mac = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


class TestVerifySignature:
    def test_valid_signature_returns_true(self):
        signature = _make_signature(BODY, SECRET)
        assert verify_signature(BODY, signature, SECRET) is True

    def test_tampered_body_returns_false(self):
        signature = _make_signature(BODY, SECRET)
        tampered_body = '{"action": "push", "ref": "refs/heads/evil"}'
        assert verify_signature(tampered_body, signature, SECRET) is False

    def test_missing_signature_returns_false(self):
        assert verify_signature(BODY, "", SECRET) is False

    def test_signature_without_prefix_returns_false(self):
        mac = hmac.new(SECRET.encode("utf-8"), BODY.encode("utf-8"), hashlib.sha256)
        signature_no_prefix = mac.hexdigest()
        assert verify_signature(BODY, signature_no_prefix, SECRET) is False

    def test_wrong_secret_returns_false(self):
        signature = _make_signature(BODY, "wrong-secret")
        assert verify_signature(BODY, signature, SECRET) is False
