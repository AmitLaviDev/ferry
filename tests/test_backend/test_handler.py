"""Tests for Lambda webhook handler (integration).

Tests cover:
- Valid signature + new delivery -> 200 accepted
- Valid signature + duplicate delivery -> 200 duplicate
- Invalid/missing signature -> 401 invalid signature
- Non-push event type -> 200 ignored
- Base64-encoded body -> decoded before validation
- Missing x-github-delivery header -> 400 missing delivery id
"""

import base64
import hashlib
import hmac
import json

import boto3
import pytest
from moto import mock_aws

TABLE_NAME = "ferry-state"
WEBHOOK_SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def _env_vars(monkeypatch):
    """Set required environment variables for Settings."""
    monkeypatch.setenv("FERRY_APP_ID", "test-app-id")
    monkeypatch.setenv("FERRY_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("FERRY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("FERRY_TABLE_NAME", TABLE_NAME)
    monkeypatch.setenv("FERRY_INSTALLATION_ID", "12345")
    monkeypatch.setenv("FERRY_LOG_LEVEL", "DEBUG")


@pytest.fixture
def dynamodb_env():
    """Create mocked DynamoDB table and yield within mock_aws context."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
        )
        yield client


def _make_signature(body: str) -> str:
    """Compute HMAC-SHA256 signature for a body."""
    mac = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
    )
    return f"sha256={mac.hexdigest()}"


def _make_push_event(
    body: str | None = None,
    signature: str | None = None,
    delivery_id: str = "delivery-001",
    event_type: str = "push",
    is_base64: bool = False,
) -> dict:
    """Build a Lambda Function URL event dict for testing."""
    if body is None:
        body = json.dumps(
            {
                "ref": "refs/heads/main",
                "after": "abc123def456",
                "before": "000000000000",
                "repository": {
                    "full_name": "owner/repo",
                    "default_branch": "main",
                },
                "pusher": {"name": "testuser"},
            }
        )

    if signature is None:
        signature = _make_signature(body)

    raw_body = body
    if is_base64:
        raw_body = base64.b64encode(body.encode("utf-8")).decode("utf-8")

    event = {
        "body": raw_body,
        "isBase64Encoded": is_base64,
        "headers": {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": event_type,
            "Content-Type": "application/json",
        },
    }
    return event


class TestHandler:
    def test_valid_signature_new_delivery_returns_accepted(self, dynamodb_env):
        from ferry_backend.webhook.handler import handler

        event = _make_push_event()
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "accepted"

    def test_valid_signature_duplicate_delivery_returns_duplicate(self, dynamodb_env):
        from ferry_backend.webhook.handler import handler

        event = _make_push_event()
        handler(event, None)  # First delivery
        result = handler(event, None)  # Same delivery ID
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "duplicate"

    def test_invalid_signature_returns_401(self, dynamodb_env):
        from ferry_backend.webhook.handler import handler

        event = _make_push_event(signature="sha256=invalid_signature_hex")
        result = handler(event, None)
        assert result["statusCode"] == 401
        body = json.loads(result["body"])
        assert body["error"] == "invalid signature"

    def test_missing_signature_returns_401(self, dynamodb_env):
        from ferry_backend.webhook.handler import handler

        event = _make_push_event(signature="")
        result = handler(event, None)
        assert result["statusCode"] == 401
        body = json.loads(result["body"])
        assert body["error"] == "invalid signature"

    def test_non_push_event_returns_ignored(self, dynamodb_env):
        from ferry_backend.webhook.handler import handler

        event = _make_push_event(event_type="pull_request")
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "ignored"

    def test_base64_encoded_body_decoded_before_validation(self, dynamodb_env):
        from ferry_backend.webhook.handler import handler

        event = _make_push_event(is_base64=True)
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "accepted"

    def test_missing_delivery_header_returns_400(self, dynamodb_env):
        from ferry_backend.webhook.handler import handler

        event = _make_push_event()
        del event["headers"]["X-GitHub-Delivery"]
        result = handler(event, None)
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error"] == "missing delivery id"
