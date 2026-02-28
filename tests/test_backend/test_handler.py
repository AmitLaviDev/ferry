"""Tests for Lambda webhook handler (Phase 1 gate tests + Phase 2 passthrough).

Tests cover:
- Valid signature + new delivery -> 200 processed (Phase 2 pipeline)
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
import yaml
from moto import mock_aws

TABLE_NAME = "ferry-state"
WEBHOOK_SECRET = "test-webhook-secret"

# Minimal ferry.yaml for tests that reach Phase 2 pipeline
_FERRY_YAML = yaml.dump({"version": 1, "lambdas": []})
_FERRY_YAML_B64 = base64.b64encode(_FERRY_YAML.encode()).decode()


@pytest.fixture(autouse=True)
def _env_vars(monkeypatch):
    """Set required environment variables for Settings."""
    monkeypatch.setenv("FERRY_APP_ID", "test-app-id")
    monkeypatch.setenv("FERRY_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("FERRY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("FERRY_TABLE_NAME", TABLE_NAME)
    monkeypatch.setenv("FERRY_INSTALLATION_ID", "12345")
    monkeypatch.setenv("FERRY_LOG_LEVEL", "DEBUG")
    # Fake AWS credentials for moto
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(autouse=True)
def _mock_jwt(monkeypatch):
    """Mock JWT generation to avoid needing a real PEM key."""
    monkeypatch.setattr(
        "ferry_backend.webhook.handler.generate_app_jwt",
        lambda app_id, pk: "fake-jwt",
    )


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
        WEBHOOK_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
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
                "after": "abc123def456" + "0" * 28,
                "before": "0" * 40,
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
        raw_body = base64.b64encode(
            body.encode("utf-8"),
        ).decode("utf-8")

    return {
        "body": raw_body,
        "isBase64Encoded": is_base64,
        "headers": {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": event_type,
            "Content-Type": "application/json",
        },
    }


def _mock_phase2_apis(httpx_mock, after_sha):
    """Mock the minimal GitHub API endpoints for Phase 2 pipeline.

    Uses empty config (no resources) so handler reaches 'processed'
    without needing dispatch or check run mocks.
    Initial push (before=0*40) skips compare API call.
    Default branch with no affected resources skips find_open_prs.
    """
    # Installation token
    httpx_mock.add_response(
        url=("https://api.github.com/app/installations/12345/access_tokens"),
        json={"token": "ghs_test_token_123"},
        status_code=201,
    )
    # Ferry config (empty config = no resources)
    httpx_mock.add_response(
        url=(f"https://api.github.com/repos/owner/repo/contents/ferry.yaml?ref={after_sha}"),
        json={"content": _FERRY_YAML_B64},
        status_code=200,
    )


class TestHandler:
    def test_valid_signature_new_delivery_returns_processed(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """Valid push event processes through Phase 2 pipeline."""
        from ferry_backend.webhook.handler import handler

        after_sha = "abc123def456" + "0" * 28
        _mock_phase2_apis(httpx_mock, after_sha)

        event = _make_push_event()
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "processed"

    def test_valid_signature_duplicate_delivery_returns_duplicate(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """Duplicate delivery ID returns duplicate status."""
        from ferry_backend.webhook.handler import handler

        after_sha = "abc123def456" + "0" * 28
        _mock_phase2_apis(httpx_mock, after_sha)

        event = _make_push_event()
        handler(event, None)  # First delivery
        result = handler(event, None)  # Same delivery ID
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "duplicate"

    def test_invalid_signature_returns_401(self, dynamodb_env):
        from ferry_backend.webhook.handler import handler

        event = _make_push_event(
            signature="sha256=invalid_signature_hex",
        )
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

    def test_base64_encoded_body_decoded_before_validation(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """Base64-encoded body is decoded before signature validation."""
        from ferry_backend.webhook.handler import handler

        after_sha = "abc123def456" + "0" * 28
        _mock_phase2_apis(httpx_mock, after_sha)

        event = _make_push_event(is_base64=True)
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "processed"

    def test_missing_delivery_header_returns_400(self, dynamodb_env):
        from ferry_backend.webhook.handler import handler

        event = _make_push_event()
        del event["headers"]["X-GitHub-Delivery"]
        result = handler(event, None)
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error"] == "missing delivery id"
