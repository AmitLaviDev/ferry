"""Tests for PR plan comment formatting, command parsing, and apply comment functions.

Tests cover:
- format_plan_comment: single lambda, multiple types, with/without env, no file paths, header
- format_no_changes_comment: output shape
- resolve_environment: match, no match, empty, first match
- parse_ferry_command: plan, apply, case-insensitive, trailing text, invalid inputs
- format_apply_comment: marker, resource count, environment, waiting line
- format_apply_status_update: success/failure/cancelled replace waiting line
- find_apply_comment: found, not found, empty, pagination
"""

from __future__ import annotations

from ferry_backend.checks.plan import (
    APPLY_MARKER_TEMPLATE,
    find_apply_comment,
    format_apply_comment,
    format_apply_status_update,
    format_no_changes_comment,
    format_plan_comment,
    parse_ferry_command,
    resolve_environment,
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
        assert body.startswith("## ")
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

    def test_header_is_first_line(self):
        """Header is the very first line of the comment body (no marker)."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        body = format_plan_comment(affected)
        assert body.startswith("## ")


# ---------------------------------------------------------------------------
# format_no_changes_comment
# ---------------------------------------------------------------------------


class TestFormatNoChangesComment:
    def test_output_shape(self):
        """No-changes comment has header and message, no marker."""
        body = format_no_changes_comment()
        assert body.startswith("## ")
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
# parse_ferry_command
# ---------------------------------------------------------------------------


class TestParseCommand:
    def test_plan(self):
        assert parse_ferry_command("/ferry plan") == "plan"

    def test_apply(self):
        assert parse_ferry_command("/ferry apply") == "apply"

    def test_whitespace_trimmed(self):
        assert parse_ferry_command("  /ferry  apply  ") == "apply"

    def test_case_insensitive_plan(self):
        assert parse_ferry_command("/Ferry Plan") == "plan"

    def test_case_insensitive_apply(self):
        assert parse_ferry_command("/FERRY APPLY") == "apply"

    def test_trailing_text_ignored(self):
        assert parse_ferry_command("/ferry apply staging") == "apply"

    def test_not_at_start(self):
        assert parse_ferry_command("Please /ferry plan") is None

    def test_multiline_not_entire_body(self):
        assert parse_ferry_command("some text\n/ferry plan") is None

    def test_no_command(self):
        assert parse_ferry_command("/ferry") is None

    def test_unknown_command(self):
        assert parse_ferry_command("/ferry status") is None

    def test_empty(self):
        assert parse_ferry_command("") is None


# ---------------------------------------------------------------------------
# format_apply_comment
# ---------------------------------------------------------------------------


class TestFormatApplyComment:
    def test_marker_present(self):
        """Apply comment includes SHA-specific marker."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        env = EnvironmentMapping(name="staging", branch="develop")
        body = format_apply_comment(affected, env, "abc123def456789")
        marker = APPLY_MARKER_TEMPLATE.format(sha="abc123def456789")
        assert marker in body

    def test_resource_count(self):
        """Apply comment shows resource count."""
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
        env = EnvironmentMapping(name="staging", branch="develop")
        body = format_apply_comment(affected, env, "abc123")
        assert "2 resource(s)" in body

    def test_environment_name(self):
        """Apply comment shows environment name."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        env = EnvironmentMapping(name="production", branch="main")
        body = format_apply_comment(affected, env, "abc123")
        assert "**production**" in body

    def test_no_environment_shows_default(self):
        """Apply comment without environment shows 'default'."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        body = format_apply_comment(affected, None, "abc123")
        assert "**default**" in body

    def test_waiting_line(self):
        """Apply comment includes waiting line."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        body = format_apply_comment(affected, None, "abc123")
        assert "_Waiting for workflow to complete..._" in body

    def test_sha_truncation(self):
        """Apply comment shows truncated SHA."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        body = format_apply_comment(affected, None, "abc123def456789")
        assert "`abc123d`" in body

    def test_header(self):
        """Apply comment has deploy triggered header."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        body = format_apply_comment(affected, None, "abc123")
        assert "## \U0001f6a2 Ferry: Deploy Triggered" in body


# ---------------------------------------------------------------------------
# format_apply_status_update
# ---------------------------------------------------------------------------


class TestFormatApplyStatusUpdate:
    def _base_body(self) -> str:
        return (
            "<!-- ferry:apply:abc123 -->\n"
            "## \U0001f6a2 Ferry: Deploy Triggered\n\n"
            "Deploying **1 resource(s)** to **staging** at `abc123d`...\n\n"
            "_Waiting for workflow to complete..._"
        )

    def test_success(self):
        """Success conclusion replaces waiting line with checkmark."""
        updated = format_apply_status_update(
            self._base_body(), "success", "https://github.com/runs/123"
        )
        assert "_Waiting for workflow to complete..._" not in updated
        assert "\u2705" in updated
        assert "`success`" in updated
        assert "https://github.com/runs/123" in updated

    def test_failure(self):
        """Failure conclusion shows red X."""
        updated = format_apply_status_update(
            self._base_body(), "failure", "https://github.com/runs/456"
        )
        assert "\u274c" in updated
        assert "`failure`" in updated

    def test_cancelled(self):
        """Cancelled conclusion shows warning."""
        updated = format_apply_status_update(
            self._base_body(), "cancelled", "https://github.com/runs/789"
        )
        assert "\u26a0\ufe0f" in updated
        assert "`cancelled`" in updated

    def test_unknown_conclusion(self):
        """Unknown conclusion shows question mark."""
        updated = format_apply_status_update(
            self._base_body(), "timed_out", "https://github.com/runs/000"
        )
        assert "\u2753" in updated
        assert "`timed_out`" in updated

    def test_run_url_in_link(self):
        """Run URL appears in [View run] link."""
        updated = format_apply_status_update(
            self._base_body(), "success", "https://github.com/runs/123"
        )
        assert "[View run](https://github.com/runs/123)" in updated


# ---------------------------------------------------------------------------
# find_apply_comment
# ---------------------------------------------------------------------------


class TestFindApplyComment:
    _BASE_URL = "https://api.github.com/repos/owner/repo/issues/42/comments"
    _PAGE1_URL = f"{_BASE_URL}?per_page=100&page=1"

    def test_found(self, httpx_mock):
        """Returns comment dict when apply marker is found."""
        marker = APPLY_MARKER_TEMPLATE.format(sha="abc123")
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=[
                {"id": 1, "body": "unrelated comment"},
                {"id": 2, "body": f"{marker}\n## Deploy"},
            ],
        )
        client = GitHubClient()
        result = find_apply_comment(client, "owner/repo", 42, "abc123")
        assert result is not None
        assert result["id"] == 2

    def test_not_found(self, httpx_mock):
        """Returns None when no comment has the apply marker."""
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=[
                {"id": 1, "body": "unrelated comment"},
                {"id": 2, "body": "another comment"},
            ],
        )
        client = GitHubClient()
        result = find_apply_comment(client, "owner/repo", 42, "abc123")
        assert result is None

    def test_empty(self, httpx_mock):
        """Returns None when there are no comments."""
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=[],
        )
        client = GitHubClient()
        result = find_apply_comment(client, "owner/repo", 42, "abc123")
        assert result is None

    def test_api_error(self, httpx_mock):
        """Returns None on API error (does not crash)."""
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json={"message": "Internal Server Error"},
            status_code=500,
        )
        client = GitHubClient()
        result = find_apply_comment(client, "owner/repo", 42, "abc123")
        assert result is None

    def test_pagination(self, httpx_mock):
        """Finds comment on the second page of results."""
        page2_url = f"{self._BASE_URL}?per_page=100&page=2"
        marker = APPLY_MARKER_TEMPLATE.format(sha="abc123")
        # Page 1: 100 unrelated comments (full page -> triggers next page)
        page1 = [{"id": i, "body": f"comment {i}"} for i in range(100)]
        # Page 2: contains the apply comment
        page2 = [{"id": 200, "body": f"{marker}\nDeploy here"}]

        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=page1,
        )
        httpx_mock.add_response(
            url=page2_url,
            json=page2,
        )

        client = GitHubClient()
        result = find_apply_comment(client, "owner/repo", 42, "abc123")
        assert result is not None
        assert result["id"] == 200

    def test_different_sha_not_matched(self, httpx_mock):
        """A comment with a different SHA marker is not matched."""
        marker_other = APPLY_MARKER_TEMPLATE.format(sha="other_sha")
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=[
                {"id": 1, "body": f"{marker_other}\n## Deploy"},
            ],
        )
        client = GitHubClient()
        result = find_apply_comment(client, "owner/repo", 42, "abc123")
        assert result is None
