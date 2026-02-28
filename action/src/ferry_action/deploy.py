"""Lambda deployment with version/alias management and digest-based skip.

Deploys a container image to an AWS Lambda function:
1. Checks if the image digest matches the currently deployed one (skip if same).
2. Updates function code with the new ECR image URI.
3. Waits for the function update to complete.
4. Publishes a new immutable version with a deployment tag description.
5. Updates (or creates) the ``live`` alias to point to the new version.

Invoked as: ``python -m ferry_action.deploy``
"""

from __future__ import annotations

import os
import sys

import boto3
from botocore.exceptions import ClientError, WaiterError

from ferry_action import gha
from ferry_action.report import format_error_detail, report_check_run


def get_current_image_digest(lambda_client: object, function_name: str) -> str | None:
    """Get the sha256 digest of the currently deployed Lambda image.

    Extracts the digest from ``Code.ResolvedImageUri`` which contains
    ``<repo>@sha256:<hash>``.

    Args:
        lambda_client: A boto3 Lambda client.
        function_name: The Lambda function name.

    Returns:
        The digest string (``sha256:...``) or ``None`` if unavailable.
    """
    try:
        response = lambda_client.get_function(FunctionName=function_name)  # type: ignore[union-attr]
    except ClientError:
        return None

    resolved_uri = response.get("Code", {}).get("ResolvedImageUri")
    if not resolved_uri or "@" not in resolved_uri:
        return None

    return resolved_uri.split("@", 1)[1]


def should_skip_deploy(current_digest: str | None, new_digest: str) -> bool:
    """Determine whether deployment should be skipped.

    Normalizes both digests to just the ``sha256:...`` part (stripping
    any leading URI) before comparing.

    Args:
        current_digest: Digest of the currently deployed image, or ``None``.
        new_digest: Digest of the image to deploy.

    Returns:
        ``True`` if digests match and deploy should be skipped.
    """
    if current_digest is None:
        return False

    def _normalize(d: str) -> str:
        if "@" in d:
            return d.split("@", 1)[1]
        return d

    return _normalize(current_digest) == _normalize(new_digest)


def deploy_lambda(
    lambda_client: object,
    function_name: str,
    image_uri: str,
    deployment_tag: str,
    alias_name: str = "live",
) -> dict[str, object]:
    """Execute the full Lambda deployment sequence.

    1. Update function code with the new image URI.
    2. Wait for ``LastUpdateStatus: Successful``.
    3. Publish a new version with a deployment tag description.
    4. Update or create the alias to point to the new version.

    Args:
        lambda_client: A boto3 Lambda client.
        function_name: The Lambda function name.
        image_uri: Full ECR image URI with tag.
        deployment_tag: Tag for traceability (e.g. ``pr-42``).
        alias_name: Alias name to update/create (default ``live``).

    Returns:
        Dict with ``version``, ``alias``, and ``skipped`` keys.

    Raises:
        ClientError: On AWS API errors.
        WaiterError: If function update times out.
    """
    client = lambda_client  # type: ignore[union-attr]

    # Step 1: Update function code
    print(f"Updating function code: {function_name} -> {image_uri}")
    client.update_function_code(
        FunctionName=function_name,
        ImageUri=image_uri,
    )

    # Step 2: Wait for function update to complete
    print("Waiting for function update to complete...")
    try:
        waiter = client.get_waiter("function_updated")
        waiter.wait(
            FunctionName=function_name,
            WaiterConfig={"Delay": 5, "MaxAttempts": 60},
        )
    except WaiterError as exc:
        msg = f"Lambda update timed out after 5 minutes for '{function_name}'"
        raise WaiterError(name="function_updated", reason=msg) from exc

    # Step 3: Publish a new version
    print("Publishing new version...")
    publish_resp = client.publish_version(
        FunctionName=function_name,
        Description=f"Deployed by Ferry: {deployment_tag}",
    )
    version = publish_resp["Version"]
    print(f"Published version: {version}")

    # Step 4: Update or create alias
    try:
        client.update_alias(
            FunctionName=function_name,
            Name=alias_name,
            FunctionVersion=version,
        )
        print(f"Updated alias '{alias_name}' -> version {version}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            client.create_alias(
                FunctionName=function_name,
                Name=alias_name,
                FunctionVersion=version,
            )
            print(f"Created alias '{alias_name}' -> version {version}")
        else:
            raise

    return {"version": version, "alias": alias_name, "skipped": False}


