"""PR comment formatting and command parsing for plan/apply workflows.

Provides:
- format_plan_comment / format_no_changes_comment -- branded plan previews
- parse_ferry_command -- parse /ferry plan|apply from comment body
- format_apply_comment / format_apply_status_update -- apply comment lifecycle
- find_deploy_comment -- paginated search for PR-level deploy marker
- extract_sha_from_comment -- extract trigger SHA from deploy comment
- resolve_environment -- match branch to environment mapping
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ferry_backend.config.schema import EnvironmentMapping, FerryConfig
    from ferry_backend.detect.changes import AffectedResource
    from ferry_backend.github.client import GitHubClient

logger = structlog.get_logger()

# Display names for resource type section headers
_TYPE_DISPLAY_NAMES: dict[str, str] = {
    "lambda": "Lambda",
    "step_function": "Step Function",
    "api_gateway": "API Gateway",
}

# Stable sort order for resource types in tables
_TYPE_ORDER: dict[str, int] = {"lambda": 0, "step_function": 1, "api_gateway": 2}

FERRY_EMOJI = "\U0001f6a2"


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------

_COMMAND_RE = re.compile(
    r"^\s*/ferry\s+(plan|apply)(?:\s.*)?$",
    re.IGNORECASE | re.DOTALL,
)


def parse_ferry_command(body: str) -> str | None:
    """Parse /ferry command from comment body.

    Recognises ``/ferry plan`` and ``/ferry apply`` at the start of the
    (trimmed) body text.  Case-insensitive, trailing text is ignored.

    Args:
        body: Raw comment body text.

    Returns:
        ``"plan"`` or ``"apply"`` if matched, otherwise ``None``.
    """
    match = _COMMAND_RE.match(body.strip())
    return match.group(1).lower() if match else None


# ---------------------------------------------------------------------------
# Environment resolution
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Plan comment formatting
# ---------------------------------------------------------------------------


def format_plan_comment(
    affected: list[AffectedResource],
    environment: EnvironmentMapping | None = None,
) -> str:
    """Format a branded plan comment for a PR.

    Args:
        affected: List of AffectedResource from change detection.
        environment: Optional environment mapping for the target branch.

    Returns:
        Markdown body for the PR comment.
    """
    parts: list[str] = []

    # Header
    if environment:
        parts.append(f"## {FERRY_EMOJI} Ferry: Deployment Plan \u2192 **{environment.name}**")
    else:
        parts.append(f"## {FERRY_EMOJI} Ferry: Deployment Plan")

    parts.append("")

    # Summary counts by type
    type_counts: dict[str, int] = {}
    for resource in affected:
        display_type = _TYPE_DISPLAY_NAMES[resource.resource_type]
        type_counts[display_type] = type_counts.get(display_type, 0) + 1
    summary = " \u00b7 ".join(f"**{count}** {name}" for name, count in type_counts.items())
    parts.append(summary)

    parts.append("")

    # Collapsible resource table
    parts.append("<details>")
    parts.append("<summary>View resources</summary>")
    parts.append("")
    parts.append("| Type | Resource |")
    parts.append("|------|----------|")

    for resource in sorted(affected, key=lambda r: _TYPE_ORDER.get(r.resource_type, 99)):
        display_type = _TYPE_DISPLAY_NAMES[resource.resource_type]
        parts.append(f"| {display_type} | **{resource.name}** |")

    parts.append("")
    parts.append("</details>")
    parts.append("")

    # CTA footer
    if environment and not environment.auto_deploy:
        env = environment.name
        parts.append(f"_Deploy with `/ferry apply`. Manual deployment to **{env}** after merge._")
    elif environment:
        parts.append(
            f"_Deploy with `/ferry apply` or merge to auto-deploy to **{environment.name}**._"
        )
    else:
        parts.append("_Deploy with `/ferry apply` or merge._")

    return "\n".join(parts)


def format_no_changes_comment() -> str:
    """Format a no-changes comment for a PR.

    Returns:
        Markdown body indicating no resources are affected.
    """
    parts: list[str] = [
        f"## {FERRY_EMOJI} Ferry: Deployment Plan",
        "",
        "No Ferry-managed resources affected by this PR.",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Apply comment formatting
# ---------------------------------------------------------------------------

DEPLOY_MARKER_TEMPLATE = "<!-- ferry:deploy:{pr_number} -->"
SHA_MARKER_TEMPLATE = "<!-- ferry:sha:{sha} -->"


def format_apply_comment(
    affected: list[AffectedResource],
    environment: EnvironmentMapping | None,
    head_sha: str,
    pr_number: int,
) -> str:
    """Format a deploy-triggered comment for a PR.

    Creates a sticky deploy comment with a resource status table.
    The comment uses a PR-level marker for upsert and an embedded SHA
    marker for workflow_run correlation.

    Args:
        affected: List of AffectedResource being deployed.
        environment: Optional environment mapping (for display name).
        head_sha: Commit SHA being deployed (used in SHA marker and display).
        pr_number: PR number (used in deploy marker).

    Returns:
        Markdown body for the deploy comment.
    """
    deploy_marker = DEPLOY_MARKER_TEMPLATE.format(pr_number=pr_number)
    sha_marker = SHA_MARKER_TEMPLATE.format(sha=head_sha)
    env_name = environment.name if environment else "default"

    parts = [
        deploy_marker,
        sha_marker,
        f"## {FERRY_EMOJI} Ferry: Deploying \u2192 **{env_name}** at `{head_sha[:7]}`",
        "",
        "| Type | Resource | Status |",
        "|------|----------|--------|",
    ]

    for resource in sorted(affected, key=lambda r: _TYPE_ORDER.get(r.resource_type, 99)):
        display_type = _TYPE_DISPLAY_NAMES[resource.resource_type]
        parts.append(f"| {display_type} | **{resource.name}** | \u23f3 |")

    return "\n".join(parts)


def format_apply_status_update(
    original_body: str,
    conclusion: str,
    run_url: str,
) -> str:
    """Update a deploy comment with final workflow conclusion.

    Updates the header (Deploying -> Deployed/Failed), replaces all
    hourglass status emojis in the resource table, and appends a result
    line with emoji + conclusion + run link.

    Args:
        original_body: The existing deploy comment body.
        conclusion: Workflow run conclusion (success, failure, cancelled, etc.).
        run_url: URL to the GitHub Actions workflow run.

    Returns:
        Updated comment body with conclusion and run link.
    """
    status_emoji = {"success": "\u2705", "failure": "\u274c", "cancelled": "\u26a0\ufe0f"}
    emoji = status_emoji.get(conclusion, "\u2753")

    # Update header: "Deploying" -> "Deployed" (or "Deploy Failed")
    if conclusion == "success":
        updated = original_body.replace("Deploying \u2192", "Deployed \u2192")
    elif conclusion == "failure":
        updated = original_body.replace("Deploying \u2192", "Deploy Failed \u2192")
    else:
        updated = original_body.replace("Deploying \u2192", f"Deploy {conclusion} \u2192")

    # Replace all hourglass in table rows with the conclusion emoji
    updated = updated.replace("| \u23f3 |", f"| {emoji} |")

    # Append result line
    result_line = f"\n\n{emoji} `{conclusion}` \u2014 [View run]({run_url})"
    updated += result_line

    return updated


# ---------------------------------------------------------------------------
# Find deploy comment (paginated)
# ---------------------------------------------------------------------------


def find_deploy_comment(
    client: GitHubClient,
    repo: str,
    pr_number: int,
) -> dict | None:
    """Find the sticky deploy comment on a PR by the PR-level marker.

    Paginates through issue comments looking for the deploy marker keyed
    on PR number (not SHA).

    Args:
        client: Authenticated GitHubClient.
        repo: Repository full name (owner/repo).
        pr_number: PR number to search comments on.

    Returns:
        The comment dict if found, or None.
    """
    marker = DEPLOY_MARKER_TEMPLATE.format(pr_number=pr_number)
    page = 1
    per_page = 100
    while True:
        resp = client.get(
            f"/repos/{repo}/issues/{pr_number}/comments",
            params={"per_page": per_page, "page": page},
        )
        if resp.status_code != 200:
            logger.warning(
                "deploy_comment_search_failed",
                status_code=resp.status_code,
                repo=repo,
                pr_number=pr_number,
            )
            return None

        comments = resp.json()
        if not comments:
            return None

        for comment in comments:
            if marker in comment.get("body", ""):
                return comment

        # If fewer than per_page results, we've seen all comments
        if len(comments) < per_page:
            return None

        page += 1


# ---------------------------------------------------------------------------
# Extract SHA from deploy comment
# ---------------------------------------------------------------------------

_SHA_MARKER_RE = re.compile(r"<!-- ferry:sha:([a-f0-9]+) -->")


def extract_sha_from_comment(body: str) -> str | None:
    """Extract the trigger SHA from a deploy comment body.

    Args:
        body: Comment body text.

    Returns:
        The SHA string, or None if not found.
    """
    match = _SHA_MARKER_RE.search(body)
    return match.group(1) if match else None
