"""Tests for installation token exchange and GitHub API client."""

import json

import pytest

from ferry_backend.auth.tokens import get_installation_token
from ferry_backend.github.client import GitHubClient
from ferry_utils.errors import GitHubAuthError


class TestGitHubClient:
    """Tests for the thin httpx GitHub API wrapper."""

    def test_default_base_url(self):
        """Default base URL should be the GitHub API."""
        client = GitHubClient()
        assert client.base_url == "https://api.github.com"

    def test_custom_base_url(self):
        """Custom base URL should be settable (for GitHub Enterprise)."""
        client = GitHubClient(base_url="https://github.example.com/api/v3")
        assert client.base_url == "https://github.example.com/api/v3"

    def test_app_auth_sets_bearer_token(self, httpx_mock):
        """app_auth should set Authorization: Bearer header."""
        httpx_mock.add_response(
            url="https://api.github.com/app",
            json={"id": 1, "name": "ferry"},
        )
        client = GitHubClient()
        client.app_auth("fake-jwt-token")
        client.get("/app")
        request = httpx_mock.get_request()
        assert request.headers["authorization"] == "Bearer fake-jwt-token"

    def test_installation_auth_sets_token(self, httpx_mock):
        """installation_auth should set Authorization: token header."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo",
            json={"full_name": "owner/repo"},
        )
        client = GitHubClient()
        client.installation_auth("ghs_abc123")
        client.get("/repos/owner/repo")
        request = httpx_mock.get_request()
        assert request.headers["authorization"] == "token ghs_abc123"

    def test_standard_github_headers(self, httpx_mock):
        """All requests should include standard GitHub API headers."""
        httpx_mock.add_response(
            url="https://api.github.com/app",
            json={"id": 1},
        )
        client = GitHubClient()
        client.app_auth("fake-jwt")
        client.get("/app")
        request = httpx_mock.get_request()
        assert request.headers["accept"] == "application/vnd.github+json"
        assert request.headers["x-github-api-version"] == "2022-11-28"

    def test_get_constructs_full_url(self, httpx_mock):
        """GET should prepend base URL to path."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations",
            json=[],
        )
        client = GitHubClient()
        client.app_auth("fake-jwt")
        client.get("/app/installations")
        request = httpx_mock.get_request()
        assert str(request.url) == "https://api.github.com/app/installations"

    def test_post_sends_json_body(self, httpx_mock):
        """POST should send JSON body and prepend base URL."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations/123/access_tokens",
            json={"token": "ghs_test"},
            status_code=201,
        )
        client = GitHubClient()
        client.app_auth("fake-jwt")
        client.post(
            "/app/installations/123/access_tokens",
            json={"permissions": {"contents": "read"}},
        )
        request = httpx_mock.get_request()
        assert request.method == "POST"
        assert "permissions" in request.content.decode()


class TestGetInstallationToken:
    """Tests for installation token exchange."""

    def test_returns_token_string(self, httpx_mock):
        """Successful exchange should return the token string."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations/12345/access_tokens",
            json={"token": "ghs_test_token_abc123", "expires_at": "2026-02-22T12:00:00Z"},
            status_code=201,
        )
        client = GitHubClient()
        client.app_auth("fake-jwt")
        token = get_installation_token(client, "fake-jwt", 12345)
        assert token == "ghs_test_token_abc123"

    def test_posts_to_correct_endpoint(self, httpx_mock):
        """Should POST to /app/installations/{id}/access_tokens."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations/99999/access_tokens",
            json={"token": "ghs_test"},
            status_code=201,
        )
        client = GitHubClient()
        client.app_auth("fake-jwt")
        get_installation_token(client, "fake-jwt", 99999)
        request = httpx_mock.get_request()
        assert "/app/installations/99999/access_tokens" in str(request.url)

    def test_requests_correct_permissions(self, httpx_mock):
        """Should request contents:read, checks:write, actions:write permissions."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations/12345/access_tokens",
            json={"token": "ghs_test"},
            status_code=201,
        )
        client = GitHubClient()
        client.app_auth("fake-jwt")
        get_installation_token(client, "fake-jwt", 12345)
        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["permissions"]["contents"] == "read"
        assert body["permissions"]["checks"] == "write"
        assert body["permissions"]["actions"] == "write"

    def test_includes_correct_headers(self, httpx_mock):
        """Should include Authorization Bearer, Accept, and API version headers."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations/12345/access_tokens",
            json={"token": "ghs_test"},
            status_code=201,
        )
        client = GitHubClient()
        client.app_auth("fake-jwt")
        get_installation_token(client, "fake-jwt", 12345)
        request = httpx_mock.get_request()
        assert "Bearer" in request.headers["authorization"]
        assert request.headers["accept"] == "application/vnd.github+json"
        assert request.headers["x-github-api-version"] == "2022-11-28"

    def test_bad_jwt_raises_github_auth_error(self, httpx_mock):
        """401 response (bad JWT) should raise GitHubAuthError."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations/12345/access_tokens",
            json={"message": "Bad credentials"},
            status_code=401,
        )
        client = GitHubClient()
        client.app_auth("bad-jwt")
        with pytest.raises(GitHubAuthError, match="401"):
            get_installation_token(client, "bad-jwt", 12345)

    def test_bad_installation_id_raises_github_auth_error(self, httpx_mock):
        """404 response (bad installation ID) should raise GitHubAuthError."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations/99998/access_tokens",
            json={"message": "Not Found"},
            status_code=404,
        )
        client = GitHubClient()
        client.app_auth("fake-jwt")
        with pytest.raises(GitHubAuthError, match="404"):
            get_installation_token(client, "fake-jwt", 99998)
