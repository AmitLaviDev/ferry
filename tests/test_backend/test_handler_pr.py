"""Integration tests for pull_request event handling in webhook handler.

Tests the complete PR pipeline: auth -> config -> detect -> plan comment + check run.
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

from ferry_backend.checks.plan import PLAN_MARKER

TABLE_NAME = "ferry-state"
WEBHOOK_SECRET = "test-webhook-secret"

# Minimal ferry.yaml with one lambda for tests
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

# ferry.yaml with environments
FERRY_YAML_WITH_ENVS = yaml.dump(
    {
        "version": 1,
        "lambdas": [
            {
                "name": "order-processor",
                "source_dir": "services/order-processor",
                "ecr_repo": "ferry/order-processor",
            },
        ],
        "environments": [
            {"name": "staging", "branch": "develop"},
            {"name": "production", "branch": "main", "auto_deploy": False},
        ],
    }
)
FERRY_YAML_WITH_ENVS_B64 = base64.b64encode(FERRY_YAML_WITH_ENVS.encode()).decode()

# Empty ferry.yaml (no resources)
FERRY_YAML_EMPTY = yaml.dump({"version": 1, "lambdas": []})
FERRY_YAML_EMPTY_B64 = base64.b64encode(FERRY_YAML_EMPTY.encode()).decode()


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


def _make_pr_event(
    action: str = "opened",
    pr_number: int = 42,
    head_sha: str = "b" * 40,
    base_ref: str = "main",
    delivery_id: str = "delivery-pr-001",
) -> dict:
    """Build a Lambda Function URL event dict for a pull_request webhook."""
    payload = {
        "action": action,
        "number": pr_number,
        "pull_request": {
            "number": pr_number,
            "head": {"sha": head_sha},
            "base": {"ref": base_ref},
        },
        "repository": {
            "full_name": "owner/repo",
            "default_branch": "main",
        },
    }
    body = json.dumps(payload)
    signature = _make_signature(body)
    return {
        "body": body,
        "isBase64Encoded": False,
        "headers": {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": "pull_request",
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
        yaml_b64 = FERRY_YAML_B64
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


def _mock_check_run(httpx_mock):
    """Mock the Check Runs API endpoint."""
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/check-runs",
        json={"id": 1, "status": "completed"},
        status_code=201,
    )


def _mock_find_no_plan_comment(httpx_mock, pr_number=42):
    """Mock listing PR comments (paginated GET) returning no plan comment."""
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/issues/{pr_number}/comments?per_page=100&page=1",
        json=[],
    )


def _mock_find_existing_plan_comment(httpx_mock, pr_number=42, comment_id=50):
    """Mock listing PR comments (paginated GET) returning an existing plan comment."""
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/issues/{pr_number}/comments?per_page=100&page=1",
        json=[{"id": comment_id, "body": f"{PLAN_MARKER}\nold plan"}],
    )


def _mock_create_comment(httpx_mock, pr_number=42):
    """Mock creating a new PR comment (POST, no query params)."""
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/issues/{pr_number}/comments",
        json={"id": 99, "body": "new plan"},
        status_code=201,
    )


def _mock_update_comment(httpx_mock, comment_id=50):
    """Mock updating an existing PR comment via PATCH."""
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/issues/comments/{comment_id}",
        json={"id": comment_id, "body": "updated plan"},
    )


class TestHandlerPR:
    def test_pr_opened_with_changes_posts_plan_comment(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """PR opened with affected resources -> new plan comment + check run."""
        head_sha = "b" * 40
        event = _make_pr_event(action="opened", head_sha=head_sha)

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, head_sha)
        _mock_compare(httpx_mock, "main", head_sha, ["services/order-processor/main.py"])
        _mock_find_no_plan_comment(httpx_mock)
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"
        assert body["affected"] == 1

        # Verify plan comment was posted
        requests = httpx_mock.get_requests()
        comment_posts = [
            r for r in requests if r.method == "POST" and "/issues/42/comments" in str(r.url)
        ]
        assert len(comment_posts) == 1
        comment_body = json.loads(comment_posts[0].content)["body"]
        assert PLAN_MARKER in comment_body
        assert "order-processor" in comment_body

        # Verify check run was posted
        check_reqs = [r for r in requests if "check-runs" in str(r.url)]
        assert len(check_reqs) == 1

    def test_pr_synchronize_updates_existing_comment(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """PR synchronize with existing comment -> PATCH update."""
        head_sha = "c" * 40
        event = _make_pr_event(
            action="synchronize",
            head_sha=head_sha,
            delivery_id="delivery-pr-002",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, head_sha)
        _mock_compare(httpx_mock, "main", head_sha, ["services/order-processor/main.py"])
        # upsert_plan_comment -> find_plan_comment (GET) -> PATCH
        _mock_find_existing_plan_comment(httpx_mock)
        _mock_update_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"
        assert body["affected"] == 1

        # Verify PATCH was used to update existing comment
        requests = httpx_mock.get_requests()
        patch_reqs = [r for r in requests if r.method == "PATCH"]
        assert len(patch_reqs) == 1
        assert "/issues/comments/50" in str(patch_reqs[0].url)

    def test_pr_opened_no_changes_no_comment_neutral_check(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """PR opened, no changes, no existing comment -> silent + neutral check run."""
        head_sha = "d" * 40
        event = _make_pr_event(
            action="opened",
            head_sha=head_sha,
            delivery_id="delivery-pr-003",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, head_sha, yaml_b64=FERRY_YAML_B64)
        _mock_compare(httpx_mock, "main", head_sha, ["unrelated/readme.md"])
        # find_plan_comment: no existing comment
        _mock_find_no_plan_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"
        assert body["affected"] == 0

        # Verify NO plan comment was posted (no POST to issues)
        requests = httpx_mock.get_requests()
        comment_posts = [r for r in requests if r.method == "POST" and "/issues/" in str(r.url)]
        assert len(comment_posts) == 0

        # Verify check run was posted with neutral conclusion
        check_reqs = [r for r in requests if "check-runs" in str(r.url)]
        assert len(check_reqs) == 1
        check_body = json.loads(check_reqs[0].content)
        assert check_body["conclusion"] == "neutral"

    def test_pr_synchronize_no_changes_updates_existing_comment(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """PR sync, no changes, existing plan comment -> update to no-changes."""
        head_sha = "e" * 40
        event = _make_pr_event(
            action="synchronize",
            head_sha=head_sha,
            delivery_id="delivery-pr-004",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, head_sha, yaml_b64=FERRY_YAML_B64)
        _mock_compare(httpx_mock, "main", head_sha, ["unrelated/readme.md"])
        # 1st GET: handler calls find_plan_comment -> finds existing
        _mock_find_existing_plan_comment(httpx_mock)
        # 2nd GET: upsert_plan_comment calls find_plan_comment again -> finds existing
        _mock_find_existing_plan_comment(httpx_mock)
        # PATCH: upsert updates existing comment
        _mock_update_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"
        assert body["affected"] == 0

        # Verify PATCH was used to update existing comment
        requests = httpx_mock.get_requests()
        patch_reqs = [r for r in requests if r.method == "PATCH"]
        assert len(patch_reqs) == 1

    def test_pr_with_environment_shows_env_in_comment(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """PR targeting a mapped branch shows environment in plan comment."""
        head_sha = "f" * 40
        event = _make_pr_event(
            action="opened",
            head_sha=head_sha,
            base_ref="main",
            delivery_id="delivery-pr-005",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, head_sha, yaml_b64=FERRY_YAML_WITH_ENVS_B64)
        _mock_compare(httpx_mock, "main", head_sha, ["services/order-processor/main.py"])
        _mock_find_no_plan_comment(httpx_mock)
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"
        assert body["affected"] == 1

        # Verify the comment body includes environment info
        requests = httpx_mock.get_requests()
        comment_posts = [
            r for r in requests if r.method == "POST" and "/issues/42/comments" in str(r.url)
        ]
        assert len(comment_posts) == 1
        comment_body = json.loads(comment_posts[0].content)["body"]
        assert "production" in comment_body
        assert "manual deployment" in comment_body  # auto_deploy=False

    def test_pr_unsupported_action_ignored(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """PR with unsupported action (e.g. closed) -> ignored."""
        head_sha = "g" * 40
        event = _make_pr_event(
            action="closed",
            head_sha=head_sha,
            delivery_id="delivery-pr-006",
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "ignored"

    def test_pr_config_error_posts_error_comment(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """PR with invalid ferry.yaml -> error comment via upsert."""
        head_sha = "h" * 40
        event = _make_pr_event(
            action="opened",
            head_sha=head_sha,
            delivery_id="delivery-pr-007",
        )

        _mock_installation_token(httpx_mock)
        # Return 404 (no ferry.yaml) to trigger ConfigError
        httpx_mock.add_response(
            url=f"https://api.github.com/repos/owner/repo/contents/ferry.yaml?ref={head_sha}",
            status_code=404,
            json={"message": "Not Found"},
        )
        # upsert_plan_comment: find (no existing) + create
        _mock_find_no_plan_comment(httpx_mock)
        _mock_create_comment(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "config_error"

        # Verify error comment was posted
        requests = httpx_mock.get_requests()
        comment_posts = [r for r in requests if r.method == "POST" and "/issues/" in str(r.url)]
        assert len(comment_posts) == 1
        comment_body = json.loads(comment_posts[0].content)["body"]
        assert "Configuration Error" in comment_body

    def test_pr_no_dispatch_triggered(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """PR events never trigger workflow dispatches."""
        head_sha = "i" * 40
        event = _make_pr_event(
            action="opened",
            head_sha=head_sha,
            delivery_id="delivery-pr-008",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, head_sha)
        _mock_compare(httpx_mock, "main", head_sha, ["services/order-processor/main.py"])
        _mock_find_no_plan_comment(httpx_mock)
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"

        # Verify NO dispatch was triggered
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 0

    def test_pr_reopened_posts_comment(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """PR reopened -> posts plan comment (treated like opened)."""
        head_sha = "j" * 40
        event = _make_pr_event(
            action="reopened",
            head_sha=head_sha,
            delivery_id="delivery-pr-009",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, head_sha)
        _mock_compare(httpx_mock, "main", head_sha, ["services/order-processor/main.py"])
        _mock_find_no_plan_comment(httpx_mock)
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"
        assert body["affected"] == 1

    def test_pr_uses_base_branch_for_compare(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """PR uses base branch (not before_sha) for compare API."""
        head_sha = "k" * 40
        event = _make_pr_event(
            action="opened",
            head_sha=head_sha,
            base_ref="develop",
            delivery_id="delivery-pr-010",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, head_sha)
        # Compare should use "develop" (base_ref) not a SHA
        _mock_compare(httpx_mock, "develop", head_sha, ["services/order-processor/main.py"])
        _mock_find_no_plan_comment(httpx_mock)
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"

        # Verify compare API was called with base branch
        requests = httpx_mock.get_requests()
        compare_reqs = [r for r in requests if "compare" in str(r.url)]
        assert len(compare_reqs) == 1
        compare_url = str(compare_reqs[0].url)
        assert f"compare/develop...{head_sha}" in compare_url

    def test_pr_duplicate_delivery_returns_duplicate(
        self,
        dynamodb_env,
        httpx_mock,
    ):
        """Duplicate PR delivery returns duplicate status."""
        head_sha = "m" * 40
        event = _make_pr_event(
            action="opened",
            head_sha=head_sha,
            delivery_id="delivery-pr-dup",
        )

        _mock_installation_token(httpx_mock)
        _mock_ferry_config(httpx_mock, head_sha)
        _mock_compare(httpx_mock, "main", head_sha, ["services/order-processor/main.py"])
        _mock_find_no_plan_comment(httpx_mock)
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        # First delivery processes normally
        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"

        # Second delivery with same ID is duplicate
        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "duplicate"
