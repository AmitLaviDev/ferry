"""Parse Ferry dispatch payload and output GHA matrix JSON.

Reads the dispatch payload from INPUT_PAYLOAD env var, validates it
against the DispatchPayload model, filters to Lambda resources, and
outputs a matrix JSON string suitable for fromJson() in GHA strategy.
"""

from __future__ import annotations

import json
import os
import sys

from ferry_action.gha import error, set_output
from ferry_utils.models.dispatch import (
    ApiGatewayResource,
    DispatchPayload,
    LambdaResource,
    StepFunctionResource,
)


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


def main() -> None:
    """CLI entrypoint: read INPUT_PAYLOAD, build matrix, write to GITHUB_OUTPUT."""
    payload_str = os.environ.get("INPUT_PAYLOAD")
    if not payload_str:
        error("INPUT_PAYLOAD environment variable is not set or empty")
        sys.exit(1)

    try:
        matrix = build_matrix(payload_str)
    except Exception as exc:
        error(f"Failed to parse dispatch payload: {exc}")
        sys.exit(1)

    matrix_json = json.dumps(matrix, separators=(",", ":"))
    set_output("matrix", matrix_json)

    # Extract resource_type for conditional job routing
    payload = DispatchPayload.model_validate_json(payload_str)
    set_output("resource_type", payload.resource_type)


if __name__ == "__main__":
    main()
