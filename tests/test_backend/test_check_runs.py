"""Tests for Check Runs, PR comments, and PR lookup functions."""

from __future__ import annotations

import json

from ferry_backend.checks.runs import (
    create_check_run,
    find_merged_pr,
    find_open_prs,
    format_deployment_plan,
    post_pr_comment,
)
from ferry_backend.detect.changes import AffectedResource
from ferry_backend.github.client import GitHubClient

# ---------------------------------------------------------------------------
# format_deployment_plan
# ---------------------------------------------------------------------------


class TestFormatDeploymentPlan:
    def test_format_deployment_plan_modified(self):
        """Modified lambda -> summary + text with ~ indicator."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=(
                    "services/order-processor/main.py",
                    "services/order-processor/requirements.txt",
                ),
            ),
        ]
        summary, text = format_deployment_plan(affected)
        assert "**1 resource(s)**" in summary
        assert "will be affected" in summary
        assert "~ **order-processor** _(modified)_" in text
        assert "`services/order-processor/main.py`" in text
        assert "`services/order-processor/requirements.txt`" in text
        assert "Ferry will deploy" in text

    def test_format_deployment_plan_new(self):
        """New resource -> + indicator."""
        affected = [
            AffectedResource(
                name="notification-sender",
                resource_type="lambda",
                change_kind="new",
                changed_files=("services/notification-sender/main.py",),
            ),
        ]
        summary, text = format_deployment_plan(affected)
        assert "+ **notification-sender** _(new)_" in text

    def test_format_deployment_plan_multiple_types(self):
        """Groups by type with correct section headers."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
            AffectedResource(
                name="checkout-flow",
                resource_type="step_function",
                change_kind="new",
                changed_files=("workflows/checkout/definition.json",),
            ),
        ]
        summary, text = format_deployment_plan(affected)
        assert "**2 resource(s)**" in summary
        assert "#### Lambdas" in text
        assert "#### Step Functions" in text
        # Lambdas section should come before Step Functions
        lambdas_idx = text.index("#### Lambdas")
        sf_idx = text.index("#### Step Functions")
        assert lambdas_idx < sf_idx

    def test_format_deployment_plan_empty(self):
        """Empty affected list -> 0 resources summary."""
        summary, _text = format_deployment_plan([])
        assert "**0 resource(s)**" in summary


# ---------------------------------------------------------------------------
# create_check_run
# ---------------------------------------------------------------------------


class TestCreateCheckRun:
    _CHECK_RUNS_URL = (
        "https://api.github.com/repos/owner/repo/check-runs"
    )

    def test_create_check_run_with_affected(self, httpx_mock):
        """Posts Check Run with deployment plan for affected resources."""
        httpx_mock.add_response(
            url=self._CHECK_RUNS_URL,
            json={"id": 1, "status": "completed"},
            status_code=201,
        )

        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]

        client = GitHubClient()
        result = create_check_run(
            client, "owner/repo", "sha123", affected,
        )

        assert result["id"] == 1
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["name"] == "Ferry: Deployment Plan"
        assert body["head_sha"] == "sha123"
        assert body["status"] == "completed"
        assert body["conclusion"] == "success"
        assert body["output"]["title"] == "Deployment Plan"
        assert "1 resource(s)" in body["output"]["summary"]
        assert "order-processor" in body["output"]["text"]

    def test_create_check_run_no_changes(self, httpx_mock):
        """Posts Check Run with 'No resources affected' when no changes."""
        httpx_mock.add_response(
            url=self._CHECK_RUNS_URL,
            json={"id": 2, "status": "completed"},
            status_code=201,
        )

        client = GitHubClient()
        create_check_run(client, "owner/repo", "sha123", [])

        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["conclusion"] == "success"
        assert body["output"]["title"] == "No Changes Detected"
        assert "No resources affected" in body["output"]["summary"]

    def test_create_check_run_error(self, httpx_mock):
        """Posts failed Check Run with error message for config errors."""
        httpx_mock.add_response(
            url=self._CHECK_RUNS_URL,
            json={"id": 3, "status": "completed"},
            status_code=201,
        )

        client = GitHubClient()
        create_check_run(
            client, "owner/repo", "sha123", [],
            error="Missing required field: name",
        )

        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["conclusion"] == "failure"
        assert body["output"]["title"] == "Configuration Error"
        assert "validation failed" in body["output"]["summary"]
        assert "Missing required field: name" in body["output"]["text"]


