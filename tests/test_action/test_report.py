"""Tests for ferry_action.report -- Check Run reporter and error formatting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ferry_action.report import format_error_detail, report_check_run


class TestReportCheckRun:
    """Tests for report_check_run()."""

    def test_posts_to_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Posts correct URL, headers, and body to GitHub API."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        with patch("ferry_action.report.httpx.post") as mock_post:
            report_check_run("order-processor", "build", "success", "Built OK", "abc123")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == "https://api.github.com/repos/owner/repo/check-runs"
        assert call_kwargs[1]["headers"]["Authorization"] == "token ghp_test123"
        assert call_kwargs[1]["headers"]["Accept"] == "application/vnd.github+json"
        assert call_kwargs[1]["headers"]["X-GitHub-Api-Version"] == "2022-11-28"
        body = call_kwargs[1]["json"]
        assert body["name"] == "Ferry: order-processor build"
        assert body["head_sha"] == "abc123"
        assert body["status"] == "completed"
        assert body["conclusion"] == "success"
        assert body["output"]["title"] == "Build succeeded"
        assert body["output"]["summary"] == "Built OK"

    def test_skips_without_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Does not call httpx.post when GITHUB_TOKEN is missing."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        with patch("ferry_action.report.httpx.post") as mock_post:
            report_check_run("svc", "build", "success", "OK", "sha1")

        mock_post.assert_not_called()

    def test_skips_without_repository(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Does not call httpx.post when GITHUB_REPOSITORY is missing."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        with patch("ferry_action.report.httpx.post") as mock_post:
            report_check_run("svc", "build", "success", "OK", "sha1")

        mock_post.assert_not_called()

    def test_catches_http_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Does not propagate httpx errors."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        import httpx

        with patch("ferry_action.report.httpx.post", side_effect=httpx.HTTPError("fail")):
            # Should not raise
            report_check_run("svc", "build", "failure", "Broken", "sha1")

    def test_check_run_name_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Check Run name follows 'Ferry: {name} {phase}' pattern."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        cases = [
            ("order-processor", "build", "Ferry: order-processor build"),
            ("my-api", "deploy", "Ferry: my-api deploy"),
            ("etl-pipeline", "build", "Ferry: etl-pipeline build"),
        ]

        for resource, phase, expected_name in cases:
            with patch("ferry_action.report.httpx.post") as mock_post:
                report_check_run(resource, phase, "success", "OK", "sha1")
            body = mock_post.call_args[1]["json"]
            assert body["name"] == expected_name

    def test_failure_title(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Failure conclusion produces correct title."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        with patch("ferry_action.report.httpx.post") as mock_post:
            report_check_run("svc", "deploy", "failure", "Broken", "sha1")

        body = mock_post.call_args[1]["json"]
        assert body["output"]["title"] == "Deploy failed"


class TestFormatErrorDetail:
    """Tests for format_error_detail()."""

    def test_default_hides_traceback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns only hint without FERRY_DEBUG set."""
        monkeypatch.delenv("FERRY_DEBUG", raising=False)

        try:
            raise ValueError("boom")
        except ValueError as exc:
            result = format_error_detail(exc, "Check your config")

        assert result == "Check your config"
        assert "traceback" not in result.lower()

    def test_debug_shows_traceback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Includes traceback when FERRY_DEBUG=1."""
        monkeypatch.setenv("FERRY_DEBUG", "1")

        try:
            raise ValueError("boom")
        except ValueError as exc:
            result = format_error_detail(exc, "Check your config")

        assert "Check your config" in result
        assert "Full traceback:" in result
        assert "ValueError" in result

    def test_debug_true_variant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Includes traceback when FERRY_DEBUG=true."""
        monkeypatch.setenv("FERRY_DEBUG", "true")

        try:
            raise RuntimeError("test error")
        except RuntimeError as exc:
            result = format_error_detail(exc, "Hint text")

        assert "Hint text" in result
        assert "Full traceback:" in result
        assert "RuntimeError" in result

    def test_debug_yes_variant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Includes traceback when FERRY_DEBUG=yes."""
        monkeypatch.setenv("FERRY_DEBUG", "yes")

        try:
            raise OSError("io error")
        except OSError as exc:
            result = format_error_detail(exc, "IO hint")

        assert "IO hint" in result
        assert "Full traceback:" in result

    def test_debug_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """FERRY_DEBUG=TRUE (uppercase) also works."""
        monkeypatch.setenv("FERRY_DEBUG", "TRUE")

        try:
            raise ValueError("test")
        except ValueError as exc:
            result = format_error_detail(exc, "hint")

        assert "Full traceback:" in result
