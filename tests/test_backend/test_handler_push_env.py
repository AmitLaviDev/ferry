"""Integration tests for environment-gated push dispatch.

Tests the push handler's environment-based gating logic:
- Mapped branch with auto_deploy: true -> dispatch with environment name
- Mapped branch with auto_deploy: false -> silent (no dispatch, no check run)
- Unmapped branch -> silent
- No environments configured -> silent
- Branch deletion -> ignored before auth
- Tag push -> ignored before auth
"""

from __future__ import annotations

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
PRIVATE_KEY_PEM = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB7MhgHcTz6sE2I2yPB
aFDrBz9vFqU4yK1P+0TQXBz/F+XmdrWWkO5fSGOsJG7gGd5K7dMx1kZ7fhEITGg
NxNsOIb6GSkY6RJQRU+v9+L4sH6gfRWiTj0kTTGkrzhDGRLmAFNK6HROQSE3vgp
m1aluNd+GVo+0g+E68qEHqCqJm2v+w9jL8sFfMdKqPKLCjQJ2uTbp9SxUx2+FrZ
pS8OGFbErThQLiV1jIE1BpYbH4PCNLX1v3LvM1SP8y4p9G5kKjXBiEHYlP/K/sFz
DcWi/pxYjQVxl27dPfpMOUTQ5UcN8AK2ZVFhmQIDAQABAoIBAC5RgZ+hBx7xHNaM
pPgwGMnCd3KE+KRYJ18I8MwfRDyl/c8VIXhPBe07HpafU1rz1j9MgK7KjYSFJtOv
CDAkz0cN2fL7IGMK6g8JR0FOTpnUWnKF9A+bJDLH0OlTaHjN4F1P2dLqkuPuD4C
u5UW8E01h0ajxQ7rSzjLj7yE0cRJoUrZ+F5GJ7nzG4LGNVPP3x6pCdN8rlabDxoV
3s+KQAEbwoJp8bZBry/GjvzWQy5nDAnCgfRPqXQ3kEiRGaBNHIO+CYL5eF3dEHaH
hJVWoT5Rlbu7xIu6SYGz3bGS7T5p0wJTTHGNXjKQcr0HQTFkXLWHs2GBoOVNRla
VxOsKcECgYEA6Y9hWm7AFJj7fHJMLybJT+HKP0Pv/6MX8pCR9VcqHKKSRMxKqEX6
V1ViXLvN3bBp+RaPdBFMXvLGnWZ+mSPWMTj/cQf2yjUan3M3P3/ey4pR8k5GsT2Y
6TsxQ7p6T9J1S5OUps9T6bNgoUoJd7TFd8K7z5z6dNM6eFoRkyUoZ0kCgYEA5YXS
eBvZKV2Fdx3wNHBsP2y0OikVD3t+JRIe94CgVL2P+lFntFGWcz6M0f8GX9L2JMFe
XHNqNJGx0BF+VWp1hn2S7p7IFP3z8dBsSTsJ2xJ8rOrqLPDY01r8ERVTmqWCHF3t
U2A38U+V5LXRK0IkR6fkVF8NRn1y3IkQNDlVOkECgYBCd/+lV6dkSFEj2RjpsBQr
GfJBMBzE3RgXKjv7hJj7CEadkNI2ef/bthY0OGe/fXqGz3PFM8P6DfzqO0jgqFEN
dJ8Nt0KHAHly/eJUzHRv7YWpBqzDAH7bNzMn7Ay7CuGJ0OKAOC+yP3WRFO8LGTGK
3FvWnEJDcGS/GD2s/DLKQQ==
-----END RSA PRIVATE KEY-----"""

# ferry.yaml WITH environments (production->main, staging->develop, both auto_deploy)
FERRY_YAML_WITH_ENVS = yaml.dump(
    {
        "version": 1,
        "environments": {
            "production": {"branch": "main", "auto_deploy": True},
            "staging": {"branch": "develop", "auto_deploy": True},
        },
        "lambdas": [
            {
                "name": "order-processor",
                "source_dir": "services/order-processor",
                "ecr_repo": "ferry/order-processor",
            },
        ],
    }
)
FERRY_YAML_WITH_ENVS_B64 = base64.b64encode(FERRY_YAML_WITH_ENVS.encode()).decode()

# ferry.yaml with auto_deploy: false on the only environment
FERRY_YAML_NO_AUTO_DEPLOY = yaml.dump(
    {
        "version": 1,
        "environments": {
            "production": {"branch": "main", "auto_deploy": False},
        },
        "lambdas": [
            {
                "name": "order-processor",
                "source_dir": "services/order-processor",
                "ecr_repo": "ferry/order-processor",
            },
        ],
    }
)
FERRY_YAML_NO_AUTO_DEPLOY_B64 = base64.b64encode(FERRY_YAML_NO_AUTO_DEPLOY.encode()).decode()

# ferry.yaml with NO environments section
FERRY_YAML_NO_ENVS = yaml.dump(
    {
        "version": 1,
        "lambdas": [
            {
                "name": "order-processor",
                "source_dir": "services/order-processor",
                "ecr_repo": "ferry/order-processor",
            },
        ],
    }
)
FERRY_YAML_NO_ENVS_B64 = base64.b64encode(FERRY_YAML_NO_ENVS.encode()).decode()


@pytest.fixture(autouse=True)
def _env_vars(monkeypatch):
    """Set required environment variables for Settings."""
    monkeypatch.setenv("FERRY_APP_ID", "test-app-id")
    monkeypatch.setenv("FERRY_PRIVATE_KEY", PRIVATE_KEY_PEM)
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
    ref: str = "refs/heads/main",
    before: str = "aaa" * 13 + "a",
    after: str = "bbb" * 13 + "b",
    default_branch: str = "main",
    delivery_id: str = "delivery-env-001",
    deleted: bool = False,
) -> dict:
    """Build a Lambda Function URL push event."""
    payload = {
        "ref": ref,
        "before": before,
        "after": after,
        "deleted": deleted,
        "repository": {
            "full_name": "owner/repo",
            "default_branch": default_branch,
        },
        "pusher": {"name": "testuser"},
    }
    body = json.dumps(payload)
    signature = _make_signature(body)
    return {
        "body": body,
        "isBase64Encoded": False,
        "headers": {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": "push",
            "Content-Type": "application/json",
        },
    }


def _mock_installation_token(httpx_mock):
    """Mock the installation token exchange endpoint."""
    httpx_mock.add_response(
        url="https://api.github.com/app/installations/12345/access_tokens",
        json={"token": "ghs_test_token_123"},
        status_code=201,
    )


def _mock_ferry_config(httpx_mock, sha, yaml_b64=None):
    """Mock the ferry.yaml Contents API endpoint."""
    if yaml_b64 is None:
        yaml_b64 = FERRY_YAML_WITH_ENVS_B64
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/contents/ferry.yaml?ref={sha}",
        json={"content": yaml_b64},
        status_code=200,
    )


def _mock_compare(httpx_mock, base, head, files):
    """Mock the Compare API endpoint."""
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/compare/{base}...{head}",
        json={
            "files": [{"filename": f, "status": "modified"} for f in files],
        },
    )


def _mock_prs_for_commit(httpx_mock, sha, prs=None):
    """Mock the commits/{sha}/pulls endpoint."""
    if prs is None:
        prs = []
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/commits/{sha}/pulls",
        json=prs,
    )


def _mock_check_run(httpx_mock):
    """Mock the Check Runs API endpoint."""
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/check-runs",
        json={"id": 1, "status": "completed"},
        status_code=201,
    )


def _mock_dispatch(httpx_mock, workflow_file="ferry.yml"):
    """Mock the workflow dispatch API endpoint."""
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/actions/workflows/{workflow_file}/dispatches",
        status_code=204,
    )


class TestPushEnvironment:
    """Tests for environment-gated push dispatch behavior."""

    def test_mapped_branch_auto_deploy_dispatches(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push to `refs/heads/main` with environments config mapping
        main->production (auto_deploy: true) triggers dispatch. Dispatch
        payload contains environment="production", mode="deploy". Check Run
        is created. Response status is "processed".
        """
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        before = "a" * 40
        after = "b" * 40
        event = _make_push_event(
            ref="refs/heads/main",
            before=before,
            after=after,
            delivery_id="delivery-env-001",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, after, yaml_b64=FERRY_YAML_WITH_ENVS_B64)
        _mock_compare(
            httpx_mock,
            before,
            after,
            ["services/order-processor/main.py"],
        )
        _mock_prs_for_commit(httpx_mock, after, prs=[])
        _mock_dispatch(httpx_mock)
        # find_merged_pr also calls commits/{sha}/pulls (second call)
        _mock_prs_for_commit(httpx_mock, after, prs=[])
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"
        assert body["affected"] == 1

        # Verify dispatch was called
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 1

        # Verify dispatch payload contains environment and mode
        dispatch_body = json.loads(dispatch_reqs[0].content)
        payload_data = json.loads(dispatch_body["inputs"]["payload"])
        assert payload_data["environment"] == "production"
        assert payload_data["mode"] == "deploy"

        # Verify Check Run was created
        check_reqs = [r for r in requests if "check-runs" in str(r.url)]
        assert len(check_reqs) == 1

    def test_environment_name_in_dispatch_payload(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push to `refs/heads/develop` with develop->staging mapping.
        Verify the JSON payload contains "environment": "staging" and
        "mode": "deploy".
        """
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        before = "c" * 40
        after = "d" * 40
        event = _make_push_event(
            ref="refs/heads/develop",
            before=before,
            after=after,
            default_branch="main",
            delivery_id="delivery-env-002",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, after, yaml_b64=FERRY_YAML_WITH_ENVS_B64)
        _mock_compare(
            httpx_mock,
            before,
            after,
            ["services/order-processor/main.py"],
        )
        _mock_prs_for_commit(httpx_mock, after, prs=[])
        _mock_dispatch(httpx_mock)
        # find_merged_pr also calls commits/{sha}/pulls (second call)
        _mock_prs_for_commit(httpx_mock, after, prs=[])
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"

        # Verify dispatch payload contains staging environment
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 1

        dispatch_body = json.loads(dispatch_reqs[0].content)
        payload_data = json.loads(dispatch_body["inputs"]["payload"])
        assert payload_data["environment"] == "staging"
        assert payload_data["mode"] == "deploy"

    def test_auto_deploy_false_silent(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push to mapped branch with auto_deploy: false. Zero dispatch
        requests, zero check-run requests. Response status is "processed".
        """
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        before = "e" * 40
        after = "f" * 40
        event = _make_push_event(
            ref="refs/heads/main",
            before=before,
            after=after,
            delivery_id="delivery-env-003",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, after, yaml_b64=FERRY_YAML_NO_AUTO_DEPLOY_B64)
        _mock_compare(
            httpx_mock,
            before,
            after,
            ["services/order-processor/main.py"],
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"

        # Zero dispatch requests
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 0

        # Zero check-run requests
        check_reqs = [r for r in requests if "check-runs" in str(r.url)]
        assert len(check_reqs) == 0

    def test_unmapped_branch_silent(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push to `refs/heads/feature-xyz` with only main->production
        mapping. Zero dispatch, zero check-run. Response status is
        "processed".
        """
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        before = "g" * 40
        after = "h" * 40
        event = _make_push_event(
            ref="refs/heads/feature-xyz",
            before=before,
            after=after,
            default_branch="main",
            delivery_id="delivery-env-004",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, after, yaml_b64=FERRY_YAML_WITH_ENVS_B64)
        _mock_compare(
            httpx_mock,
            before,
            after,
            ["services/order-processor/main.py"],
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"

        # Zero dispatch requests
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 0

        # Zero check-run requests
        check_reqs = [r for r in requests if "check-runs" in str(r.url)]
        assert len(check_reqs) == 0

    def test_no_environments_silent(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push to default branch with ferry.yaml that has NO environments
        section. Zero dispatch, zero check-run. Response status is
        "processed".
        """
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        before = "i" * 40
        after = "j" * 40
        event = _make_push_event(
            ref="refs/heads/main",
            before=before,
            after=after,
            delivery_id="delivery-env-005",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, after, yaml_b64=FERRY_YAML_NO_ENVS_B64)
        _mock_compare(
            httpx_mock,
            before,
            after,
            ["services/order-processor/main.py"],
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"

        # Zero dispatch requests
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 0

        # Zero check-run requests
        check_reqs = [r for r in requests if "check-runs" in str(r.url)]
        assert len(check_reqs) == 0

    def test_branch_deletion_ignored(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push event with `deleted: true` in payload. Response status is
        "ignored", reason is "branch deleted". Zero API calls (no auth
        token exchange, no config fetch).
        """
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        event = _make_push_event(
            ref="refs/heads/main",
            before="a" * 40,
            after="0" * 40,
            delivery_id="delivery-env-006",
            deleted=True,
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "ignored"
        assert body["reason"] == "branch deleted"

        # Zero GitHub API calls (no installation token, no config fetch)
        requests = httpx_mock.get_requests()
        github_reqs = [r for r in requests if "github.com" in str(r.url)]
        assert len(github_reqs) == 0

    def test_tag_push_ignored(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push event with `ref: "refs/tags/v1.0"`. Response status is
        "ignored", reason is "tag push". Zero API calls beyond signature
        validation.
        """
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        event = _make_push_event(
            ref="refs/tags/v1.0",
            before="a" * 40,
            after="b" * 40,
            delivery_id="delivery-env-007",
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "ignored"
        assert body["reason"] == "tag push"

        # Zero GitHub API calls
        requests = httpx_mock.get_requests()
        github_reqs = [r for r in requests if "github.com" in str(r.url)]
        assert len(github_reqs) == 0
