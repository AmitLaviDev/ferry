"""Tests for dispatch triggering: build_deployment_tag and trigger_dispatches."""

from __future__ import annotations

import json

from ferry_backend.config.schema import (
    ApiGatewayConfig,
    FerryConfig,
    LambdaConfig,
    StepFunctionConfig,
)
from ferry_backend.detect.changes import AffectedResource
from ferry_backend.dispatch.trigger import (
    _build_resource,
    build_deployment_tag,
    trigger_dispatches,
)
from ferry_backend.github.client import GitHubClient
from ferry_utils.models.dispatch import DispatchPayload

# ---------------------------------------------------------------------------
# build_deployment_tag
# ---------------------------------------------------------------------------


class TestBuildDeploymentTag:
    def test_build_deployment_tag_with_pr(self):
        """PR number present -> 'pr-{N}'."""
        result = build_deployment_tag("42", "feature-branch", "abc123def456789")
        assert result == "pr-42"

    def test_build_deployment_tag_without_pr(self):
        """No PR number -> '{branch}-{sha7}'."""
        result = build_deployment_tag("", "main", "abc123def456789")
        assert result == "main-abc123d"


# ---------------------------------------------------------------------------
# trigger_dispatches
# ---------------------------------------------------------------------------


class TestTriggerDispatches:
    def _make_config(
        self,
        lambdas: list[LambdaConfig] | None = None,
        step_functions: list[StepFunctionConfig] | None = None,
        api_gateways: list[ApiGatewayConfig] | None = None,
    ) -> FerryConfig:
        return FerryConfig(
            lambdas=lambdas or [],
            step_functions=step_functions or [],
            api_gateways=api_gateways or [],
        )

    def _make_affected(
        self,
        name: str,
        resource_type: str = "lambda",
        change_kind: str = "modified",
        changed_files: tuple[str, ...] = ("file.py",),
    ) -> AffectedResource:
        return AffectedResource(
            name=name,
            resource_type=resource_type,
            change_kind=change_kind,
            changed_files=changed_files,
        )

    def test_trigger_dispatches_single_type(self, httpx_mock):
        """Two lambdas -> one dispatch with both in resources list."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/actions/workflows/ferry-lambdas.yml/dispatches"
            ),
            status_code=204,
        )

        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order",
                    source_dir="services/order",
                    ecr_repo="ferry/order",
                ),
                LambdaConfig(
                    name="payment",
                    source_dir="services/payment",
                    ecr_repo="ferry/payment",
                ),
            ],
        )
        affected = [
            self._make_affected(
                "order",
                changed_files=("services/order/main.py",),
            ),
            self._make_affected(
                "payment",
                changed_files=("services/payment/main.py",),
            ),
        ]

        client = GitHubClient()
        results = trigger_dispatches(
            client,
            "owner/repo",
            config,
            affected,
            "sha123",
            "main-sha123",
            "",
        )
        assert len(results) == 1
        assert results[0]["type"] == "lambda"
        assert results[0]["status"] == 204
        assert results[0]["workflow"] == "ferry-lambdas.yml"

        # Verify payload contains both resources
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        payload_data = json.loads(body["inputs"]["payload"])
        assert len(payload_data["resources"]) == 2
        names = {r["name"] for r in payload_data["resources"]}
        assert names == {"order", "payment"}

    def test_trigger_dispatches_multiple_types(self, httpx_mock):
        """Lambda + step_function -> 2 dispatches."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/actions/workflows/ferry-lambdas.yml/dispatches"
            ),
            status_code=204,
        )
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/actions/workflows/ferry-step_functions.yml/dispatches"
            ),
            status_code=204,
        )

        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order",
                    source_dir="services/order",
                    ecr_repo="ferry/order",
                ),
            ],
            step_functions=[
                StepFunctionConfig(
                    name="checkout",
                    source_dir="workflows/checkout",
                    state_machine_name="checkout-sm",
                    definition_file="stepfunction.json",
                ),
            ],
        )
        affected = [
            self._make_affected(
                "order",
                changed_files=("services/order/main.py",),
            ),
            self._make_affected(
                "checkout",
                resource_type="step_function",
                changed_files=("workflows/checkout/def.json",),
            ),
        ]

        client = GitHubClient()
        results = trigger_dispatches(
            client,
            "owner/repo",
            config,
            affected,
            "sha123",
            "main-sha123",
            "",
        )
        assert len(results) == 2
        types = {r["type"] for r in results}
        assert types == {"lambda", "step_function"}

    def test_trigger_dispatches_empty(self, httpx_mock):
        """No affected resources -> no API calls, empty result."""
        config = self._make_config()
        client = GitHubClient()
        results = trigger_dispatches(
            client,
            "owner/repo",
            config,
            [],
            "sha123",
            "main-sha123",
            "",
        )
        assert results == []
        assert len(httpx_mock.get_requests()) == 0

    def test_trigger_dispatches_payload_format(self, httpx_mock):
        """Verify JSON payload structure matches DispatchPayload schema."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/actions/workflows/ferry-lambdas.yml/dispatches"
            ),
            status_code=204,
        )

        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order",
                    source_dir="services/order",
                    ecr_repo="ferry/order",
                ),
            ],
        )
        affected = [
            self._make_affected(
                "order",
                changed_files=("services/order/main.py",),
            ),
        ]

        client = GitHubClient()
        trigger_dispatches(
            client,
            "owner/repo",
            config,
            affected,
            "deadbeef123",
            "pr-42",
            "42",
        )

        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["ref"] == "main"  # default_branch default

        # Parse the inner payload and validate against DispatchPayload
        payload_json = body["inputs"]["payload"]
        payload = DispatchPayload.model_validate_json(payload_json)
        assert payload.resource_type == "lambda"
        assert payload.trigger_sha == "deadbeef123"
        assert payload.deployment_tag == "pr-42"
        assert payload.pr_number == "42"
        assert len(payload.resources) == 1
        assert payload.resources[0].name == "order"
        assert payload.resources[0].source == "services/order"
        assert payload.resources[0].ecr == "ferry/order"
        # function_name defaults to name when not set explicitly
        assert payload.resources[0].function_name == "order"

    def test_trigger_dispatches_includes_explicit_function_name(self, httpx_mock):
        """function_name that differs from name flows through dispatch payload."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/actions/workflows/ferry-lambdas.yml/dispatches"
            ),
            status_code=204,
        )

        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order",
                    source_dir="services/order",
                    ecr_repo="ferry/order",
                    function_name="order-processor-prod",
                ),
            ],
        )
        affected = [
            self._make_affected(
                "order",
                changed_files=("services/order/main.py",),
            ),
        ]

        client = GitHubClient()
        trigger_dispatches(
            client,
            "owner/repo",
            config,
            affected,
            "sha123",
            "main-sha123",
            "",
        )

        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        payload_data = json.loads(body["inputs"]["payload"])
        resource = payload_data["resources"][0]
        assert resource["name"] == "order"
        assert resource["function_name"] == "order-processor-prod"

    def test_trigger_dispatches_uses_correct_workflow_file(self, httpx_mock):
        """lambda -> ferry-lambdas.yml, step_function -> ferry-step_functions.yml."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/actions/workflows/ferry-lambdas.yml/dispatches"
            ),
            status_code=204,
        )
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/actions/workflows/ferry-step_functions.yml/dispatches"
            ),
            status_code=204,
        )

        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order",
                    source_dir="services/order",
                    ecr_repo="ferry/order",
                ),
            ],
            step_functions=[
                StepFunctionConfig(
                    name="checkout",
                    source_dir="workflows/checkout",
                    state_machine_name="checkout-sm",
                    definition_file="stepfunction.json",
                ),
            ],
        )
        affected = [
            self._make_affected(
                "order",
                changed_files=("services/order/main.py",),
            ),
            self._make_affected(
                "checkout",
                resource_type="step_function",
                changed_files=("workflows/checkout/def.json",),
            ),
        ]

        client = GitHubClient()
        results = trigger_dispatches(
            client,
            "owner/repo",
            config,
            affected,
            "sha123",
            "main-sha123",
            "",
        )

        workflows = {r["workflow"] for r in results}
        assert "ferry-lambdas.yml" in workflows
        assert "ferry-step_functions.yml" in workflows

    def test_trigger_dispatches_resource_field_mapping(self, httpx_mock):
        """Verify source_dir -> 'source' and ecr_repo -> 'ecr' in payload."""
        httpx_mock.add_response(
            url=(
                "https://api.github.com/repos/owner/repo"
                "/actions/workflows/ferry-lambdas.yml/dispatches"
            ),
            status_code=204,
        )

        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order",
                    source_dir="services/order-processor",
                    ecr_repo="ferry/order-proc",
                ),
            ],
        )
        affected = [
            self._make_affected(
                "order",
                changed_files=("services/order-processor/main.py",),
            ),
        ]

        client = GitHubClient()
        trigger_dispatches(
            client,
            "owner/repo",
            config,
            affected,
            "sha123",
            "main-sha123",
            "",
        )

        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        payload_data = json.loads(body["inputs"]["payload"])
        resource = payload_data["resources"][0]
        assert resource["source"] == "services/order-processor"
        assert resource["ecr"] == "ferry/order-proc"


# ---------------------------------------------------------------------------
# _build_resource field mapping
# ---------------------------------------------------------------------------


class TestBuildResource:
    """Tests for _build_resource passing type-specific config fields."""

    def test_build_resource_step_function_fields(self) -> None:
        """SF config fields map to dispatch resource fields."""
        config = FerryConfig(
            step_functions=[
                StepFunctionConfig(
                    name="checkout",
                    source_dir="workflows/checkout",
                    state_machine_name="checkout-sm",
                    definition_file="stepfunction.json",
                ),
            ],
        )
        resource = _build_resource("step_function", "checkout", config)
        assert resource.name == "checkout"
        assert resource.source == "workflows/checkout"
        assert resource.state_machine_name == "checkout-sm"
        assert resource.definition_file == "stepfunction.json"

    def test_build_resource_api_gateway_fields(self) -> None:
        """APIGW config fields map to dispatch resource fields."""
        config = FerryConfig(
            api_gateways=[
                ApiGatewayConfig(
                    name="public-api",
                    source_dir="apis/public",
                    rest_api_id="abc123",
                    stage_name="prod",
                    spec_file="openapi.yaml",
                ),
            ],
        )
        resource = _build_resource("api_gateway", "public-api", config)
        assert resource.name == "public-api"
        assert resource.source == "apis/public"
        assert resource.rest_api_id == "abc123"
        assert resource.stage_name == "prod"
        assert resource.spec_file == "openapi.yaml"

    def test_build_resource_lambda_fields(self) -> None:
        """Lambda config fields still map correctly."""
        config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="order",
                    source_dir="services/order",
                    ecr_repo="ferry/order",
                ),
            ],
        )
        resource = _build_resource("lambda", "order", config)
        assert resource.name == "order"
        assert resource.source == "services/order"
        assert resource.ecr == "ferry/order"
        # function_name defaults to name when not set
        assert resource.function_name == "order"
        # runtime defaults to python3.14 (from LambdaConfig)
        assert resource.runtime == "python3.14"

    def test_build_resource_lambda_explicit_function_name(self) -> None:
        """Lambda config with explicit function_name carries through."""
        config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="order",
                    source_dir="services/order",
                    ecr_repo="ferry/order",
                    function_name="order-processor-prod",
                ),
            ],
        )
        resource = _build_resource("lambda", "order", config)
        assert resource.name == "order"
        assert resource.function_name == "order-processor-prod"

    def test_build_resource_lambda_runtime_override(self) -> None:
        """Explicit runtime in config flows through to dispatch resource."""
        config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="legacy",
                    source_dir="services/legacy",
                    ecr_repo="ferry/legacy",
                    runtime="python3.12",
                ),
            ],
        )
        resource = _build_resource("lambda", "legacy", config)
        assert resource.runtime == "python3.12"
