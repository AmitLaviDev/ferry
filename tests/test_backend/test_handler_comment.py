"""Integration tests for issue_comment event handling (/ferry plan and /ferry apply).

Tests the complete comment pipeline: auth -> command parse -> change detect ->
plan comment / dispatch + apply comment + check run.
Uses pytest-httpx to mock ALL GitHub API calls and moto for DynamoDB.
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

# Minimal ferry.yaml with one lambda
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
    mac = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    )
    return f"sha256={mac.hexdigest()}"


def _make_issue_comment_event(
    body: str = "/ferry plan",
    pr_number: int = 42,
    comment_id: int = 99,
    is_pr: bool = True,
    state: str = "open",
    delivery_id: str = "delivery-ic-001",
) -> dict:
    """Build a Lambda Function URL event dict for an issue_comment webhook."""
    issue: dict = {
        "number": pr_number,
        "state": state,
    }
    if is_pr:
        issue["pull_request"] = {
            "url": f"https://api.github.com/repos/owner/repo/pulls/{pr_number}"
        }

    payload = {
        "action": "created",
        "issue": issue,
        "comment": {"id": comment_id, "body": body},
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
            "X-GitHub-Event": "issue_comment",
            "Content-Type": "application/json",
        },
    }


def _make_issue_comment_event_with_action(
    action: str = "created",
    body: str = "/ferry plan",
    pr_number: int = 42,
    comment_id: int = 99,
    delivery_id: str = "delivery-ic-001",
) -> dict:
    """Build event with a specific action (e.g. edited, deleted)."""
    payload = {
        "action": action,
        "issue": {
            "number": pr_number,
            "state": "open",
            "pull_request": {"url": "..."},
        },
        "comment": {"id": comment_id, "body": body},
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
            "X-GitHub-Event": "issue_comment",
            "Content-Type": "application/json",
        },
    }


def _mock_installation_token(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/app/installations/12345/access_tokens",
        json={"token": "ghs_test_token_123"},
        status_code=201,
    )


def _mock_reaction(httpx_mock, comment_id=99):
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/issues/comments/{comment_id}/reactions",
        json={"id": 1, "content": "rocket"},
        status_code=201,
    )


def _mock_fetch_pr(
    httpx_mock, pr_number=42, head_sha="a" * 40, base_branch="main", head_branch="feature-branch"
):
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/pulls/{pr_number}",
        json={
            "number": pr_number,
            "head": {"sha": head_sha, "ref": head_branch},
            "base": {"ref": base_branch},
            "state": "open",
        },
    )


def _mock_ferry_config(httpx_mock, sha, yaml_b64=None):
    if yaml_b64 is None:
        yaml_b64 = FERRY_YAML_B64
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/contents/ferry.yaml?ref={sha}",
        json={"content": yaml_b64},
        status_code=200,
    )


def _mock_compare(httpx_mock, base, head, files):
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/compare/{base}...{head}",
        json={
            "files": [{"filename": f, "status": "modified"} for f in files],
        },
    )


def _mock_check_run(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/check-runs",
        json={"id": 1, "status": "completed"},
        status_code=201,
    )


def _mock_create_comment(httpx_mock, pr_number=42):
    httpx_mock.add_response(
        url=f"https://api.github.com/repos/owner/repo/issues/{pr_number}/comments",
        json={"id": 200, "body": "comment posted"},
        status_code=201,
    )


def _mock_dispatch(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches",
        status_code=204,
    )


class TestIssuePlan:
    def test_plan_on_pr_with_changes_posts_comment(self, dynamodb_env, httpx_mock):
        """/ferry plan on open PR with changes -> rocket + plan comment + check run."""
        head_sha = "a" * 40
        event = _make_issue_comment_event(body="/ferry plan")

        _mock_installation_token(httpx_mock)
        _mock_reaction(httpx_mock)
        _mock_fetch_pr(httpx_mock, head_sha=head_sha)
        _mock_ferry_config(httpx_mock, head_sha)
        _mock_compare(httpx_mock, "main", head_sha, ["services/order-processor/main.py"])
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"
        assert body["command"] == "plan"
        assert body["affected"] == 1

        # Verify rocket reaction
        requests = httpx_mock.get_requests()
        reaction_reqs = [r for r in requests if "reactions" in str(r.url)]
        assert len(reaction_reqs) == 1
        reaction_body = json.loads(reaction_reqs[0].content)
        assert reaction_body["content"] == "rocket"

        # Verify plan comment posted
        comment_posts = [
            r for r in requests if r.method == "POST" and "/issues/42/comments" in str(r.url)
        ]
        assert len(comment_posts) == 1
        comment_body = json.loads(comment_posts[0].content)["body"]
        assert "Deployment Plan" in comment_body

        # Verify check run
        check_reqs = [r for r in requests if "check-runs" in str(r.url)]
        assert len(check_reqs) == 1

    def test_plan_on_pr_no_changes_posts_no_changes(self, dynamodb_env, httpx_mock):
        """/ferry plan with no affected resources -> no-changes comment + neutral check."""
        head_sha = "b" * 40
        event = _make_issue_comment_event(body="/ferry plan", delivery_id="delivery-ic-002")

        _mock_installation_token(httpx_mock)
        _mock_reaction(httpx_mock)
        _mock_fetch_pr(httpx_mock, head_sha=head_sha)
        _mock_ferry_config(httpx_mock, head_sha)
        _mock_compare(httpx_mock, "main", head_sha, ["unrelated/readme.md"])
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"
        assert body["affected"] == 0

        # Verify no-changes comment
        requests = httpx_mock.get_requests()
        comment_posts = [
            r for r in requests if r.method == "POST" and "/issues/42/comments" in str(r.url)
        ]
        assert len(comment_posts) == 1
        posted_body = json.loads(comment_posts[0].content)["body"]
        assert "No Ferry-managed resources" in posted_body

    def test_plan_on_closed_pr_posts_refusal(self, dynamodb_env, httpx_mock):
        """/ferry plan on closed PR -> rocket + refusal comment, no change detection."""
        event = _make_issue_comment_event(
            body="/ferry plan", state="closed", delivery_id="delivery-ic-003"
        )

        _mock_installation_token(httpx_mock)
        _mock_reaction(httpx_mock)
        _mock_create_comment(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "refused"

        # Verify refusal comment
        requests = httpx_mock.get_requests()
        comment_posts = [
            r for r in requests if r.method == "POST" and "/issues/42/comments" in str(r.url)
        ]
        assert len(comment_posts) == 1
        posted_body = json.loads(comment_posts[0].content)["body"]
        assert "not open" in posted_body

    def test_plan_on_issue_silently_ignored(self, dynamodb_env, httpx_mock):
        """/ferry plan on a non-PR issue -> 200, ignored, no API calls beyond sig."""
        event = _make_issue_comment_event(
            body="/ferry plan", is_pr=False, delivery_id="delivery-ic-004"
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "ignored"
        assert "issue" in body["reason"]

    def test_plan_case_insensitive(self, dynamodb_env, httpx_mock):
        """/Ferry Plan is accepted."""
        head_sha = "c" * 40
        event = _make_issue_comment_event(body="/Ferry Plan", delivery_id="delivery-ic-005")

        _mock_installation_token(httpx_mock)
        _mock_reaction(httpx_mock)
        _mock_fetch_pr(httpx_mock, head_sha=head_sha)
        _mock_ferry_config(httpx_mock, head_sha)
        _mock_compare(httpx_mock, "main", head_sha, ["services/order-processor/main.py"])
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"
        assert body["command"] == "plan"

    def test_non_ferry_comment_ignored(self, dynamodb_env, httpx_mock):
        """Regular comment -> 200, ignored."""
        event = _make_issue_comment_event(body="hello world", delivery_id="delivery-ic-006")

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "ignored"
        assert "not a ferry command" in body["reason"]

    def test_comment_edited_ignored(self, dynamodb_env, httpx_mock):
        """action=edited -> 200, ignored."""
        event = _make_issue_comment_event_with_action(
            action="edited", delivery_id="delivery-ic-007"
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "ignored"


class TestIssueApply:
    def test_apply_on_pr_with_changes_triggers_dispatch(self, dynamodb_env, httpx_mock):
        """/ferry apply on open PR -> rocket + dispatch + apply comment + check run."""
        head_sha = "d" * 40
        event = _make_issue_comment_event(body="/ferry apply", delivery_id="delivery-ic-010")

        _mock_installation_token(httpx_mock)
        _mock_reaction(httpx_mock)
        _mock_fetch_pr(httpx_mock, head_sha=head_sha)
        _mock_ferry_config(httpx_mock, head_sha)
        _mock_compare(httpx_mock, "main", head_sha, ["services/order-processor/main.py"])
        _mock_dispatch(httpx_mock)
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "processed"
        assert body["command"] == "apply"
        assert body["affected"] == 1

        # Verify dispatch was triggered
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 1
        dispatch_body = json.loads(dispatch_reqs[0].content)
        payload_json = dispatch_body["inputs"]["payload"]
        from ferry_utils.models.dispatch import BatchedDispatchPayload

        payload = BatchedDispatchPayload.model_validate_json(payload_json)
        assert payload.mode == "deploy"

    def test_apply_uses_environment(self, dynamodb_env, httpx_mock):
        """/ferry apply on PR targeting 'main' -> dispatch has environment='production'."""
        head_sha = "e" * 40
        event = _make_issue_comment_event(body="/ferry apply", delivery_id="delivery-ic-011")

        _mock_installation_token(httpx_mock)
        _mock_reaction(httpx_mock)
        _mock_fetch_pr(httpx_mock, head_sha=head_sha, base_branch="main")
        _mock_ferry_config(httpx_mock, head_sha, yaml_b64=FERRY_YAML_WITH_ENVS_B64)
        _mock_compare(httpx_mock, "main", head_sha, ["services/order-processor/main.py"])
        _mock_dispatch(httpx_mock)
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"

        # Verify dispatch payload has environment
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 1
        dispatch_body = json.loads(dispatch_reqs[0].content)
        from ferry_utils.models.dispatch import BatchedDispatchPayload

        payload = BatchedDispatchPayload.model_validate_json(dispatch_body["inputs"]["payload"])
        assert payload.environment == "production"

    def test_apply_no_changes_refuses_dispatch(self, dynamodb_env, httpx_mock):
        """/ferry apply with no affected resources -> no dispatch, 'nothing to deploy'."""
        head_sha = "f" * 40
        event = _make_issue_comment_event(body="/ferry apply", delivery_id="delivery-ic-012")

        _mock_installation_token(httpx_mock)
        _mock_reaction(httpx_mock)
        _mock_fetch_pr(httpx_mock, head_sha=head_sha)
        _mock_ferry_config(httpx_mock, head_sha)
        _mock_compare(httpx_mock, "main", head_sha, ["unrelated/readme.md"])
        _mock_create_comment(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"
        assert body["affected"] == 0

        # Verify no dispatch
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 0

        # Verify "nothing to deploy" comment
        comment_posts = [
            r for r in requests if r.method == "POST" and "/issues/42/comments" in str(r.url)
        ]
        assert len(comment_posts) == 1
        posted_body = json.loads(comment_posts[0].content)["body"]
        assert "nothing to deploy" in posted_body

    def test_apply_on_closed_pr_posts_refusal(self, dynamodb_env, httpx_mock):
        """/ferry apply on closed PR -> refusal, no dispatch."""
        event = _make_issue_comment_event(
            body="/ferry apply", state="closed", delivery_id="delivery-ic-013"
        )

        _mock_installation_token(httpx_mock)
        _mock_reaction(httpx_mock)
        _mock_create_comment(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "refused"

        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 0

    def test_apply_on_issue_ignored(self, dynamodb_env, httpx_mock):
        """/ferry apply on non-PR issue -> silently ignored (DEPLOY-04)."""
        event = _make_issue_comment_event(
            body="/ferry apply", is_pr=False, delivery_id="delivery-ic-014"
        )

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "ignored"

    def test_apply_fetches_fresh_head_sha(self, dynamodb_env, httpx_mock):
        """Head SHA in dispatch matches GET /pulls response, not webhook payload."""
        fresh_sha = "d" * 40
        event = _make_issue_comment_event(body="/ferry apply", delivery_id="delivery-ic-015")

        _mock_installation_token(httpx_mock)
        _mock_reaction(httpx_mock)
        _mock_fetch_pr(httpx_mock, head_sha=fresh_sha, base_branch="main")
        _mock_ferry_config(httpx_mock, fresh_sha)
        _mock_compare(httpx_mock, "main", fresh_sha, ["services/order-processor/main.py"])
        _mock_dispatch(httpx_mock)
        _mock_create_comment(httpx_mock)
        _mock_check_run(httpx_mock)

        from ferry_backend.webhook.handler import handler

        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "processed"

        # Verify the dispatch payload uses the fresh SHA
        requests = httpx_mock.get_requests()
        dispatch_reqs = [r for r in requests if "dispatches" in str(r.url)]
        assert len(dispatch_reqs) == 1
        dispatch_body = json.loads(dispatch_reqs[0].content)
        from ferry_utils.models.dispatch import BatchedDispatchPayload

        payload = BatchedDispatchPayload.model_validate_json(dispatch_body["inputs"]["payload"])
        assert payload.trigger_sha == fresh_sha
