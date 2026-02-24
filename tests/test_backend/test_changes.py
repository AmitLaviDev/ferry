"""Tests for change detection: Compare API fetch, source_dir matching, and config diffing."""

from __future__ import annotations

import structlog.testing

from ferry_backend.config.schema import (
    ApiGatewayConfig,
    FerryConfig,
    LambdaConfig,
    StepFunctionConfig,
)
from ferry_backend.detect.changes import (
    AffectedResource,
    detect_config_changes,
    get_changed_files,
    match_resources,
    merge_affected,
)
from ferry_backend.github.client import GitHubClient

# ---------------------------------------------------------------------------
# get_changed_files
# ---------------------------------------------------------------------------


class TestGetChangedFiles:
    """Tests for Compare API fetch via get_changed_files."""

    def test_get_changed_files_success(self, httpx_mock):
        """Mock compare API returns a list of changed file paths."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/compare/abc123...def456",
            json={
                "files": [
                    {"filename": "services/order/main.py", "status": "modified"},
                    {"filename": "services/order/utils.py", "status": "added"},
                ]
            },
        )
        client = GitHubClient()
        result = get_changed_files(client, "owner/repo", "abc123", "def456")
        assert result == ["services/order/main.py", "services/order/utils.py"]

    def test_get_changed_files_empty(self, httpx_mock):
        """No files changed returns empty list."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/compare/abc123...def456",
            json={"files": []},
        )
        client = GitHubClient()
        result = get_changed_files(client, "owner/repo", "abc123", "def456")
        assert result == []

    def test_get_changed_files_truncation_warning(self, httpx_mock):
        """Exactly 300 files triggers a truncation warning log."""
        files = [{"filename": f"file{i}.py", "status": "modified"} for i in range(300)]
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/compare/abc123...def456",
            json={"files": files},
        )
        client = GitHubClient()
        with structlog.testing.capture_logs() as cap_logs:
            result = get_changed_files(client, "owner/repo", "abc123", "def456")
        assert len(result) == 300
        # Check that a warning was logged about truncation
        warning_logs = [log for log in cap_logs if log.get("log_level") == "warning"]
        assert len(warning_logs) >= 1
        assert "truncat" in warning_logs[0].get("event", "").lower()

    def test_get_changed_files_initial_push(self, httpx_mock):
        """Base SHA of all zeros returns empty list without API call."""
        client = GitHubClient()
        zero_sha = "0" * 40
        result = get_changed_files(client, "owner/repo", zero_sha, "def456")
        assert result == []
        # Verify no HTTP request was made
        assert len(httpx_mock.get_requests()) == 0


# ---------------------------------------------------------------------------
# match_resources
# ---------------------------------------------------------------------------


class TestMatchResources:
    """Tests for source_dir prefix matching via match_resources."""

    def _make_config(
        self,
        lambdas: list[LambdaConfig] | None = None,
        step_functions: list[StepFunctionConfig] | None = None,
        api_gateways: list[ApiGatewayConfig] | None = None,
    ) -> FerryConfig:
        """Helper to build a FerryConfig for tests."""
        return FerryConfig(
            lambdas=lambdas or [],
            step_functions=step_functions or [],
            api_gateways=api_gateways or [],
        )

    def test_match_resources_lambda_hit(self):
        """File under lambda source_dir produces AffectedResource with type=lambda."""
        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-processor",
                )
            ],
        )
        result = match_resources(config, ["services/order-processor/main.py"])
        assert len(result) == 1
        assert result[0].name == "order-processor"
        assert result[0].resource_type == "lambda"
        assert result[0].change_kind == "modified"
        assert "services/order-processor/main.py" in result[0].changed_files

    def test_match_resources_no_match(self):
        """File outside all source_dirs returns empty list."""
        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-processor",
                )
            ],
        )
        result = match_resources(config, ["unrelated/file.py"])
        assert result == []

    def test_match_resources_multiple_types(self):
        """Files matching lambda + step_function produce 2 AffectedResources."""
        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-processor",
                )
            ],
            step_functions=[
                StepFunctionConfig(
                    name="checkout-flow",
                    source_dir="workflows/checkout",
                )
            ],
        )
        result = match_resources(
            config,
            [
                "services/order-processor/main.py",
                "workflows/checkout/definition.json",
            ],
        )
        assert len(result) == 2
        types = {r.resource_type for r in result}
        assert types == {"lambda", "step_function"}

    def test_match_resources_trailing_slash(self):
        """source_dir with trailing slash still matches correctly."""
        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor/",
                    ecr_repo="ferry/order-processor",
                )
            ],
        )
        result = match_resources(config, ["services/order-processor/main.py"])
        assert len(result) == 1
        assert result[0].name == "order-processor"

    def test_match_resources_partial_prefix_no_match(self):
        """source_dir 'services/order' does NOT match 'services/order-ext/main.py'."""
        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order",
                    source_dir="services/order",
                    ecr_repo="ferry/order",
                )
            ],
        )
        result = match_resources(config, ["services/order-ext/main.py"])
        assert result == []


