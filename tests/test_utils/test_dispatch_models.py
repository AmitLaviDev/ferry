"""Tests for dispatch payload Pydantic models."""

import pytest
from pydantic import ValidationError

from ferry_utils.constants import SCHEMA_VERSION
from ferry_utils.models.dispatch import (
    ApiGatewayResource,
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
        )
        assert resource.resource_type == "lambda"
        assert resource.name == "my-function"
        assert resource.source == "services/my-function"
        assert resource.ecr == "my-function-repo"

    def test_lambda_resource_default_type(self):
        resource = LambdaResource(
            name="fn", source="src/fn", ecr="fn-repo"
        )
        assert resource.resource_type == "lambda"


class TestStepFunctionResource:
    def test_valid_step_function_resource(self):
        resource = StepFunctionResource(
            name="my-workflow",
            source="workflows/my-workflow",
        )
        assert resource.resource_type == "step_function"
        assert resource.name == "my-workflow"
        assert resource.source == "workflows/my-workflow"


class TestApiGatewayResource:
    def test_valid_api_gateway_resource(self):
        resource = ApiGatewayResource(
            name="my-api",
            source="apis/my-api",
        )
        assert resource.resource_type == "api_gateway"
        assert resource.name == "my-api"


class TestDispatchPayload:
    def test_valid_payload_with_lambda_resources(self):
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(name="fn-a", source="services/fn-a", ecr="fn-a-repo"),
                LambdaResource(name="fn-b", source="services/fn-b", ecr="fn-b-repo"),
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
                LambdaResource(name="fn", source="src/fn", ecr="fn-repo"),
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
                LambdaResource(name="fn", source="src/fn", ecr="fn-repo"),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
        )
        assert payload.pr_number == ""

    def test_pr_number_can_be_set(self):
        payload = DispatchPayload(
            resource_type="lambdas",
            resources=[
                LambdaResource(name="fn", source="src/fn", ecr="fn-repo"),
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
                LambdaResource(name="fn", source="src/fn", ecr="fn-repo"),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
        )
        with pytest.raises(ValidationError):
            payload.trigger_sha = "new-sha"

    def test_frozen_resource_rejects_mutation(self):
        resource = LambdaResource(name="fn", source="src/fn", ecr="fn-repo")
        with pytest.raises(ValidationError):
            resource.name = "new-name"

    def test_payload_with_step_function_resources(self):
        payload = DispatchPayload(
            resource_type="step_functions",
            resources=[
                StepFunctionResource(name="wf-a", source="workflows/wf-a"),
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
                ApiGatewayResource(name="api-a", source="apis/api-a"),
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
                LambdaResource(name="fn", source="src/fn", ecr="fn-repo"),
                StepFunctionResource(name="wf", source="workflows/wf"),
            ],
            trigger_sha="abc123",
            deployment_tag="v1.0.0",
        )
        # Model allows it -- application logic should enforce single-type
        assert len(payload.resources) == 2

    def test_lambda_resource_missing_ecr_fails(self):
        with pytest.raises(ValidationError, match="ecr"):
            LambdaResource(name="fn", source="src/fn")  # type: ignore[call-arg]
