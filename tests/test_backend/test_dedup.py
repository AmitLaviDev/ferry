"""Tests for DynamoDB dual-key deduplication.

Tests cover:
- First delivery with unique delivery_id is not duplicate
- Same delivery_id again is duplicate
- New delivery_id but same repo+SHA (re-queued event) is duplicate
- Missing repo/SHA in payload skips event-level dedup
- TTL field set on all records
"""

import time

import boto3
import pytest
from moto import mock_aws

from ferry_backend.webhook.dedup import is_duplicate

TABLE_NAME = "ferry-state"


@pytest.fixture
def dynamodb_client():
    """Create a mocked DynamoDB table for dedup testing."""
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
        client.update_time_to_live(
            TableName=TABLE_NAME,
            TimeToLiveSpecification={
                "Enabled": True,
                "AttributeName": "expires_at",
            },
        )
        yield client


PUSH_PAYLOAD = {
    "ref": "refs/heads/main",
    "after": "abc123def456",
    "repository": {
        "full_name": "owner/repo",
    },
}

ISSUE_COMMENT_PAYLOAD = {
    "action": "created",
    "issue": {"number": 42, "state": "open", "pull_request": {"url": "..."}},
    "comment": {"id": 99, "body": "/ferry plan"},
    "repository": {"full_name": "owner/repo"},
}

WORKFLOW_RUN_PAYLOAD = {
    "action": "completed",
    "workflow_run": {"id": 12345, "event": "workflow_dispatch", "conclusion": "success"},
    "repository": {"full_name": "owner/repo"},
}

PR_PAYLOAD = {
    "action": "opened",
    "number": 42,
    "pull_request": {
        "number": 42,
        "head": {"sha": "pr_head_sha_123"},
        "base": {"ref": "main"},
    },
    "repository": {
        "full_name": "owner/repo",
    },
}


