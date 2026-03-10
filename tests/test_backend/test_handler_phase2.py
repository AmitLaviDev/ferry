"""Phase 2 integration tests for webhook handler.

Tests the complete pipeline: auth -> config -> detect -> dispatch/check run.
Uses pytest-httpx to mock ALL GitHub API calls and moto for DynamoDB.
Each test sends a full Lambda Function URL event through the handler.
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

# Minimal ferry.yaml for tests
FERRY_YAML = yaml.dump(
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

FERRY_YAML_B64 = base64.b64encode(FERRY_YAML.encode()).decode()

# The PEM key above is intentionally malformed for size.
# We'll mock the JWT generation instead.


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
    delivery_id: str = "delivery-p2-001",
) -> dict:
    """Build a Lambda Function URL push event for Phase 2 tests."""
    payload = {
        "ref": ref,
        "before": before,
        "after": after,
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
        url=("https://api.github.com/app/installations/12345/access_tokens"),
        json={"token": "ghs_test_token_123"},
        status_code=201,
    )


def _mock_ferry_config(httpx_mock, sha, yaml_b64=None):
    """Mock the ferry.yaml Contents API endpoint."""
    if yaml_b64 is None:
        yaml_b64 = FERRY_YAML_B64
    httpx_mock.add_response(
        url=(f"https://api.github.com/repos/owner/repo/contents/ferry.yaml?ref={sha}"),
        json={"content": yaml_b64},
        status_code=200,
    )


def _mock_compare(httpx_mock, base, head, files):
    """Mock the Compare API endpoint."""
    httpx_mock.add_response(
        url=(f"https://api.github.com/repos/owner/repo/compare/{base}...{head}"),
        json={
            "files": [{"filename": f, "status": "modified"} for f in files],
        },
    )


def _mock_prs_for_commit(httpx_mock, sha, prs=None):
    """Mock the commits/{sha}/pulls endpoint."""
    if prs is None:
        prs = []
    httpx_mock.add_response(
        url=(f"https://api.github.com/repos/owner/repo/commits/{sha}/pulls"),
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
        url=(
            f"https://api.github.com/repos/owner/repo/actions/workflows/{workflow_file}/dispatches"
        ),
        status_code=204,
    )


def _mock_pr_comment(httpx_mock, pr_number):
    """Mock the Issues Comments API endpoint for PR comments."""
    httpx_mock.add_response(
        url=(f"https://api.github.com/repos/owner/repo/issues/{pr_number}/comments"),
        json={"id": 100, "body": "test"},
        status_code=201,
    )


class TestHandlerPhase2:
    def test_handler_default_branch_push_triggers_dispatch(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push to default branch with changed lambda files -> dispatch.

        Compare API called with before_sha...after_sha. No check run
        posted (no open PR for this commit).
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
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, after)
        _mock_compare(
            httpx_mock,
            before,
            after,
            ["services/order-processor/main.py"],
        )
        # No open PRs for this commit (default branch merge)
        _mock_prs_for_commit(httpx_mock, after, prs=[])
        _mock_dispatch(httpx_mock)

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

        # Verify NO check run was posted (no open PR)
        check_reqs = [r for r in requests if "check-runs" in str(r.url)]
        assert len(check_reqs) == 0

    def test_handler_pr_branch_push_creates_check_run(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push to feature branch with open PR -> check run, no dispatch.

        Compare API called with default_branch...after_sha (merge-base).
        """
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        before = "a" * 40
        after = "b" * 40
        event = _make_push_event(
            ref="refs/heads/feature-branch",
            before=before,
            after=after,
            delivery_id="delivery-p2-002",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, after)
        # PR branch: compare uses default_branch (main) as base
        _mock_compare(
            httpx_mock,
            "main",
            after,
            ["services/order-processor/main.py"],
        )
        _mock_prs_for_commit(
            httpx_mock,
            after,
            prs=[{"number": 42, "state": "open"}],
        )
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"
        assert body["affected"] == 1

        # Verify check run was posted
        requests = httpx_mock.get_requests()
        check_reqs = [r for r in requests if "check-runs" in str(r.url)]
        assert len(check_reqs) == 1

        # Verify check run body content
        check_body = json.loads(check_reqs[0].content)
        assert check_body["name"] == "Ferry: Deployment Plan"
        assert check_body["conclusion"] == "success"
        assert "order-processor" in check_body["output"]["text"]

        # Verify NO dispatch was triggered
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 0

    def test_handler_pr_branch_second_push_full_diff(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Second push to PR branch still uses merge-base comparison.

        Compare API should use default_branch...after_sha, NOT
        before_sha...after_sha. This ensures the Check Run shows ALL
        affected resources, not just incremental changes.
        """
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        # Second push: before_sha is NOT the initial push
        before = "c" * 40
        after = "d" * 40
        event = _make_push_event(
            ref="refs/heads/feature-branch",
            before=before,
            after=after,
            delivery_id="delivery-p2-003",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, after)
        # Must use main...after (merge-base), NOT before...after
        _mock_compare(
            httpx_mock,
            "main",
            after,
            ["services/order-processor/main.py"],
        )
        _mock_prs_for_commit(
            httpx_mock,
            after,
            prs=[{"number": 42, "state": "open"}],
        )
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"

        # Verify compare was called with main...after, not before...after
        requests = httpx_mock.get_requests()
        compare_reqs = [r for r in requests if "compare" in str(r.url)]
        assert len(compare_reqs) == 1
        compare_url = str(compare_reqs[0].url)
        assert f"compare/main...{after}" in compare_url
        assert f"compare/{before}" not in compare_url

    def test_config_error_posts_pr_comment_not_check_run(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push to PR branch with invalid ferry.yaml -> PR comment, NOT check run."""
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        after = "e" * 40
        event = _make_push_event(
            ref="refs/heads/feature-branch",
            before="a" * 40,
            after=after,
            delivery_id="delivery-p2-004",
        )

        _mock_installation_token(httpx_mock)
        # Return 404 (no ferry.yaml) to trigger ConfigError
        httpx_mock.add_response(
            url=(f"https://api.github.com/repos/owner/repo/contents/ferry.yaml?ref={after}"),
            status_code=404,
            json={"message": "Not Found"},
        )
        _mock_prs_for_commit(
            httpx_mock,
            after,
            prs=[{"number": 42, "state": "open"}],
        )
        _mock_pr_comment(httpx_mock, 42)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "config_error"
        assert "error" in body

        # Verify PR comment was posted (not a Check Run)
        requests = httpx_mock.get_requests()
        comment_reqs = [r for r in requests if "/issues/" in str(r.url)]
        assert len(comment_reqs) == 1
        comment_body = json.loads(comment_reqs[0].content)
        assert "Configuration Error" in comment_body["body"]
        assert "ferry.yaml validation failed" in comment_body["body"]

        # Verify NO check run was posted
        check_reqs = [r for r in requests if "check-runs" in str(r.url)]
        assert len(check_reqs) == 0

    def test_handler_no_changes_creates_empty_check_run(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push to PR branch, no file matches -> 'No resources affected'."""
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        after = "f" * 40
        event = _make_push_event(
            ref="refs/heads/feature-branch",
            before="a" * 40,
            after=after,
            delivery_id="delivery-p2-005",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, after)
        # Changed files don't match any resource source_dir
        _mock_compare(
            httpx_mock,
            "main",
            after,
            ["unrelated/readme.md"],
        )
        _mock_prs_for_commit(
            httpx_mock,
            after,
            prs=[{"number": 42, "state": "open"}],
        )
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"
        assert body["affected"] == 0

        # Verify check run was posted with "No Changes Detected"
        requests = httpx_mock.get_requests()
        check_reqs = [r for r in requests if "check-runs" in str(r.url)]
        assert len(check_reqs) == 1
        check_body = json.loads(check_reqs[0].content)
        assert check_body["conclusion"] == "success"
        assert check_body["output"]["title"] == "No Changes Detected"

    def test_handler_initial_push_dispatches_all(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """before SHA is all zeros -> all resources dispatched.

        Uses detect_config_changes(None, config) for initial push.
        """
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        zero_sha = "0" * 40
        after = "g" * 40
        event = _make_push_event(
            ref="refs/heads/main",
            before=zero_sha,
            after=after,
            delivery_id="delivery-p2-006",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, after)
        # No compare API call needed for initial push
        # Initial push on default branch -> dispatch + find PRs
        _mock_prs_for_commit(httpx_mock, after, prs=[])
        _mock_dispatch(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"
        assert body["affected"] == 1  # One lambda in config

        # Verify dispatch was called
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 1

        # Verify NO compare API call was made
        compare_reqs = [r for r in requests if "compare" in str(r.url)]
        assert len(compare_reqs) == 0

    def test_handler_ferry_yaml_change_triggers_config_diff(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """ferry.yaml in changed files -> config diff logic runs.

        When ferry.yaml itself is among the changed files, the handler
        should fetch the old config and diff it against the new config.
        """
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        before = "h" * 40
        after = "i" * 40

        # New config has the resource
        new_yaml = yaml.dump(
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
        new_yaml_b64 = base64.b64encode(new_yaml.encode()).decode()

        # Old config: empty (no lambdas)
        old_yaml = yaml.dump({"version": 1})
        old_yaml_b64 = base64.b64encode(old_yaml.encode()).decode()

        event = _make_push_event(
            ref="refs/heads/main",
            before=before,
            after=after,
            delivery_id="delivery-p2-007",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, after, yaml_b64=new_yaml_b64)
        _mock_compare(
            httpx_mock,
            before,
            after,
            ["ferry.yaml"],  # Only ferry.yaml changed
        )
        # Fetch old config at before_sha
        httpx_mock.add_response(
            url=(f"https://api.github.com/repos/owner/repo/contents/ferry.yaml?ref={before}"),
            json={"content": old_yaml_b64},
            status_code=200,
        )
        _mock_prs_for_commit(httpx_mock, after, prs=[])
        _mock_dispatch(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"
        # The resource should be detected as "new" via config diff
        assert body["affected"] == 1

        # Verify dispatch was called (default branch push)
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 1

    def test_config_error_default_branch_posts_to_merged_pr(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Push to default branch with invalid ferry.yaml -> comment on merged PR."""
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: "fake-jwt",
        )

        after = "j" * 40
        event = _make_push_event(
            ref="refs/heads/main",
            before="a" * 40,
            after=after,
            delivery_id="delivery-p2-008",
        )

        _mock_installation_token(httpx_mock)
        # Return 404 (no ferry.yaml) to trigger ConfigError
        httpx_mock.add_response(
            url=(f"https://api.github.com/repos/owner/repo/contents/ferry.yaml?ref={after}"),
            status_code=404,
            json={"message": "Not Found"},
        )
        # find_open_prs is called first (returns empty -- no open PRs).
        # find_merged_pr is called second (returns the merged PR).
        # Both hit the same endpoint, so register the response twice.
        merged_prs = [
            {
                "number": 55,
                "state": "closed",
                "merged_at": "2026-02-28T00:00:00Z",
            },
        ]
        _mock_prs_for_commit(httpx_mock, after, prs=merged_prs)
        _mock_prs_for_commit(httpx_mock, after, prs=merged_prs)
        _mock_pr_comment(httpx_mock, 55)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "config_error"

        # Verify PR comment was posted on the merged PR
        requests = httpx_mock.get_requests()
        comment_reqs = [r for r in requests if "/issues/" in str(r.url)]
        assert len(comment_reqs) == 1
        assert "/issues/55/comments" in str(comment_reqs[0].url)
        comment_body = json.loads(comment_reqs[0].content)
        assert "Configuration Error" in comment_body["body"]

    def test_auth_error_returns_structured_500(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """GitHubAuthError in handler -> structured 500 with auth_error status."""
        from ferry_utils.errors import GitHubAuthError

        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: (_ for _ in ()).throw(
                GitHubAuthError("JWT generation failed: bad key"),
            ),
        )

        after = "k" * 40
        event = _make_push_event(
            ref="refs/heads/main",
            before="a" * 40,
            after=after,
            delivery_id="delivery-p2-009",
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 500
        assert body["status"] == "auth_error"
        assert "JWT generation failed" in body["error"]

    def test_unhandled_error_returns_structured_500(
        self,
        dynamodb_env,
        httpx_mock,
        monkeypatch,
    ):
        """Unexpected exception -> structured 500 with internal_error, no leak."""
        monkeypatch.setattr(
            "ferry_backend.webhook.handler.generate_app_jwt",
            lambda app_id, pk: (_ for _ in ()).throw(
                RuntimeError("super secret internal detail"),
            ),
        )

        after = "m" * 40
        event = _make_push_event(
            ref="refs/heads/main",
            before="a" * 40,
            after=after,
            delivery_id="delivery-p2-010",
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 500
        assert body["status"] == "internal_error"
        assert body["error"] == "internal server error"
        # Must NOT leak internal details
        assert "super secret" not in body["error"]
