"""Sticky PR plan comment -- branded deployment preview on pull requests.

Creates and updates a single "plan" comment per PR showing affected resources,
environment mapping, and expected deployment behavior. Uses a hidden HTML marker
to find and update the same comment across PR synchronize events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ferry_backend.config.schema import EnvironmentMapping, FerryConfig
    from ferry_backend.detect.changes import AffectedResource
    from ferry_backend.github.client import GitHubClient

logger = structlog.get_logger()

PLAN_MARKER = "<!-- ferry:plan -->"

# Display names for resource type section headers
_TYPE_DISPLAY_NAMES: dict[str, str] = {
    "lambda": "Lambdas",
    "step_function": "Step Functions",
    "api_gateway": "API Gateways",
}


def resolve_environment(
    config: FerryConfig,
    base_branch: str,
) -> EnvironmentMapping | None:
    """Find the environment mapping for a target branch.

    Matches the first environment whose ``branch`` field equals *base_branch*
    (the PR's merge target).

    Args:
        config: Validated FerryConfig with optional environments list.
        base_branch: The PR base branch name (e.g. "main", "develop").

    Returns:
        The first matching EnvironmentMapping, or None if no match.
    """
    for env in config.environments:
        if env.branch == base_branch:
            return env
    return None


def format_plan_comment(
    affected: list[AffectedResource],
    environment: EnvironmentMapping | None = None,
) -> str:
    """Format a branded sticky plan comment for a PR.

    Args:
        affected: List of AffectedResource from change detection.
        environment: Optional environment mapping for the target branch.

    Returns:
        Markdown body for the PR comment.
    """
    parts: list[str] = [PLAN_MARKER]

    # Header
    if environment:
        parts.append(f"## \U0001f6a2 Ferry: Deployment Plan \u2192 **{environment.name}**")
    else:
        parts.append("## \U0001f6a2 Ferry: Deployment Plan")

    parts.append("")

    # Group by resource type
    grouped: dict[str, list[AffectedResource]] = {}
    for resource in affected:
        grouped.setdefault(resource.resource_type, []).append(resource)

    # Iterate in stable order
    for rtype in ("lambda", "step_function", "api_gateway"):
        resources = grouped.get(rtype)
        if not resources:
            continue

        display_name = _TYPE_DISPLAY_NAMES[rtype]
        parts.append(f"#### {display_name}")
        parts.append("")

        for resource in resources:
            parts.append(f"- **{resource.name}** _({resource.change_kind})_")

        parts.append("")

    # CTA footer
    if environment and not environment.auto_deploy:
        parts.append(
            "_These resources will be queued for manual deployment "
            f"to **{environment.name}** when this PR is merged._"
        )
    elif environment:
        parts.append(
            f"_These resources will be deployed to **{environment.name}** when this PR is merged._"
        )
    else:
        parts.append("_These resources will be deployed when this PR is merged._")

    return "\n".join(parts)


def format_no_changes_comment() -> str:
    """Format a no-changes update for an existing plan comment.

    Returns:
        Markdown body indicating no resources are affected.
    """
    parts: list[str] = [
        PLAN_MARKER,
        "## \U0001f6a2 Ferry: Deployment Plan",
        "",
        "No Ferry-managed resources affected by this PR.",
    ]
    return "\n".join(parts)


def find_plan_comment(
    client: GitHubClient,
    repo: str,
    pr_number: int,
) -> dict | None:
    """Find an existing plan comment on a PR by the hidden marker.

    Paginates through issue comments looking for ``PLAN_MARKER`` in the body.

    Args:
        client: Authenticated GitHubClient.
        repo: Repository full name (owner/repo).
        pr_number: PR number to search comments on.

    Returns:
        The comment dict if found, or None.
    """
    page = 1
    per_page = 100
    while True:
        resp = client.get(
            f"/repos/{repo}/issues/{pr_number}/comments",
            params={"per_page": per_page, "page": page},
        )
        if resp.status_code != 200:
            logger.warning(
                "plan_comment_search_failed",
                status_code=resp.status_code,
                repo=repo,
                pr_number=pr_number,
            )
            return None

        comments = resp.json()
        if not comments:
            return None

        for comment in comments:
            body = comment.get("body", "")
            if PLAN_MARKER in body:
                return comment

        # If fewer than per_page results, we've seen all comments
        if len(comments) < per_page:
            return None

        page += 1


def upsert_plan_comment(
    client: GitHubClient,
    repo: str,
    pr_number: int,
    body: str,
) -> dict:
    """Create or update the sticky plan comment on a PR.

    Searches for an existing comment with ``PLAN_MARKER``; if found, updates
    it via PATCH. Otherwise creates a new comment via POST.

    Args:
        client: Authenticated GitHubClient.
        repo: Repository full name (owner/repo).
        pr_number: PR number to comment on.
        body: Markdown body for the comment.

    Returns:
        Response JSON from the GitHub API.
    """
    existing = find_plan_comment(client, repo, pr_number)

    if existing:
        comment_id = existing["id"]
        resp = client.patch(
            f"/repos/{repo}/issues/comments/{comment_id}",
            json={"body": body},
        )
        logger.info(
            "plan_comment_updated",
            repo=repo,
            pr_number=pr_number,
            comment_id=comment_id,
        )
        return resp.json()

    resp = client.post(
        f"/repos/{repo}/issues/{pr_number}/comments",
        json={"body": body},
    )
    logger.info(
        "plan_comment_created",
        repo=repo,
        pr_number=pr_number,
    )
    return resp.json()
