"""Tests for dispatch payload Pydantic models."""

import json

import pytest
from pydantic import ValidationError

from ferry_utils.constants import BATCHED_SCHEMA_VERSION, SCHEMA_VERSION
from ferry_utils.models.dispatch import (
    ApiGatewayResource,
    BatchedDispatchPayload,
    DispatchPayload,
    LambdaResource,
    StepFunctionResource,
)


class TestLambdaResource:
    def test_valid_lambda_resource(self):
        resource = LambdaResource(
            name="my-function",
            source="services/my-function",
            ecr="my-function-repo",
            runtime="python3.14",
        )
        assert resource.resource_type == "lambda"
        assert resource.name == "my-function"
        assert resource.source == "services/my-function"
        assert resource.ecr == "my-function-repo"
        assert resource.runtime == "python3.14"

    def test_lambda_resource_default_type(self):
        resource = LambdaResource(
            name="fn",
            source="src/fn",
            ecr="fn-repo",
            runtime="python3.14",
        )
        assert resource.resource_type == "lambda"

    def test_lambda_resource_name_is_aws_function_name(self):
        """name IS the AWS Lambda function name (no separate function_name field)."""
        resource = LambdaResource(
            name="order-processor-prod",
            source="services/order",
            ecr="ferry/order",
            runtime="python3.14",
        )
        assert resource.name == "order-processor-prod"
        data = resource.model_dump()
        assert data["name"] == "order-processor-prod"
        assert "function_name" not in data
        restored = LambdaResource.model_validate(data)
        assert restored.name == "order-processor-prod"

    def test_lambda_resource_missing_runtime_fails(self):
        """Missing runtime raises ValidationError (required field)."""
        with pytest.raises(ValidationError, match="runtime"):
            LambdaResource(name="fn", source="src/fn", ecr="fn-repo")  # type: ignore[call-arg]

    def test_lambda_resource_custom_runtime(self):
        """Runtime can be any string value (e.g. different Python version)."""
        resource = LambdaResource(
            name="fn",
            source="src/fn",
            ecr="fn-repo",
            runtime="python3.12",
        )
        assert resource.runtime == "python3.12"


class TestStepFunctionResource:
    def test_valid_step_function_resource(self):
        resource = StepFunctionResource(
            name="my-sm",
            source="workflows/my-workflow",
            definition_file="stepfunction.json",
        )
        assert resource.resource_type == "step_function"
        assert resource.name == "my-sm"
        assert resource.source == "workflows/my-workflow"
        assert resource.definition_file == "stepfunction.json"


class TestApiGatewayResource:
    def test_valid_api_gateway_resource(self):
        resource = ApiGatewayResource(
            name="my-api",
            source="apis/my-api",
            rest_api_id="abc123",
            stage_name="prod",
            spec_file="openapi.yaml",
        )
        assert resource.resource_type == "api_gateway"
        assert resource.name == "my-api"
        assert resource.rest_api_id == "abc123"
        assert resource.stage_name == "prod"
        assert resource.spec_file == "openapi.yaml"


