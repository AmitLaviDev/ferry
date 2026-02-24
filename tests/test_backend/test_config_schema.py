"""Tests for ferry.yaml Pydantic v2 config schema and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ferry_backend.config.schema import (
    ApiGatewayConfig,
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
        """function_name defaults to name, runtime defaults to python3.10."""
        cfg = LambdaConfig(name="proc", source_dir="src/proc", ecr_repo="ferry/proc")
        assert cfg.function_name == "proc"
        assert cfg.runtime == "python3.10"

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
        """name + source_dir -> valid model."""
        cfg = StepFunctionConfig(name="workflow", source_dir="src/workflow")
        assert cfg.name == "workflow"
        assert cfg.source_dir == "src/workflow"


class TestApiGatewayConfig:
    """Tests for ApiGatewayConfig model."""

    def test_api_gateway_config_valid(self) -> None:
        """name + source_dir -> valid model."""
        cfg = ApiGatewayConfig(name="api", source_dir="src/api")
        assert cfg.name == "api"
        assert cfg.source_dir == "src/api"


class TestFerryConfig:
    """Tests for FerryConfig model."""

    def test_ferry_config_full(self) -> None:
        """All 3 sections with resources -> valid FerryConfig."""
        cfg = FerryConfig(
            lambdas=[
                LambdaConfig(name="a", source_dir="s/a", ecr_repo="e/a"),
            ],
            step_functions=[
                StepFunctionConfig(name="b", source_dir="s/b"),
            ],
            api_gateways=[
                ApiGatewayConfig(name="c", source_dir="s/c"),
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

    def test_validate_config_invalid(self) -> None:
        """Bad dict -> raises ConfigError (not raw ValidationError)."""
        raw = {
            "lambdas": [
                {"name": "proc"},  # missing source_dir and ecr_repo
            ],
        }
        with pytest.raises(ConfigError):
            validate_config(raw)
