"""Tests for API Gateway deployment module.

TDD tests using moto for API Gateway mocking.
moto supports put_rest_api and create_deployment but does NOT support
tag_resource/get_tags for API Gateway, so tag operations use manual mocks.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGION = "us-east-1"
STAGE = "prod"
REST_API_NAME = "my-api"

# Spec that moto can import (needs x-amazon-apigateway-integration for methods)
VALID_MOTO_SPEC = {
    "openapi": "3.0.1",
    "info": {"title": "Test API", "version": "1.0"},
    "paths": {
        "/health": {
            "get": {
                "responses": {"200": {"description": "OK"}},
                "x-amazon-apigateway-integration": {
                    "type": "HTTP",
                    "httpMethod": "GET",
                    "uri": "https://example.com/health",
                },
            }
        }
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy AWS credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def moto_aws(aws_env: None):  # noqa: ANN201
    """Activate moto mock for all AWS services."""
    with mock_aws():
        yield


@pytest.fixture
def apigw_client(moto_aws: None) -> boto3.client:
    """Return a moto-backed API Gateway client."""
    return boto3.client("apigateway", region_name=REGION)


@pytest.fixture
def sts_client(moto_aws: None) -> boto3.client:
    """Return a moto-backed STS client."""
    return boto3.client("sts", region_name=REGION)


@pytest.fixture
def rest_api(apigw_client: boto3.client) -> str:
    """Create a REST API via moto and return the ID."""
    resp = apigw_client.create_rest_api(name=REST_API_NAME)
    return resp["id"]


# ---------------------------------------------------------------------------
# strip_openapi_fields tests
# ---------------------------------------------------------------------------


class TestStripOpenapiFields:
    def test_strips_swagger_20_fields(self) -> None:
        from ferry_action.deploy_apigw import strip_openapi_fields

        spec = {
            "swagger": "2.0",
            "info": {"title": "Test"},
            "host": "api.example.com",
            "schemes": ["https"],
            "basePath": "/v1",
            "paths": {},
        }
        result = strip_openapi_fields(spec)
        assert "host" not in result
        assert "schemes" not in result
        assert "basePath" not in result
        assert result["swagger"] == "2.0"
        assert result["info"] == {"title": "Test"}
        assert result["paths"] == {}

    def test_strips_openapi_3x_servers(self) -> None:
        from ferry_action.deploy_apigw import strip_openapi_fields

        spec = {
            "openapi": "3.0.1",
            "info": {"title": "Test"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {},
        }
        result = strip_openapi_fields(spec)
        assert "servers" not in result
        assert result["openapi"] == "3.0.1"

    def test_strips_all_problematic_fields(self) -> None:
        from ferry_action.deploy_apigw import strip_openapi_fields

        spec = {
            "openapi": "3.0.1",
            "host": "api.example.com",
            "schemes": ["https"],
            "basePath": "/v1",
            "servers": [{"url": "https://api.example.com"}],
            "paths": {},
        }
        result = strip_openapi_fields(spec)
        assert "host" not in result
        assert "schemes" not in result
        assert "basePath" not in result
        assert "servers" not in result

    def test_preserves_required_fields(self) -> None:
        from ferry_action.deploy_apigw import strip_openapi_fields

        spec = {
            "swagger": "2.0",
            "openapi": "3.0.1",
            "info": {"title": "Test"},
            "paths": {"/a": {}},
        }
        result = strip_openapi_fields(spec)
        assert result["swagger"] == "2.0"
        assert result["openapi"] == "3.0.1"
        assert result["info"] == {"title": "Test"}
        assert result["paths"] == {"/a": {}}

    def test_handles_missing_fields_gracefully(self) -> None:
        from ferry_action.deploy_apigw import strip_openapi_fields

        spec = {"openapi": "3.0.1", "info": {"title": "Test"}, "paths": {}}
        result = strip_openapi_fields(spec)
        assert result == spec


# ---------------------------------------------------------------------------
# should_skip_deploy tests
# ---------------------------------------------------------------------------


class TestShouldSkipDeploy:
    def test_skip_when_hash_matches(self) -> None:
        from ferry_action.deploy_apigw import should_skip_deploy

        mock_client = MagicMock()
        mock_client.get_tags.return_value = {"tags": {"ferry:content-hash": "abc123def456"}}

        result = should_skip_deploy(mock_client, "test-api-id", REGION, "abc123def456")
        assert result is True

    def test_deploy_when_hash_differs(self) -> None:
        from ferry_action.deploy_apigw import should_skip_deploy

        mock_client = MagicMock()
        mock_client.get_tags.return_value = {"tags": {"ferry:content-hash": "old-hash"}}

        result = should_skip_deploy(mock_client, "test-api-id", REGION, "new-hash")
        assert result is False

    def test_deploy_when_no_tag_exists(self) -> None:
        from ferry_action.deploy_apigw import should_skip_deploy

        mock_client = MagicMock()
        mock_client.get_tags.return_value = {"tags": {}}

        result = should_skip_deploy(mock_client, "test-api-id", REGION, "any-hash")
        assert result is False

    def test_deploy_when_get_tags_fails(self) -> None:
        from ferry_action.deploy_apigw import should_skip_deploy

        mock_client = MagicMock()
        mock_client.get_tags.side_effect = ClientError(
            {"Error": {"Code": "NotFoundException", "Message": "Not found"}},
            "GetTags",
        )

        result = should_skip_deploy(mock_client, "test-api-id", REGION, "any-hash")
        assert result is False


# ---------------------------------------------------------------------------
# deploy_api_gateway tests
# ---------------------------------------------------------------------------


class TestDeployApiGateway:
    def test_uploads_spec_via_put_rest_api(
        self,
        apigw_client: boto3.client,
        rest_api: str,
    ) -> None:
        from ferry_action.deploy_apigw import deploy_api_gateway

        spec_body = json.dumps(VALID_MOTO_SPEC).encode("utf-8")
        canonical = json.dumps(VALID_MOTO_SPEC, sort_keys=True, separators=(",", ":"))

        with patch.object(apigw_client, "tag_resource"):
            deploy_api_gateway(apigw_client, rest_api, STAGE, spec_body, canonical, REGION, "pr-42")

        # Verify the API still exists (put_rest_api succeeded)
        resp = apigw_client.get_rest_api(restApiId=rest_api)
        assert resp["id"] == rest_api

    def test_creates_deployment(
        self,
        apigw_client: boto3.client,
        rest_api: str,
    ) -> None:
        from ferry_action.deploy_apigw import deploy_api_gateway

        spec_body = json.dumps(VALID_MOTO_SPEC).encode("utf-8")
        canonical = json.dumps(VALID_MOTO_SPEC, sort_keys=True, separators=(",", ":"))

        with patch.object(apigw_client, "tag_resource"):
            deploy_api_gateway(apigw_client, rest_api, STAGE, spec_body, canonical, REGION, "pr-42")

        deployments = apigw_client.get_deployments(restApiId=rest_api)
        assert len(deployments["items"]) >= 1

    def test_tags_content_hash(
        self,
        apigw_client: boto3.client,
        rest_api: str,
    ) -> None:
        from ferry_action.deploy_apigw import deploy_api_gateway

        canonical = json.dumps(VALID_MOTO_SPEC, sort_keys=True, separators=(",", ":"))
        spec_body = canonical.encode("utf-8")

        from ferry_action.envsubst import compute_content_hash

        expected_hash = compute_content_hash(canonical)
        expected_arn = f"arn:aws:apigateway:{REGION}::/restapis/{rest_api}"

        with patch.object(apigw_client, "tag_resource") as mock_tag:
            deploy_api_gateway(apigw_client, rest_api, STAGE, spec_body, canonical, REGION, "pr-42")

        mock_tag.assert_called_once_with(
            resourceArn=expected_arn,
            tags={"ferry:content-hash": expected_hash},
        )

    def test_body_is_bytes(
        self,
        apigw_client: boto3.client,
        rest_api: str,
    ) -> None:
        from ferry_action.deploy_apigw import deploy_api_gateway

        spec_body = json.dumps(VALID_MOTO_SPEC).encode("utf-8")
        canonical = json.dumps(VALID_MOTO_SPEC, sort_keys=True, separators=(",", ":"))

        with (
            patch.object(apigw_client, "put_rest_api", wraps=apigw_client.put_rest_api) as mock_put,
            patch.object(apigw_client, "tag_resource"),
        ):
            deploy_api_gateway(apigw_client, rest_api, STAGE, spec_body, canonical, REGION, "pr-42")

        call_args = mock_put.call_args
        assert isinstance(call_args.kwargs.get("body") or call_args[1].get("body"), bytes)

    def test_returns_result_dict(
        self,
        apigw_client: boto3.client,
        rest_api: str,
    ) -> None:
        from ferry_action.deploy_apigw import deploy_api_gateway

        spec_body = json.dumps(VALID_MOTO_SPEC).encode("utf-8")
        canonical = json.dumps(VALID_MOTO_SPEC, sort_keys=True, separators=(",", ":"))

        with patch.object(apigw_client, "tag_resource"):
            result = deploy_api_gateway(
                apigw_client, rest_api, STAGE, spec_body, canonical, REGION, "pr-42"
            )

        assert "deployment_id" in result
        assert "skipped" in result
        assert "rest_api_id" in result
        assert "stage" in result
        assert result["skipped"] is False
        assert result["rest_api_id"] == rest_api
        assert result["stage"] == STAGE


# ---------------------------------------------------------------------------
# main() tests
# ---------------------------------------------------------------------------


class TestMain:
    def _setup_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
        rest_api_id: str,
        spec_content: str,
        spec_filename: str = "openapi.json",
    ) -> tuple:
        """Helper to set up env vars and temp files for main() tests."""
        source_dir = tmp_path / "src"
        source_dir.mkdir()
        spec_file = source_dir / spec_filename
        spec_file.write_text(spec_content)

        output_file = tmp_path / "github_output"
        output_file.touch()
        summary_file = tmp_path / "github_summary"
        summary_file.touch()

        monkeypatch.setenv("INPUT_RESOURCE_NAME", "my-api")
        monkeypatch.setenv("INPUT_REST_API_ID", rest_api_id)
        monkeypatch.setenv("INPUT_STAGE_NAME", STAGE)
        monkeypatch.setenv("INPUT_SPEC_FILE", spec_filename)
        monkeypatch.setenv("INPUT_SOURCE_DIR", str(source_dir))
        monkeypatch.setenv("INPUT_DEPLOYMENT_TAG", "pr-42")
        monkeypatch.setenv("INPUT_TRIGGER_SHA", "abc123")
        monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        return output_file, summary_file

    def test_deploys_json_spec(
        self,
        monkeypatch: pytest.MonkeyPatch,
        apigw_client: boto3.client,
        sts_client: boto3.client,
        rest_api: str,
        tmp_path,
    ) -> None:
        from ferry_action.deploy_apigw import main

        output_file, summary_file = self._setup_env(
            monkeypatch, tmp_path, rest_api, json.dumps(VALID_MOTO_SPEC), "openapi.json"
        )

        with (
            patch("ferry_action.deploy_apigw.boto3") as mock_boto,
            patch("ferry_action.deploy_apigw.should_skip_deploy", return_value=False),
            patch("ferry_action.deploy_apigw._tag_content_hash"),
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sts_client if svc == "sts" else apigw_client
            )
            main()

        outputs = output_file.read_text()
        assert "skipped=false" in outputs

    def test_deploys_yaml_spec(
        self,
        monkeypatch: pytest.MonkeyPatch,
        apigw_client: boto3.client,
        sts_client: boto3.client,
        rest_api: str,
        tmp_path,
    ) -> None:
        import yaml as _yaml

        from ferry_action.deploy_apigw import main

        yaml_content = _yaml.dump(VALID_MOTO_SPEC)
        output_file, summary_file = self._setup_env(
            monkeypatch, tmp_path, rest_api, yaml_content, "openapi.yaml"
        )

        with (
            patch("ferry_action.deploy_apigw.boto3") as mock_boto,
            patch("ferry_action.deploy_apigw.should_skip_deploy", return_value=False),
            patch("ferry_action.deploy_apigw._tag_content_hash"),
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sts_client if svc == "sts" else apigw_client
            )
            main()

        outputs = output_file.read_text()
        assert "skipped=false" in outputs

    def test_envsubst_applied(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sts_client: boto3.client,
        rest_api: str,
        tmp_path,
    ) -> None:
        from ferry_action.deploy_apigw import main

        spec = {
            "openapi": "3.0.1",
            "info": {"title": "Test"},
            "paths": {},
            "x-account": "${ACCOUNT_ID}",
        }
        output_file, summary_file = self._setup_env(
            monkeypatch, tmp_path, rest_api, json.dumps(spec), "openapi.json"
        )

        mock_apigw = MagicMock()
        mock_apigw.put_rest_api.return_value = {"id": rest_api}
        mock_apigw.create_deployment.return_value = {"id": "deploy-123"}

        with (
            patch("ferry_action.deploy_apigw.boto3") as mock_boto,
            patch("ferry_action.deploy_apigw.should_skip_deploy", return_value=False),
            patch("ferry_action.deploy_apigw._tag_content_hash"),
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sts_client if svc == "sts" else mock_apigw
            )
            main()

        # Capture the body passed to put_rest_api
        call_args = mock_apigw.put_rest_api.call_args
        body = call_args.kwargs.get("body") or call_args[1].get("body")
        body_str = body.decode("utf-8") if isinstance(body, bytes) else body
        # Account ID from moto STS is 123456789012
        assert "${ACCOUNT_ID}" not in body_str
        assert "123456789012" in body_str

    def test_strips_fields_before_upload(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sts_client: boto3.client,
        rest_api: str,
        tmp_path,
    ) -> None:
        from ferry_action.deploy_apigw import main

        spec = {
            "openapi": "3.0.1",
            "info": {"title": "Test"},
            "host": "api.example.com",
            "servers": [{"url": "https://api.example.com"}],
            "paths": {},
        }
        output_file, summary_file = self._setup_env(
            monkeypatch, tmp_path, rest_api, json.dumps(spec), "openapi.json"
        )

        mock_apigw = MagicMock()
        mock_apigw.put_rest_api.return_value = {"id": rest_api}
        mock_apigw.create_deployment.return_value = {"id": "deploy-123"}

        with (
            patch("ferry_action.deploy_apigw.boto3") as mock_boto,
            patch("ferry_action.deploy_apigw.should_skip_deploy", return_value=False),
            patch("ferry_action.deploy_apigw._tag_content_hash"),
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sts_client if svc == "sts" else mock_apigw
            )
            main()

        call_args = mock_apigw.put_rest_api.call_args
        body = call_args.kwargs.get("body") or call_args[1].get("body")
        body_str = body.decode("utf-8") if isinstance(body, bytes) else body
        parsed = json.loads(body_str)
        assert "host" not in parsed
        assert "servers" not in parsed

    def test_skips_when_spec_unchanged(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sts_client: boto3.client,
        rest_api: str,
        tmp_path,
    ) -> None:
        from ferry_action.deploy_apigw import main

        spec = {"openapi": "3.0.1", "info": {"title": "Test"}, "paths": {}}
        output_file, summary_file = self._setup_env(
            monkeypatch, tmp_path, rest_api, json.dumps(spec), "openapi.json"
        )

        mock_apigw = MagicMock()

        with (
            patch("ferry_action.deploy_apigw.boto3") as mock_boto,
            patch("ferry_action.deploy_apigw.should_skip_deploy", return_value=True),
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sts_client if svc == "sts" else mock_apigw
            )
            main()

        outputs = output_file.read_text()
        assert "skipped=true" in outputs
        mock_apigw.put_rest_api.assert_not_called()

    def test_writes_job_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        apigw_client: boto3.client,
        sts_client: boto3.client,
        rest_api: str,
        tmp_path,
    ) -> None:
        from ferry_action.deploy_apigw import main

        output_file, summary_file = self._setup_env(
            monkeypatch, tmp_path, rest_api, json.dumps(VALID_MOTO_SPEC), "openapi.json"
        )

        with (
            patch("ferry_action.deploy_apigw.boto3") as mock_boto,
            patch("ferry_action.deploy_apigw.should_skip_deploy", return_value=False),
            patch("ferry_action.deploy_apigw._tag_content_hash"),
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sts_client if svc == "sts" else apigw_client
            )
            main()

        summary = summary_file.read_text()
        assert rest_api in summary
        assert STAGE in summary
        assert "Deployed" in summary or "deployed" in summary

    def test_error_hint_for_missing_api(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sts_client: boto3.client,
        tmp_path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from ferry_action.deploy_apigw import main

        spec = {"openapi": "3.0.1", "info": {"title": "Test"}, "paths": {}}
        output_file, summary_file = self._setup_env(
            monkeypatch, tmp_path, "nonexistent-api-id", json.dumps(spec), "openapi.json"
        )

        mock_apigw = MagicMock()
        mock_apigw.put_rest_api.side_effect = ClientError(
            {"Error": {"Code": "NotFoundException", "Message": "Not found"}},
            "PutRestApi",
        )

        with (
            patch("ferry_action.deploy_apigw.boto3") as mock_boto,
            patch("ferry_action.deploy_apigw.should_skip_deploy", return_value=False),
        ):
            mock_boto.client.side_effect = lambda svc, **kw: (
                sts_client if svc == "sts" else mock_apigw
            )
            with pytest.raises(SystemExit):
                main()

        captured = capsys.readouterr()
        assert "::error::" in captured.out
        assert "nonexistent-api-id" in captured.out