class TestDispatchPayload:
    def test_valid_payload_with_lambda_resources(self):
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
                LambdaResource(
                    name="fn-b",
                    source="services/fn-b",
                    ecr="fn-b-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123def456",
            deployment_tag="v1.0.0-abc123d",
        )
        assert payload.resource_type == "lambdas"
        assert len(payload.resources) == 2
        assert payload.trigger_sha == "abc123def456"
        assert payload.deployment_tag == "v1.0.0-abc123d"

    def test_discriminated_union_rejects_unknown_resource_type(self):
        with pytest.raises(ValidationError, match="resource_type"):
            DispatchPayload(
                resource_type="lambdas",
                resources=[
                    {"resource_type": "unknown_type", "name": "bad", "source": "bad"},
                ],
                trigger_sha="abc123",
                deployment_tag="v1.0.0",
            )

    def test_schema_version_defaults_to_current(self):
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(
                    name="fn",
                    source="src/fn",
                    ecr="fn-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
        )
        assert payload.v == SCHEMA_VERSION
        assert payload.v == 1

    def test_pr_number_defaults_to_empty_string(self):
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(
                    name="fn",
                    source="src/fn",
                    ecr="fn-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
        )
        assert payload.pr_number == ""

    def test_pr_number_can_be_set(self):
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(
                    name="fn",
                    source="src/fn",
                    ecr="fn-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
            pr_number="42",
        )
        assert payload.pr_number == "42"

    def test_frozen_model_rejects_mutation(self):
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(
                    name="fn",
                    source="src/fn",
                    ecr="fn-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
        )
        with pytest.raises(ValidationError):
            payload.trigger_sha = "new-sha"

    def test_frozen_resource_rejects_mutation(self):
        resource = LambdaResource(name="fn", source="src/fn", ecr="fn-repo", runtime="python3.14")
        with pytest.raises(ValidationError):
            resource.name = "new-name"

    def test_payload_with_step_function_resources(self):
        payload = DispatchPayload(
            resource_type="step_functions",
            resources=[
                StepFunctionResource(
                    name="wf-a",
                    source="workflows/wf-a",
                    definition_file="def.json",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
        )
        assert len(payload.resources) == 1
        assert payload.resources[0].resource_type == "step_function"

    def test_payload_with_api_gateway_resources(self):
        payload = DispatchPayload(
            resource_type="api_gateways",
            resources=[
                ApiGatewayResource(
                    name="api-a",
                    source="apis/api-a",
                    rest_api_id="id123",
                    stage_name="prod",
                    spec_file="spec.yaml",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
        )
        assert len(payload.resources) == 1
        assert payload.resources[0].resource_type == "api_gateway"

    def test_mixed_resource_types_in_single_payload(self):
        """Resources in a single payload can technically be mixed types since
        the discriminated union validates each individually. The resource_type
        field on the payload is the intended grouping key, enforced at the
        application layer rather than the model layer."""
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(
                    name="fn",
                    source="src/fn",
                    ecr="fn-repo",
                    runtime="python3.14",
                ),
                StepFunctionResource(
                    name="wf",
                    source="workflows/wf",
                    definition_file="def.json",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
        )
        # Model allows it -- application logic should enforce single-type
        assert len(payload.resources) == 2

    def test_lambda_resource_missing_ecr_fails(self):
        with pytest.raises(ValidationError, match="ecr"):
            LambdaResource(name="fn", source="src/fn", runtime="python3.14")  # type: ignore[call-arg]


class TestBatchedDispatchPayload:
    """Tests for the v2 BatchedDispatchPayload model."""

    def test_batched_payload_all_three_types(self):
        payload = BatchedDispatchPayload(
            lambdas=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            step_functions=[
                StepFunctionResource(
                    name="wf-a",
                    source="workflows/wf-a",
                    definition_file="def.json",
                ),
            ],
            api_gateways=[
                ApiGatewayResource(
                    name="api-a",
                    source="apis/api-a",
                    rest_api_id="id123",
                    stage_name="prod",
                    spec_file="spec.yaml",
                ),
            ],
            trigger_sha="abc123def456",
            deployment_tag="v2.0.0-abc123d",
        )
        assert payload.v == 2
        assert len(payload.lambdas) == 1
        assert len(payload.step_functions) == 1
        assert len(payload.api_gateways) == 1
        assert payload.trigger_sha == "abc123def456"
        assert payload.deployment_tag == "v2.0.0-abc123d"
        assert payload.lambdas[0].name == "fn-a"
        assert payload.step_functions[0].name == "wf-a"
        assert payload.api_gateways[0].name == "api-a"

    def test_batched_payload_single_type_only(self):
        payload = BatchedDispatchPayload(
            lambdas=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        assert len(payload.lambdas) == 1
        assert payload.step_functions == []
        assert payload.api_gateways == []

    def test_batched_payload_empty_lists_valid(self):
        payload = BatchedDispatchPayload(
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        assert payload.lambdas == []
        assert payload.step_functions == []
        assert payload.api_gateways == []

    def test_batched_payload_version_is_always_2(self):
        payload = BatchedDispatchPayload(
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        assert payload.v == 2
        assert payload.v == BATCHED_SCHEMA_VERSION

        # Explicit v=2 works
        payload2 = BatchedDispatchPayload(
            v=2,
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        assert payload2.v == 2

        # v=1 should raise ValidationError (Literal[2] enforcement)
        with pytest.raises(ValidationError, match="v"):
            BatchedDispatchPayload(
                v=1,
                trigger_sha="abc123",
                deployment_tag="v2.0.0",
            )

    def test_batched_payload_round_trip_json(self):
        original = BatchedDispatchPayload(
            lambdas=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            step_functions=[
                StepFunctionResource(
                    name="wf-a",
                    source="workflows/wf-a",
                    definition_file="def.json",
                ),
            ],
            api_gateways=[
                ApiGatewayResource(
                    name="api-a",
                    source="apis/api-a",
                    rest_api_id="id123",
                    stage_name="prod",
                    spec_file="spec.yaml",
                ),
            ],
            trigger_sha="abc123def456",
            deployment_tag="v2.0.0-abc123d",
            pr_number="42",
        )
        json_str = original.model_dump_json()
        restored = BatchedDispatchPayload.model_validate_json(json_str)
        assert restored.v == original.v
        assert restored.trigger_sha == original.trigger_sha
        assert restored.deployment_tag == original.deployment_tag
        assert restored.pr_number == original.pr_number
        assert len(restored.lambdas) == 1
        assert restored.lambdas[0].name == "fn-a"
        assert len(restored.step_functions) == 1
        assert restored.step_functions[0].name == "wf-a"
        assert len(restored.api_gateways) == 1
        assert restored.api_gateways[0].rest_api_id == "id123"

    def test_batched_payload_round_trip_dict(self):
        original = BatchedDispatchPayload(
            lambdas=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        data = original.model_dump()
        restored = BatchedDispatchPayload.model_validate(data)
        assert restored.v == original.v
        assert restored.trigger_sha == original.trigger_sha
        assert restored.deployment_tag == original.deployment_tag
        assert restored.lambdas == original.lambdas
        assert restored.step_functions == original.step_functions
        assert restored.api_gateways == original.api_gateways

    def test_batched_payload_frozen(self):
        payload = BatchedDispatchPayload(
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        with pytest.raises(ValidationError):
            payload.trigger_sha = "new-sha"

    def test_batched_payload_pr_number_defaults_empty(self):
        payload = BatchedDispatchPayload(
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        assert payload.pr_number == ""

    def test_batched_payload_resource_types_all_three(self):
        payload = BatchedDispatchPayload(
            lambdas=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            step_functions=[
                StepFunctionResource(
                    name="wf-a",
                    source="workflows/wf-a",
                    definition_file="def.json",
                ),
            ],
            api_gateways=[
                ApiGatewayResource(
                    name="api-a",
                    source="apis/api-a",
                    rest_api_id="id123",
                    stage_name="prod",
                    spec_file="spec.yaml",
                ),
            ],
            trigger_sha="abc123def456",
            deployment_tag="v2.0.0-abc123d",
        )
        assert payload.resource_types == "lambda,step_function,api_gateway"

    def test_batched_payload_resource_types_single(self):
        payload = BatchedDispatchPayload(
            lambdas=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        assert payload.resource_types == "lambda"

    def test_batched_payload_resource_types_empty(self):
        payload = BatchedDispatchPayload(
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        assert payload.resource_types == ""

    def test_batched_payload_resource_types_in_json(self):
        payload = BatchedDispatchPayload(
            lambdas=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            step_functions=[
                StepFunctionResource(
                    name="wf-a",
                    source="workflows/wf-a",
                    definition_file="def.json",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        data = json.loads(payload.model_dump_json())
        assert "resource_types" in data
        assert data["resource_types"] == "lambda,step_function"

    def test_batched_payload_resource_types_in_dump(self):
        payload = BatchedDispatchPayload(
            lambdas=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        data = payload.model_dump()
        assert "resource_types" in data
        assert data["resource_types"] == "lambda"

    def test_batched_payload_new_fields_defaults(self):
        """New v2 fields default to safe values."""
        payload = BatchedDispatchPayload(
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
        )
        assert payload.mode == "deploy"
        assert payload.environment == ""
        assert payload.head_ref == ""
        assert payload.base_ref == ""

    def test_batched_payload_new_fields_explicit(self):
        """New v2 fields can be set explicitly."""
        payload = BatchedDispatchPayload(
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
            mode="plan",
            environment="staging",
            head_ref="feature/foo",
            base_ref="main",
        )
        assert payload.mode == "plan"
        assert payload.environment == "staging"
        assert payload.head_ref == "feature/foo"
        assert payload.base_ref == "main"

    def test_batched_payload_v2_backward_compat(self):
        """Old v2 payload dict (no mode/environment/head_ref/base_ref) still works."""
        old_v2_dict = {
            "v": 2,
            "lambdas": [
                {
                    "resource_type": "lambda",
                    "name": "fn-a",
                    "source": "services/fn-a",
                    "ecr": "fn-a-repo",
                    "runtime": "python3.14",
                },
            ],
            "step_functions": [],
            "api_gateways": [],
            "trigger_sha": "abc123",
            "deployment_tag": "v2.0.0",
            "pr_number": "",
        }
        payload = BatchedDispatchPayload.model_validate(old_v2_dict)
        assert payload.mode == "deploy"
        assert payload.environment == ""
        assert payload.head_ref == ""
        assert payload.base_ref == ""
        assert len(payload.lambdas) == 1

    def test_batched_payload_round_trip_with_new_fields(self):
        """New fields survive JSON round-trip."""
        original = BatchedDispatchPayload(
            trigger_sha="abc123",
            deployment_tag="v2.0.0",
            mode="plan",
            environment="staging",
            head_ref="feature/bar",
            base_ref="develop",
        )
        json_str = original.model_dump_json()
        restored = BatchedDispatchPayload.model_validate_json(json_str)
        assert restored.mode == "plan"
        assert restored.environment == "staging"
        assert restored.head_ref == "feature/bar"
        assert restored.base_ref == "develop"

    def test_v1_payload_still_unchanged(self):
        """DispatchPayload (v1) has mode/environment defaults but no head_ref/base_ref."""
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123def456",
            deployment_tag="v1.0.0-abc123d",
        )
        assert payload.v == 1
        assert payload.v == SCHEMA_VERSION
        assert payload.resource_type == "lambdas"
        assert len(payload.resources) == 1
        assert payload.trigger_sha == "abc123def456"
        assert payload.pr_number == ""
        assert payload.mode == "deploy"
        assert payload.environment == ""
        assert not hasattr(payload, "head_ref")
        assert not hasattr(payload, "base_ref")

    def test_v1_payload_mode_defaults(self):
        """DispatchPayload defaults mode='deploy' and environment='' when not specified."""
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
        )
        assert payload.mode == "deploy"
        assert payload.environment == ""

    def test_v1_payload_mode_explicit(self):
        """DispatchPayload accepts explicit mode and environment values."""
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
            mode="deploy",
            environment="staging",
        )
        assert payload.mode == "deploy"
        assert payload.environment == "staging"

    def test_v1_payload_mode_from_json(self):
        """DispatchPayload parses mode/environment from JSON, defaults when absent."""
        # With fields
        with_fields = json.dumps(
            {
                "v": 1,
                "resource_type": "lambda",
                "resources": [],
                "trigger_sha": "abc",
                "deployment_tag": "t",
                "mode": "deploy",
                "environment": "production",
            }
        )
        p1 = DispatchPayload.model_validate_json(with_fields)
        assert p1.mode == "deploy"
        assert p1.environment == "production"

        # Without fields (backward compat)
        without_fields = json.dumps(
            {
                "v": 1,
                "resource_type": "lambda",
                "resources": [],
                "trigger_sha": "abc",
                "deployment_tag": "t",
            }
        )
        p2 = DispatchPayload.model_validate_json(without_fields)
        assert p2.mode == "deploy"
        assert p2.environment == ""

    def test_v1_payload_unchanged(self):
        """Guard rail: DispatchPayload (v1) still works exactly as before."""
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(
                    name="fn-a",
                    source="services/fn-a",
                    ecr="fn-a-repo",
                    runtime="python3.14",
                ),
            ],
            trigger_sha="abc123def456",
            deployment_tag="v1.0.0-abc123d",
        )
        assert payload.v == 1
        assert payload.v == SCHEMA_VERSION
        assert payload.resource_type == "lambdas"
        assert len(payload.resources) == 1
        assert payload.trigger_sha == "abc123def456"
        assert payload.pr_number == ""
