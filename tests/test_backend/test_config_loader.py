"""Tests for ferry.yaml config loader (fetch + parse)."""

from __future__ import annotations

import base64

import httpx
import pytest

from ferry_backend.config.loader import fetch_ferry_config, parse_config
from ferry_backend.github.client import GitHubClient
from ferry_utils.errors import ConfigError

SAMPLE_YAML = """\
lambdas:
  - name: order-processor
    source_dir: services/order-processor
    ecr_repo: ferry/order-processor
"""


class TestFetchConfig:
    """Tests for fetch_ferry_config."""

    def test_fetch_config_success(self, httpx_mock) -> None:
        """Mock GET 200 with base64-encoded YAML content returns decoded string."""
        encoded = base64.b64encode(SAMPLE_YAML.encode()).decode()
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/contents/ferry.yaml?ref=abc123",
            json={"content": encoded, "encoding": "base64"},
        )

        client = GitHubClient()
        result = fetch_ferry_config(client, "owner/repo", "abc123")
        assert result == SAMPLE_YAML

    def test_fetch_config_not_found(self, httpx_mock) -> None:
        """Mock GET 404 raises ConfigError with 'not found' message."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/contents/ferry.yaml?ref=abc123",
            status_code=404,
            json={"message": "Not Found"},
        )

        client = GitHubClient()
        with pytest.raises(ConfigError, match="ferry.yaml not found in repository root"):
            fetch_ferry_config(client, "owner/repo", "abc123")

    def test_fetch_config_api_error(self, httpx_mock) -> None:
        """Mock GET 500 raises ConfigError with status detail."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/contents/ferry.yaml?ref=abc123",
            status_code=500,
            json={"message": "Internal Server Error"},
        )

        client = GitHubClient()
        with pytest.raises(ConfigError, match="500"):
            fetch_ferry_config(client, "owner/repo", "abc123")


class TestParseConfig:
    """Tests for parse_config."""

    def test_parse_config_valid(self) -> None:
        """Valid YAML string returns dict with expected keys."""
        result = parse_config(SAMPLE_YAML)
        assert isinstance(result, dict)
        assert "lambdas" in result
        assert result["lambdas"][0]["name"] == "order-processor"

    def test_parse_config_invalid(self) -> None:
        """Malformed YAML raises ConfigError."""
        bad_yaml = "lambdas:\n  - [broken"
        with pytest.raises(ConfigError, match="Malformed ferry.yaml"):
            parse_config(bad_yaml)

    def test_parse_config_empty(self) -> None:
        """Empty string returns None (yaml.safe_load behavior)."""
        result = parse_config("")
        assert result is None
