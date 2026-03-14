"""Tests for ferry_action.parse_payload — dispatch payload to GHA matrix."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from ferry_action.parse_payload import build_matrix, main, parse_payload


def _make_payload(
    *,
    resources: list[dict] | None = None,
    trigger_sha: str = "abc1234def5678",
    deployment_tag: str = "pr-42",
    resource_type: str = "lambda",
    mode: str | None = None,
    environment: str | None = None,
) -> str:
    """Build a valid dispatch payload JSON string."""
    if resources is None:
        resources = [
            {
                "resource_type": "lambda",
                "name": "order-processor",
                "source": "services/order-processor",
                "ecr": "ferry/order-processor",
                "runtime": "python3.14",
            },
            {
                "resource_type": "lambda",
                "name": "email-sender",
                "source": "services/email-sender",
                "ecr": "ferry/email-sender",
                "runtime": "python3.14",
            },
        ]
    payload: dict = {
        "v": 1,
        "resource_type": resource_type,
        "resources": resources,
        "trigger_sha": trigger_sha,
        "deployment_tag": deployment_tag,
    }
    if mode is not None:
        payload["mode"] = mode
    if environment is not None:
        payload["environment"] = environment
    return json.dumps(payload)


def _make_batched_payload(
    *,
    lambdas: list[dict] | None = None,
    step_functions: list[dict] | None = None,
    api_gateways: list[dict] | None = None,
    trigger_sha: str = "abc1234def5678",
    deployment_tag: str = "pr-42",
    mode: str | None = None,
    environment: str | None = None,
) -> str:
    """Build a valid v2 batched dispatch payload JSON string."""
    payload: dict = {
        "v": 2,
        "trigger_sha": trigger_sha,
        "deployment_tag": deployment_tag,
    }
    if lambdas is not None:
        payload["lambdas"] = lambdas
    if step_functions is not None:
        payload["step_functions"] = step_functions
    if api_gateways is not None:
        payload["api_gateways"] = api_gateways
    if mode is not None:
        payload["mode"] = mode
    if environment is not None:
        payload["environment"] = environment
    return json.dumps(payload)


_LAMBDA_A = {
    "resource_type": "lambda",
    "name": "order-processor",
    "source": "services/order-processor",
    "ecr": "ferry/order-processor",
    "runtime": "python3.14",
}
_SF_A = {
    "resource_type": "step_function",
    "name": "checkout-sm",
    "source": "workflows/checkout",
    "definition_file": "stepfunction.json",
}
_AG_A = {
    "resource_type": "api_gateway",
    "name": "public-api",
    "source": "apis/public",
    "rest_api_id": "abc123",
    "stage_name": "prod",
    "spec_file": "openapi.yaml",
}


class TestBuildMatrix:
    """Tests for build_matrix()."""

    def test_parse_valid_lambda_payload(self) -> None:
        """Two Lambda resources produce a matrix with two include entries."""
        payload_str = _make_payload()
        result = build_matrix(payload_str)

        assert "include" in result
        assert len(result["include"]) == 2

        first = result["include"][0]
        assert first["name"] == "order-processor"
        assert first["source"] == "services/order-processor"
        assert first["ecr"] == "ferry/order-processor"
        assert first["trigger_sha"] == "abc1234def5678"
        assert first["deployment_tag"] == "pr-42"
        assert first["runtime"] == "python3.14"
        assert "function_name" not in first

        second = result["include"][1]
        assert second["name"] == "email-sender"
        assert second["source"] == "services/email-sender"
        assert second["ecr"] == "ferry/email-sender"
        assert "function_name" not in second

    def test_parse_single_resource(self) -> None:
        """Single Lambda resource produces matrix with one include entry."""
        resources = [
            {
                "resource_type": "lambda",
                "name": "my-func",
                "source": "src/my-func",
                "ecr": "ferry/my-func",
                "runtime": "python3.14",
            },
        ]
        payload_str = _make_payload(resources=resources)
        result = build_matrix(payload_str)

        assert len(result["include"]) == 1
        assert result["include"][0]["name"] == "my-func"

    def test_parse_invalid_json(self) -> None:
        """Invalid JSON raises an error."""
        with pytest.raises((json.JSONDecodeError, ValidationError)):
            build_matrix("not valid json{{{")

    def test_parse_invalid_payload_schema(self) -> None:
        """Valid JSON but missing required fields raises ValidationError."""
        with pytest.raises(ValidationError):
            build_matrix('{"foo": "bar"}')

    def test_matrix_output_is_valid_json(self) -> None:
        """Matrix dict round-trips through JSON serialization."""
        payload_str = _make_payload()
        result = build_matrix(payload_str)

        json_str = json.dumps(result, separators=(",", ":"))
        parsed = json.loads(json_str)

        assert parsed == result
        assert isinstance(parsed["include"], list)

    def test_filters_non_lambda_resources(self) -> None:
        """Non-Lambda resources are filtered out of lambda matrix."""
        resources = [
            {
                "resource_type": "lambda",
                "name": "my-lambda",
                "source": "src/lambda",
                "ecr": "ferry/lambda",
                "runtime": "python3.14",
            },
            {
                "resource_type": "step_function",
                "name": "my-sm",
                "source": "src/sfn",
                "definition_file": "def.json",
            },
        ]
        payload_str = _make_payload(resources=resources)
        result = build_matrix(payload_str)

        assert len(result["include"]) == 1
        assert result["include"][0]["name"] == "my-lambda"

    def test_empty_resources_produces_empty_include(self) -> None:
        """Empty resource list produces empty include array."""
        payload_str = _make_payload(resources=[])
        result = build_matrix(payload_str)

        assert result == {"include": []}

    def test_propagates_trigger_sha_and_deployment_tag(self) -> None:
        """Trigger SHA and deployment tag from payload propagate to all entries."""
        resources = [
            {
                "resource_type": "lambda",
                "name": "a",
                "source": "src/a",
                "ecr": "ferry/a",
                "runtime": "python3.14",
            },
            {
                "resource_type": "lambda",
                "name": "b",
                "source": "src/b",
                "ecr": "ferry/b",
                "runtime": "python3.14",
            },
        ]
        payload_str = _make_payload(
            resources=resources,
            trigger_sha="deadbeef12345678",
            deployment_tag="pr-99",
        )
        result = build_matrix(payload_str)

        for entry in result["include"]:
            assert entry["trigger_sha"] == "deadbeef12345678"
            assert entry["deployment_tag"] == "pr-99"

    def test_lambda_matrix_no_function_name_key(self) -> None:
        """function_name key is NOT in lambda matrix output; name IS the function name."""
        payload_str = _make_payload()
        result = build_matrix(payload_str)

        first = result["include"][0]
        assert "function_name" not in first
        assert first["name"] == "order-processor"

    def test_lambda_matrix_name_is_aws_function_name(self) -> None:
        """name IS the AWS function name directly."""
        resources = [
            {
                "resource_type": "lambda",
                "name": "order-processor-prod",
                "source": "services/order",
                "ecr": "ferry/order",
                "runtime": "python3.14",
            },
        ]
        payload_str = _make_payload(resources=resources)
        result = build_matrix(payload_str)

        entry = result["include"][0]
        assert entry["name"] == "order-processor-prod"
        assert "function_name" not in entry

    def test_step_function_matrix(self) -> None:
        """Step Function resources produce correct matrix entries."""
        resources = [
            {
                "resource_type": "step_function",
                "name": "checkout-sm",
                "source": "workflows/checkout",
                "definition_file": "stepfunction.json",
            },
        ]
        payload_str = _make_payload(
            resources=resources,
            resource_type="step_function",
        )
        result = build_matrix(payload_str)

        assert len(result["include"]) == 1
        entry = result["include"][0]
        assert entry["name"] == "checkout-sm"
        assert entry["source"] == "workflows/checkout"
        assert entry["definition_file"] == "stepfunction.json"
        assert entry["trigger_sha"] == "abc1234def5678"
        assert entry["deployment_tag"] == "pr-42"
        # No state_machine_name key; name IS the state machine name
        assert "state_machine_name" not in entry
        # Lambda-specific fields must NOT be present
        assert "ecr" not in entry
        assert "runtime" not in entry

    def test_api_gateway_matrix(self) -> None:
        """API Gateway resources produce correct matrix entries."""
        resources = [
            {
                "resource_type": "api_gateway",
                "name": "public-api",
                "source": "apis/public",
                "rest_api_id": "abc123",
                "stage_name": "prod",
                "spec_file": "openapi.yaml",
            },
        ]
        payload_str = _make_payload(
            resources=resources,
            resource_type="api_gateway",
        )
        result = build_matrix(payload_str)

        assert len(result["include"]) == 1
        entry = result["include"][0]
        assert entry["name"] == "public-api"
        assert entry["source"] == "apis/public"
        assert entry["rest_api_id"] == "abc123"
        assert entry["stage_name"] == "prod"
        assert entry["spec_file"] == "openapi.yaml"
        assert entry["trigger_sha"] == "abc1234def5678"
        assert entry["deployment_tag"] == "pr-42"
        # Lambda-specific fields must NOT be present
        assert "ecr" not in entry
        assert "runtime" not in entry

    def test_step_function_matrix_multiple_resources(self) -> None:
        """Multiple SF resources produce multiple matrix entries."""
        resources = [
            {
                "resource_type": "step_function",
                "name": "sm-a",
                "source": "wf/a",
                "definition_file": "def-a.json",
            },
            {
                "resource_type": "step_function",
                "name": "sm-b",
                "source": "wf/b",
                "definition_file": "def-b.json",
            },
        ]
        payload_str = _make_payload(
            resources=resources,
            resource_type="step_function",
        )
        result = build_matrix(payload_str)

        assert len(result["include"]) == 2
        names = {e["name"] for e in result["include"]}
        assert names == {"sm-a", "sm-b"}


class TestParsePayloadV2:
    """Tests for parse_payload() with v2 batched payloads."""

    def test_v2_all_three_types(self) -> None:
        """V2 payload with all three types sets all flags and matrices."""
        result = parse_payload(
            _make_batched_payload(
                lambdas=[_LAMBDA_A],
                step_functions=[_SF_A],
                api_gateways=[_AG_A],
            )
        )
        assert result.has_lambdas is True
        assert result.has_step_functions is True
        assert result.has_api_gateways is True
        assert len(result.lambda_matrix["include"]) == 1
        assert len(result.sf_matrix["include"]) == 1
        assert len(result.ag_matrix["include"]) == 1
        assert result.resource_types == "lambda,step_function,api_gateway"

    def test_v2_single_type_lambda(self) -> None:
        """V2 payload with only lambdas sets only lambda flag and matrix."""
        result = parse_payload(_make_batched_payload(lambdas=[_LAMBDA_A]))
        assert result.has_lambdas is True
        assert result.has_step_functions is False
        assert result.has_api_gateways is False
        assert len(result.lambda_matrix["include"]) == 1
        assert result.sf_matrix["include"] == []
        assert result.ag_matrix["include"] == []
        assert result.resource_types == "lambda"

    def test_v2_lambda_matrix_fields(self) -> None:
        """V2 lambda matrix entry has correct fields and values."""
        result = parse_payload(_make_batched_payload(lambdas=[_LAMBDA_A]))
        entry = result.lambda_matrix["include"][0]
        assert entry["name"] == "order-processor"
        assert entry["source"] == "services/order-processor"
        assert entry["ecr"] == "ferry/order-processor"
        assert entry["trigger_sha"] == "abc1234def5678"
        assert entry["deployment_tag"] == "pr-42"
        assert entry["runtime"] == "python3.14"
        assert "function_name" not in entry

    def test_v2_sf_matrix_fields(self) -> None:
        """V2 step function matrix entry has correct fields, no lambda fields."""
        result = parse_payload(_make_batched_payload(step_functions=[_SF_A]))
        entry = result.sf_matrix["include"][0]
        assert entry["name"] == "checkout-sm"
        assert entry["source"] == "workflows/checkout"
        assert entry["definition_file"] == "stepfunction.json"
        assert entry["trigger_sha"] == "abc1234def5678"
        assert entry["deployment_tag"] == "pr-42"
        assert "state_machine_name" not in entry
        assert "ecr" not in entry
        assert "runtime" not in entry

    def test_v2_ag_matrix_fields(self) -> None:
        """V2 API gateway matrix entry has correct fields, no lambda fields."""
        result = parse_payload(_make_batched_payload(api_gateways=[_AG_A]))
        entry = result.ag_matrix["include"][0]
        assert entry["name"] == "public-api"
        assert entry["source"] == "apis/public"
        assert entry["rest_api_id"] == "abc123"
        assert entry["stage_name"] == "prod"
        assert entry["spec_file"] == "openapi.yaml"
        assert entry["trigger_sha"] == "abc1234def5678"
        assert entry["deployment_tag"] == "pr-42"
        assert "ecr" not in entry
        assert "runtime" not in entry

    def test_v2_multiple_lambdas(self) -> None:
        """V2 payload with two lambdas produces two matrix entries."""
        lambda_b = {
            "resource_type": "lambda",
            "name": "email-sender",
            "source": "services/email-sender",
            "ecr": "ferry/email-sender",
            "runtime": "python3.14",
        }
        result = parse_payload(_make_batched_payload(lambdas=[_LAMBDA_A, lambda_b]))
        assert len(result.lambda_matrix["include"]) == 2
        names = {e["name"] for e in result.lambda_matrix["include"]}
        assert names == {"order-processor", "email-sender"}

    def test_v2_empty_payload(self) -> None:
        """V2 payload with no types sets all flags False and matrices empty."""
        result = parse_payload(_make_batched_payload())
        assert result.has_lambdas is False
        assert result.has_step_functions is False
        assert result.has_api_gateways is False
        assert result.lambda_matrix["include"] == []
        assert result.sf_matrix["include"] == []
        assert result.ag_matrix["include"] == []
        assert result.resource_types == ""

    def test_v2_parse_mode_defaults(self) -> None:
        """V2 payload without mode/environment returns defaults."""
        result = parse_payload(_make_batched_payload(lambdas=[_LAMBDA_A]))
        assert result.mode == "deploy"
        assert result.environment == ""

    def test_v2_parse_mode_explicit(self) -> None:
        """V2 payload with explicit mode/environment returns those values."""
        result = parse_payload(
            _make_batched_payload(lambdas=[_LAMBDA_A], mode="deploy", environment="staging")
        )
        assert result.mode == "deploy"
        assert result.environment == "staging"

    def test_v2_propagates_trigger_sha_and_tag(self) -> None:
        """V2 trigger_sha and deployment_tag appear in every matrix entry."""
        result = parse_payload(
            _make_batched_payload(
                lambdas=[_LAMBDA_A],
                step_functions=[_SF_A],
                api_gateways=[_AG_A],
                trigger_sha="deadbeef",
                deployment_tag="pr-99",
            )
        )
        for matrix in [result.lambda_matrix, result.sf_matrix, result.ag_matrix]:
            for entry in matrix["include"]:
                assert entry["trigger_sha"] == "deadbeef"
                assert entry["deployment_tag"] == "pr-99"


class TestParsePayloadV1Compat:
    """Tests for parse_payload() with v1 payloads (backward compatibility)."""

    def test_v1_lambda_through_parse_payload(self) -> None:
        """V1 lambda payload parsed through unified parse_payload."""
        result = parse_payload(_make_payload())
        assert result.has_lambdas is True
        assert result.has_step_functions is False
        assert result.has_api_gateways is False
        assert len(result.lambda_matrix["include"]) == 2
        assert result.resource_types == "lambda"

    def test_v1_step_function_through_parse_payload(self) -> None:
        """V1 step_function payload parsed through unified parse_payload."""
        result = parse_payload(_make_payload(resources=[_SF_A], resource_type="step_function"))
        assert result.has_step_functions is True
        assert result.has_lambdas is False
        assert result.has_api_gateways is False
        assert len(result.sf_matrix["include"]) == 1

    def test_v1_api_gateway_through_parse_payload(self) -> None:
        """V1 api_gateway payload parsed through unified parse_payload."""
        result = parse_payload(_make_payload(resources=[_AG_A], resource_type="api_gateway"))
        assert result.has_api_gateways is True
        assert result.has_lambdas is False
        assert result.has_step_functions is False
        assert len(result.ag_matrix["include"]) == 1

    def test_v1_empty_resources_through_parse_payload(self) -> None:
        """V1 payload with empty resources sets all flags False."""
        result = parse_payload(_make_payload(resources=[]))
        assert result.has_lambdas is False
        assert result.has_step_functions is False
        assert result.has_api_gateways is False
        assert result.lambda_matrix["include"] == []
        assert result.sf_matrix["include"] == []
        assert result.ag_matrix["include"] == []

    def test_v1_parse_mode_defaults(self) -> None:
        """V1 payload without mode/environment returns defaults."""
        result = parse_payload(_make_payload())
        assert result.mode == "deploy"
        assert result.environment == ""

    def test_v1_parse_mode_explicit(self) -> None:
        """V1 payload with explicit mode/environment returns those values."""
        result = parse_payload(_make_payload(mode="deploy", environment="production"))
        assert result.mode == "deploy"
        assert result.environment == "production"


class TestMain:
    """Tests for the main() CLI entrypoint."""

    def test_missing_payload_env_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing INPUT_PAYLOAD env var causes sys.exit(1)."""
        monkeypatch.delenv("INPUT_PAYLOAD", raising=False)
        with pytest.raises(SystemExit, match="1"):
            main()

    def test_empty_payload_env_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty INPUT_PAYLOAD env var causes sys.exit(1)."""
        monkeypatch.setenv("INPUT_PAYLOAD", "")
        with pytest.raises(SystemExit, match="1"):
            main()

    def test_invalid_payload_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid JSON in INPUT_PAYLOAD causes sys.exit(1)."""
        monkeypatch.setenv("INPUT_PAYLOAD", "not json")
        with pytest.raises(SystemExit, match="1"):
            main()

    def test_valid_payload_writes_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Valid v1 payload writes per-type flags and matrices to GITHUB_OUTPUT."""
        output_file = tmp_path / "github_output"
        output_file.touch()

        monkeypatch.setenv("INPUT_PAYLOAD", _make_payload())
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        main()

        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 9

        outputs = {}
        for line in lines:
            key, _, value = line.partition("=")
            outputs[key] = value

        assert outputs["has_lambdas"] == "true"
        assert outputs["has_step_functions"] == "false"
        assert outputs["has_api_gateways"] == "false"

        lambda_matrix = json.loads(outputs["lambda_matrix"])
        assert len(lambda_matrix["include"]) == 2

        sf_matrix = json.loads(outputs["sf_matrix"])
        assert sf_matrix["include"] == []

        ag_matrix = json.loads(outputs["ag_matrix"])
        assert ag_matrix["include"] == []

        assert outputs["resource_types"] == "lambda"
        assert outputs["mode"] == "deploy"
        assert outputs["environment"] == ""

    def test_valid_v2_payload_writes_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Valid v2 batched payload writes per-type flags and matrices."""
        output_file = tmp_path / "github_output"
        output_file.touch()

        monkeypatch.setenv(
            "INPUT_PAYLOAD",
            _make_batched_payload(lambdas=[_LAMBDA_A], step_functions=[_SF_A]),
        )
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        main()

        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 9

        outputs = {}
        for line in lines:
            key, _, value = line.partition("=")
            outputs[key] = value

        assert outputs["has_lambdas"] == "true"
        assert outputs["has_step_functions"] == "true"
        assert outputs["has_api_gateways"] == "false"

        lambda_matrix = json.loads(outputs["lambda_matrix"])
        assert len(lambda_matrix["include"]) == 1

        sf_matrix = json.loads(outputs["sf_matrix"])
        assert len(sf_matrix["include"]) == 1

        ag_matrix = json.loads(outputs["ag_matrix"])
        assert ag_matrix["include"] == []

        assert outputs["resource_types"] == "lambda,step_function"
        assert outputs["mode"] == "deploy"
        assert outputs["environment"] == ""

    def test_main_v1_explicit_mode_environment(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """V1 payload with explicit mode/environment outputs those values."""
        output_file = tmp_path / "github_output"
        output_file.touch()
        monkeypatch.setenv("INPUT_PAYLOAD", _make_payload(mode="deploy", environment="production"))
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        main()
        content = output_file.read_text()
        outputs = {}
        for line in content.strip().split("\n"):
            key, _, value = line.partition("=")
            outputs[key] = value
        assert outputs["mode"] == "deploy"
        assert outputs["environment"] == "production"

    def test_main_v2_explicit_mode_environment(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """V2 payload with explicit mode/environment outputs those values."""
        output_file = tmp_path / "github_output"
        output_file.touch()
        monkeypatch.setenv(
            "INPUT_PAYLOAD",
            _make_batched_payload(lambdas=[_LAMBDA_A], mode="deploy", environment="staging"),
        )
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        main()
        content = output_file.read_text()
        outputs = {}
        for line in content.strip().split("\n"):
            key, _, value = line.partition("=")
            outputs[key] = value
        assert outputs["mode"] == "deploy"
        assert outputs["environment"] == "staging"
