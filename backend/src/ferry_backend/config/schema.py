"""ferry.yaml Pydantic v2 schema models with fail-fast validation.

Typed models for all ferry.yaml resource types. Each resource type has
its own model with type-specific required/optional fields. All models
frozen with extra=forbid per project convention.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from ferry_utils.errors import ConfigError


class LambdaConfig(BaseModel):
    """Lambda resource configuration from ferry.yaml."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source_dir: str
    ecr_repo: str
    runtime: str = "python3.14"
    function_name: str | None = None

    @model_validator(mode="after")
    def set_function_name_default(self) -> LambdaConfig:
        """Default function_name to name if not explicitly set."""
        if self.function_name is None:
            object.__setattr__(self, "function_name", self.name)
        return self


class StepFunctionConfig(BaseModel):
    """Step Function resource configuration from ferry.yaml."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source_dir: str
    state_machine_name: str
    definition_file: str


class ApiGatewayConfig(BaseModel):
    """API Gateway resource configuration from ferry.yaml."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source_dir: str
    rest_api_id: str
    stage_name: str
    spec_file: str


class FerryConfig(BaseModel):
    """Top-level ferry.yaml configuration model.

    All sections optional (default to empty list).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    lambdas: list[LambdaConfig] = []
    step_functions: list[StepFunctionConfig] = []
    api_gateways: list[ApiGatewayConfig] = []


def validate_config(raw: dict) -> FerryConfig:
    """Validate parsed YAML dict against ferry.yaml schema.

    Wraps Pydantic ValidationError in ConfigError for fail-fast behavior.

    Args:
        raw: Parsed YAML dictionary.

    Returns:
        Validated FerryConfig instance.

    Raises:
        ConfigError: If validation fails, with field-level error details.
    """
    try:
        return FerryConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid ferry.yaml: {exc}") from exc
