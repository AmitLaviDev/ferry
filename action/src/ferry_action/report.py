"""Check Run reporter for GitHub PRs.

Creates per-resource Check Runs on pull requests to surface
build and deploy results directly in the PR status view.
Also provides debug-mode error formatting.
"""

from __future__ import annotations

import logging
import os
import traceback

import httpx

logger = logging.getLogger(__name__)

_GITHUB_API_TIMEOUT = 30.0


def report_check_run(
    resource_name: str,
    phase: str,
    conclusion: str,
    summary: str,
    trigger_sha: str,
) -> None:
    """Create a GitHub Check Run for a build or deploy result.

    Posts a Check Run to the GitHub API with a resource-specific name
    (e.g. ``Ferry: my-lambda build``) and a terse summary.

    If ``GITHUB_TOKEN`` or ``GITHUB_REPOSITORY`` are not set, logs a
    warning and returns silently -- this allows local testing without
    GitHub credentials.

    Args:
        resource_name: The resource name (e.g. ``"order-processor"``).
        phase: Either ``"build"`` or ``"deploy"``.
        conclusion: Either ``"success"`` or ``"failure"``.
        summary: Terse message for the Check Run output.
        trigger_sha: The git SHA to attach the Check Run to.
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    if not token or not repo:
        logger.warning(
            "GITHUB_TOKEN or GITHUB_REPOSITORY not set -- skipping Check Run"
        )
        return

    check_name = f"Ferry: {resource_name} {phase}"
    title = f"{phase.capitalize()} {'succeeded' if conclusion == 'success' else 'failed'}"

    url = f"https://api.github.com/repos/{repo}/check-runs"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = {
        "name": check_name,
        "head_sha": trigger_sha,
        "status": "completed",
        "conclusion": conclusion,
        "output": {
            "title": title,
            "summary": summary,
        },
    }

    try:
        httpx.post(url, headers=headers, json=body, timeout=_GITHUB_API_TIMEOUT)
    except (httpx.HTTPError, httpx.TimeoutException):
        logger.warning("Failed to create Check Run for %s", check_name, exc_info=True)


def format_error_detail(exc: BaseException, hint: str) -> str:
    """Format an error message with optional traceback.

    Returns only the *hint* by default. When ``FERRY_DEBUG`` is set
    to ``1``, ``true``, or ``yes`` (case-insensitive), appends the
    full traceback for debugging.

    Args:
        exc: The exception that was caught.
        hint: A human-readable error hint.

    Returns:
        Formatted error string.
    """
    debug = os.environ.get("FERRY_DEBUG", "").lower()
    if debug in ("1", "true", "yes"):
        return f"{hint}\n\nFull traceback:\n{traceback.format_exc()}"
    return hint
