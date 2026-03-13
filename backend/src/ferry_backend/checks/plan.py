"""PR comment formatting and command parsing for plan/apply workflows.

Provides:
- format_plan_comment / format_no_changes_comment -- branded plan previews
- parse_ferry_command -- parse /ferry plan|apply from comment body
- format_apply_comment / format_apply_status_update -- apply comment lifecycle
- find_apply_comment -- paginated search for SHA-specific apply marker
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
    "lambda": "Lambdas",
    "step_function": "Step Functions",
    "api_gateway": "API Gateways",
}

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

APPLY_MARKER_TEMPLATE = "<!-- ferry:apply:{sha} -->"


def format_apply_comment(
    affected: list[AffectedResource],
    environment: EnvironmentMapping | None,
    head_sha: str,
) -> str:
    """Format a deploy-triggered comment for a PR.

    Args:
        affected: List of AffectedResource being deployed.
        environment: Optional environment mapping (for display name).
        head_sha: Commit SHA being deployed (used in marker and display).

    Returns:
        Markdown body for the apply comment.
    """
    marker = APPLY_MARKER_TEMPLATE.format(sha=head_sha)
    env_name = environment.name if environment else "default"
    parts = [
        marker,
        f"## {FERRY_EMOJI} Ferry: Deploy Triggered",
        "",
        f"Deploying **{len(affected)} resource(s)** to **{env_name}** at `{head_sha[:7]}`...",
        "",
        "_Waiting for workflow to complete..._",
    ]
    return "\n".join(parts)


def format_apply_status_update(
    original_body: str,
    conclusion: str,
    run_url: str,
) -> str:
    """Replace the waiting line in an apply comment with the final status.

    Args:
        original_body: The existing apply comment body.
        conclusion: Workflow run conclusion (success, failure, cancelled, etc.).
        run_url: URL to the GitHub Actions workflow run.

    Returns:
        Updated comment body with conclusion and run link.
    """
    status_emoji = {"success": "\u2705", "failure": "\u274c", "cancelled": "\u26a0\ufe0f"}
    emoji = status_emoji.get(conclusion, "\u2753")
    status_line = f"**Result:** {emoji} `{conclusion}` -- [View run]({run_url})"
    return original_body.replace(
        "_Waiting for workflow to complete..._",
        status_line,
    )


# ---------------------------------------------------------------------------
# Find apply comment (paginated)
# ---------------------------------------------------------------------------


def find_apply_comment(
    client: GitHubClient,
    repo: str,
    pr_number: int,
    trigger_sha: str,
) -> dict | None:
    """Find an existing apply comment on a PR by the SHA-specific marker.

    Paginates through issue comments looking for the apply marker with the
    given trigger SHA.

    Args:
        client: Authenticated GitHubClient.
        repo: Repository full name (owner/repo).
        pr_number: PR number to search comments on.
        trigger_sha: The SHA used in the apply marker.

    Returns:
        The comment dict if found, or None.
    """
    marker = APPLY_MARKER_TEMPLATE.format(sha=trigger_sha)
    page = 1
    per_page = 100
    while True:
        resp = client.get(
            f"/repos/{repo}/issues/{pr_number}/comments",
            params={"per_page": per_page, "page": page},
        )
        if resp.status_code != 200:
            logger.warning(
                "apply_comment_search_failed",
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
