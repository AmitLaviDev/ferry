"""Change detection: Compare API fetch, source_dir matching, config diffing.

Core intelligence of Ferry App -- determines which resources need dispatch
based on changed files and config diffs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ferry_backend.config.schema import FerryConfig
    from ferry_backend.github.client import GitHubClient

logger = structlog.get_logger()

# Maps config section attribute name to resource_type string
_SECTION_TYPE_MAP: dict[str, str] = {
    "lambdas": "lambda",
    "step_functions": "step_function",
    "api_gateways": "api_gateway",
}


@dataclass(frozen=True)
class AffectedResource:
    """A resource affected by a push event.

    Attributes:
        name: Resource name from ferry.yaml.
        resource_type: One of "lambda", "step_function", "api_gateway".
        change_kind: "modified" or "new".
        changed_files: File paths that triggered this resource (tuple for immutability).
    """

    name: str
    resource_type: str
    change_kind: str
    changed_files: tuple[str, ...]


def get_changed_files(
    client: GitHubClient,
    repo: str,
    base: str,
    head: str,
) -> list[str]:
    """Fetch changed file paths from GitHub Compare API.

    Args:
        client: Authenticated GitHub API client.
        repo: Repository full name (owner/repo).
        base: Base commit SHA.
        head: Head commit SHA.

    Returns:
        List of changed file paths. Empty list if base is all zeros
        (initial push -- caller handles via all-resources fallback).
    """
    # Initial push: base is all zeros, no comparison possible
    if base == "0" * 40:
        return []

    resp = client.get(f"/repos/{repo}/compare/{base}...{head}")
    resp.raise_for_status()
    data = resp.json()

    files = [f["filename"] for f in data.get("files", [])]

    if len(files) == 300:
        logger.warning(
            "Compare API returned 300 files (possible truncation)",
            repo=repo,
            base=base,
            head=head,
        )

    return files


def match_resources(
    config: FerryConfig,
    changed_files: list[str],
) -> list[AffectedResource]:
    """Match changed files to ferry.yaml resources by source_dir prefix.

    For each resource across all type sections, checks if any changed file
    starts with the resource's source_dir (with trailing slash normalization
    to prevent partial-prefix false matches).

    Args:
        config: Parsed and validated FerryConfig.
        changed_files: List of changed file paths from Compare API.

    Returns:
        List of AffectedResource with change_kind="modified" for source_dir matches.
    """
    affected: list[AffectedResource] = []

    for section_attr, resource_type in _SECTION_TYPE_MAP.items():
        resources = getattr(config, section_attr)
        for resource in resources:
            # Normalize source_dir to ensure trailing slash for prefix comparison
            prefix = resource.source_dir.rstrip("/") + "/"
            matching = [f for f in changed_files if f.startswith(prefix)]
            if matching:
                affected.append(
                    AffectedResource(
                        name=resource.name,
                        resource_type=resource_type,
                        change_kind="modified",
                        changed_files=tuple(matching),
                    )
                )

    return affected


def merge_affected(
    source_affected: list[AffectedResource],
    config_affected: list[AffectedResource],
) -> list[AffectedResource]:
    """Merge source-dir and config-diff affected resource lists.

    Deduplicates by (name, resource_type) key. If the same resource
    appears in both lists, prefers the "new" change_kind entry,
    otherwise keeps the entry with more changed_files.

    Args:
        source_affected: Resources affected by source file changes.
        config_affected: Resources affected by ferry.yaml config changes.

    Returns:
        Deduplicated list of AffectedResource.
    """
    merged: dict[tuple[str, str], AffectedResource] = {}

    for resource in source_affected:
        key = (resource.name, resource.resource_type)
        merged[key] = resource

    for resource in config_affected:
        key = (resource.name, resource.resource_type)
        existing = merged.get(key)
        if existing is None:
            merged[key] = resource
        elif resource.change_kind == "new":
            # "new" from config takes priority
            merged[key] = resource
        elif len(resource.changed_files) > len(existing.changed_files):
            merged[key] = resource

    return list(merged.values())


def detect_config_changes(
    old_config: FerryConfig | None,
    new_config: FerryConfig,
) -> list[AffectedResource]:
    """Diff old vs new ferry.yaml to identify resources whose config changed.

    Compares resource entries between old and new config by name within
    each resource type section:
    - Resource in new but not old -> "new"
    - Resource in old but not new -> ignored (removal, no dispatch)
    - Resource in both but fields differ -> "modified" (changed_files=("ferry.yaml",))
    - Resource in both and identical -> not affected

    Args:
        old_config: Previous ferry.yaml config (None if ferry.yaml didn't exist before).
        new_config: Current ferry.yaml config.

    Returns:
        List of AffectedResource entries for config-level changes.
    """
    affected: list[AffectedResource] = []

    for section_attr, resource_type in _SECTION_TYPE_MAP.items():
        new_resources = getattr(new_config, section_attr)

        if old_config is None:
            # No previous config: all resources are new
            for resource in new_resources:
                affected.append(
                    AffectedResource(
                        name=resource.name,
                        resource_type=resource_type,
                        change_kind="new",
                        changed_files=("ferry.yaml",),
                    )
                )
            continue

        old_resources = getattr(old_config, section_attr)

        # Build name -> resource dicts for comparison
        old_by_name = {r.name: r for r in old_resources}
        new_by_name = {r.name: r for r in new_resources}

        old_names = set(old_by_name.keys())
        new_names = set(new_by_name.keys())

        # New resources (in new but not old)
        for name in new_names - old_names:
            affected.append(
                AffectedResource(
                    name=name,
                    resource_type=resource_type,
                    change_kind="new",
                    changed_files=("ferry.yaml",),
                )
            )

        # Removed resources (in old but not new): skip (no dispatch)

        # Common resources: compare model_dump() dicts
        for name in new_names & old_names:
            if old_by_name[name].model_dump() != new_by_name[name].model_dump():
                affected.append(
                    AffectedResource(
                        name=name,
                        resource_type=resource_type,
                        change_kind="modified",
                        changed_files=("ferry.yaml",),
                    )
                )

    return affected
