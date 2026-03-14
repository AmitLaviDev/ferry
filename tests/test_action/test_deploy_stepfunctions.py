"""Tests for Step Functions deployment module.

TDD tests using moto for AWS Step Functions mocking.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

if TYPE_CHECKING:
    from pathlib import Path

from ferry_action.envsubst import compute_content_hash

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIMPLE_DEFINITION = json.dumps(
    {"StartAt": "Pass", "States": {"Pass": {"Type": "Pass", "End": True}}}
)

UPDATED_DEFINITION = json.dumps(
    {
        "StartAt": "Hello",
        "States": {"Hello": {"Type": "Pass", "Result": "world", "End": True}},
    }
)

DEFINITION_WITH_VARS = json.dumps(
    {
        "StartAt": "Task",
        "States": {
            "Task": {
                "Type": "Task",
                "Resource": "arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:my-func",
                "End": True,
            }
        },
    }
)

STATE_MACHINE_NAME = "my-state-machine"


# ---------------------------------------------------------------------------
# Fixtures -- all wrapped inside mock_aws context
# ---------------------------------------------------------------------------


@pytest.fixture
def aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy AWS credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")


@pytest.fixture
def moto_aws(aws_env: None):  # noqa: ANN201
    """Activate moto mock for all AWS services."""
    with mock_aws():
        yield


@pytest.fixture
def sfn_client(moto_aws: None) -> boto3.client:
    """Return a moto-backed Step Functions client."""
    return boto3.client("stepfunctions", region_name="us-east-1")


@pytest.fixture
def sts_client(moto_aws: None) -> boto3.client:
    """Return a moto-backed STS client."""
    return boto3.client("sts", region_name="us-east-1")


@pytest.fixture
def iam_role(moto_aws: None) -> str:
    """Create a dummy IAM role and return its ARN."""
    iam = boto3.client("iam", region_name="us-east-1")
    iam.create_role(
        RoleName="sfn-role",
        AssumeRolePolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": []}),
        Path="/",
    )
    return iam.get_role(RoleName="sfn-role")["Role"]["Arn"]


@pytest.fixture
def state_machine(sfn_client: boto3.client, iam_role: str) -> str:
    """Create a state machine and return its ARN.

    Tags it with a known content hash for skip tests.
    """
    known_hash = compute_content_hash(SIMPLE_DEFINITION)
    resp = sfn_client.create_state_machine(
        name=STATE_MACHINE_NAME,
        definition=SIMPLE_DEFINITION,
        roleArn=iam_role,
        tags=[{"key": "ferry:content-hash", "value": known_hash}],
    )
    return resp["stateMachineArn"]


# ---------------------------------------------------------------------------
# should_skip_deploy tests
# ---------------------------------------------------------------------------


class TestShouldSkipDeploy:
    def test_skip_when_hash_matches(self, sfn_client: boto3.client, state_machine: str) -> None:
        from ferry_action.deploy_stepfunctions import should_skip_deploy

        matching_hash = compute_content_hash(SIMPLE_DEFINITION)
        assert should_skip_deploy(sfn_client, state_machine, matching_hash) is True

    def test_deploy_when_hash_differs(self, sfn_client: boto3.client, state_machine: str) -> None:
        from ferry_action.deploy_stepfunctions import should_skip_deploy

        different_hash = compute_content_hash(UPDATED_DEFINITION)
        assert should_skip_deploy(sfn_client, state_machine, different_hash) is False

    def test_deploy_when_no_tag_exists(self, sfn_client: boto3.client, iam_role: str) -> None:
        from ferry_action.deploy_stepfunctions import should_skip_deploy

        # Create a state machine with NO ferry:content-hash tag
        resp = sfn_client.create_state_machine(
            name="no-tag-machine",
            definition=SIMPLE_DEFINITION,
            roleArn=iam_role,
        )
        arn = resp["stateMachineArn"]
        assert should_skip_deploy(sfn_client, arn, "somehash") is False


# ---------------------------------------------------------------------------
# deploy_step_function tests
# ---------------------------------------------------------------------------


class TestDeployStepFunction:
    def test_updates_state_machine_definition(
        self, sfn_client: boto3.client, state_machine: str
    ) -> None:
        from ferry_action.deploy_stepfunctions import deploy_step_function

        deploy_step_function(sfn_client, state_machine, UPDATED_DEFINITION, "pr-42")

        desc = sfn_client.describe_state_machine(stateMachineArn=state_machine)
        assert json.loads(desc["definition"]) == json.loads(UPDATED_DEFINITION)

    def test_publishes_version(self, sfn_client: boto3.client, state_machine: str) -> None:
        from ferry_action.deploy_stepfunctions import deploy_step_function

        # update_state_machine with publish=True should work
        # moto may or may not return a real versionArn, but the call should succeed
        result = deploy_step_function(sfn_client, state_machine, UPDATED_DEFINITION, "pr-42")
        # Verify the definition was updated (confirms update_state_machine was called)
        desc = sfn_client.describe_state_machine(stateMachineArn=state_machine)
        assert json.loads(desc["definition"]) == json.loads(UPDATED_DEFINITION)
        # version_arn key must exist in result (may be empty string if moto doesn't support it)
        assert "version_arn" in result

    def test_tags_content_hash(self, sfn_client: boto3.client, state_machine: str) -> None:
        from ferry_action.deploy_stepfunctions import deploy_step_function

        deploy_step_function(sfn_client, state_machine, UPDATED_DEFINITION, "pr-42")

        tags_resp = sfn_client.list_tags_for_resource(resourceArn=state_machine)
        expected_hash = compute_content_hash(UPDATED_DEFINITION)
        tag_map = {t["key"]: t["value"] for t in tags_resp["tags"]}
        assert tag_map["ferry:content-hash"] == expected_hash

    def test_returns_result_dict(self, sfn_client: boto3.client, state_machine: str) -> None:
        from ferry_action.deploy_stepfunctions import deploy_step_function

        result = deploy_step_function(sfn_client, state_machine, UPDATED_DEFINITION, "pr-42")

        assert "version_arn" in result
        assert "skipped" in result
        assert "state_machine_arn" in result
        assert result["skipped"] is False
        assert result["state_machine_arn"] == state_machine


# ---------------------------------------------------------------------------
# main() tests
# ---------------------------------------------------------------------------


class TestMain:
    def test_skips_when_definition_unchanged(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sfn_client: boto3.client,
        sts_client: boto3.client,
        state_machine: str,
        tmp_path: Path,
    ) -> None:
        from ferry_action.deploy_stepfunctions import main

        # Write definition file identical to what the state machine has
        source_dir = tmp_path / "src"
        source_dir.mkdir()
        def_file = source_dir / "definition.asl.json"
        def_file.write_text(SIMPLE_DEFINITION)

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", STATE_MACHINE_NAME)
        monkeypatch.setenv("INPUT_DEFINITION_FILE", "definition.asl.json")
        monkeypatch.setenv("INPUT_SOURCE_DIR", str(source_dir))
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("INPUT_TRIGGER_SHA", "abc123")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        with (
            patch("ferry_action.deploy_stepfunctions.boto3") as mock_boto,
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sfn_client if svc == "stepfunctions" else sts_client
            )
            main()

        outputs = output_file.read_text()
        assert "skipped=true" in outputs

    def test_deploys_when_definition_changed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sfn_client: boto3.client,
        sts_client: boto3.client,
        state_machine: str,
        tmp_path: Path,
    ) -> None:
        from ferry_action.deploy_stepfunctions import main

        # Write a DIFFERENT definition file
        source_dir = tmp_path / "src"
        source_dir.mkdir()
        def_file = source_dir / "definition.asl.json"
        def_file.write_text(UPDATED_DEFINITION)

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", STATE_MACHINE_NAME)
        monkeypatch.setenv("INPUT_DEFINITION_FILE", "definition.asl.json")
        monkeypatch.setenv("INPUT_SOURCE_DIR", str(source_dir))
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("INPUT_TRIGGER_SHA", "abc123")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        with (
            patch("ferry_action.deploy_stepfunctions.boto3") as mock_boto,
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sfn_client if svc == "stepfunctions" else sts_client
            )
            main()

        outputs = output_file.read_text()
        assert "skipped=false" in outputs

        # Verify definition was actually updated
        desc = sfn_client.describe_state_machine(stateMachineArn=state_machine)
        assert json.loads(desc["definition"]) == json.loads(UPDATED_DEFINITION)

    def test_envsubst_applied(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sfn_client: boto3.client,
        sts_client: boto3.client,
        state_machine: str,
        tmp_path: Path,
    ) -> None:
        from ferry_action.deploy_stepfunctions import main

        source_dir = tmp_path / "src"
        source_dir.mkdir()
        def_file = source_dir / "definition.asl.json"
        def_file.write_text(DEFINITION_WITH_VARS)

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", STATE_MACHINE_NAME)
        monkeypatch.setenv("INPUT_DEFINITION_FILE", "definition.asl.json")
        monkeypatch.setenv("INPUT_SOURCE_DIR", str(source_dir))
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("INPUT_TRIGGER_SHA", "abc123")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        with (
            patch("ferry_action.deploy_stepfunctions.boto3") as mock_boto,
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sfn_client if svc == "stepfunctions" else sts_client
            )
            main()

        # Get the actual account ID from STS
        account_id = sts_client.get_caller_identity()["Account"]

        # Verify definition has substituted values, not placeholders
        desc = sfn_client.describe_state_machine(stateMachineArn=state_machine)
        definition = desc["definition"]
        assert "${ACCOUNT_ID}" not in definition
        assert "${AWS_REGION}" not in definition
        assert account_id in definition
        assert "us-east-1" in definition

    def test_writes_job_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sfn_client: boto3.client,
        sts_client: boto3.client,
        state_machine: str,
        tmp_path: Path,
    ) -> None:
        from ferry_action.deploy_stepfunctions import main

        source_dir = tmp_path / "src"
        source_dir.mkdir()
        def_file = source_dir / "definition.asl.json"
        def_file.write_text(UPDATED_DEFINITION)

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", STATE_MACHINE_NAME)
        monkeypatch.setenv("INPUT_DEFINITION_FILE", "definition.asl.json")
        monkeypatch.setenv("INPUT_SOURCE_DIR", str(source_dir))
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("INPUT_TRIGGER_SHA", "abc123")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        with (
            patch("ferry_action.deploy_stepfunctions.boto3") as mock_boto,
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sfn_client if svc == "stepfunctions" else sts_client
            )
            main()

        summary = summary_file.read_text()
        assert STATE_MACHINE_NAME in summary
        assert "Deployed" in summary or "deployed" in summary

    def test_error_hint_for_missing_state_machine(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sfn_client: boto3.client,
        sts_client: boto3.client,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from ferry_action.deploy_stepfunctions import main

        source_dir = tmp_path / "src"
        source_dir.mkdir()
        def_file = source_dir / "definition.asl.json"
        def_file.write_text(UPDATED_DEFINITION)

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", "nonexistent-machine")
        monkeypatch.setenv("INPUT_DEFINITION_FILE", "definition.asl.json")
        monkeypatch.setenv("INPUT_SOURCE_DIR", str(source_dir))
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("INPUT_TRIGGER_SHA", "abc123")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        with (
            patch("ferry_action.deploy_stepfunctions.boto3") as mock_boto,
            pytest.raises(SystemExit, match="1"),
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sfn_client if svc == "stepfunctions" else sts_client
            )
            main()

        captured = capsys.readouterr()
        assert "::error::" in captured.out
