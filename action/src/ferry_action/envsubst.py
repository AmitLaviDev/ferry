"""Shared variable substitution and content hashing utilities.

Provides envsubst-style ``${ACCOUNT_ID}`` and ``${AWS_REGION}`` replacement,
SHA-256 content hashing for change detection, and tag extraction helpers
for both Step Functions and API Gateway tag formats.
"""

from __future__ import annotations

import hashlib
import re

# Only matches ${ACCOUNT_ID} and ${AWS_REGION} -- nothing else.
# JSONPath expressions ($.path) use dollar-dot, not dollar-brace,
# so they are never matched by this pattern.
_ENVSUBST_PATTERN = re.compile(r"\$\{(ACCOUNT_ID|AWS_REGION)\}")

_TAG_KEY = "ferry:content-hash"


def envsubst(content: str, account_id: str, region: str) -> str:
    """Replace ``${ACCOUNT_ID}`` and ``${AWS_REGION}`` in *content*.

    Only these two variables are substituted. All other content
    (including JSONPath expressions like ``$.path``, plain ``$VAR``,
    and unknown ``${OTHER}``) is left untouched.

    Args:
        content: The string to perform substitution on.
        account_id: AWS account ID to substitute.
        region: AWS region to substitute.

    Returns:
        The content string with known variables replaced.
    """
    replacements = {"ACCOUNT_ID": account_id, "AWS_REGION": region}
    return _ENVSUBST_PATTERN.sub(lambda m: replacements[m.group(1)], content)


def compute_content_hash(content: str) -> str:
    """Compute a SHA-256 hex digest of *content* for change detection.

    Args:
        content: The string content to hash.

    Returns:
        A 64-character lowercase hex digest string.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_content_hash_tag(tags: list[dict] | dict) -> str | None:
    """Extract the ``ferry:content-hash`` value from AWS resource tags.

    Handles both tag formats:
    - **Step Functions** (list of dicts): ``[{"key": "...", "value": "..."}]``
    - **API Gateway** (flat dict): ``{"ferry:content-hash": "abc123"}``

    Args:
        tags: Tags in either SF list format or APIGW dict format.

    Returns:
        The content hash string, or ``None`` if the tag is not present.
    """
    if isinstance(tags, dict):
        return tags.get(_TAG_KEY)

    # Step Functions list-of-dicts format
    for tag in tags:
        if tag.get("key") == _TAG_KEY:
            return tag.get("value")

    return None
