"""Parse Ferry dispatch payload (v1 + v2) and output per-type GHA matrices.

Reads the dispatch payload from INPUT_PAYLOAD env var, validates it
against the DispatchPayload (v1) or BatchedDispatchPayload (v2) model,
and outputs per-type boolean flags and matrix JSON strings suitable for
fromJson() in GHA strategy.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

from ferry_action.gha import error, set_output
from ferry_utils.models.dispatch import (
    ApiGatewayResource,
    BatchedDispatchPayload,
    DispatchPayload,
    LambdaResource,
    StepFunctionResource,
)


@dataclass(frozen=True)
class ParseResult:
    """Typed result from parsing a dispatch payload."""

    lambda_matrix: dict
    sf_matrix: dict
    ag_matrix: dict
    has_lambdas: bool
    has_step_functions: bool
    has_api_gateways: bool
    resource_types: str


def _build_lambda_matrix(payload: DispatchPayload) -> list[dict]:
    """Build matrix entries for Lambda resources.

    Runtime flows from the dispatch payload (source of truth: ``LambdaConfig``
    in ferry.yaml).  The build action also accepts ``runtime`` as an input for
    direct workflow-level overrides.
    """
    return [
        {
            "name": r.name,
            "source": r.source,
            "ecr": r.ecr,
            "function_name": r.function_name,
            "trigger_sha": payload.trigger_sha,
            "deployment_tag": payload.deployment_tag,
            "runtime": r.runtime,
        }
        for r in payload.resources
        if isinstance(r, LambdaResource)
    ]


def _build_step_function_matrix(
    payload: DispatchPayload,
) -> list[dict]:
    """Build matrix entries for Step Function resources."""
    return [
        {
            "name": r.name,
            "source": r.source,
            "state_machine_name": r.state_machine_name,
            "definition_file": r.definition_file,
            "trigger_sha": payload.trigger_sha,
            "deployment_tag": payload.deployment_tag,
        }
        for r in payload.resources
        if isinstance(r, StepFunctionResource)
    ]


def _build_api_gateway_matrix(
    payload: DispatchPayload,
) -> list[dict]:
    """Build matrix entries for API Gateway resources."""
    return [
        {
            "name": r.name,
            "source": r.source,
            "rest_api_id": r.rest_api_id,
            "stage_name": r.stage_name,
            "spec_file": r.spec_file,
            "trigger_sha": payload.trigger_sha,
            "deployment_tag": payload.deployment_tag,
        }
        for r in payload.resources
        if isinstance(r, ApiGatewayResource)
    ]


_MATRIX_BUILDERS = {
    "lambda": _build_lambda_matrix,
    "step_function": _build_step_function_matrix,
    "api_gateway": _build_api_gateway_matrix,
}


def build_matrix(payload_str: str) -> dict:
    """Parse dispatch payload and build a GHA matrix dict.

    Args:
        payload_str: Raw JSON string of the dispatch payload.

    Returns:
        Dict with ``include`` key containing one entry per resource.
        Entry fields vary by resource type:

        - **lambda**: name, source, ecr, function_name, trigger_sha, deployment_tag, runtime
        - **step_function**: name, source, state_machine_name,
          definition_file, trigger_sha, deployment_tag
        - **api_gateway**: name, source, rest_api_id, stage_name,
          spec_file, trigger_sha, deployment_tag

    Raises:
        pydantic.ValidationError: If the payload JSON is invalid.
        json.JSONDecodeError: If the string is not valid JSON.
    """
    payload = DispatchPayload.model_validate_json(payload_str)

    builder = _MATRIX_BUILDERS.get(payload.resource_type)
    if builder is None:
        return {"include": []}

    return {"include": builder(payload)}


def parse_payload(payload_str: str) -> ParseResult:
    """Parse v1 or v2 dispatch payload into typed per-type outputs."""
    raw = json.loads(payload_str)
    version = raw.get("v", 1)

    if version == 2:
        return _parse_v2(payload_str)
    return _parse_v1(payload_str)


def _parse_v1(payload_str: str) -> ParseResult:
    """Parse v1 per-type payload into ParseResult format."""
    payload = DispatchPayload.model_validate_json(payload_str)

    builder = _MATRIX_BUILDERS.get(payload.resource_type)
    entries = builder(payload) if builder else []
    matrix = {"include": entries}
    has_resources = bool(entries)

    is_lambda = payload.resource_type == "lambda"
    is_sf = payload.resource_type == "step_function"
    is_ag = payload.resource_type == "api_gateway"

    return ParseResult(
        lambda_matrix=matrix if is_lambda else {"include": []},
        sf_matrix=matrix if is_sf else {"include": []},
        ag_matrix=matrix if is_ag else {"include": []},
        has_lambdas=is_lambda and has_resources,
        has_step_functions=is_sf and has_resources,
        has_api_gateways=is_ag and has_resources,
        resource_types=payload.resource_type if has_resources else "",
    )


def _parse_v2(payload_str: str) -> ParseResult:
    """Parse v2 batched payload into ParseResult format."""
    payload = BatchedDispatchPayload.model_validate_json(payload_str)

    lambda_entries = [
        {
            "name": r.name,
            "source": r.source,
            "ecr": r.ecr,
            "function_name": r.function_name,
            "trigger_sha": payload.trigger_sha,
            "deployment_tag": payload.deployment_tag,
            "runtime": r.runtime,
        }
        for r in payload.lambdas
    ]
    sf_entries = [
        {
            "name": r.name,
            "source": r.source,
            "state_machine_name": r.state_machine_name,
            "definition_file": r.definition_file,
            "trigger_sha": payload.trigger_sha,
            "deployment_tag": payload.deployment_tag,
        }
        for r in payload.step_functions
    ]
    ag_entries = [
        {
            "name": r.name,
            "source": r.source,
            "rest_api_id": r.rest_api_id,
            "stage_name": r.stage_name,
            "spec_file": r.spec_file,
            "trigger_sha": payload.trigger_sha,
            "deployment_tag": payload.deployment_tag,
        }
        for r in payload.api_gateways
    ]

    types: list[str] = []
    if lambda_entries:
        types.append("lambda")
    if sf_entries:
        types.append("step_function")
    if ag_entries:
        types.append("api_gateway")

    return ParseResult(
        lambda_matrix={"include": lambda_entries},
        sf_matrix={"include": sf_entries},
        ag_matrix={"include": ag_entries},
        has_lambdas=bool(lambda_entries),
        has_step_functions=bool(sf_entries),
        has_api_gateways=bool(ag_entries),
        resource_types=",".join(types),
    )


def main() -> None:
    """CLI entrypoint: read INPUT_PAYLOAD, parse, write all outputs to GITHUB_OUTPUT."""
    payload_str = os.environ.get("INPUT_PAYLOAD")
    if not payload_str:
        error("INPUT_PAYLOAD environment variable is not set or empty")
        sys.exit(1)

    try:
        result = parse_payload(payload_str)
    except Exception as exc:
        error(f"Failed to parse dispatch payload: {exc}")
        sys.exit(1)

    set_output("has_lambdas", str(result.has_lambdas).lower())
    set_output("has_step_functions", str(result.has_step_functions).lower())
    set_output("has_api_gateways", str(result.has_api_gateways).lower())
    set_output("lambda_matrix", json.dumps(result.lambda_matrix, separators=(",", ":")))
    set_output("sf_matrix", json.dumps(result.sf_matrix, separators=(",", ":")))
    set_output("ag_matrix", json.dumps(result.ag_matrix, separators=(",", ":")))
    set_output("resource_types", result.resource_types)


if __name__ == "__main__":
    main()
