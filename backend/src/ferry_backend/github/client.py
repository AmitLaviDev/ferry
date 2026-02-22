"""Thin httpx wrapper for GitHub API.

Adds base URL, standard headers, and auth to all requests.
~150 lines max per project constraint. Not a full GitHub SDK --
just enough for Ferry's 6 endpoints.

See: https://docs.github.com/en/rest/overview/resources-in-the-rest-api
"""

from __future__ import annotations

from typing import Any

import httpx

GITHUB_API_VERSION = "2022-11-28"
GITHUB_ACCEPT = "application/vnd.github+json"


class GitHubClient:
    """Authenticated GitHub API client.

    Wraps httpx.Client with base URL, standard GitHub headers,
    and switchable auth (App JWT or installation token).
    """

    def __init__(
        self,
        base_url: str = "https://api.github.com",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url
        self._headers: dict[str, str] = {
            "Accept": GITHUB_ACCEPT,
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        self._client = httpx.Client(timeout=timeout)

    def app_auth(self, jwt_token: str) -> None:
        """Set auth for GitHub App JWT (short-lived).

        Args:
            jwt_token: RS256-signed JWT from generate_app_jwt.
        """
        self._headers["Authorization"] = f"Bearer {jwt_token}"

    def installation_auth(self, token: str) -> None:
        """Set auth for installation access token.

        Args:
            token: Installation token from get_installation_token.
        """
        self._headers["Authorization"] = f"token {token}"

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send GET request to GitHub API.

        Args:
            path: API path (e.g., "/app/installations"). Prepended with base_url.
            **kwargs: Additional arguments passed to httpx.Client.get.

        Returns:
            httpx.Response from the API.
        """
        url = f"{self.base_url}{path}"
        return self._client.get(url, headers=self._headers, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send POST request to GitHub API.

        Args:
            path: API path (e.g., "/app/installations/{id}/access_tokens").
            **kwargs: Additional arguments passed to httpx.Client.post (e.g., json=...).

        Returns:
            httpx.Response from the API.
        """
        url = f"{self.base_url}{path}"
        return self._client.post(url, headers=self._headers, **kwargs)

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
