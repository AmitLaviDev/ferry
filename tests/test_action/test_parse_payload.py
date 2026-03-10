"""Tests for ferry_action.parse_payload — dispatch payload to GHA matrix."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from ferry_action.parse_payload import build_matrix, main


def _make_payload(
    *,
    resources: list[dict] | None = None,
    trigger_sha: str = "abc1234def5678",
    deployment_tag: str = "pr-42",
    resource_type: str = "lambda",
) -> str:
    """Build a valid dispatch payload JSON string."""
    if resources is None:
        resources = [
            {
                "resource_type": "lambda",
                "name": "order-processor",
                "source": "services/order-processor",
                "ecr": "ferry/order-processor",
                "function_name": "order-processor",
                "runtime": "python3.14",
            },
            {
                "resource_type": "lambda",
                "name": "email-sender",
                "source": "services/email-sender",
                "ecr": "ferry/email-sender",
                "function_name": "email-sender",
                "runtime": "python3.14",
            },
        ]
    payload = {
        "v": 1,
        "resource_type": resource_type,
        "resources": resources,
        "trigger_sha": trigger_sha,
        "deployment_tag": deployment_tag,
    }
    return json.dumps(payload)


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
        assert first["function_name"] == "order-processor"
        assert first["trigger_sha"] == "abc1234def5678"
        assert first["deployment_tag"] == "pr-42"
        assert first["runtime"] == "python3.14"

        second = result["include"][1]
        assert second["name"] == "email-sender"
        assert second["source"] == "services/email-sender"
        assert second["ecr"] == "ferry/email-sender"
        assert second["function_name"] == "email-sender"

    def test_parse_single_resource(self) -> None:
        """Single Lambda resource produces matrix with one include entry."""
        resources = [
            {
                "resource_type": "lambda",
                "name": "my-func",
                "source": "src/my-func",
                "ecr": "ferry/my-func",
                "function_name": "my-func",
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
                "function_name": "my-lambda",
                "runtime": "python3.14",
            },
            {
                "resource_type": "step_function",
                "name": "my-sfn",
                "source": "src/sfn",
                "state_machine_name": "my-sm",
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
                "function_name": "a",
                "runtime": "python3.14",
            },
            {
                "resource_type": "lambda",
                "name": "b",
                "source": "src/b",
                "ecr": "ferry/b",
                "function_name": "b",
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

    def test_lambda_matrix_includes_function_name(self) -> None:
        """function_name appears in lambda matrix output."""
        payload_str = _make_payload()
        result = build_matrix(payload_str)

        first = result["include"][0]
        assert "function_name" in first
        assert first["function_name"] == "order-processor"

    def test_lambda_matrix_explicit_function_name_override(self) -> None:
        """function_name different from name flows through to matrix."""
        resources = [
            {
                "resource_type": "lambda",
                "name": "order",
                "source": "services/order",
                "ecr": "ferry/order",
                "function_name": "order-processor-prod",
                "runtime": "python3.14",
            },
        ]
        payload_str = _make_payload(resources=resources)
        result = build_matrix(payload_str)

        entry = result["include"][0]
        assert entry["name"] == "order"
        assert entry["function_name"] == "order-processor-prod"

    def test_step_function_matrix(self) -> None:
        """Step Function resources produce correct matrix entries."""
        resources = [
            {
                "resource_type": "step_function",
                "name": "checkout-flow",
                "source": "workflows/checkout",
                "state_machine_name": "checkout-sm",
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
        assert entry["name"] == "checkout-flow"
        assert entry["source"] == "workflows/checkout"
        assert entry["state_machine_name"] == "checkout-sm"
        assert entry["definition_file"] == "stepfunction.json"
        assert entry["trigger_sha"] == "abc1234def5678"
        assert entry["deployment_tag"] == "pr-42"
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
                "name": "flow-a",
                "source": "wf/a",
                "state_machine_name": "sm-a",
                "definition_file": "def-a.json",
            },
            {
                "resource_type": "step_function",
                "name": "flow-b",
                "source": "wf/b",
                "state_machine_name": "sm-b",
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
        assert names == {"flow-a", "flow-b"}


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
        """Valid payload writes matrix JSON to GITHUB_OUTPUT file."""
        output_file = tmp_path / "github_output"
        output_file.touch()

        monkeypatch.setenv("INPUT_PAYLOAD", _make_payload())
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        main()

        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2

        # First line: matrix output
        assert lines[0].startswith("matrix=")
        matrix_json = lines[0].split("=", 1)[1]
        matrix = json.loads(matrix_json)
        assert "include" in matrix
        assert len(matrix["include"]) == 2

        # Second line: resource_type output
        assert lines[1] == "resource_type=lambda"
