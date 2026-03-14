"""Tests for PR plan comment formatting, command parsing, and deploy comment functions.

Tests cover:
- format_plan_comment: table format with resource details, with/without config/env
- format_no_changes_comment: output shape
- resolve_environment: match, no match, empty, first match
- parse_ferry_command: plan, apply, case-insensitive, trailing text, invalid inputs
- format_apply_comment: deploy+sha markers, resource table, environment, status
- format_apply_status_update: header update, status emoji replacement, result line
- find_deploy_comment: found, not found, empty, pagination
- extract_sha_from_comment: SHA extraction from comment body
"""

from __future__ import annotations

from ferry_backend.checks.plan import (
    DEPLOY_MARKER_TEMPLATE,
    SHA_MARKER_TEMPLATE,
    extract_sha_from_comment,
    find_deploy_comment,
    format_apply_comment,
    format_apply_status_update,
    format_no_changes_comment,
    format_plan_comment,
    parse_ferry_command,
    resolve_environment,
)
from ferry_backend.config.schema import (
    ApiGatewayConfig,
    EnvironmentMapping,
    FerryConfig,
    LambdaConfig,
    StepFunctionConfig,
)
from ferry_backend.detect.changes import AffectedResource
from ferry_backend.github.client import GitHubClient


def _test_config() -> FerryConfig:
    """Minimal FerryConfig for formatter tests."""
    return FerryConfig(
        lambdas=[
            LambdaConfig(
                name="order-processor",
                source_dir="services/order-processor",
                ecr_repo="ferry/order-processor",
                function_name="order-fn",
            ),
        ],
        step_functions=[
            StepFunctionConfig(
                name="checkout-flow",
                source_dir="workflows/checkout",
                state_machine_name="checkout-sm",
                definition_file="definition.json",
            ),
        ],
        api_gateways=[
            ApiGatewayConfig(
                name="public-api",
                source_dir="api",
                rest_api_id="abc123",
                stage_name="prod",
                spec_file="openapi.yaml",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# format_plan_comment
# ---------------------------------------------------------------------------


class TestFormatPlanComment:
    def test_single_lambda_with_config(self):
        """Single modified lambda shows table with resource details."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        body = format_plan_comment(affected, config=_test_config())
        assert body.startswith("## ")
        assert "## \U0001f6a2 Ferry: Deployment Plan" in body
        assert "| Resource | Type | Details |" in body
        assert "| **order-processor** | Lambda |" in body
        assert "`order-fn`" in body
        assert "`ferry/order-processor`" in body
        assert "Deploy with `/ferry apply` or merge." in body

    def test_single_lambda_without_config(self):
        """Without config, shows change_kind as fallback detail."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        body = format_plan_comment(affected)
        assert "| **order-processor** | Lambda | _(modified)_ |" in body

    def test_multiple_types(self):
        """Multiple resource types in table with correct type ordering."""
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
        body = format_plan_comment(affected, config=_test_config())
        assert "| **order-processor** | Lambda |" in body
        assert "| **checkout-flow** | Step Function |" in body
        assert "| **public-api** | API Gateway |" in body
        # Stable ordering: lambda < step_function < api_gateway
        assert body.index("Lambda") < body.index("Step Function")
        assert body.index("Step Function") < body.index("API Gateway")
        # Verify detail strings
        assert "`checkout-sm`" in body
        assert "`abc123` / stage `prod`" in body

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
        assert "auto-deploy to **staging**" in body

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
        assert "Manual deployment to **production** after merge." in body
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
        assert "Deploy with `/ferry apply` or merge." in body

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
    def test_deploy_marker_present(self):
        """Apply comment includes PR-level deploy marker."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        env = EnvironmentMapping(name="staging", branch="develop")
        body = format_apply_comment(affected, env, "abc123def456789", pr_number=42)
        marker = DEPLOY_MARKER_TEMPLATE.format(pr_number=42)
        assert marker in body

    def test_sha_marker_present(self):
        """Apply comment includes SHA marker for workflow_run correlation."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        env = EnvironmentMapping(name="staging", branch="develop")
        body = format_apply_comment(affected, env, "abc123def456789", pr_number=42)
        sha_marker = SHA_MARKER_TEMPLATE.format(sha="abc123def456789")
        assert sha_marker in body

    def test_resource_table(self):
        """Apply comment shows resource table with hourglass status."""
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
        body = format_apply_comment(affected, env, "abc123", pr_number=42)
        assert "| Resource | Type | Status |" in body
        assert "| **order-processor**" in body
        assert "| **checkout-flow**" in body
        assert "\u23f3" in body  # hourglass

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
        body = format_apply_comment(affected, env, "abc123", pr_number=42)
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
        body = format_apply_comment(affected, None, "abc123", pr_number=42)
        assert "**default**" in body

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
        body = format_apply_comment(affected, None, "abc123def456789", pr_number=42)
        assert "`abc123d`" in body

    def test_deploying_header(self):
        """Apply comment has deploying header."""
        affected = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            ),
        ]
        body = format_apply_comment(affected, None, "abc123", pr_number=42)
        assert "Deploying \u2192" in body


# ---------------------------------------------------------------------------
# format_apply_status_update
# ---------------------------------------------------------------------------


class TestFormatApplyStatusUpdate:
    def _base_body(self) -> str:
        return (
            "<!-- ferry:deploy:42 -->\n"
            "<!-- ferry:sha:abc123 -->\n"
            "## \U0001f6a2 Ferry: Deploying \u2192 **staging** at `abc123d`\n\n"
            "| Resource | Type | Status |\n"
            "|----------|------|--------|\n"
            "| **order** | Lambda | \u23f3 |"
        )

    def test_success(self):
        """Success conclusion updates header and replaces hourglass."""
        updated = format_apply_status_update(
            self._base_body(), "success", "https://github.com/runs/123"
        )
        assert "\u23f3" not in updated
        assert "Deployed \u2192" in updated
        assert "\u2705" in updated
        assert "`success`" in updated
        assert "https://github.com/runs/123" in updated

    def test_failure(self):
        """Failure conclusion shows red X and Deploy Failed header."""
        updated = format_apply_status_update(
            self._base_body(), "failure", "https://github.com/runs/456"
        )
        assert "Deploy Failed \u2192" in updated
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
# find_deploy_comment
# ---------------------------------------------------------------------------


class TestFindDeployComment:
    _BASE_URL = "https://api.github.com/repos/owner/repo/issues/42/comments"
    _PAGE1_URL = f"{_BASE_URL}?per_page=100&page=1"

    def test_found(self, httpx_mock):
        """Returns comment dict when deploy marker is found."""
        marker = DEPLOY_MARKER_TEMPLATE.format(pr_number=42)
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=[
                {"id": 1, "body": "unrelated comment"},
                {"id": 2, "body": f"{marker}\n## Deploy"},
            ],
        )
        client = GitHubClient()
        result = find_deploy_comment(client, "owner/repo", 42)
        assert result is not None
        assert result["id"] == 2

    def test_not_found(self, httpx_mock):
        """Returns None when no comment has the deploy marker."""
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=[
                {"id": 1, "body": "unrelated comment"},
                {"id": 2, "body": "another comment"},
            ],
        )
        client = GitHubClient()
        result = find_deploy_comment(client, "owner/repo", 42)
        assert result is None

    def test_empty(self, httpx_mock):
        """Returns None when there are no comments."""
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json=[],
        )
        client = GitHubClient()
        result = find_deploy_comment(client, "owner/repo", 42)
        assert result is None

    def test_api_error(self, httpx_mock):
        """Returns None on API error (does not crash)."""
        httpx_mock.add_response(
            url=self._PAGE1_URL,
            json={"message": "Internal Server Error"},
            status_code=500,
        )
        client = GitHubClient()
        result = find_deploy_comment(client, "owner/repo", 42)
        assert result is None

    def test_pagination(self, httpx_mock):
        """Finds comment on the second page of results."""
        page2_url = f"{self._BASE_URL}?per_page=100&page=2"
        marker = DEPLOY_MARKER_TEMPLATE.format(pr_number=42)
        # Page 1: 100 unrelated comments (full page -> triggers next page)
        page1 = [{"id": i, "body": f"comment {i}"} for i in range(100)]
        # Page 2: contains the deploy comment
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
        result = find_deploy_comment(client, "owner/repo", 42)
        assert result is not None
        assert result["id"] == 200


# ---------------------------------------------------------------------------
# extract_sha_from_comment
# ---------------------------------------------------------------------------


class TestExtractShaFromComment:
    def test_extracts_sha(self):
        """Extracts SHA from deploy comment body."""
        body = "<!-- ferry:deploy:42 -->\n<!-- ferry:sha:abc123def456 -->\n..."
        assert extract_sha_from_comment(body) == "abc123def456"

    def test_no_marker_returns_none(self):
        """Returns None when no SHA marker present."""
        body = "<!-- ferry:deploy:42 -->\nno sha marker"
        assert extract_sha_from_comment(body) is None

    def test_empty_body(self):
        """Returns None for empty body."""
        assert extract_sha_from_comment("") is None
