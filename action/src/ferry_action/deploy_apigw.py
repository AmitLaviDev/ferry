"""API Gateway deployment with OpenAPI spec upload and content-hash skip.

Deploys an OpenAPI spec to an API Gateway REST API:
1. Reads spec file (JSON or YAML) from source_dir.
2. Performs envsubst (${ACCOUNT_ID}, ${AWS_REGION}).
3. Parses to dict, strips problematic fields (host, schemes, basePath, servers).
4. Serializes to canonical JSON for hashing and upload.
5. Checks content hash against ferry:content-hash tag (skip if unchanged).
6. Calls put_rest_api (mode=overwrite) + create_deployment.
7. Updates the content hash tag.

Invoked as: python -m ferry_action.deploy_apigw
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import boto3
import yaml
from botocore.exceptions import ClientError

from ferry_action import gha
from ferry_action.envsubst import compute_content_hash, envsubst, get_content_hash_tag

# Fields that API Gateway manages via stages -- these should not be in the spec
_STRIP_FIELDS = frozenset({"host", "schemes", "basePath", "servers"})


def strip_openapi_fields(spec: dict) -> dict:
    """Remove AWS-managed fields from an OpenAPI/Swagger spec.

    Strips Swagger 2.0 fields (``host``, ``schemes``, ``basePath``) and
    OpenAPI 3.x field (``servers``) since API Gateway manages endpoints
    via stages.

    Args:
        spec: The parsed OpenAPI spec dictionary.

    Returns:
        A shallow copy with problematic fields removed.
    """
    result = dict(spec)
    for field in _STRIP_FIELDS:
        result.pop(field, None)
    return result


def should_skip_deploy(
    apigw_client: object,
    rest_api_id: str,
    region: str,
    new_hash: str,
) -> bool:
    """Check whether the deploy can be skipped based on content hash.

    Compares the new content hash against the ``ferry:content-hash`` tag
    on the REST API. If they match, the spec hasn't changed.

    Args:
        apigw_client: A boto3 API Gateway client.
        rest_api_id: The REST API ID to check.
        region: AWS region (for ARN construction).
        new_hash: SHA-256 hash of the canonical spec JSON.

    Returns:
        ``True`` if the hashes match and deploy should be skipped.
    """
    arn = f"arn:aws:apigateway:{region}::/restapis/{rest_api_id}"
    try:
        resp = apigw_client.get_tags(resourceArn=arn)  # type: ignore[union-attr]
    except ClientError:
        return False

    tags = resp.get("tags", {})
    existing_hash = get_content_hash_tag(tags)
    return existing_hash == new_hash


def _tag_content_hash(
    apigw_client: object,
    rest_api_id: str,
    region: str,
    content_hash: str,
) -> None:
    """Tag the REST API with the content hash for skip detection.

    Args:
        apigw_client: A boto3 API Gateway client.
        rest_api_id: The REST API ID to tag.
        region: AWS region (for ARN construction).
        content_hash: The SHA-256 hash to store.
    """
    arn = f"arn:aws:apigateway:{region}::/restapis/{rest_api_id}"
    apigw_client.tag_resource(  # type: ignore[union-attr]
        resourceArn=arn,
        tags={"ferry:content-hash": content_hash},
    )


def deploy_api_gateway(
    apigw_client: object,
    rest_api_id: str,
    stage_name: str,
    spec_body: bytes,
    canonical_json: str,
    region: str,
    deployment_tag: str,
) -> dict[str, object]:
    """Execute the full API Gateway deployment sequence.

    1. Upload spec via ``put_rest_api`` (mode=overwrite).
    2. Create deployment to push changes to the target stage.
    3. Tag the REST API with the content hash.

    Args:
        apigw_client: A boto3 API Gateway client.
        rest_api_id: The REST API ID to deploy to.
        stage_name: The stage name (e.g. ``prod``).
        spec_body: The spec as UTF-8 bytes for ``put_rest_api``.
        canonical_json: Canonical JSON string for content hashing.
        region: AWS region.
        deployment_tag: Tag for traceability (e.g. ``pr-42``).

    Returns:
        Dict with ``deployment_id``, ``rest_api_id``, ``stage``, ``skipped``.
    """
    client = apigw_client  # type: ignore[union-attr]

    # Step 1: Upload spec
    print(f"Uploading spec to REST API {rest_api_id}")
    client.put_rest_api(
        restApiId=rest_api_id,
        mode="overwrite",
        failOnWarnings=False,
        body=spec_body,
    )

    # Step 2: Create deployment
    print(f"Creating deployment to stage '{stage_name}'")
    deploy_resp = client.create_deployment(
        restApiId=rest_api_id,
        stageName=stage_name,
        description=f"Deployed by Ferry: {deployment_tag}",
    )

    # Step 3: Tag content hash
    content_hash = compute_content_hash(canonical_json)
    _tag_content_hash(apigw_client, rest_api_id, region, content_hash)

    return {
        "deployment_id": deploy_resp["id"],
        "rest_api_id": rest_api_id,
        "stage": stage_name,
        "skipped": False,
    }


def main() -> None:
    """Orchestrate API Gateway deployment from GHA environment variables.

    Reads ``INPUT_*`` env vars set by the composite action, parses the
    OpenAPI spec (JSON or YAML), applies envsubst, strips problematic
    fields, checks for content-hash skip, and deploys.
    """
    resource_name = os.environ["INPUT_RESOURCE_NAME"]
    rest_api_id = os.environ["INPUT_REST_API_ID"]
    stage_name = os.environ["INPUT_STAGE_NAME"]
    spec_file = os.environ["INPUT_SPEC_FILE"]
    source_dir = os.environ["INPUT_SOURCE_DIR"]
    deployment_tag = os.environ["INPUT_DEPLOYMENT_TAG"]
    _trigger_sha = os.environ.get("INPUT_TRIGGER_SHA", "unknown")

    # AWS clients
    sts_client = boto3.client("sts")
    account_id = sts_client.get_caller_identity()["Account"]
    region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION", "us-east-1")

    apigw_client = boto3.client("apigateway", region_name=region)

    gha.begin_group(f"Deploying API Gateway: {resource_name}")

    try:
        # Step 1: Read spec file
        spec_path = Path(source_dir) / spec_file
        print(f"Reading spec: {spec_path}")
        raw_content = spec_path.read_text(encoding="utf-8")

        # Step 2: envsubst
        substituted = envsubst(raw_content, account_id, region)

        # Step 3: Parse (JSON or YAML)
        suffix = spec_path.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            spec_dict = yaml.safe_load(substituted)
        else:
            spec_dict = json.loads(substituted)

        # Step 4: Strip problematic fields
        spec_dict = strip_openapi_fields(spec_dict)

        # Step 5: Canonical JSON for deterministic hashing
        canonical = json.dumps(spec_dict, sort_keys=True, separators=(",", ":"))
        content_hash = compute_content_hash(canonical)

        # Step 6: Check skip
        if should_skip_deploy(apigw_client, rest_api_id, region, content_hash):
            print(f"Skipping deploy for {resource_name} -- spec unchanged")
            gha.set_output("skipped", "true")
            gha.set_output("deployment-id", "")

            gha.write_summary(
                f"\n## {resource_name}\n"
                f"| Field | Value |\n"
                f"|---|---|\n"
                f"| REST API | `{rest_api_id}` |\n"
                f"| Stage | `{stage_name}` |\n"
                f"| Status | **Skipped** (spec unchanged) |\n"
                f"| Deployment Tag | `{deployment_tag}` |\n"
            )
            return

        # Step 7: Deploy
        spec_body = canonical.encode("utf-8")
        result = deploy_api_gateway(
            apigw_client, rest_api_id, stage_name, spec_body, canonical, region, deployment_tag
        )

        gha.set_output("skipped", "false")
        gha.set_output("deployment-id", result["deployment_id"])

        gha.write_summary(
            f"\n## {resource_name}\n"
            f"| Field | Value |\n"
            f"|---|---|\n"
            f"| REST API | `{rest_api_id}` |\n"
            f"| Stage | `{stage_name}` |\n"
            f"| Deployment ID | `{result['deployment_id']}` |\n"
            f"| Status | **Deployed** |\n"
            f"| Deployment Tag | `{deployment_tag}` |\n"
        )

    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        hints = {
            "NotFoundException": (
                f"REST API '{rest_api_id}' not found"
            ),
            "BadRequestException": (
                "Invalid OpenAPI spec -- check spec syntax"
            ),
            "AccessDeniedException": (
                "IAM role lacks apigateway permissions"
            ),
        }
        hint = hints.get(error_code, str(exc))
        gha.error(f"Deploy failed for {resource_name}: {hint}")
        sys.exit(1)

    finally:
        gha.end_group()


if __name__ == "__main__":
    main()