class TestIsDuplicate:
    def test_first_delivery_is_not_duplicate(self, dynamodb_client):
        result = is_duplicate("delivery-001", PUSH_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is False

    def test_same_delivery_id_is_duplicate(self, dynamodb_client):
        is_duplicate("delivery-001", PUSH_PAYLOAD, TABLE_NAME, dynamodb_client)
        result = is_duplicate("delivery-001", PUSH_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is True

    def test_requeued_event_new_delivery_id_same_repo_sha_is_duplicate(self, dynamodb_client):
        """GitHub can re-queue with a new delivery ID but same event content."""
        is_duplicate("delivery-001", PUSH_PAYLOAD, TABLE_NAME, dynamodb_client)
        result = is_duplicate("delivery-002", PUSH_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is True

    def test_missing_repo_in_payload_skips_event_dedup(self, dynamodb_client):
        """Without repo/SHA, only delivery-level dedup applies."""
        payload_no_repo = {"ref": "refs/heads/main"}
        result = is_duplicate("delivery-001", payload_no_repo, TABLE_NAME, dynamodb_client)
        assert result is False
        # Second call with same delivery ID should still be caught
        result = is_duplicate("delivery-001", payload_no_repo, TABLE_NAME, dynamodb_client)
        assert result is True

    def test_different_repo_different_sha_is_not_duplicate(self, dynamodb_client):
        """Different events should not be flagged as duplicates."""
        payload_other = {
            "ref": "refs/heads/main",
            "after": "different_sha_789",
            "repository": {"full_name": "other-owner/other-repo"},
        }
        is_duplicate("delivery-001", PUSH_PAYLOAD, TABLE_NAME, dynamodb_client)
        result = is_duplicate("delivery-002", payload_other, TABLE_NAME, dynamodb_client)
        assert result is False

    def test_ttl_set_on_records(self, dynamodb_client):
        """Records should have expires_at TTL field set to ~24 hours from now."""
        is_duplicate("delivery-ttl", PUSH_PAYLOAD, TABLE_NAME, dynamodb_client)

        response = dynamodb_client.get_item(
            TableName=TABLE_NAME,
            Key={
                "pk": {"S": "DELIVERY#delivery-ttl"},
                "sk": {"S": "METADATA"},
            },
        )
        item = response["Item"]
        expires_at = int(item["expires_at"]["N"])
        now = int(time.time())
        # TTL should be approximately 24 hours from now (within 10 second tolerance)
        assert abs(expires_at - (now + 86400)) < 10


class TestIsDuplicatePR:
    """Deduplication tests for pull_request event payloads."""

    def test_first_pr_delivery_is_not_duplicate(self, dynamodb_client):
        result = is_duplicate("delivery-pr-001", PR_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is False

    def test_same_pr_delivery_is_duplicate(self, dynamodb_client):
        is_duplicate("delivery-pr-001", PR_PAYLOAD, TABLE_NAME, dynamodb_client)
        result = is_duplicate("delivery-pr-001", PR_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is True

    def test_requeued_pr_event_is_duplicate(self, dynamodb_client):
        """Re-queued PR event with new delivery ID but same PR+SHA is duplicate."""
        is_duplicate("delivery-pr-001", PR_PAYLOAD, TABLE_NAME, dynamodb_client)
        result = is_duplicate("delivery-pr-002", PR_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is True

    def test_different_head_sha_is_not_duplicate(self, dynamodb_client):
        """PR with different head SHA (new push) is not a duplicate."""
        is_duplicate("delivery-pr-001", PR_PAYLOAD, TABLE_NAME, dynamodb_client)
        pr_payload_new_sha = {
            **PR_PAYLOAD,
            "pull_request": {
                **PR_PAYLOAD["pull_request"],
                "head": {"sha": "new_head_sha_456"},
            },
        }
        result = is_duplicate("delivery-pr-002", pr_payload_new_sha, TABLE_NAME, dynamodb_client)
        assert result is False

    def test_pr_and_push_keys_are_isolated(self, dynamodb_client):
        """PR and push dedup keys do not interfere with each other."""
        # A push payload with the same repo should not collide with a PR payload
        is_duplicate("delivery-001", PUSH_PAYLOAD, TABLE_NAME, dynamodb_client)
        result = is_duplicate("delivery-pr-001", PR_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is False


class TestIsDuplicateIssueComment:
    """Deduplication tests for issue_comment event payloads."""

    def test_first_comment_is_not_duplicate(self, dynamodb_client):
        result = is_duplicate("delivery-ic-001", ISSUE_COMMENT_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is False

    def test_same_comment_id_is_duplicate(self, dynamodb_client):
        """Different delivery ID but same comment_id is event-level duplicate."""
        is_duplicate("delivery-ic-001", ISSUE_COMMENT_PAYLOAD, TABLE_NAME, dynamodb_client)
        result = is_duplicate("delivery-ic-002", ISSUE_COMMENT_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is True

    def test_different_comment_id_is_not_duplicate(self, dynamodb_client):
        is_duplicate("delivery-ic-001", ISSUE_COMMENT_PAYLOAD, TABLE_NAME, dynamodb_client)
        other = {
            **ISSUE_COMMENT_PAYLOAD,
            "comment": {"id": 100, "body": "/ferry apply"},
        }
        result = is_duplicate("delivery-ic-002", other, TABLE_NAME, dynamodb_client)
        assert result is False


class TestIsDuplicateWorkflowRun:
    """Deduplication tests for workflow_run event payloads."""

    def test_first_run_is_not_duplicate(self, dynamodb_client):
        result = is_duplicate("delivery-wr-001", WORKFLOW_RUN_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is False

    def test_same_run_id_is_duplicate(self, dynamodb_client):
        is_duplicate("delivery-wr-001", WORKFLOW_RUN_PAYLOAD, TABLE_NAME, dynamodb_client)
        result = is_duplicate("delivery-wr-002", WORKFLOW_RUN_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is True

    def test_different_run_id_is_not_duplicate(self, dynamodb_client):
        is_duplicate("delivery-wr-001", WORKFLOW_RUN_PAYLOAD, TABLE_NAME, dynamodb_client)
        other = {
            **WORKFLOW_RUN_PAYLOAD,
            "workflow_run": {**WORKFLOW_RUN_PAYLOAD["workflow_run"], "id": 99999},
        }
        result = is_duplicate("delivery-wr-002", other, TABLE_NAME, dynamodb_client)
        assert result is False


class TestIsDuplicateEventIsolation:
    """Cross-event-type dedup isolation tests."""

    def test_comment_and_push_keys_isolated(self, dynamodb_client):
        """issue_comment dedup does not conflict with push dedup."""
        is_duplicate("delivery-001", PUSH_PAYLOAD, TABLE_NAME, dynamodb_client)
        result = is_duplicate("delivery-ic-001", ISSUE_COMMENT_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is False

    def test_comment_and_pr_keys_isolated(self, dynamodb_client):
        """issue_comment dedup does not conflict with pull_request dedup."""
        is_duplicate("delivery-pr-001", PR_PAYLOAD, TABLE_NAME, dynamodb_client)
        result = is_duplicate("delivery-ic-001", ISSUE_COMMENT_PAYLOAD, TABLE_NAME, dynamodb_client)
        assert result is False
