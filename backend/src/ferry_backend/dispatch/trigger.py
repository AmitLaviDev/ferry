"""Dispatch triggering -- fire one workflow_dispatch per resource type.

Groups affected resources by type, builds DispatchPayload for each group,
and POSTs to the GitHub Actions workflow_dispatch API.

One dispatch per resource TYPE (not per resource, not monolithic).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from ferry_utils.constants import WORKFLOW_FILENAME
from ferry_utils.models.dispatch import (
    ApiGatewayResource,
    DispatchPayload,
    LambdaResource,
    StepFunctionResource,
)

if TYPE_CHECKING:
    from ferry_backend.config.schema import FerryConfig
    from ferry_backend.detect.changes import AffectedResource
    from ferry_backend.github.client import GitHubClient

logger = structlog.get_logger()

# Maximum payload size for workflow_dispatch inputs (GitHub limit is 65535,
# but we use a conservative limit to avoid edge cases)
_MAX_PAYLOAD_SIZE = 65535


def build_deployment_tag(pr_number: str, branch: str, sha: str) -> str:
    """Build a deployment tag for the dispatch payload.

    Args:
        pr_number: PR number string (empty string if not a PR).
        branch: Branch name.
        sha: Full commit SHA.

    Returns:
        Deployment tag: "pr-{N}" for PRs, "{branch}-{sha7}" otherwise.
    """
    if pr_number:
        return f"pr-{pr_number}"
    return f"{branch}-{sha[:7]}"


def _build_resource(
    resource_type: str,
    name: str,
    config: FerryConfig,
) -> LambdaResource | StepFunctionResource | ApiGatewayResource:
    """Build a dispatch Resource model from an AffectedResource and FerryConfig.

    Looks up the resource in the config to get type-specific fields
    (source_dir -> source, ecr_repo -> ecr, function_name, runtime for lambdas).

    Args:
        resource_type: Resource type string ("lambda", "step_function", "api_gateway").
        name: Resource name to look up in config.
        config: Parsed FerryConfig with full resource details.

    Returns:
        Typed resource model for the dispatch payload.
    """
    if resource_type == "lambda":
        for lam in config.lambdas:
            if lam.name == name:
                return LambdaResource(
                    name=name,
                    source=lam.source_dir,
                    ecr=lam.ecr_repo,
                    function_name=lam.function_name,
                    runtime=lam.runtime,
                )
    elif resource_type == "step_function":
        for sf in config.step_functions:
            if sf.name == name:
                return StepFunctionResource(
                    name=name,
                    source=sf.source_dir,
                    state_machine_name=sf.state_machine_name,
                    definition_file=sf.definition_file,
                )
    elif resource_type == "api_gateway":
        for ag in config.api_gateways:
            if ag.name == name:
                return ApiGatewayResource(
                    name=name,
                    source=ag.source_dir,
                    rest_api_id=ag.rest_api_id,
                    stage_name=ag.stage_name,
                    spec_file=ag.spec_file,
                )

    msg = f"Resource '{name}' of type '{resource_type}' not found in config"
    raise ValueError(msg)


def trigger_dispatches(
    client: GitHubClient,
    repo: str,
    config: FerryConfig,
    affected: list[AffectedResource],
    sha: str,
    deployment_tag: str,
    pr_number: str,
    default_branch: str = "main",
) -> list[dict]:
    """Fire one workflow_dispatch per affected resource type.

    Groups affected resources by type, builds a DispatchPayload for each,
    and POSTs to the GitHub Actions API.

    Args:
        client: Authenticated GitHubClient with installation token.
        repo: Repository full name (owner/repo).
        config: Parsed FerryConfig for resource field lookup.
        affected: List of AffectedResource from change detection.
        sha: Trigger commit SHA.
        deployment_tag: Tag for this deployment (e.g., "pr-42" or "main-abc1234").
        pr_number: PR number string (empty if not a PR merge).
        default_branch: Default branch name for dispatch ref.

    Returns:
        List of result dicts: [{"type": str, "status": int, "workflow": str}].
    """
    if not affected:
        return []

    # Group by resource type
    grouped: dict[str, list[AffectedResource]] = {}
    for resource in affected:
        grouped.setdefault(resource.resource_type, []).append(resource)

    results: list[dict] = []

    for rtype, resources in grouped.items():
        # Build dispatch resources from config
        dispatch_resources = [_build_resource(rtype, r.name, config) for r in resources]

        payload = DispatchPayload(
            resource_type=rtype,
            resources=dispatch_resources,
            trigger_sha=sha,
            deployment_tag=deployment_tag,
            pr_number=pr_number,
        )

        # Determine workflow file
        workflow_file = WORKFLOW_FILENAME

        # Check payload size
        payload_json = payload.model_dump_json()
        if len(payload_json) > _MAX_PAYLOAD_SIZE:
            logger.error(
                "dispatch_payload_too_large",
                resource_type=rtype,
                size=len(payload_json),
                max_size=_MAX_PAYLOAD_SIZE,
                resource_count=len(resources),
            )
            results.append({"type": rtype, "status": 413, "workflow": workflow_file})
            continue

        resp = client.post(
            f"/repos/{repo}/actions/workflows/{workflow_file}/dispatches",
            json={"ref": default_branch, "inputs": {"payload": payload_json}},
        )

        logger.info(
            "dispatch_triggered",
            resource_type=rtype,
            workflow=workflow_file,
            resource_count=len(resources),
            status=resp.status_code,
        )

        results.append({"type": rtype, "status": resp.status_code, "workflow": workflow_file})

    return results
