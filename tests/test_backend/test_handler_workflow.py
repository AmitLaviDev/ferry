"""Integration tests for workflow_run event handling (deploy status updates).

Tests the complete workflow_run pipeline: auth -> fetch run -> find deploy comment -> update.
Uses pytest-httpx to mock ALL GitHub API calls and moto for DynamoDB.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import boto3
import pytest
from moto import mock_aws

from ferry_backend.checks.plan import DEPLOY_MARKER_TEMPLATE, SHA_MARKER_TEMPLATE

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
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(autouse=True)
def _mock_jwt(monkeypatch):
    monkeypatch.setattr(
        "ferry_backend.webhook.handler.generate_app_jwt",
        lambda app_id, pk: "fake-jwt",
    )


@pytest.fixture
def dynamodb_env():
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
    mac = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    )
    return f"sha256={mac.hexdigest()}"


def _make_workflow_run_event(
    run_id: int = 12345,
    conclusion: str = "success",
    event: str = "workflow_dispatch",
    path: str = ".github/workflows/ferry.yml",
    action: str = "completed",
    delivery_id: str = "delivery-wr-001",
    head_sha: str = "abc123",
) -> dict:
    """Build a Lambda Function URL event dict for a workflow_run webhook."""
    payload = {
        "action": action,
        "workflow_run": {
            "id": run_id,
            "conclusion": conclusion,
            "event": event,
            "path": path,
            "head_sha": head_sha,
            "html_url": f"https://github.com/owner/repo/actions/runs/{run_id}",
        },
        "repository": {
            "full_name": "owner/repo",
            "default_branch": "main",
        },
    }
    body_str = json.dumps(payload)
    signature = _make_signature(body_str)
    return {
        "body": body_str,
        "isBase64Encoded": False,
        "headers": {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": "workflow_run",
            "Content-Type": "application/json",
        },
    }


def _mock_installation_token(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/app/installations/12345/access_tokens",
        json={"token": "ghs_test_token_123"},
        status_code=201,
    )


def _mock_commits_pulls(httpx_mock, trigger_sha="abc123", pr_number=42, state="open"):
    """Mock GET /repos/{repo}/commits/{sha}/pulls returning associated PRs."""
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/commits/{trigger_sha}/pulls",
        json=[
            {
                "number": pr_number,
                "state": state,
                "merged_at": None if state == "open" else "2026-01-01T00:00:00Z",
            }
        ],
    )


def _mock_commits_pulls_empty(httpx_mock, trigger_sha="abc123"):
    """Mock GET /repos/{repo}/commits/{sha}/pulls returning no PRs."""
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/commits/{trigger_sha}/pulls",
        json=[],
    )


def _mock_find_deploy_comment(httpx_mock, pr_number=42, trigger_sha="abc123", comment_id=300):
    """Mock paginated GET returning a comment with deploy+sha markers."""
    deploy_marker = DEPLOY_MARKER_TEMPLATE.format(pr_number=pr_number)
    sha_marker = SHA_MARKER_TEMPLATE.format(sha=trigger_sha)
    deploy_body = (
        f"{deploy_marker}\n{sha_marker}\n"
        f"## \U0001f6a2 Ferry: Deploying \u2192 **default** at `{trigger_sha[:7]}`\n\n"
        "| Type | Resource | Status |\n"
        "|------|----------|--------|\n"
        "| Lambda | **order** | \u23f3 |"
    )
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/issues/{pr_number}/comments?per_page=100&page=1",
        json=[{"id": comment_id, "body": deploy_body}],
    )


def _mock_find_no_deploy_comment(httpx_mock, pr_number=42):
    """Mock paginated GET returning no deploy comment."""
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/issues/{pr_number}/comments?per_page=100&page=1",
        json=[],
    )


def _mock_update_deploy_comment(httpx_mock, comment_id=300):
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/issues/comments/{comment_id}",
        json={"id": comment_id, "body": "updated"},
    )


class TestWorkflowRun:
    def test_completed_success_updates_deploy_comment(self, dynamodb_env, httpx_mock):
        """workflow_run completed success -> finds PR via commit, finds comment, PATCHes."""
        trigger_sha = "abc123"
        event = _make_workflow_run_event(conclusion="success", head_sha=trigger_sha)

        _mock_installation_token(httpx_mock)
        _mock_commits_pulls(httpx_mock, trigger_sha=trigger_sha)
        _mock_find_deploy_comment(httpx_mock, trigger_sha=trigger_sha)
        _mock_update_deploy_comment(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"
        assert body["conclusion"] == "success"

        # Verify PATCH to update deploy comment
        requests = httpx_mock.get_requests()
        patch_reqs = [r for r in requests if r.method == "PATCH"]
        assert len(patch_reqs) == 1
        patched_body = json.loads(patch_reqs[0].content)["body"]
        assert "Deployed \u2192" in patched_body
        assert "\u2705" in patched_body
        assert "`success`" in patched_body
        assert "View run" in patched_body

    def test_completed_failure_updates_deploy_comment(self, dynamodb_env, httpx_mock):
        """workflow_run completed failure -> PATCHes with failure status."""
        trigger_sha = "def456"
        event = _make_workflow_run_event(
            conclusion="failure", delivery_id="delivery-wr-002", head_sha=trigger_sha
        )

        _mock_installation_token(httpx_mock)
        _mock_commits_pulls(httpx_mock, trigger_sha=trigger_sha)
        _mock_find_deploy_comment(httpx_mock, trigger_sha=trigger_sha)
        _mock_update_deploy_comment(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["conclusion"] == "failure"

        requests = httpx_mock.get_requests()
        patch_reqs = [r for r in requests if r.method == "PATCH"]
        assert len(patch_reqs) == 1
        patched_body = json.loads(patch_reqs[0].content)["body"]
        assert "Deploy Failed \u2192" in patched_body
        assert "\u274c" in patched_body
        assert "`failure`" in patched_body

    def test_non_dispatch_run_ignored(self, dynamodb_env, httpx_mock):
        """workflow_run with event=push -> ignored."""
        event = _make_workflow_run_event(event="push", delivery_id="delivery-wr-003")

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "ignored"
        assert "not dispatch" in body["reason"]

    def test_non_ferry_workflow_ignored(self, dynamodb_env, httpx_mock):
        """workflow_run with path='.github/workflows/ci.yml' -> ignored."""
        event = _make_workflow_run_event(
            path=".github/workflows/ci.yml", delivery_id="delivery-wr-004"
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "ignored"
        assert "not ferry" in body["reason"]

    def test_action_requested_ignored(self, dynamodb_env, httpx_mock):
        """workflow_run with action=requested -> ignored."""
        event = _make_workflow_run_event(action="requested", delivery_id="delivery-wr-005")

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "ignored"
        assert "not completed" in body["reason"]

    def test_no_correlation_data_ignored(self, dynamodb_env, httpx_mock):
        """workflow_run where commit has no associated PRs -> ignored."""
        trigger_sha = "orphan123"
        event = _make_workflow_run_event(delivery_id="delivery-wr-006", head_sha=trigger_sha)

        _mock_installation_token(httpx_mock)
        _mock_commits_pulls_empty(httpx_mock, trigger_sha=trigger_sha)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "ignored"
        assert "no correlation" in body["reason"]

    def test_deploy_comment_not_found_logs_warning(self, dynamodb_env, httpx_mock):
        """workflow_run where no deploy comment exists -> processes without error."""
        trigger_sha = "ghi789"
        event = _make_workflow_run_event(delivery_id="delivery-wr-007", head_sha=trigger_sha)

        _mock_installation_token(httpx_mock)
        _mock_commits_pulls(httpx_mock, trigger_sha=trigger_sha)
        _mock_find_no_deploy_comment(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"

        # No PATCH should have been made
        requests = httpx_mock.get_requests()
        patch_reqs = [r for r in requests if r.method == "PATCH"]
        assert len(patch_reqs) == 0

    def test_sha_mismatch_skips_update(self, dynamodb_env, httpx_mock):
        """workflow_run where deploy comment has different SHA -> no update."""
        trigger_sha = "abc123"
        event = _make_workflow_run_event(delivery_id="delivery-wr-008", head_sha=trigger_sha)

        _mock_installation_token(httpx_mock)
        _mock_commits_pulls(httpx_mock, trigger_sha=trigger_sha)
        # Deploy comment has a DIFFERENT sha (newer /ferry apply ran)
        _mock_find_deploy_comment(httpx_mock, trigger_sha="def456def456789")

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"

        # No PATCH should have been made
        requests = httpx_mock.get_requests()
        patch_reqs = [r for r in requests if r.method == "PATCH"]
        assert len(patch_reqs) == 0
