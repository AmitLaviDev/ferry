"""Ferry config loader -- fetch ferry.yaml from GitHub and parse YAML.

Retrieves ferry.yaml at a specific commit SHA via the GitHub Contents API,
then parses the raw YAML into a Python dict. Both functions raise ConfigError
on failure for fail-fast semantics.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import yaml

from ferry_utils.errors import ConfigError

if TYPE_CHECKING:
    from ferry_backend.github.client import GitHubClient


def fetch_ferry_config(client: GitHubClient, repo: str, sha: str) -> str:
    """Fetch ferry.yaml content from GitHub Contents API at exact commit SHA.

    Args:
        client: Authenticated GitHubClient instance.
        repo: Repository full name (e.g., "owner/repo").
        sha: Commit SHA to fetch config at.

    Returns:
        Raw YAML string (base64-decoded from Contents API response).

    Raises:
        ConfigError: If ferry.yaml not found (404) or other API error.
    """
    resp = client.get(f"/repos/{repo}/contents/ferry.yaml", params={"ref": sha})

    if resp.status_code == 404:
        msg = "ferry.yaml not found in repository root"
        raise ConfigError(msg)

    if resp.status_code >= 400:
        msg = f"GitHub API error fetching ferry.yaml: {resp.status_code} {resp.text}"
        raise ConfigError(msg)

    data = resp.json()
    return base64.b64decode(data["content"]).decode("utf-8")


def parse_config(raw_yaml: str) -> dict[str, Any] | None:
    """Parse raw YAML string into a Python dict.

    Args:
        raw_yaml: Raw YAML string from fetch_ferry_config.

    Returns:
        Parsed dict, or None if the YAML is empty.

    Raises:
        ConfigError: If YAML is malformed.
    """
    try:
        return yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        msg = f"Malformed ferry.yaml: {exc}"
        raise ConfigError(msg) from exc
