"""Tests for webhook event Pydantic models."""

import pytest
from pydantic import ValidationError

from ferry_utils.models.webhook import Pusher, PushEvent, Repository, WebhookHeaders


class TestWebhookHeaders:
    def test_valid_headers(self):
        headers = WebhookHeaders(
            event_type="push",
            delivery_id="72d3162e-cc78-11e3-81ab-4c9367dc0958",
            signature="sha256=abc123",
        )
        assert headers.event_type == "push"
        assert headers.delivery_id == "72d3162e-cc78-11e3-81ab-4c9367dc0958"
        assert headers.signature == "sha256=abc123"

    def test_frozen_headers_reject_mutation(self):
        headers = WebhookHeaders(
            event_type="push",
            delivery_id="delivery-1",
            signature="sha256=abc",
        )
        with pytest.raises(ValidationError):
            headers.event_type = "pull_request"

    def test_headers_from_raw_dict(self):
        """Simulate extracting headers from a raw HTTP header dict."""
        raw_headers = {
            "x-github-event": "push",
            "x-github-delivery": "72d3162e-cc78-11e3-81ab-4c9367dc0958",
            "x-hub-signature-256": "sha256=abc123def456",
        }
        headers = WebhookHeaders(
            event_type=raw_headers["x-github-event"],
            delivery_id=raw_headers["x-github-delivery"],
            signature=raw_headers["x-hub-signature-256"],
        )
        assert headers.event_type == "push"
        assert headers.delivery_id == "72d3162e-cc78-11e3-81ab-4c9367dc0958"
        assert headers.signature == "sha256=abc123def456"


class TestRepository:
    def test_valid_repository(self):
        repo = Repository(full_name="octocat/hello-world", default_branch="main")
        assert repo.full_name == "octocat/hello-world"
        assert repo.default_branch == "main"

    def test_missing_full_name_fails(self):
        with pytest.raises(ValidationError, match="full_name"):
            Repository(default_branch="main")  # type: ignore[call-arg]


class TestPusher:
    def test_valid_pusher(self):
        pusher = Pusher(name="octocat")
        assert pusher.name == "octocat"


class TestPushEvent:
    def test_parse_push_event_payload(self):
        """Test parsing a realistic GitHub push event payload structure."""
        raw_payload = {
            "ref": "refs/heads/main",
            "before": "0000000000000000000000000000000000000000",
            "after": "abc123def456789012345678901234567890abcd",
            "repository": {
                "full_name": "myorg/my-repo",
                "default_branch": "main",
            },
            "pusher": {
                "name": "developer",
            },
        }
        event = PushEvent.model_validate(raw_payload)
        assert event.ref == "refs/heads/main"
        assert event.before == "0000000000000000000000000000000000000000"
        assert event.after == "abc123def456789012345678901234567890abcd"
        assert event.repository.full_name == "myorg/my-repo"
        assert event.repository.default_branch == "main"
        assert event.pusher.name == "developer"

    def test_push_event_frozen(self):
        event = PushEvent(
            ref="refs/heads/main",
            before="000",
            after="abc",
            repository=Repository(full_name="org/repo", default_branch="main"),
            pusher=Pusher(name="dev"),
        )
        with pytest.raises(ValidationError):
            event.ref = "refs/heads/develop"

    def test_push_event_missing_repository_fails(self):
        with pytest.raises(ValidationError, match="repository"):
            PushEvent(
                ref="refs/heads/main",
                before="000",
                after="abc",
                pusher=Pusher(name="dev"),
            )  # type: ignore[call-arg]

    def test_push_event_extra_fields_ignored(self):
        """GitHub sends many more fields -- our model should accept payloads
        with extra fields and only parse what we need."""
        raw_payload = {
            "ref": "refs/heads/main",
            "before": "000",
            "after": "abc",
            "repository": {
                "full_name": "org/repo",
                "default_branch": "main",
                "id": 12345,
                "private": True,
                "html_url": "https://github.com/org/repo",
            },
            "pusher": {
                "name": "dev",
                "email": "dev@example.com",
            },
            "commits": [{"id": "abc", "message": "test"}],
            "head_commit": {"id": "abc"},
            "sender": {"login": "dev"},
        }
        event = PushEvent.model_validate(raw_payload)
        assert event.repository.full_name == "org/repo"
        assert event.pusher.name == "dev"
