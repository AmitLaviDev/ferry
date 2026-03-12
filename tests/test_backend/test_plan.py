"""Tests for sticky PR plan comment functions.

Tests cover:
- format_plan_comment: single lambda, multiple types, with/without env, no file paths, marker
- format_no_changes_comment: output shape
- resolve_environment: match, no match, empty, first match
- find_plan_comment: found, not found, empty, API error, pagination
- upsert_plan_comment: creates new, updates existing
"""

from __future__ import annotations

from ferry_backend.checks.plan import (
    PLAN_MARKER,
    find_plan_comment,
    format_no_changes_comment,
    format_plan_comment,
    resolve_environment,
    upsert_plan_comment,
)
from ferry_backend.config.schema import EnvironmentMapping, FerryConfig
from ferry_backend.detect.changes import AffectedResource
from ferry_backend.github.client import GitHubClient

# ---------------------------------------------------------------------------
# format_plan_comment
# ---------------------------------------------------------------------------


class TestFormatPlanComment:
    def test_single_lambda(self):
        """Single modified lambda shows header + resource + footer."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        body = format_plan_comment(affected)
        assert PLAN_MARKER in body
        assert "## \U0001f6a2 Ferry: Deployment Plan" in body
        assert "#### Lambdas" in body
        assert "- **order-processor** _(modified)_" in body
        assert "will be deployed when this PR is merged" in body

    def test_multiple_types(self):
        """Multiple resource types grouped with correct section headers."""
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
            AffectedResource(
                name="public-api",
                resource_type="api_gateway",
                change_kind="modified",
                changed_files=("api/openapi.yaml",),
            ),
        ]
        body = format_plan_comment(affected)
        assert "#### Lambdas" in body
        assert "#### Step Functions" in body
        assert "#### API Gateways" in body
        # Stable ordering: lambda < step_function < api_gateway
        assert body.index("#### Lambdas") < body.index("#### Step Functions")
        assert body.index("#### Step Functions") < body.index("#### API Gateways")

    def test_with_environment(self):
        """Environment mapping shown in header and footer."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        env = EnvironmentMapping(name="staging", branch="develop", auto_deploy=True)
        body = format_plan_comment(affected, environment=env)
        assert "\u2192 **staging**" in body
        assert "deployed to **staging**" in body

    def test_with_environment_no_auto_deploy(self):
        """Environment with auto_deploy=False shows manual deploy CTA."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        env = EnvironmentMapping(name="production", branch="main", auto_deploy=False)
        body = format_plan_comment(affected, environment=env)
        assert "queued for manual deployment" in body
        assert "**production**" in body

    def test_without_environment(self):
        """No environment shows generic header and footer."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        body = format_plan_comment(affected, environment=None)
        assert "## \U0001f6a2 Ferry: Deployment Plan" in body
        assert "\u2192" not in body
        assert "will be deployed when this PR is merged" in body

    def test_no_file_paths_in_comment(self):
        """Plan comment does NOT include individual file paths."""
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
        body = format_plan_comment(affected)
        assert "main.py" not in body
        assert "requirements.txt" not in body

    def test_marker_is_first_line(self):
        """PLAN_MARKER is the very first line of the comment body."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        body = format_plan_comment(affected)
        assert body.startswith(PLAN_MARKER)


# ---------------------------------------------------------------------------
# format_no_changes_comment
# ---------------------------------------------------------------------------


class TestFormatNoChangesComment:
    def test_output_shape(self):
        """No-changes comment has marker, header, and message."""
        body = format_no_changes_comment()
        assert body.startswith(PLAN_MARKER)
        assert "## \U0001f6a2 Ferry: Deployment Plan" in body
        assert "No Ferry-managed resources affected by this PR." in body


# ---------------------------------------------------------------------------
# resolve_environment
# ---------------------------------------------------------------------------


class TestResolveEnvironment:
    def test_match(self):
        """Returns environment when branch matches."""
        config = FerryConfig(
            environments=[
                EnvironmentMapping(name="staging", branch="develop"),
                EnvironmentMapping(name="production", branch="main"),
            ],
        )
        env = resolve_environment(config, "main")
        assert env is not None
        assert env.name == "production"

    def test_no_match(self):
        """Returns None when no branch matches."""
        config = FerryConfig(
            environments=[
                EnvironmentMapping(name="staging", branch="develop"),
            ],
        )
        env = resolve_environment(config, "main")
        assert env is None

    def test_empty_environments(self):
        """Returns None when environments list is empty."""
        config = FerryConfig()
        env = resolve_environment(config, "main")
        assert env is None

    def test_first_match_wins(self):
        """Returns the first matching environment."""
        config = FerryConfig(
            environments=[
                EnvironmentMapping(name="staging", branch="main"),
                EnvironmentMapping(name="production", branch="main"),
            ],
        )
        env = resolve_environment(config, "main")
        assert env is not None
        assert env.name == "staging"


# ---------------------------------------------------------------------------
# find_plan_comment
# ---------------------------------------------------------------------------


class TestFindPlanComment:
    _BASE_URL = "https://api.github.com/repos/owner/repo/issues/42/comments"
    _PAGE1_URL = f"{_BASE_URL}?per_page=100&page=1"

    def test_found(self, httpx_mock):
        """Returns comment dict when marker is found."""
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=[
                {"id": 1, "body": "unrelated comment"},
                {"id": 2, "body": f"{PLAN_MARKER}\n## Plan"},
            ],
        )
        client = GitHubClient()
        result = find_plan_comment(client, "owner/repo", 42)
        assert result is not None
        assert result["id"] == 2

    def test_not_found(self, httpx_mock):
        """Returns None when no comment has the marker."""
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=[
                {"id": 1, "body": "unrelated comment"},
                {"id": 2, "body": "another comment"},
            ],
        )
        client = GitHubClient()
        result = find_plan_comment(client, "owner/repo", 42)
        assert result is None

    def test_empty(self, httpx_mock):
        """Returns None when there are no comments."""
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=[],
        )
        client = GitHubClient()
        result = find_plan_comment(client, "owner/repo", 42)
        assert result is None

    def test_api_error(self, httpx_mock):
        """Returns None on API error (does not crash)."""
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json={"message": "Internal Server Error"},
            status_code=500,
        )
        client = GitHubClient()
        result = find_plan_comment(client, "owner/repo", 42)
        assert result is None

    def test_pagination(self, httpx_mock):
        """Finds comment on the second page of results."""
        page2_url = f"{self._BASE_URL}?per_page=100&page=2"
        # Page 1: 100 unrelated comments (full page -> triggers next page)
        page1 = [{"id": i, "body": f"comment {i}"} for i in range(100)]
        # Page 2: contains the plan comment
        page2 = [{"id": 200, "body": f"{PLAN_MARKER}\nPlan here"}]

        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=page1,
        )
        httpx_mock.add_response(
            url=page2_url,
            json=page2,
        )

        client = GitHubClient()
        result = find_plan_comment(client, "owner/repo", 42)
        assert result is not None
        assert result["id"] == 200


# ---------------------------------------------------------------------------
# upsert_plan_comment
# ---------------------------------------------------------------------------


class TestUpsertPlanComment:
    _COMMENTS_URL = "https://api.github.com/repos/owner/repo/issues/42/comments"
    _FIND_URL = f"{_COMMENTS_URL}?per_page=100&page=1"

    def test_creates_new(self, httpx_mock):
        """Creates new comment when no existing plan comment found."""
        # find_plan_comment: GET with params returns empty
        httpx_mock.add_response(
            url=self._FIND_URL,
            json=[],
        )
        # POST new comment (no query params)
        httpx_mock.add_response(
            url=self._COMMENTS_URL,
            json={"id": 99, "body": "new plan"},
            status_code=201,
        )

        client = GitHubClient()
        result = upsert_plan_comment(client, "owner/repo", 42, "new plan body")
        assert result["id"] == 99

        # Verify POST was made (second request, after GET for search)
        requests = httpx_mock.get_requests()
        post_reqs = [r for r in requests if r.method == "POST"]
        assert len(post_reqs) == 1

    def test_updates_existing(self, httpx_mock):
        """Updates existing comment via PATCH when marker found."""
        # find_plan_comment: GET with params returns the existing comment
        httpx_mock.add_response(
            url=self._FIND_URL,
            json=[{"id": 50, "body": f"{PLAN_MARKER}\nold plan"}],
        )
        # PATCH existing comment
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/issues/comments/50",
            json={"id": 50, "body": "updated plan"},
        )

        client = GitHubClient()
        result = upsert_plan_comment(client, "owner/repo", 42, "updated plan body")
        assert result["id"] == 50

        # Verify PATCH was made
        requests = httpx_mock.get_requests()
        patch_reqs = [r for r in requests if r.method == "PATCH"]
        assert len(patch_reqs) == 1
        assert "/issues/comments/50" in str(patch_reqs[0].url)