# ---------------------------------------------------------------------------
# find_open_prs
# ---------------------------------------------------------------------------


class TestFindOpenPrs:
    def test_find_open_prs_found(self, httpx_mock):
        """Mock returns open PR -> returns it."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/commits/sha123/pulls"
            ),
            json=[{"number": 42, "state": "open"}],
        )

        client = GitHubClient()
        result = find_open_prs(client, "owner/repo", "sha123")
        assert len(result) == 1
        assert result[0]["number"] == 42

    def test_find_open_prs_none(self, httpx_mock):
        """Mock returns closed/merged PRs -> returns empty list."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/commits/sha123/pulls"
            ),
            json=[
                {"number": 10, "state": "closed"},
                {"number": 11, "state": "closed"},
            ],
        )

        client = GitHubClient()
        result = find_open_prs(client, "owner/repo", "sha123")
        assert result == []

    def test_find_open_prs_filters_closed(self, httpx_mock):
        """Mix of open and closed -> only open returned."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/commits/sha123/pulls"
            ),
            json=[
                {"number": 42, "state": "open"},
                {"number": 10, "state": "closed"},
                {"number": 99, "state": "open"},
            ],
        )

        client = GitHubClient()
        result = find_open_prs(client, "owner/repo", "sha123")
        assert len(result) == 2
        numbers = {pr["number"] for pr in result}
        assert numbers == {42, 99}


# ---------------------------------------------------------------------------
# find_merged_pr
# ---------------------------------------------------------------------------


class TestFindMergedPr:
    def test_find_merged_pr_returns_merged(self, httpx_mock):
        """Returns PR with merged_at set."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/commits/sha123/pulls"
            ),
            json=[
                {"number": 10, "state": "closed", "merged_at": None},
                {"number": 42, "state": "closed", "merged_at": "2026-02-28T00:00:00Z"},
            ],
        )

        client = GitHubClient()
        result = find_merged_pr(client, "owner/repo", "sha123")
        assert result is not None
        assert result["number"] == 42

    def test_find_merged_pr_returns_none_when_no_merged(self, httpx_mock):
        """Returns None when no PRs have merged_at set."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/commits/sha123/pulls"
            ),
            json=[
                {"number": 10, "state": "closed", "merged_at": None},
                {"number": 11, "state": "open", "merged_at": None},
            ],
        )

        client = GitHubClient()
        result = find_merged_pr(client, "owner/repo", "sha123")
        assert result is None

    def test_find_merged_pr_returns_first_merged(self, httpx_mock):
        """Returns the first merged PR when multiple exist."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/commits/sha123/pulls"
            ),
            json=[
                {"number": 42, "state": "closed", "merged_at": "2026-02-28T00:00:00Z"},
                {"number": 43, "state": "closed", "merged_at": "2026-02-28T01:00:00Z"},
            ],
        )

        client = GitHubClient()
        result = find_merged_pr(client, "owner/repo", "sha123")
        assert result is not None
        assert result["number"] == 42


# ---------------------------------------------------------------------------
# post_pr_comment
# ---------------------------------------------------------------------------


class TestPostPrComment:
    def test_post_pr_comment_posts_to_issues_api(self, httpx_mock):
        """Verify post_pr_comment sends POST to issues comments endpoint."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/issues/42/comments"
            ),
            json={"id": 100, "body": "test comment"},
            status_code=201,
        )

        client = GitHubClient()
        result = post_pr_comment(
            client, "owner/repo", 42, "test comment",
        )
        assert result["id"] == 100

        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["body"] == "test comment"
        assert "/issues/42/comments" in str(request.url)
