"""ferry.yaml Pydantic v2 schema models with fail-fast validation.

Typed models for all ferry.yaml resource types. Each resource type has
its own model with type-specific required/optional fields. All models
frozen with extra=forbid per project convention.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from ferry_utils.errors import ConfigError


class LambdaConfig(BaseModel):
    """Lambda resource configuration from ferry.yaml.

    `name` is the AWS Lambda function name.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source_dir: str
    ecr_repo: str
    runtime: str = "python3.14"

    @model_validator(mode="before")
    @classmethod
    def handle_deprecated_function_name(cls, data: Any) -> Any:
        """Backward-compat: accept old `function_name` field silently."""
        if isinstance(data, dict) and "function_name" in data:
            if "name" not in data:
                data["name"] = data.pop("function_name")
            else:
                data.pop("function_name")
        return data


class StepFunctionConfig(BaseModel):
    """Step Function resource configuration from ferry.yaml.

    `name` is the AWS Step Functions state machine name.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source_dir: str
    definition_file: str

    @model_validator(mode="before")
    @classmethod
    def handle_deprecated_state_machine_name(cls, data: Any) -> Any:
        """Backward-compat: accept old `state_machine_name` field silently.

        If both `name` and `state_machine_name` are present and differ,
        `state_machine_name` wins (it is the AWS resource name).
        """
        if isinstance(data, dict) and "state_machine_name" in data:
            if "name" not in data or data["name"] != data["state_machine_name"]:
                data["name"] = data.pop("state_machine_name")
            else:
                data.pop("state_machine_name")
        return data


class ApiGatewayConfig(BaseModel):
    """API Gateway resource configuration from ferry.yaml."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source_dir: str
    rest_api_id: str
    stage_name: str
    spec_file: str


class EnvironmentMapping(BaseModel):
    """Environment-to-branch mapping from ferry.yaml."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    branch: str
    auto_deploy: bool = True


class FerryConfig(BaseModel):
    """Top-level ferry.yaml configuration model.

    All sections optional (default to empty list).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    lambdas: list[LambdaConfig] = []
    step_functions: list[StepFunctionConfig] = []
    api_gateways: list[ApiGatewayConfig] = []
    environments: list[EnvironmentMapping] = []

    @model_validator(mode="before")
    @classmethod
    def expand_environments_dict(cls, data: Any) -> Any:
        """Convert dict-keyed environments YAML to list of EnvironmentMapping dicts."""
        if isinstance(data, dict) and "environments" in data:
            envs = data["environments"]
            if isinstance(envs, dict):
                data = {
                    **data,
                    "environments": [{"name": name, **cfg} for name, cfg in envs.items()],
                }
        return data


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
