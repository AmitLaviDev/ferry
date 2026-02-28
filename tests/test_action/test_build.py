"""Tests for ferry_action.build module.

TDD tests for Docker build + ECR push logic. All Docker/subprocess
calls are mocked -- these tests verify command construction and
orchestration, never actually invoke Docker.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ferry_action.build import (
    build_docker_command,
    build_ecr_uri,
    ecr_login,
    main,
    parse_runtime_version,
    push_image,
)


class TestBuildEcrUri:
    """Test ECR URI construction."""

    def test_build_ecr_uri(self) -> None:
        result = build_ecr_uri("123456789012", "us-east-1", "ferry/order-processor")
        assert result == "123456789012.dkr.ecr.us-east-1.amazonaws.com/ferry/order-processor"

    def test_build_ecr_uri_different_region(self) -> None:
        result = build_ecr_uri("111222333444", "eu-west-1", "myapp/worker")
        assert result == "111222333444.dkr.ecr.eu-west-1.amazonaws.com/myapp/worker"


class TestParseRuntimeVersion:
    """Test runtime version string parsing."""

    def test_parse_runtime_version_python312(self) -> None:
        assert parse_runtime_version("python3.12") == "3.12"

    def test_parse_runtime_version_python314(self) -> None:
        assert parse_runtime_version("python3.14") == "3.14"

    def test_parse_runtime_version_already_numeric(self) -> None:
        assert parse_runtime_version("3.12") == "3.12"

    def test_parse_runtime_version_python310(self) -> None:
        assert parse_runtime_version("python3.10") == "3.10"


class TestBuildDockerCommand:
    """Test Docker build command construction."""

    def test_build_docker_command_basic(self) -> None:
        cmd = build_docker_command(
            dockerfile_path="/path/to/Dockerfile",
            source_dir="/app/services/order-processor",
            image_tag="123456789012.dkr.ecr.us-east-1.amazonaws.com/ferry/order-processor:pr-42",
            python_version="3.12",
            github_token=None,
        )
        assert cmd[0] == "docker"
        assert cmd[1] == "build"
        assert "--build-arg" in cmd
        # Find the build-arg value
        ba_idx = cmd.index("--build-arg")
        assert cmd[ba_idx + 1] == "PYTHON_VERSION=3.12"
        # Check tag
        assert "--tag" in cmd
        tag_idx = cmd.index("--tag")
        assert (
            cmd[tag_idx + 1]
            == "123456789012.dkr.ecr.us-east-1.amazonaws.com/ferry/order-processor:pr-42"
        )
        # Check file
        assert "--file" in cmd
        file_idx = cmd.index("--file")
        assert cmd[file_idx + 1] == "/path/to/Dockerfile"
        # Build context is last arg
        assert cmd[-1] == "/app/services/order-processor"
        # No secret flag
        assert "--secret" not in cmd

    def test_build_docker_command_with_github_token(self) -> None:
        cmd = build_docker_command(
            dockerfile_path="/path/to/Dockerfile",
            source_dir="/app/services/order-processor",
            image_tag="123456789012.dkr.ecr.us-east-1.amazonaws.com/ferry/order-processor:pr-42",
            python_version="3.12",
            github_token="ghp_abc123",
        )
        assert "--secret" in cmd
        secret_idx = cmd.index("--secret")
        assert cmd[secret_idx + 1] == "id=github_token,env=GITHUB_TOKEN"

    def test_build_docker_command_without_github_token(self) -> None:
        # Empty string should be treated as no token
        cmd = build_docker_command(
            dockerfile_path="/path/to/Dockerfile",
            source_dir="/app/src",
            image_tag="repo:tag",
            python_version="3.14",
            github_token="",
        )
        assert "--secret" not in cmd


class TestEcrLogin:
    """Test ECR login command construction."""

    @patch("ferry_action.build.subprocess.run")
    def test_ecr_login_command(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="password123\n")
        ecr_login("us-east-1", "123456789012.dkr.ecr.us-east-1.amazonaws.com/ferry/repo")

        assert mock_run.call_count == 2
        # First call: get-login-password
        first_call = mock_run.call_args_list[0]
        assert "ecr" in first_call[0][0]
        assert "get-login-password" in first_call[0][0]
        assert "--region" in first_call[0][0]
        assert "us-east-1" in first_call[0][0]

        # Second call: docker login
        second_call = mock_run.call_args_list[1]
        assert "docker" in second_call[0][0]
        assert "login" in second_call[0][0]
        assert "123456789012.dkr.ecr.us-east-1.amazonaws.com" in second_call[0][0]


class TestPushImage:
    """Test image push and digest capture."""

    @patch("ferry_action.build.subprocess.run")
    def test_push_image_captures_digest(self, mock_run: MagicMock) -> None:
        # docker push returns successfully
        push_result = MagicMock()
        push_result.returncode = 0
        # docker inspect returns the repo digest
        inspect_result = MagicMock()
        ecr_base = "123456789012.dkr.ecr.us-east-1.amazonaws.com/ferry/order-processor"
        inspect_result.stdout = f"{ecr_base}@sha256:abcdef1234567890\n"
        mock_run.side_effect = [push_result, inspect_result]

        digest = push_image(f"{ecr_base}:pr-42")

        assert digest == f"{ecr_base}@sha256:abcdef1234567890"
        assert mock_run.call_count == 2
        # First call: docker push
        push_call = mock_run.call_args_list[0]
        assert "push" in push_call[0][0]
        # Second call: docker inspect
        inspect_call = mock_run.call_args_list[1]
        assert "inspect" in inspect_call[0][0]


class TestMain:
    """Test the main orchestrator function."""

    @patch("ferry_action.build.push_image")
    @patch("ferry_action.build.ecr_login")
    @patch("ferry_action.build.subprocess.run")
    @patch("ferry_action.build.boto3")
    def test_main_reads_env_and_orchestrates(
        self,
        mock_boto3: MagicMock,
        mock_subprocess_run: MagicMock,
        mock_ecr_login: MagicMock,
        mock_push_image: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: object,
    ) -> None:
        # Set up env vars
        monkeypatch.setenv("INPUT_RESOURCE_NAME", "order-processor")
        monkeypatch.setenv("INPUT_SOURCE_DIR", "/workspace/services/order-processor")
        monkeypatch.setenv("INPUT_ECR_REPO", "ferry/order-processor")
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("INPUT_RUNTIME", "python3.12")
        monkeypatch.setenv("INPUT_TRIGGER_SHA", "abc1234")
        monkeypatch.setenv("INPUT_GITHUB_TOKEN", "")
        monkeypatch.setenv("AWS_REGION", "us-east-1")

        # Set up GITHUB_OUTPUT
        output_file = tmp_path / "github_output"  # type: ignore[operator]
        output_file.write_text("")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        # Set up GITHUB_STEP_SUMMARY
        summary_file = tmp_path / "step_summary"  # type: ignore[operator]
        summary_file.write_text("")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        # Mock STS
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
        mock_boto3.client.return_value = mock_sts

        # Mock push_image return
        mock_push_image.return_value = "ferry/order-processor@sha256:abc123"

        # Mock subprocess.run for docker build
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        main()

        # Verify STS was called
        mock_boto3.client.assert_called_with("sts")
        mock_sts.get_caller_identity.assert_called_once()

        # Verify docker build was called
        mock_subprocess_run.assert_called_once()
        build_cmd = mock_subprocess_run.call_args[0][0]
        assert "docker" in build_cmd
        assert "build" in build_cmd

        # Verify ECR login was called
        mock_ecr_login.assert_called_once()

        # Verify push was called
        mock_push_image.assert_called_once()

        # Verify outputs were written
        output_content = output_file.read_text()
        assert "image-uri=" in output_content
        assert "image-digest=" in output_content

    @patch("ferry_action.build.push_image")
    @patch("ferry_action.build.ecr_login")
    @patch("ferry_action.build.subprocess.run")
    @patch("ferry_action.build.boto3")
    @patch("ferry_action.build.gha")
    def test_main_masks_account_id(
        self,
        mock_gha: MagicMock,
        mock_boto3: MagicMock,
        mock_subprocess_run: MagicMock,
        mock_ecr_login: MagicMock,
        mock_push_image: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: object,
    ) -> None:
        # Set up env vars
        monkeypatch.setenv("INPUT_RESOURCE_NAME", "order-processor")
        monkeypatch.setenv("INPUT_SOURCE_DIR", "/workspace/services/order-processor")
        monkeypatch.setenv("INPUT_ECR_REPO", "ferry/order-processor")
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("INPUT_RUNTIME", "python3.12")
        monkeypatch.setenv("INPUT_TRIGGER_SHA", "abc1234")
        monkeypatch.setenv("INPUT_GITHUB_TOKEN", "")
        monkeypatch.setenv("AWS_REGION", "us-east-1")

        # Set up GITHUB_OUTPUT and GITHUB_STEP_SUMMARY
        output_file = tmp_path / "github_output"  # type: ignore[operator]
        output_file.write_text("")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        summary_file = tmp_path / "step_summary"  # type: ignore[operator]
        summary_file.write_text("")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        # Mock STS
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
        mock_boto3.client.return_value = mock_sts

        mock_push_image.return_value = "repo@sha256:abc123"
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        main()

        # Verify mask_value was called with the account ID
        mock_gha.mask_value.assert_any_call("123456789012")
