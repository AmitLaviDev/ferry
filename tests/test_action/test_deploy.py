"""Tests for Lambda deployment module.

TDD tests using moto for AWS Lambda mocking.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ECR_BASE = "123456789012.dkr.ecr.us-east-1.amazonaws.com"
REPO = "my-service"
IMAGE_TAG = "pr-42"
IMAGE_URI = f"{ECR_BASE}/{REPO}:{IMAGE_TAG}"
IMAGE_URI_V2 = f"{ECR_BASE}/{REPO}:pr-43"


# ---------------------------------------------------------------------------
# Fixtures — all wrapped inside mock_aws context
# ---------------------------------------------------------------------------


@pytest.fixture
def aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy AWS credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def moto_aws(aws_env: None):  # noqa: ANN201
    """Activate moto mock for all AWS services."""
    with mock_aws():
        yield


@pytest.fixture
def lambda_role(moto_aws: None) -> str:
    """Create a dummy IAM role and return its ARN."""
    iam = boto3.client("iam", region_name="us-east-1")
    iam.create_role(
        RoleName="lambda-role",
        AssumeRolePolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": []}),
        Path="/",
    )
    return iam.get_role(RoleName="lambda-role")["Role"]["Arn"]


@pytest.fixture
def lambda_client(moto_aws: None) -> boto3.client:
    """Return a moto-backed Lambda client."""
    return boto3.client("lambda", region_name="us-east-1")


@pytest.fixture
def lambda_function(lambda_client: boto3.client, lambda_role: str) -> str:
    """Create a Lambda function with a container image. Return function name."""
    func_name = "my-service-func"
    lambda_client.create_function(
        FunctionName=func_name,
        Role=lambda_role,
        Code={"ImageUri": IMAGE_URI},
        PackageType="Image",
    )
    return func_name


# ---------------------------------------------------------------------------
# should_skip_deploy tests
# ---------------------------------------------------------------------------


class TestShouldSkipDeploy:
    def test_matching_digest(self) -> None:
        from ferry_action.deploy import should_skip_deploy

        assert should_skip_deploy("sha256:abc123", "sha256:abc123") is True

    def test_different_digest(self) -> None:
        from ferry_action.deploy import should_skip_deploy

        assert should_skip_deploy("sha256:abc123", "sha256:def456") is False

    def test_no_current_digest(self) -> None:
        from ferry_action.deploy import should_skip_deploy

        assert should_skip_deploy(None, "sha256:abc123") is False


# ---------------------------------------------------------------------------
# get_current_image_digest tests
# ---------------------------------------------------------------------------


class TestGetCurrentImageDigest:
    def test_returns_digest(
        self,
        lambda_client: boto3.client,
        lambda_function: str,
    ) -> None:
        from ferry_action.deploy import get_current_image_digest

        digest = get_current_image_digest(lambda_client, lambda_function)
        # moto generates a sha256 digest for the ResolvedImageUri
        assert digest is not None
        assert digest.startswith("sha256:")

    def test_returns_none_for_missing_function(
        self,
        lambda_client: boto3.client,
    ) -> None:
        from ferry_action.deploy import get_current_image_digest

        digest = get_current_image_digest(lambda_client, "nonexistent-func")
        assert digest is None


# ---------------------------------------------------------------------------
# deploy_lambda tests
# ---------------------------------------------------------------------------


class TestDeployLambda:
    def test_updates_function_code(
        self,
        lambda_client: boto3.client,
        lambda_function: str,
    ) -> None:
        from ferry_action.deploy import deploy_lambda

        deploy_lambda(lambda_client, lambda_function, IMAGE_URI_V2, "pr-43", "live")

        gf = lambda_client.get_function(FunctionName=lambda_function)
        assert IMAGE_URI_V2 in gf["Code"]["ImageUri"]

    def test_publishes_version(
        self,
        lambda_client: boto3.client,
        lambda_function: str,
    ) -> None:
        from ferry_action.deploy import deploy_lambda

        deploy_lambda(lambda_client, lambda_function, IMAGE_URI_V2, "pr-43", "live")

        versions = lambda_client.list_versions_by_function(FunctionName=lambda_function)["Versions"]
        # $LATEST + published version
        assert len(versions) >= 2
        published = [v for v in versions if v["Version"] != "$LATEST"]
        assert len(published) >= 1
        assert "Ferry" in published[0]["Description"]
        assert "pr-43" in published[0]["Description"]

    def test_updates_alias(
        self,
        lambda_client: boto3.client,
        lambda_function: str,
    ) -> None:
        from ferry_action.deploy import deploy_lambda

        # Create an existing alias first
        lambda_client.publish_version(FunctionName=lambda_function)
        lambda_client.create_alias(
            FunctionName=lambda_function,
            Name="live",
            FunctionVersion="1",
        )

        result = deploy_lambda(lambda_client, lambda_function, IMAGE_URI_V2, "pr-43", "live")

        alias = lambda_client.get_alias(FunctionName=lambda_function, Name="live")
        assert alias["FunctionVersion"] == result["version"]

    def test_creates_alias_if_not_exists(
        self,
        lambda_client: boto3.client,
        lambda_function: str,
    ) -> None:
        from ferry_action.deploy import deploy_lambda

        # No alias exists yet -- deploy_lambda should create it
        result = deploy_lambda(lambda_client, lambda_function, IMAGE_URI_V2, "pr-43", "live")

        alias = lambda_client.get_alias(FunctionName=lambda_function, Name="live")
        assert alias["Name"] == "live"
        assert alias["FunctionVersion"] == result["version"]

    def test_returns_result_dict(
        self,
        lambda_client: boto3.client,
        lambda_function: str,
    ) -> None:
        from ferry_action.deploy import deploy_lambda

        result = deploy_lambda(lambda_client, lambda_function, IMAGE_URI_V2, "pr-43", "live")

        assert "version" in result
        assert "alias" in result
        assert "skipped" in result
        assert result["skipped"] is False
        assert result["alias"] == "live"
        assert result["version"].isdigit()


# ---------------------------------------------------------------------------
# main() tests
# ---------------------------------------------------------------------------


class TestMain:
    def test_skips_when_digest_matches(
        self,
        monkeypatch: pytest.MonkeyPatch,
        lambda_client: boto3.client,
        lambda_function: str,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        from ferry_action.deploy import main

        # Get the current digest from the moto function
        gf = lambda_client.get_function(FunctionName=lambda_function)
        current_digest = gf["Code"]["ResolvedImageUri"].split("@")[1]

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", lambda_function)
        monkeypatch.setenv("INPUT_IMAGE_URI", IMAGE_URI)
        monkeypatch.setenv("INPUT_IMAGE_DIGEST", current_digest)
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        with patch("ferry_action.deploy.boto3") as mock_boto:
            mock_boto.client.return_value = lambda_client
            main()

        outputs = output_file.read_text()
        assert "skipped=true" in outputs

    def test_deploys_when_digest_differs(
        self,
        monkeypatch: pytest.MonkeyPatch,
        lambda_client: boto3.client,
        lambda_function: str,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        from ferry_action.deploy import main

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", lambda_function)
        monkeypatch.setenv("INPUT_IMAGE_URI", IMAGE_URI_V2)
        monkeypatch.setenv("INPUT_IMAGE_DIGEST", "sha256:completely-different-digest")
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-43")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        with patch("ferry_action.deploy.boto3") as mock_boto:
            mock_boto.client.return_value = lambda_client
            main()

        outputs = output_file.read_text()
        assert "skipped=false" in outputs
        assert "lambda-version=" in outputs
        # Extract version number
        for line in outputs.splitlines():
            if line.startswith("lambda-version="):
                version = line.split("=", 1)[1]
                assert version.isdigit()

    def test_writes_job_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        lambda_client: boto3.client,
        lambda_function: str,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        from ferry_action.deploy import main

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", lambda_function)
        monkeypatch.setenv("INPUT_IMAGE_URI", IMAGE_URI_V2)
        monkeypatch.setenv("INPUT_IMAGE_DIGEST", "sha256:completely-different-digest")
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-43")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        with patch("ferry_action.deploy.boto3") as mock_boto:
            mock_boto.client.return_value = lambda_client
            main()

        summary = summary_file.read_text()
        assert lambda_function in summary
        assert "Deployed" in summary or "deployed" in summary
        assert "pr-43" in summary

    def test_resource_not_found_error_message(
        self,
        monkeypatch: pytest.MonkeyPatch,
        lambda_client: boto3.client,
        moto_aws: None,
        tmp_path: pytest.TempPathFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ResourceNotFoundException error includes ferry.yaml guidance."""
        from ferry_action.deploy import main

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", "nonexistent-function")
        monkeypatch.setenv("INPUT_IMAGE_URI", IMAGE_URI_V2)
        monkeypatch.setenv("INPUT_IMAGE_DIGEST", "sha256:different")
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        with patch("ferry_action.deploy.boto3") as mock_boto:
            mock_boto.client.return_value = lambda_client
            with pytest.raises(SystemExit, match="1"):
                main()

        captured = capsys.readouterr()
        assert "Check ferry.yaml name field" in captured.out

    def test_resource_not_found_hint_unchanged(
        self,
        monkeypatch: pytest.MonkeyPatch,
        moto_aws: None,
        tmp_path: pytest.TempPathFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ResourceNotFoundException hint mentions ferry.yaml name field."""
        from botocore.exceptions import ClientError

        from ferry_action.deploy import main

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", "my-func")
        monkeypatch.setenv("INPUT_IMAGE_URI", IMAGE_URI_V2)
        monkeypatch.setenv("INPUT_IMAGE_DIGEST", "sha256:different")
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        mock_client = MagicMock()
        # get_function returns normally (digest check); update raises error
        mock_client.get_function.return_value = {
            "Code": {"ResolvedImageUri": f"{ECR_BASE}/{REPO}@sha256:old"},
        }
        mock_client.update_function_code.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Function not found"}},
            "UpdateFunctionCode",
        )

        with patch("ferry_action.deploy.boto3") as mock_boto:
            mock_boto.client.return_value = mock_client
            with pytest.raises(SystemExit, match="1"):
                main()

        captured = capsys.readouterr()
        assert "Check ferry.yaml name field" in captured.out

    def test_no_unnecessary_masking(
        self,
        monkeypatch: pytest.MonkeyPatch,
        lambda_client: boto3.client,
        lambda_function: str,
        tmp_path: pytest.TempPathFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from ferry_action.deploy import main

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", lambda_function)
        monkeypatch.setenv("INPUT_IMAGE_URI", IMAGE_URI_V2)
        monkeypatch.setenv("INPUT_IMAGE_DIGEST", "sha256:completely-different-digest")
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-43")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        with patch("ferry_action.deploy.boto3") as mock_boto:
            mock_boto.client.return_value = lambda_client
            main()

        captured = capsys.readouterr()
        assert "::add-mask::" not in captured.out


# ---------------------------------------------------------------------------
# Error mapping tests
# ---------------------------------------------------------------------------


class TestErrorMapping:
    """Tests for improved error mapping in main() -- TD-01 + TD-05."""

    def _setup_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: object,
    ) -> None:
        """Set up minimal env vars for main()."""
        output_file = tmp_path / "github_output"  # type: ignore[operator]
        output_file.write_text("")
        summary_file = tmp_path / "github_summary"  # type: ignore[operator]
        summary_file.write_text("")

        monkeypatch.setenv("INPUT_RESOURCE_NAME", "my-func")
        monkeypatch.setenv("INPUT_IMAGE_URI", IMAGE_URI_V2)
        monkeypatch.setenv("INPUT_IMAGE_DIGEST", "sha256:different")
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    def _make_client_error(self, code: str, message: str) -> object:
        """Create a ClientError with the given code and message."""
        from botocore.exceptions import ClientError

        return ClientError(
            {"Error": {"Code": code, "Message": message}},
            "UpdateFunctionCode",
        )

    def test_access_denied_caller_role(
        self,
        monkeypatch: pytest.MonkeyPatch,
        moto_aws: None,
        tmp_path: pytest.TempPathFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """AccessDeniedException with 'not authorized to perform' hints about deploy role."""
        from ferry_action.deploy import main

        self._setup_env(monkeypatch, tmp_path)

        mock_client = MagicMock()
        # get_function succeeds (returns digest info for skip check)
        mock_client.get_function.return_value = {
            "Code": {"ResolvedImageUri": f"{ECR_BASE}/{REPO}@sha256:old"},
        }
        # update_function_code raises the error
        mock_client.update_function_code.side_effect = self._make_client_error(
            "AccessDeniedException",
            "User: arn:aws:sts::123:assumed-role/deploy is "
            "not authorized to perform: lambda:UpdateFunctionCode",
        )

        with patch("ferry_action.deploy.boto3") as mock_boto:
            mock_boto.client.return_value = mock_client
            with pytest.raises(SystemExit, match="1"):
                main()

        captured = capsys.readouterr()
        output = captured.out
        assert "deploy role" in output.lower() or "lacks permissions" in output.lower()
        assert "(raw:" not in output

    def test_access_denied_target_role(
        self,
        monkeypatch: pytest.MonkeyPatch,
        moto_aws: None,
        tmp_path: pytest.TempPathFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """AccessDeniedException with 'cannot be assumed' hints about execution role."""
        from ferry_action.deploy import main

        self._setup_env(monkeypatch, tmp_path)

        mock_client = MagicMock()
        mock_client.get_function.return_value = {
            "Code": {"ResolvedImageUri": f"{ECR_BASE}/{REPO}@sha256:old"},
        }
        mock_client.update_function_code.side_effect = self._make_client_error(
            "AccessDeniedException",
            "The role defined for the function cannot be assumed by Lambda",
        )

        with patch("ferry_action.deploy.boto3") as mock_boto:
            mock_boto.client.return_value = mock_client
            with pytest.raises(SystemExit, match="1"):
                main()

        captured = capsys.readouterr()
        output = captured.out
        assert "execution role" in output.lower()

    def test_access_denied_generic(
        self,
        monkeypatch: pytest.MonkeyPatch,
        moto_aws: None,
        tmp_path: pytest.TempPathFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """AccessDeniedException with generic message hints about both roles."""
        from ferry_action.deploy import main

        self._setup_env(monkeypatch, tmp_path)

        mock_client = MagicMock()
        mock_client.get_function.return_value = {
            "Code": {"ResolvedImageUri": f"{ECR_BASE}/{REPO}@sha256:old"},
        }
        mock_client.update_function_code.side_effect = self._make_client_error(
            "AccessDeniedException",
            "",
        )

        with patch("ferry_action.deploy.boto3") as mock_boto:
            mock_boto.client.return_value = mock_client
            with pytest.raises(SystemExit, match="1"):
                main()

        captured = capsys.readouterr()
        output = captured.out
        # Should mention both deploy role and execution role
        assert "deploy role" in output.lower() or "both roles" in output.lower()
        assert "execution role" in output.lower() or "both roles" in output.lower()

    def test_error_no_raw_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        moto_aws: None,
        tmp_path: pytest.TempPathFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """No ClientError output should contain '(raw:' pattern."""
        from ferry_action.deploy import main

        self._setup_env(monkeypatch, tmp_path)

        mock_client = MagicMock()
        mock_client.get_function.return_value = {
            "Code": {"ResolvedImageUri": f"{ECR_BASE}/{REPO}@sha256:old"},
        }
        mock_client.update_function_code.side_effect = self._make_client_error(
            "ServiceException",
            "Internal error",
        )

        with patch("ferry_action.deploy.boto3") as mock_boto:
            mock_boto.client.return_value = mock_client
            with pytest.raises(SystemExit, match="1"):
                main()

        captured = capsys.readouterr()
        assert "(raw:" not in captured.out
