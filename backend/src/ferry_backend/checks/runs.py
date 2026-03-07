"""Check Run creation -- Terraform-plan-like deployment preview on PRs.

Posts a GitHub Check Run named "Ferry: Deployment Plan" with a summary
of affected resources. Also handles config errors and empty changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ferry_backend.detect.changes import AffectedResource
    from ferry_backend.github.client import GitHubClient

logger = structlog.get_logger()

# Display names for resource type section headers
_TYPE_DISPLAY_NAMES: dict[str, str] = {
    "lambda": "Lambdas",
    "step_function": "Step Functions",
    "api_gateway": "API Gateways",
}

# Change kind indicators (Terraform-plan style)
_CHANGE_INDICATORS: dict[str, str] = {
    "modified": "~",
    "new": "+",
}


def format_deployment_plan(affected: list[AffectedResource]) -> tuple[str, str]:
    """Format affected resources as a Terraform-plan-like deployment preview.

    Args:
        affected: List of AffectedResource from change detection.

    Returns:
        Tuple of (summary, text) for Check Run output.
        - summary: "**N resource(s)** will be affected by this change."
        - text: Markdown-formatted deployment plan grouped by type.
    """
    summary = f"**{len(affected)} resource(s)** will be affected by this change."

    # Group by resource type
    grouped: dict[str, list[AffectedResource]] = {}
    for resource in affected:
        grouped.setdefault(resource.resource_type, []).append(resource)

    text_parts: list[str] = []

    # Iterate in a stable order based on type display names
    for rtype in ("lambda", "step_function", "api_gateway"):
        resources = grouped.get(rtype)
        if not resources:
            continue

        display_name = _TYPE_DISPLAY_NAMES[rtype]
        text_parts.append(f"#### {display_name}")
        text_parts.append("")

        for resource in resources:
            indicator = _CHANGE_INDICATORS.get(resource.change_kind, "~")
            text_parts.append(f"  {indicator} **{resource.name}** _({resource.change_kind})_")

            for file_path in resource.changed_files:
                text_parts.append(f"    - `{file_path}`")

            text_parts.append("")

    text_parts.append("_Ferry will deploy these resources when this PR is merged._")

    text = "\n".join(text_parts)
    return summary, text


def create_check_run(
    client: GitHubClient,
    repo: str,
    sha: str,
    affected: list[AffectedResource],
    error: str | None = None,
) -> dict:
    """Post a GitHub Check Run with deployment plan or error.

    Args:
        client: Authenticated GitHubClient with installation token.
        repo: Repository full name (owner/repo).
        sha: Commit SHA to attach the Check Run to.
        affected: List of AffectedResource (empty list if no changes).
        error: Config error message (if ferry.yaml validation failed).

    Returns:
        Response JSON from the Check Runs API.
    """
    if error:
        conclusion = "failure"
        title = "Configuration Error"
        summary = "ferry.yaml validation failed"
        text = f"```\n{error}\n```"
    elif not affected:
        conclusion = "success"
        title = "No Changes Detected"
        summary = "No resources affected by this change."
        text = None
    else:
        conclusion = "success"
        title = "Deployment Plan"
        summary, text = format_deployment_plan(affected)

    output: dict = {
        "title": title,
        "summary": summary,
    }
    if text is not None:
        output["text"] = text

    body: dict = {
        "name": "Ferry: Deployment Plan",
        "head_sha": sha,
        "status": "completed",
        "conclusion": conclusion,
        "output": output,
    }

    resp = client.post(f"/repos/{repo}/check-runs", json=body)

    logger.info(
        "check_run_created",
        conclusion=conclusion,
        title=title,
        affected_count=len(affected),
    )

    return resp.json()


def find_open_prs(
    client: GitHubClient,
    repo: str,
    sha: str,
) -> list[dict]:
    """Find open PRs associated with a commit SHA.

    Uses the List pull requests associated with a commit API endpoint.

    Args:
        client: Authenticated GitHubClient with installation token.
        repo: Repository full name (owner/repo).
        sha: Commit SHA to find PRs for.

    Returns:
        List of open PR dicts (filtered by state=="open").
    """
    resp = client.get(f"/repos/{repo}/commits/{sha}/pulls")
    if resp.status_code != 200:
        logger.warning(
            "pr_lookup_failed",
            status_code=resp.status_code,
            repo=repo,
            sha=sha[:7],
        )
        return []
    prs = resp.json()
    return [pr for pr in prs if pr.get("state") == "open"]


def find_merged_pr(
    client: GitHubClient,
    repo: str,
    sha: str,
) -> dict | None:
    """Find the merged PR associated with a commit SHA.

    Uses the same endpoint as find_open_prs but filters by merged_at
    instead of state=="open". This handles the case where a PR is already
    merged/closed (e.g., config error on default branch push).

    Args:
        client: Authenticated GitHubClient with installation token.
        repo: Repository full name (owner/repo).
        sha: Commit SHA to find the merged PR for.

    Returns:
        The first merged PR dict, or None if no merged PR found.
    """
    resp = client.get(f"/repos/{repo}/commits/{sha}/pulls")
    if resp.status_code != 200:
        logger.warning(
            "pr_lookup_failed",
            status_code=resp.status_code,
            repo=repo,
            sha=sha[:7],
        )
        return None
    prs = resp.json()
    for pr in prs:
        if pr.get("merged_at") is not None:
            return pr
    return None


def post_pr_comment(
    client: GitHubClient,
    repo: str,
    pr_number: int,
    body: str,
) -> dict:
    """Post a comment on a PR (issues API -- PRs are issues).

    Args:
        client: Authenticated GitHubClient with installation token.
        repo: Repository full name (owner/repo).
        pr_number: PR number to comment on.
        body: Markdown body for the comment.

    Returns:
        Response JSON from the Issues Comments API.
    """
    resp = client.post(
        f"/repos/{repo}/issues/{pr_number}/comments",
        json={"body": body},
    )

    logger.info(
        "pr_comment_posted",
        repo=repo,
        pr_number=pr_number,
    )

    return resp.json()