# ---------------------------------------------------------------------------
# merge_affected
# ---------------------------------------------------------------------------


class TestMergeAffected:
    """Tests for deduplicating AffectedResource lists via merge_affected."""

    def test_merge_affected_dedup(self):
        """Same resource in both lists produces single entry."""
        source_list = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            )
        ]
        config_list = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("ferry.yaml",),
            )
        ]
        result = merge_affected(source_list, config_list)
        assert len(result) == 1
        assert result[0].name == "order-processor"

    def test_merge_affected_no_overlap(self):
        """Different resources in each list are all kept."""
        source_list = [
            AffectedResource(
                name="order-processor",
                resource_type="lambda",
                change_kind="modified",
                changed_files=("services/order-processor/main.py",),
            )
        ]
        config_list = [
            AffectedResource(
                name="payment-handler",
                resource_type="lambda",
                change_kind="new",
                changed_files=("ferry.yaml",),
            )
        ]
        result = merge_affected(source_list, config_list)
        assert len(result) == 2
        names = {r.name for r in result}
        assert names == {"order-processor", "payment-handler"}


# ---------------------------------------------------------------------------
# detect_config_changes
# ---------------------------------------------------------------------------


class TestDetectConfigChanges:
    """Tests for ferry.yaml config diff detection via detect_config_changes."""

    def test_config_change_new_resource(self):
        """Resource in new but not old is marked as 'new'."""
        old_config = FerryConfig(lambdas=[], step_functions=[], api_gateways=[])
        new_config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-processor",
                )
            ],
        )
        result = detect_config_changes(old_config, new_config)
        assert len(result) == 1
        assert result[0].name == "order-processor"
        assert result[0].resource_type == "lambda"
        assert result[0].change_kind == "new"

    def test_config_change_removed_resource(self):
        """Resource in old but not new is not in affected list (removal = no dispatch)."""
        old_config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-processor",
                )
            ],
        )
        new_config = FerryConfig(lambdas=[], step_functions=[], api_gateways=[])
        result = detect_config_changes(old_config, new_config)
        assert result == []

    def test_config_change_modified_resource(self):
        """Same name, different runtime produces AffectedResource(change_kind='modified')."""
        old_config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-processor",
                    runtime="python3.10",
                )
            ],
        )
        new_config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-processor",
                    runtime="python3.12",
                )
            ],
        )
        result = detect_config_changes(old_config, new_config)
        assert len(result) == 1
        assert result[0].name == "order-processor"
        assert result[0].change_kind == "modified"
        assert result[0].changed_files == ("ferry.yaml",)

    def test_config_change_identical(self):
        """Same config in old and new produces empty affected list."""
        config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-processor",
                )
            ],
        )
        result = detect_config_changes(config, config)
        assert result == []

    def test_config_change_no_old_config(self):
        """old_config is None means all resources in new_config are 'new'."""
        new_config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-processor",
                )
            ],
            step_functions=[
                StepFunctionConfig(
                    name="checkout-flow",
                    source_dir="workflows/checkout",
                )
            ],
        )
        result = detect_config_changes(None, new_config)
        assert len(result) == 2
        assert all(r.change_kind == "new" for r in result)
        names = {r.name for r in result}
        assert names == {"order-processor", "checkout-flow"}

    def test_config_change_multiple_types(self):
        """Changes across lambdas and step_functions are both detected."""
        old_config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-processor",
                    runtime="python3.10",
                )
            ],
            step_functions=[
                StepFunctionConfig(
                    name="checkout-flow",
                    source_dir="workflows/checkout",
                )
            ],
        )
        new_config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="order-processor",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-processor",
                    runtime="python3.12",
                )
            ],
            step_functions=[
                StepFunctionConfig(
                    name="checkout-flow",
                    source_dir="workflows/checkout-v2",
                )
            ],
        )
        result = detect_config_changes(old_config, new_config)
        assert len(result) == 2
        types = {r.resource_type for r in result}
        assert types == {"lambda", "step_function"}