def main() -> None:
    """Orchestrate Lambda deployment from GHA environment variables.

    Reads ``INPUT_*`` env vars set by the composite action, checks for
    digest-based skip, and either skips or performs the full deploy sequence.
    Writes outputs to ``GITHUB_OUTPUT`` and a summary to ``GITHUB_STEP_SUMMARY``.
    """
    resource_name = os.environ["INPUT_RESOURCE_NAME"]
    function_name = os.environ.get("INPUT_FUNCTION_NAME", "")
    if not function_name:
        gha.error(
            "INPUT_FUNCTION_NAME is required but missing or empty. "
            "Ensure ferry.yaml includes function_name for this Lambda resource."
        )
        sys.exit(1)
    image_uri = os.environ["INPUT_IMAGE_URI"]
    image_digest = os.environ["INPUT_IMAGE_DIGEST"]
    deployment_tag = os.environ["INPUT_DEPLOYMENT_TAG"]
    trigger_sha = os.environ.get("INPUT_TRIGGER_SHA", "")

    client = boto3.client("lambda")

    gha.begin_group(f"Deploying {resource_name}")

    try:
        current_digest = get_current_image_digest(client, function_name)

        if should_skip_deploy(current_digest, image_digest):
            print(f"Skipping deploy for {resource_name} -- image unchanged")
            gha.set_output("skipped", "true")
            gha.set_output("lambda-version", "")

            report_check_run(
                resource_name,
                "deploy",
                "success",
                f"Skipped {resource_name} (image unchanged)",
                trigger_sha,
            )

            gha.write_summary(
                f"\n## {resource_name}\n"
                f"| Field | Value |\n"
                f"|---|---|\n"
                f"| Function | `{function_name}` |\n"
                f"| Status | **Skipped** (image unchanged) |\n"
                f"| Deployment Tag | `{deployment_tag}` |\n"
            )
            return

        result = deploy_lambda(client, function_name, image_uri, deployment_tag)

        gha.set_output("skipped", "false")
        gha.set_output("lambda-version", result["version"])

        report_check_run(
            resource_name,
            "deploy",
            "success",
            f"Deployed {resource_name} v{result['version']}",
            trigger_sha,
        )

        gha.write_summary(
            f"\n## {resource_name}\n"
            f"| Field | Value |\n"
            f"|---|---|\n"
            f"| Function | `{function_name}` |\n"
            f"| ECR Image | `{image_uri}` |\n"
            f"| Lambda Version | `{result['version']}` |\n"
            f"| Alias | `live` |\n"
            f"| Status | **Deployed** |\n"
            f"| Deployment Tag | `{deployment_tag}` |\n"
        )

    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        hints = {
            "AccessDeniedException": (
                f"IAM role lacks lambda:UpdateFunctionCode permission for '{function_name}'"
            ),
            "ResourceNotFoundException": (
                f"Lambda function '{function_name}' not found. "
                f"Check ferry.yaml function_name or verify the "
                f"Lambda exists in the target account."
            ),
        }
        hint = hints.get(error_code, str(exc))
        gha.error(format_error_detail(exc, f"Deploy failed for {resource_name}: {hint}"))
        report_check_run(resource_name, "deploy", "failure", hint, trigger_sha)
        sys.exit(1)

    except WaiterError as exc:
        hint = "Lambda update timed out after 5 minutes"
        gha.error(format_error_detail(exc, f"Deploy failed for {resource_name}: {hint}"))
        report_check_run(resource_name, "deploy", "failure", hint, trigger_sha)
        sys.exit(1)

    finally:
        gha.end_group()


if __name__ == "__main__":
    main()
