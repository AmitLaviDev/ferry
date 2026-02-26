"""Parse Ferry dispatch payload and output GHA matrix JSON.

Reads the dispatch payload from INPUT_PAYLOAD env var, validates it
against the DispatchPayload model, filters to Lambda resources, and
outputs a matrix JSON string suitable for fromJson() in GHA strategy.
"""

from __future__ import annotations

import json
import os
import sys

from ferry_utils.models.dispatch import DispatchPayload, LambdaResource

from ferry_action.gha import error, set_output


def build_matrix(payload_str: str) -> dict:
    """Parse dispatch payload and build a GHA matrix dict.

    Args:
        payload_str: Raw JSON string of the dispatch payload.

    Returns:
        Dict with "include" key containing one entry per Lambda resource.
        Each entry has: name, source, ecr, trigger_sha, deployment_tag, runtime.

    Raises:
        pydantic.ValidationError: If the payload JSON is invalid.
        json.JSONDecodeError: If the string is not valid JSON.
    """
    payload = DispatchPayload.model_validate_json(payload_str)

    # Filter to Lambda resources only (this phase handles Lambda deployments)
    lambda_resources = [r for r in payload.resources if isinstance(r, LambdaResource)]

    # NOTE: The dispatch payload intentionally does not include a `runtime` field.
    # Runtime is a build concern from ferry.yaml's LambdaConfig, not a dispatch concern.
    # For v1 we default to "python3.12". The build action accepts `runtime` as an
    # input so it can be overridden at the workflow level if needed.
    include = [
        {
            "name": r.name,
            "source": r.source,
            "ecr": r.ecr,
            "trigger_sha": payload.trigger_sha,
            "deployment_tag": payload.deployment_tag,
            "runtime": "python3.12",
        }
        for r in lambda_resources
    ]

    return {"include": include}


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


if __name__ == "__main__":
    main()
