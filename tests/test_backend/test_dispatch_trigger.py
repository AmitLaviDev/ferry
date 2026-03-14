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
from ferry_utils.models.dispatch import BatchedDispatchPayload

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

    # --- Updated existing tests (adapted for batched dispatch v2) ---

    def test_trigger_dispatches_single_type(self, httpx_mock):
        """Two lambdas -> one batched dispatch with both in lambdas list."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
        assert results[0]["workflow"] == "ferry.yml"

        # Verify payload is BatchedDispatchPayload v2 with both lambdas
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        payload = BatchedDispatchPayload.model_validate_json(body["inputs"]["payload"])
        assert payload.v == 2
        assert len(payload.lambdas) == 2
        names = {r.name for r in payload.lambdas}
        assert names == {"order", "payment"}

    def test_trigger_dispatches_multiple_types(self, httpx_mock):
        """Lambda + step_function -> 1 batched dispatch (not 2)."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
                    name="checkout-sm",
                    source_dir="workflows/checkout",
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
                "checkout-sm",
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

        # Only 1 API call (batched), not 2
        assert len(httpx_mock.get_requests()) == 1

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
        """Verify JSON payload structure matches BatchedDispatchPayload v2 schema."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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

        # Parse the inner payload and validate against BatchedDispatchPayload v2
        payload_json = body["inputs"]["payload"]
        payload = BatchedDispatchPayload.model_validate_json(payload_json)
        assert payload.v == 2
        assert payload.trigger_sha == "deadbeef123"
        assert payload.deployment_tag == "pr-42"
        assert payload.pr_number == "42"
        assert len(payload.lambdas) == 1
        assert payload.lambdas[0].name == "order"
        assert payload.lambdas[0].source == "services/order"
        assert payload.lambdas[0].ecr == "ferry/order"
        # name IS the AWS function name
        assert payload.lambdas[0].name == "order"

    def test_trigger_dispatches_name_is_aws_name(self, httpx_mock):
        """name in config flows as name in dispatch payload (no separate function_name)."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
            status_code=204,
        )

        config = self._make_config(
            lambdas=[
                LambdaConfig(
                    name="order-processor-prod",
                    source_dir="services/order",
                    ecr_repo="ferry/order",
                ),
            ],
        )
        affected = [
            self._make_affected(
                "order-processor-prod",
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
        payload = BatchedDispatchPayload.model_validate_json(body["inputs"]["payload"])
        assert payload.lambdas[0].name == "order-processor-prod"

    def test_trigger_dispatches_uses_correct_workflow_file(self, httpx_mock):
        """All resource types dispatch to ferry.yml in a single batched call."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
                    name="checkout-sm",
                    source_dir="workflows/checkout",
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
                "checkout-sm",
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
        assert workflows == {"ferry.yml"}  # All types use unified workflow

        # Only 1 API call (batched)
        assert len(httpx_mock.get_requests()) == 1

    def test_trigger_dispatches_resource_field_mapping(self, httpx_mock):
        """Verify source_dir -> 'source' and ecr_repo -> 'ecr' in batched payload."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
        payload = BatchedDispatchPayload.model_validate_json(body["inputs"]["payload"])
        assert payload.lambdas[0].source == "services/order-processor"
        assert payload.lambdas[0].ecr == "ferry/order-proc"

    # --- New tests for batched dispatch behavior ---

    def test_trigger_dispatches_multiple_types_batched(self, httpx_mock):
        """2 types -> 1 API call, results have 2 entries, payload is BatchedDispatchPayload v2."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
                    name="checkout-sm",
                    source_dir="workflows/checkout",
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
                "checkout-sm",
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

        # Exactly 1 API call
        assert len(httpx_mock.get_requests()) == 1
        # 2 result entries (one per type)
        assert len(results) == 2
        types = {r["type"] for r in results}
        assert types == {"lambda", "step_function"}

        # Payload is BatchedDispatchPayload v2
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        payload = BatchedDispatchPayload.model_validate_json(body["inputs"]["payload"])
        assert payload.v == 2
        assert len(payload.lambdas) == 1
        assert len(payload.step_functions) == 1

    def test_trigger_dispatches_single_type_batched(self, httpx_mock):
        """1 lambda -> 1 API call, payload is BatchedDispatchPayload v2 with only lambdas."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
        results = trigger_dispatches(
            client,
            "owner/repo",
            config,
            affected,
            "sha123",
            "main-sha123",
            "",
        )

        assert len(httpx_mock.get_requests()) == 1
        assert len(results) == 1

        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        payload = BatchedDispatchPayload.model_validate_json(body["inputs"]["payload"])
        assert payload.v == 2
        assert len(payload.lambdas) == 1
        assert payload.step_functions == []
        assert payload.api_gateways == []

    def test_trigger_dispatches_batched_payload_format(self, httpx_mock):
        """Verify all BatchedDispatchPayload fields: v, sha, tag, pr, resources."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
        payload = BatchedDispatchPayload.model_validate_json(body["inputs"]["payload"])

        assert payload.v == 2
        assert payload.trigger_sha == "deadbeef123"
        assert payload.deployment_tag == "pr-42"
        assert payload.pr_number == "42"
        assert len(payload.lambdas) == 1
        lam = payload.lambdas[0]
        assert lam.name == "order"
        assert lam.source == "services/order"
        assert lam.ecr == "ferry/order"
        assert lam.name == "order"

    def test_trigger_dispatches_all_three_types(self, httpx_mock):
        """3 types -> 1 API call, 3 result entries, payload has all 3 lists populated."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
                    name="checkout-sm",
                    source_dir="workflows/checkout",
                    definition_file="stepfunction.json",
                ),
            ],
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
        affected = [
            self._make_affected("order", changed_files=("services/order/main.py",)),
            self._make_affected(
                "checkout-sm",
                resource_type="step_function",
                changed_files=("workflows/checkout/def.json",),
            ),
            self._make_affected(
                "public-api",
                resource_type="api_gateway",
                changed_files=("apis/public/spec.yaml",),
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

        # 1 API call
        assert len(httpx_mock.get_requests()) == 1
        # 3 result entries
        assert len(results) == 3
        types = {r["type"] for r in results}
        assert types == {"lambda", "step_function", "api_gateway"}

        # Payload has all 3 lists
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        payload = BatchedDispatchPayload.model_validate_json(body["inputs"]["payload"])
        assert len(payload.lambdas) == 1
        assert len(payload.step_functions) == 1
        assert len(payload.api_gateways) == 1

    def test_trigger_dispatches_return_shape(self, httpx_mock):
        """Each result dict has 'type' (str), 'status' (int), 'workflow' (str) keys."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
                    name="checkout-sm",
                    source_dir="workflows/checkout",
                    definition_file="stepfunction.json",
                ),
            ],
        )
        affected = [
            self._make_affected("order", changed_files=("services/order/main.py",)),
            self._make_affected(
                "checkout-sm",
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

        for result in results:
            assert set(result.keys()) == {"type", "status", "workflow"}
            assert isinstance(result["type"], str)
            assert isinstance(result["status"], int)
            assert isinstance(result["workflow"], str)

    def test_trigger_dispatches_forwards_environment_fields(self, httpx_mock):
        """mode, environment, head_ref, base_ref flow into BatchedDispatchPayload."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
        affected = [self._make_affected("order")]
        client = GitHubClient()
        trigger_dispatches(
            client,
            "owner/repo",
            config,
            affected,
            "sha123",
            "pr-42",
            "42",
            mode="deploy",
            environment="staging",
            head_ref="feature-branch",
            base_ref="develop",
        )
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        payload = BatchedDispatchPayload.model_validate_json(body["inputs"]["payload"])
        assert payload.mode == "deploy"
        assert payload.environment == "staging"
        assert payload.head_ref == "feature-branch"
        assert payload.base_ref == "develop"

    def test_trigger_dispatches_defaults_without_environment(self, httpx_mock):
        """Without environment kwargs, defaults apply (backward-compatible)."""
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
        affected = [self._make_affected("order")]
        client = GitHubClient()
        trigger_dispatches(client, "owner/repo", config, affected, "sha123", "main-sha123", "")
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        payload = BatchedDispatchPayload.model_validate_json(body["inputs"]["payload"])
        assert payload.mode == "deploy"
        assert payload.environment == ""
        assert payload.head_ref == ""
        assert payload.base_ref == ""

    def test_trigger_dispatches_fallback_on_oversized(self, httpx_mock, monkeypatch):
        """Oversized payload -> falls back to per-type v1 dispatch (N API calls)."""
        monkeypatch.setattr("ferry_backend.dispatch.trigger._MAX_PAYLOAD_SIZE", 10)

        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
            status_code=204,
        )
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
                    name="checkout-sm",
                    source_dir="workflows/checkout",
                    definition_file="stepfunction.json",
                ),
            ],
        )
        affected = [
            self._make_affected("order", changed_files=("services/order/main.py",)),
            self._make_affected(
                "checkout-sm",
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

        # Fallback: 2 API calls (one per type)
        assert len(httpx_mock.get_requests()) == 2
        assert len(results) == 2

    def test_trigger_dispatches_fallback_uses_v1_payload(self, httpx_mock, monkeypatch):
        """Fallback dispatches use v1 DispatchPayload with v=1, resource_type, resources."""
        monkeypatch.setattr("ferry_backend.dispatch.trigger._MAX_PAYLOAD_SIZE", 10)

        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
            status_code=204,
        )
        httpx_mock.add_response(
            url=("https://api.github.com/repos/owner/repo/actions/workflows/ferry.yml/dispatches"),
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
                    name="checkout-sm",
                    source_dir="workflows/checkout",
                    definition_file="stepfunction.json",
                ),
            ],
        )
        affected = [
            self._make_affected("order", changed_files=("services/order/main.py",)),
            self._make_affected(
                "checkout-sm",
                resource_type="step_function",
                changed_files=("workflows/checkout/def.json",),
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

        # Each fallback request should have v1 DispatchPayload format
        for request in httpx_mock.get_requests():
            body = json.loads(request.content)
            payload_data = json.loads(body["inputs"]["payload"])
            assert payload_data["v"] == 1
            assert "resource_type" in payload_data
            assert "resources" in payload_data


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
                    name="checkout-sm",
                    source_dir="workflows/checkout",
                    definition_file="stepfunction.json",
                ),
            ],
        )
        resource = _build_resource("step_function", "checkout-sm", config)
        assert resource.name == "checkout-sm"
        assert resource.source == "workflows/checkout"
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
        # runtime defaults to python3.14 (from LambdaConfig)
        assert resource.runtime == "python3.14"

    def test_build_resource_lambda_name_is_aws_name(self) -> None:
        """Lambda config name IS the AWS function name -- flows to dispatch resource."""
        config = FerryConfig(
            lambdas=[
                LambdaConfig(
                    name="order-processor-prod",
                    source_dir="services/order",
                    ecr_repo="ferry/order",
                ),
            ],
        )
        resource = _build_resource("lambda", "order-processor-prod", config)
        assert resource.name == "order-processor-prod"

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
