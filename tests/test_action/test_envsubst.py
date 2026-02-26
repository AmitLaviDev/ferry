"""Tests for ferry_action.envsubst -- variable substitution and content hashing."""

from __future__ import annotations

from ferry_action.envsubst import (
    compute_content_hash,
    envsubst,
    get_content_hash_tag,
)


class TestEnvsubst:
    """Tests for envsubst() variable substitution."""

    def test_replaces_account_id(self) -> None:
        """${ACCOUNT_ID} is replaced with the provided account ID."""
        content = "arn:aws:states:us-east-1:${ACCOUNT_ID}:stateMachine:foo"
        result = envsubst(content, "123456789012", "us-east-1")
        assert result == "arn:aws:states:us-east-1:123456789012:stateMachine:foo"

    def test_replaces_aws_region(self) -> None:
        """${AWS_REGION} is replaced with the provided region."""
        content = "arn:aws:states:${AWS_REGION}:123:stateMachine:foo"
        result = envsubst(content, "123456789012", "us-west-2")
        assert result == "arn:aws:states:us-west-2:123:stateMachine:foo"

    def test_replaces_both_variables(self) -> None:
        """Both ${ACCOUNT_ID} and ${AWS_REGION} are replaced in the same string."""
        content = "arn:aws:states:${AWS_REGION}:${ACCOUNT_ID}:stateMachine:foo"
        result = envsubst(content, "111222333444", "eu-west-1")
        assert result == "arn:aws:states:eu-west-1:111222333444:stateMachine:foo"

    def test_leaves_jsonpath_untouched(self) -> None:
        """JSONPath expressions like $.input.path are not modified."""
        content = '{"InputPath": "$.input.path", "ResultPath": "$.result"}'
        result = envsubst(content, "123456789012", "us-east-1")
        assert result == content

    def test_leaves_plain_dollar_untouched(self) -> None:
        """$PLAIN without braces is not substituted."""
        content = "value is $PLAIN"
        result = envsubst(content, "123456789012", "us-east-1")
        assert result == "value is $PLAIN"

    def test_leaves_unknown_braced_var_untouched(self) -> None:
        """${UNKNOWN_VAR} is not substituted (only ACCOUNT_ID and AWS_REGION)."""
        content = "value is ${UNKNOWN_VAR}"
        result = envsubst(content, "123456789012", "us-east-1")
        assert result == "value is ${UNKNOWN_VAR}"

    def test_passthrough_no_variables(self) -> None:
        """Content with no variables is returned unchanged."""
        content = "no variables here at all"
        result = envsubst(content, "123456789012", "us-east-1")
        assert result == content

    def test_multiple_occurrences_of_same_variable(self) -> None:
        """Multiple occurrences of the same variable are all replaced."""
        content = "${ACCOUNT_ID}-${ACCOUNT_ID}-${ACCOUNT_ID}"
        result = envsubst(content, "999", "us-east-1")
        assert result == "999-999-999"

    def test_mixed_content_with_jsonpath_and_variables(self) -> None:
        """Content mixing JSONPath and substitution variables works correctly."""
        content = (
            '{"Resource": "arn:aws:states:${AWS_REGION}:${ACCOUNT_ID}:stateMachine:inner",'
            ' "InputPath": "$.input.data"}'
        )
        result = envsubst(content, "111", "ap-southeast-1")
        expected = (
            '{"Resource": "arn:aws:states:ap-southeast-1:111:stateMachine:inner",'
            ' "InputPath": "$.input.data"}'
        )
        assert result == expected


class TestComputeContentHash:
    """Tests for compute_content_hash() SHA-256 hashing."""

    def test_returns_hex_string(self) -> None:
        """Hash is a hex digest string."""
        result = compute_content_hash("hello")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest is 64 chars

    def test_deterministic(self) -> None:
        """Same content always produces the same hash."""
        h1 = compute_content_hash("deterministic content")
        h2 = compute_content_hash("deterministic content")
        assert h1 == h2

    def test_different_content_different_hash(self) -> None:
        """Different content produces different hashes."""
        h1 = compute_content_hash("content A")
        h2 = compute_content_hash("content B")
        assert h1 != h2


class TestGetContentHashTag:
    """Tests for get_content_hash_tag() tag extraction."""

    def test_extracts_from_sf_tag_format(self) -> None:
        """Extracts from Step Functions list-of-dicts tag format."""
        tags = [
            {"key": "environment", "value": "prod"},
            {"key": "ferry:content-hash", "value": "abc123"},
        ]
        assert get_content_hash_tag(tags) == "abc123"

    def test_extracts_from_apigw_dict_format(self) -> None:
        """Extracts from API Gateway flat dict tag format."""
        tags = {"environment": "prod", "ferry:content-hash": "def456"}
        assert get_content_hash_tag(tags) == "def456"

    def test_returns_none_when_not_present_list(self) -> None:
        """Returns None when tag not in SF list format."""
        tags = [{"key": "other-tag", "value": "val"}]
        assert get_content_hash_tag(tags) is None

    def test_returns_none_when_not_present_dict(self) -> None:
        """Returns None when tag not in APIGW dict format."""
        tags = {"other-tag": "val"}
        assert get_content_hash_tag(tags) is None

    def test_returns_none_for_empty_list(self) -> None:
        """Returns None for empty tag list."""
        assert get_content_hash_tag([]) is None

    def test_returns_none_for_empty_dict(self) -> None:
        """Returns None for empty tag dict."""
        assert get_content_hash_tag({}) is None
