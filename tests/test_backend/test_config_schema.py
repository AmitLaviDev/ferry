"""Tests for ferry.yaml Pydantic v2 config schema and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ferry_backend.config.schema import (
    ApiGatewayConfig,
    EnvironmentMapping,
    FerryConfig,
    LambdaConfig,
    StepFunctionConfig,
    validate_config,
)
from ferry_utils.errors import ConfigError


class TestLambdaConfig:
    """Tests for LambdaConfig model."""

    def test_lambda_config_required_fields(self) -> None:
        """All 3 required fields provided -> valid model."""
        cfg = LambdaConfig(name="proc", source_dir="src/proc", ecr_repo="ferry/proc")
        assert cfg.name == "proc"
        assert cfg.source_dir == "src/proc"
        assert cfg.ecr_repo == "ferry/proc"

    def test_lambda_config_defaults(self) -> None:
        """function_name defaults to name, runtime defaults to python3.14."""
        cfg = LambdaConfig(name="proc", source_dir="src/proc", ecr_repo="ferry/proc")
        assert cfg.function_name == "proc"
        assert cfg.runtime == "python3.14"

    def test_lambda_config_explicit_function_name(self) -> None:
        """Explicit function_name overrides default."""
        cfg = LambdaConfig(
            name="proc",
            source_dir="src/proc",
            ecr_repo="ferry/proc",
            function_name="my-custom-fn",
        )
        assert cfg.function_name == "my-custom-fn"

    def test_lambda_config_missing_ecr_repo(self) -> None:
        """Missing ecr_repo raises ValidationError."""
        with pytest.raises(ValidationError, match="ecr_repo"):
            LambdaConfig(name="proc", source_dir="src/proc")  # type: ignore[call-arg]

    def test_lambda_config_extra_field(self) -> None:
        """Extra field raises ValidationError (extra=forbid)."""
        with pytest.raises(ValidationError, match="extra"):
            LambdaConfig(
                name="proc",
                source_dir="src/proc",
                ecr_repo="ferry/proc",
                unknown="z",  # type: ignore[call-arg]
            )


class TestStepFunctionConfig:
    """Tests for StepFunctionConfig model."""

    def test_step_function_config_valid(self) -> None:
        """All required fields -> valid model."""
        cfg = StepFunctionConfig(
            name="workflow",
            source_dir="src/workflow",
            state_machine_name="my-state-machine",
            definition_file="stepfunction.json",
        )
        assert cfg.name == "workflow"
        assert cfg.source_dir == "src/workflow"
        assert cfg.state_machine_name == "my-state-machine"
        assert cfg.definition_file == "stepfunction.json"

    def test_step_function_config_missing_state_machine_name(self) -> None:
        """Missing state_machine_name raises ValidationError."""
        with pytest.raises(ValidationError, match="state_machine_name"):
            StepFunctionConfig(
                name="workflow",
                source_dir="src/workflow",
                definition_file="stepfunction.json",
            )  # type: ignore[call-arg]

    def test_step_function_config_missing_definition_file(self) -> None:
        """Missing definition_file raises ValidationError."""
        with pytest.raises(ValidationError, match="definition_file"):
            StepFunctionConfig(
                name="workflow",
                source_dir="src/workflow",
                state_machine_name="my-sm",
            )  # type: ignore[call-arg]


class TestApiGatewayConfig:
    """Tests for ApiGatewayConfig model."""

    def test_api_gateway_config_valid(self) -> None:
        """All required fields -> valid model."""
        cfg = ApiGatewayConfig(
            name="api",
            source_dir="src/api",
            rest_api_id="abc123def",
            stage_name="prod",
            spec_file="openapi.yaml",
        )
        assert cfg.name == "api"
        assert cfg.source_dir == "src/api"
        assert cfg.rest_api_id == "abc123def"
        assert cfg.stage_name == "prod"
        assert cfg.spec_file == "openapi.yaml"

    def test_api_gateway_config_missing_rest_api_id(self) -> None:
        """Missing rest_api_id raises ValidationError."""
        with pytest.raises(ValidationError, match="rest_api_id"):
            ApiGatewayConfig(
                name="api",
                source_dir="src/api",
                stage_name="prod",
                spec_file="openapi.yaml",
            )  # type: ignore[call-arg]

    def test_api_gateway_config_missing_stage_name(self) -> None:
        """Missing stage_name raises ValidationError."""
        with pytest.raises(ValidationError, match="stage_name"):
            ApiGatewayConfig(
                name="api",
                source_dir="src/api",
                rest_api_id="abc123def",
                spec_file="openapi.yaml",
            )  # type: ignore[call-arg]

    def test_api_gateway_config_missing_spec_file(self) -> None:
        """Missing spec_file raises ValidationError."""
        with pytest.raises(ValidationError, match="spec_file"):
            ApiGatewayConfig(
                name="api",
                source_dir="src/api",
                rest_api_id="abc123def",
                stage_name="prod",
            )  # type: ignore[call-arg]


class TestEnvironmentMapping:
    """Tests for EnvironmentMapping model."""

    def test_environment_mapping_required_fields(self) -> None:
        """name + branch -> valid EnvironmentMapping."""
        env = EnvironmentMapping(name="staging", branch="develop")
        assert env.name == "staging"
        assert env.branch == "develop"

    def test_environment_mapping_auto_deploy_default(self) -> None:
        """auto_deploy defaults to True."""
        env = EnvironmentMapping(name="staging", branch="develop")
        assert env.auto_deploy is True

    def test_environment_mapping_auto_deploy_false(self) -> None:
        """Explicit auto_deploy=False works."""
        env = EnvironmentMapping(name="staging", branch="develop", auto_deploy=False)
        assert env.auto_deploy is False

    def test_environment_mapping_extra_field_rejected(self) -> None:
        """extra=forbid enforced on EnvironmentMapping."""
        with pytest.raises(ValidationError, match="extra"):
            EnvironmentMapping(
                name="staging",
                branch="develop",
                unknown="z",  # type: ignore[call-arg]
            )

    def test_environment_mapping_missing_branch_fails(self) -> None:
        """branch is required."""
        with pytest.raises(ValidationError, match="branch"):
            EnvironmentMapping(name="staging")  # type: ignore[call-arg]


class TestFerryConfig:
    """Tests for FerryConfig model."""

    def test_ferry_config_full(self) -> None:
        """All 3 sections with resources -> valid FerryConfig."""
        cfg = FerryConfig(
            lambdas=[
                LambdaConfig(name="a", source_dir="s/a", ecr_repo="e/a"),
            ],
            step_functions=[
                StepFunctionConfig(
                    name="b",
                    source_dir="s/b",
                    state_machine_name="sm-b",
                    definition_file="def.json",
                ),
            ],
            api_gateways=[
                ApiGatewayConfig(
                    name="c",
                    source_dir="s/c",
                    rest_api_id="api123",
                    stage_name="prod",
                    spec_file="spec.yaml",
                ),
            ],
        )
        assert len(cfg.lambdas) == 1
        assert len(cfg.step_functions) == 1
        assert len(cfg.api_gateways) == 1

    def test_ferry_config_empty(self) -> None:
        """No sections -> valid FerryConfig with empty lists."""
        cfg = FerryConfig()
        assert cfg.lambdas == []
        assert cfg.step_functions == []
        assert cfg.api_gateways == []
        assert cfg.version == 1

    def test_ferry_config_partial(self) -> None:
        """Only lambdas section -> valid, others empty."""
        cfg = FerryConfig(
            lambdas=[
                LambdaConfig(name="x", source_dir="s/x", ecr_repo="e/x"),
            ],
        )
        assert len(cfg.lambdas) == 1
        assert cfg.step_functions == []
        assert cfg.api_gateways == []

    def test_ferry_config_extra_section(self) -> None:
        """Unknown top-level key raises ValidationError."""
        with pytest.raises(ValidationError, match="extra"):
            FerryConfig(unknown_section="bad")  # type: ignore[call-arg]

    def test_ferry_config_with_environments(self) -> None:
        """Dict-keyed environments in raw dict -> list of EnvironmentMapping."""
        raw = {
            "lambdas": [
                {"name": "proc", "source_dir": "src/proc", "ecr_repo": "ferry/proc"},
            ],
            "environments": {
                "staging": {"branch": "develop", "auto_deploy": True},
                "production": {"branch": "main", "auto_deploy": False},
            },
        }
        cfg = FerryConfig.model_validate(raw)
        assert len(cfg.environments) == 2
        assert isinstance(cfg.environments[0], EnvironmentMapping)
        assert cfg.environments[0].name == "staging"
        assert cfg.environments[0].branch == "develop"
        assert cfg.environments[0].auto_deploy is True
        assert cfg.environments[1].name == "production"
        assert cfg.environments[1].branch == "main"
        assert cfg.environments[1].auto_deploy is False

    def test_ferry_config_environments_empty_dict(self) -> None:
        """environments: {} -> empty list."""
        raw = {"environments": {}}
        cfg = FerryConfig.model_validate(raw)
        assert cfg.environments == []

    def test_ferry_config_no_environments(self) -> None:
        """Omitting environments entirely -> empty list (backward compat)."""
        cfg = FerryConfig()
        assert cfg.environments == []

    def test_ferry_config_environments_preserves_order(self) -> None:
        """Two environments, ordering preserved."""
        raw = {
            "environments": {
                "alpha": {"branch": "alpha"},
                "beta": {"branch": "beta"},
            },
        }
        cfg = FerryConfig.model_validate(raw)
        assert len(cfg.environments) == 2
        assert cfg.environments[0].name == "alpha"
        assert cfg.environments[1].name == "beta"


class TestValidateConfig:
    """Tests for validate_config wrapper."""

    def test_validate_config_success(self) -> None:
        """Valid dict -> FerryConfig."""
        raw = {
            "lambdas": [
                {"name": "proc", "source_dir": "src/proc", "ecr_repo": "ferry/proc"},
            ],
        }
        result = validate_config(raw)
        assert isinstance(result, FerryConfig)
        assert result.lambdas[0].name == "proc"

    def test_validate_config_with_environments(self) -> None:
        """Raw dict with environments section parses via validate_config()."""
        raw = {
            "lambdas": [
                {"name": "proc", "source_dir": "src/proc", "ecr_repo": "ferry/proc"},
            ],
            "environments": {
                "staging": {"branch": "develop"},
            },
        }
        result = validate_config(raw)
        assert isinstance(result, FerryConfig)
        assert len(result.environments) == 1
        assert result.environments[0].name == "staging"
        assert result.environments[0].branch == "develop"
        assert result.environments[0].auto_deploy is True

    def test_validate_config_invalid(self) -> None:
        """Bad dict -> raises ConfigError (not raw ValidationError)."""
        raw = {
            "lambdas": [
                {"name": "proc"},  # missing source_dir and ecr_repo
            ],
        }
        with pytest.raises(ConfigError):
            validate_config(raw)
