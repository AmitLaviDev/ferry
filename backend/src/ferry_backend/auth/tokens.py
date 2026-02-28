"""Installation token exchange for GitHub App.

Exchanges a short-lived App JWT for a scoped installation access token
via the GitHub API. The installation token is used for all subsequent
API calls within a webhook processing cycle.

See: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from ferry_utils.errors import GitHubAuthError

if TYPE_CHECKING:
    from ferry_backend.github.client import GitHubClient


def get_installation_token(
    client: GitHubClient,
    jwt_token: str,
    installation_id: int,
) -> str:
    """Exchange App JWT for a scoped installation access token.

    Args:
        client: Authenticated GitHubClient instance (app_auth already called).
        jwt_token: RS256-signed JWT from generate_app_jwt.
        installation_id: GitHub App installation ID for the target repo.

    Returns:
        Installation access token string (e.g., "ghs_...").

    Raises:
        GitHubAuthError: If the JWT is invalid (401) or installation not found (404).
    """
    try:
        resp = client.post(
            f"/app/installations/{installation_id}/access_tokens",
            json={
                "permissions": {
                    "contents": "read",
                    "checks": "write",
                    "actions": "write",
                }
            },
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise GitHubAuthError(
            f"Installation token exchange failed: {exc.response.status_code} {exc.response.text}"
        ) from exc

    return resp.json()["token"]
