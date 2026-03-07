"""Docker build + ECR push logic for Lambda container images.

Constructs Docker images using the Magic Dockerfile and pushes them
to ECR. Reads inputs from environment variables set by the composite
action (INPUT_* prefix).

Usage::

    python -m ferry_action.build
"""

from __future__ import annotations

import importlib.resources
import os
import subprocess
import sys

import boto3

from ferry_action import gha
from ferry_action.report import format_error_detail, report_check_run


def parse_runtime_version(runtime: str) -> str:
    """Extract numeric version from a runtime string.

    Strips the ``python`` prefix if present, returning just the
    version number (e.g. ``"python3.14"`` -> ``"3.14"``).

    Args:
        runtime: Runtime string like ``"python3.14"`` or ``"3.14"``.

    Returns:
        Numeric version string.
    """
    if runtime.startswith("python"):
        return runtime[len("python") :]
    return runtime


def build_ecr_uri(aws_account_id: str, aws_region: str, ecr_repo: str) -> str:
    """Construct a full ECR repository URI.

    Args:
        aws_account_id: AWS account ID (12 digits).
        aws_region: AWS region (e.g. ``"us-east-1"``).
        ecr_repo: ECR repository name (e.g. ``"ferry/order-processor"``).

    Returns:
        Full ECR URI like ``"123456789012.dkr.ecr.us-east-1.amazonaws.com/ferry/order-processor"``.
    """
    return f"{aws_account_id}.dkr.ecr.{aws_region}.amazonaws.com/{ecr_repo}"


def build_docker_command(
    dockerfile_path: str,
    source_dir: str,
    image_tag: str,
    python_version: str,
    github_token: str | None,
) -> list[str]:
    """Build the ``docker build`` command as a list of arguments.

    Args:
        dockerfile_path: Path to the Magic Dockerfile.
        source_dir: Path to the Lambda source directory (build context).
        image_tag: Full image tag including ECR URI and deployment tag.
        python_version: Python version for the base image (e.g. ``"3.12"``).
        github_token: GitHub token for private repo deps, or None/empty.

    Returns:
        Command as a list of strings suitable for ``subprocess.run``.
    """
    cmd = [
        "docker",
        "build",
        "--build-arg",
        f"PYTHON_VERSION={python_version}",
        "--tag",
        image_tag,
        "--file",
        dockerfile_path,
    ]
    if github_token:
        cmd.extend(["--secret", "id=github_token,env=GITHUB_TOKEN"])
    cmd.append(source_dir)
    return cmd


def ecr_login(aws_region: str, ecr_uri: str) -> None:
    """Authenticate Docker to ECR.

    Runs ``aws ecr get-login-password`` and pipes the result to
    ``docker login``.

    Args:
        aws_region: AWS region for the ECR registry.
        ecr_uri: Full ECR URI; the registry domain is extracted from it.
    """
    # Extract registry domain (everything before the first /)
    registry = ecr_uri.split("/")[0]

    password_result = subprocess.run(
        ["aws", "ecr", "get-login-password", "--region", aws_region],
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        [
            "docker",
            "login",
            "--username",
            "AWS",
            "--password-stdin",
            registry,
        ],
        input=password_result.stdout.strip(),
        check=True,
    )


