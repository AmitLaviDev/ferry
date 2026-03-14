"""Step Functions deployment with envsubst and content-hash skip.

Deploys a state machine definition:
1. Reads definition file from source_dir.
2. Performs envsubst (${ACCOUNT_ID}, ${AWS_REGION}).
3. Checks content hash against ferry:content-hash tag (skip if unchanged).
4. Calls update_state_machine with publish=True.
5. Updates the content hash tag.

Invoked as: ``python -m ferry_action.deploy_stepfunctions``
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from ferry_action import gha
from ferry_action.envsubst import (
    compute_content_hash,
    envsubst,
    get_content_hash_tag,
)
from ferry_action.report import format_error_detail, report_check_run


def should_skip_deploy(sfn_client: object, state_machine_arn: str, new_hash: str) -> bool:
    """Determine whether deployment should be skipped based on content hash.

    Reads the ``ferry:content-hash`` tag from the state machine and compares
    it with *new_hash*.

    Args:
        sfn_client: A boto3 Step Functions client.
        state_machine_arn: The ARN of the state machine.
        new_hash: SHA-256 hash of the new definition content.

    Returns:
        ``True`` if the hash matches and deploy should be skipped.
    """
    client = sfn_client  # type: ignore[union-attr]
    try:
        resp = client.list_tags_for_resource(resourceArn=state_machine_arn)
    except ClientError:
        return False

    current_hash = get_content_hash_tag(resp.get("tags", []))
    if current_hash is None:
        return False

    return current_hash == new_hash


def deploy_step_function(
    sfn_client: object,
    state_machine_arn: str,
    definition: str,
    deployment_tag: str,
) -> dict[str, object]:
    """Execute the Step Functions deployment.

    1. Update the state machine definition with ``publish=True``.
    2. Tag the resource with the new content hash.

    Args:
        sfn_client: A boto3 Step Functions client.
        state_machine_arn: The ARN of the state machine.
        definition: The JSON definition string to deploy.
        deployment_tag: Tag for traceability (e.g. ``pr-42``).

    Returns:
        Dict with ``version_arn``, ``state_machine_arn``, and ``skipped`` keys.
    """
    client = sfn_client  # type: ignore[union-attr]

    print(f"Updating state machine: {state_machine_arn}")
    resp = client.update_state_machine(
        stateMachineArn=state_machine_arn,
        definition=definition,
        publish=True,
        versionDescription=f"Deployed by Ferry: {deployment_tag}",
    )

    version_arn = resp.get("stateMachineVersionArn", "")

    # Tag with content hash for skip detection on next deploy
    content_hash = compute_content_hash(definition)
    client.tag_resource(
        resourceArn=state_machine_arn,
        tags=[{"key": "ferry:content-hash", "value": content_hash}],
    )

    return {
        "version_arn": version_arn,
        "state_machine_arn": state_machine_arn,
        "skipped": False,
    }


def main() -> None:
    """Orchestrate Step Functions deployment from GHA environment variables.

    Reads ``INPUT_*`` env vars set by the composite action, applies envsubst,
    checks for content-hash-based skip, and either skips or performs the deploy.
    Writes outputs to ``GITHUB_OUTPUT`` and a summary to ``GITHUB_STEP_SUMMARY``.
    """
    resource_name = os.environ["INPUT_RESOURCE_NAME"]
    state_machine_name = resource_name  # name IS the AWS state machine name
    definition_file = os.environ["INPUT_DEFINITION_FILE"]
    source_dir = os.environ["INPUT_SOURCE_DIR"]
    deployment_tag = os.environ["INPUT_DEPLOYMENT_TAG"]
    trigger_sha = os.environ.get("INPUT_TRIGGER_SHA", "")

    # AWS clients
    sts_client = boto3.client("sts")
    sfn_client = boto3.client("stepfunctions")

    gha.begin_group(f"Deploying {resource_name}")

    try:
        # Resolve account ID and region
        account_id = sts_client.get_caller_identity()["Account"]
        region = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))

        # Construct state machine ARN
        state_machine_arn = (
            f"arn:aws:states:{region}:{account_id}:stateMachine:{state_machine_name}"
        )

        # Read definition file
        def_path = Path(source_dir) / definition_file
        definition_content = def_path.read_text(encoding="utf-8")

        # Apply envsubst
        definition = envsubst(definition_content, account_id, region)

        # Compute content hash of substituted definition
        content_hash = compute_content_hash(definition)

        # Check skip
        if should_skip_deploy(sfn_client, state_machine_arn, content_hash):
            print(f"Skipping deploy for {resource_name} -- definition unchanged")
            gha.set_output("skipped", "true")
            gha.set_output("version-arn", "")

            report_check_run(
                resource_name,
                "deploy",
                "success",
                f"Skipped {resource_name} (definition unchanged)",
                trigger_sha,
            )

            gha.write_summary(
                f"\n## {resource_name}\n"
                f"| Field | Value |\n"
                f"|---|---|\n"
                f"| State Machine | `{state_machine_name}` |\n"
                f"| Definition File | `{definition_file}` |\n"
                f"| Status | **Skipped** (definition unchanged) |\n"
                f"| Deployment Tag | `{deployment_tag}` |\n"
            )
            return

        # Deploy
        result = deploy_step_function(sfn_client, state_machine_arn, definition, deployment_tag)

        gha.set_output("skipped", "false")
        gha.set_output("version-arn", str(result["version_arn"]))

        report_check_run(
            resource_name,
            "deploy",
            "success",
            f"Deployed {resource_name}",
            trigger_sha,
        )

        gha.write_summary(
            f"\n## {resource_name}\n"
            f"| Field | Value |\n"
            f"|---|---|\n"
            f"| State Machine | `{state_machine_name}` |\n"
            f"| Definition File | `{definition_file}` |\n"
            f"| Version ARN | `{result['version_arn']}` |\n"
            f"| Status | **Deployed** |\n"
            f"| Deployment Tag | `{deployment_tag}` |\n"
        )

    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        error_msg = exc.response["Error"].get("Message", "")
        hints = {
            "StateMachineDoesNotExist": (
                f"State machine '{state_machine_name}' not found -- verify it exists in {region}"
            ),
            "AccessDeniedException": (
                f"IAM role lacks states:UpdateStateMachine permission for '{state_machine_name}'"
            ),
            "InvalidDefinition": (
                f"State machine definition is invalid -- check '{definition_file}' syntax"
            ),
        }
        hint = hints.get(error_code, error_code)
        detail = f"Deploy failed for {resource_name}: {hint} ({error_code}: {error_msg})"
        gha.error(format_error_detail(exc, detail))
        report_check_run(resource_name, "deploy", "failure", detail, trigger_sha)
        sys.exit(1)

    finally:
        gha.end_group()


if __name__ == "__main__":
    main()