def push_image(image_tag: str) -> str:
    """Push a Docker image and return the repo digest.

    Args:
        image_tag: Full image tag to push (e.g. ``"ecr_uri:pr-42"``).

    Returns:
        Repo digest string (e.g. ``"repo@sha256:abc123..."``).
    """
    subprocess.run(["docker", "push", image_tag], check=True)
    result = subprocess.run(
        [
            "docker",
            "inspect",
            "--format={{index .RepoDigests 0}}",
            image_tag,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def main() -> None:
    """Orchestrate Docker build and ECR push.

    Reads configuration from environment variables set by the
    composite action, builds the container image, authenticates
    to ECR, pushes the image, and sets GHA outputs.
    """
    # Read inputs from environment
    resource_name = os.environ["INPUT_RESOURCE_NAME"]
    source_dir = os.environ["INPUT_SOURCE_DIR"]
    ecr_repo = os.environ["INPUT_ECR_REPO"]
    deployment_tag = os.environ["INPUT_DEPLOYMENT_TAG"]
    runtime = os.environ["INPUT_RUNTIME"]
    trigger_sha = os.environ["INPUT_TRIGGER_SHA"]
    github_token = os.environ.get("INPUT_GITHUB_TOKEN", "")
    aws_region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

    # Get AWS account ID
    sts_client = boto3.client("sts")
    account_id = sts_client.get_caller_identity()["Account"]

    # Mask sensitive values
    gha.mask_value(account_id)

    # Build ECR URI
    python_version = parse_runtime_version(runtime)
    ecr_uri = build_ecr_uri(account_id, aws_region, ecr_repo)
    image_tag = f"{ecr_uri}:{deployment_tag}"

    # Locate the Magic Dockerfile bundled inside the package
    dockerfile_path = str(importlib.resources.files("ferry_action").joinpath("Dockerfile"))

    # Build
    gha.begin_group(f"Building {resource_name}")
    try:
        print(f"[1/3] Building Docker image for {resource_name}...")
        cmd = build_docker_command(
            dockerfile_path=dockerfile_path,
            source_dir=source_dir,
            image_tag=image_tag,
            python_version=python_version,
            github_token=github_token or None,
        )
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        hint = "Docker not found. Ensure Docker is installed and available on PATH."
        gha.error(format_error_detail(exc, hint))
        report_check_run(resource_name, "build", "failure", hint, trigger_sha)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or "" if hasattr(exc, "stderr") and exc.stderr else ""
        if "requirements.txt" in stderr:
            hint = (
                "pip install failed. Check requirements.txt for syntax errors "
                "or unavailable packages."
            )
        elif "main.py" in stderr:
            hint = (
                "Lambda handler not found. Ensure main.py exists in source_dir "
                "with a handler() function."
            )
        else:
            hint = (
                f"Build failed for {resource_name}: docker build exited with code {exc.returncode}"
            )
        gha.error(format_error_detail(exc, hint))
        report_check_run(resource_name, "build", "failure", hint, trigger_sha)
        raise
    finally:
        gha.end_group()

    # Push to ECR
    gha.begin_group(f"Pushing {resource_name} to ECR")
    try:
        print("[2/3] Authenticating to ECR...")
        ecr_login(aws_region, ecr_uri)
        print("[3/3] Pushing to ECR...")
        digest = push_image(image_tag)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or "" if hasattr(exc, "stderr") and exc.stderr else ""
        if "ecr" in stderr.lower() or "authorization" in stderr.lower():
            hint = "ECR login failed. Verify the IAM role has ecr:GetAuthorizationToken permission."
        else:
            hint = f"Push failed for {resource_name}: ECR push exited with code {exc.returncode}"
        gha.error(format_error_detail(exc, hint))
        report_check_run(resource_name, "build", "failure", hint, trigger_sha)
        raise
    finally:
        gha.end_group()

    print(f"Done: {resource_name} built and pushed")

    # Report success Check Run
    report_check_run(
        resource_name,
        "build",
        "success",
        f"Built and pushed {resource_name}",
        trigger_sha,
    )

    # Set outputs
    gha.set_output("image-uri", image_tag)
    gha.set_output("image-digest", digest)

    # Write job summary
    summary = (
        f"## {resource_name}\n"
        f"| Field | Value |\n"
        f"|---|---|\n"
        f"| ECR Tag | `{deployment_tag}` |\n"
        f"| Image URI | `{image_tag}` |\n"
        f"| Trigger SHA | `{trigger_sha}` |\n"
        f"| Status | Built and pushed |\n"
    )
    gha.write_summary(summary)


if __name__ == "__main__":
    main()
