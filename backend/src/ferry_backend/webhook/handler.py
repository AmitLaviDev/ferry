"""Lambda Function URL entry point for GitHub webhook processing.

Wires together signature validation, deduplication, config loading,
change detection, dispatch triggering, and Check Run creation.

Response format follows Lambda Function URL payload format v2:
{statusCode: int, headers: dict, body: str (JSON)}
"""

import base64
import json

import boto3
import structlog

from ferry_backend.auth.jwt import generate_app_jwt
from ferry_backend.auth.tokens import get_installation_token
from ferry_backend.checks.plan import (
    find_plan_comment,
    format_no_changes_comment,
    format_plan_comment,
    resolve_environment,
    upsert_plan_comment,
)
from ferry_backend.checks.runs import (
    create_check_run,
    find_merged_pr,
    find_open_prs,
    post_pr_comment,
)
from ferry_backend.config.loader import fetch_ferry_config, parse_config
from ferry_backend.config.schema import validate_config
from ferry_backend.detect.changes import (
    detect_config_changes,
    get_changed_files,
    match_resources,
    merge_affected,
)
from ferry_backend.dispatch.trigger import (
    build_deployment_tag,
    trigger_dispatches,
)
from ferry_backend.github.client import GitHubClient
from ferry_backend.logging import configure_logging
from ferry_backend.settings import Settings
from ferry_backend.webhook.dedup import is_duplicate
from ferry_backend.webhook.signature import verify_signature
from ferry_utils.errors import ConfigError, GitHubAuthError

# Module-level initialization for Lambda cold start optimization
settings = Settings()
configure_logging(settings.log_level)
log = structlog.get_logger()
dynamodb_client = boto3.client("dynamodb", region_name="us-east-1")
github_client = GitHubClient()


def handler(event: dict, context: object) -> dict:
    """Lambda Function URL handler for GitHub webhooks.

    Processing order:
    1. Extract and decode body (handle base64)
    2. Normalize headers to lowercase
    3. Validate HMAC-SHA256 signature (before JSON parsing)
    4. Check for required headers
    5. Filter non-push events
    6. Deduplicate
    7. Authenticate as GitHub App installation
    8. Fetch and validate config
    9. Detect changes
    10. Dispatch or create Check Run

    Args:
        event: Lambda Function URL event (payload format v2).
        context: Lambda context object (unused).

    Returns:
        Lambda Function URL response dict with statusCode, headers, body.
    """
    # 1. Extract body - handle possible base64 encoding (Pitfall 1)
    body = event.get("body", "")
    if event.get("isBase64Encoded", False):
        body = base64.b64decode(body).decode("utf-8")

    # 2. Normalize headers to lowercase (Pitfall 5)
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}

    # 3. Validate signature BEFORE any JSON parsing
    signature = headers.get("x-hub-signature-256", "")
    if not verify_signature(body, signature, settings.webhook_secret):
        log.warning("webhook_signature_invalid")
        return _response(401, {"error": "invalid signature"})

    # 4. Check for required delivery ID header
    delivery_id = headers.get("x-github-delivery", "")
    if not delivery_id:
        log.warning("webhook_missing_delivery_id")
        return _response(400, {"error": "missing delivery id"})

    event_type = headers.get("x-github-event", "")

    # Bind context for structured logging
    structlog.contextvars.bind_contextvars(
        delivery_id=delivery_id,
        event_type=event_type,
    )

    # 5. Filter unsupported events
    if event_type not in {"push", "pull_request"}:
        log.info("webhook_event_ignored", reason="unsupported event")
        return _response(200, {"status": "ignored"})

    # 6. Parse payload (after signature validation)
    payload = json.loads(body)

    # Bind repo to log context
    repo = payload.get("repository", {}).get("full_name", "unknown")
    structlog.contextvars.bind_contextvars(repo=repo)

    # 7. Deduplicate
    if is_duplicate(
        delivery_id,
        payload,
        settings.table_name,
        dynamodb_client,
    ):
        log.info("webhook_duplicate_delivery")
        return _response(200, {"status": "duplicate"})

    # Route pull_request events to dedicated handler
    if event_type == "pull_request":
        return _handle_pull_request(payload, repo)

    # --- Phase 2: Auth -> Config -> Detect -> Dispatch/Check Run ---
    # Wrapped in top-level exception handler (Phase 8) to ensure
    # all errors produce structured JSON responses.

    try:
        # 8. Authenticate as GitHub App installation
        jwt_token = generate_app_jwt(settings.app_id, settings.private_key)
        github_client.app_auth(jwt_token)
        inst_token = get_installation_token(
            github_client,
            jwt_token,
            settings.installation_id,
        )
        github_client.installation_auth(inst_token)

        # 9. Extract push context
        before_sha = payload.get("before", "")
        after_sha = payload.get("after", "")
        ref = payload.get("ref", "")
        default_branch = payload["repository"]["default_branch"]
        branch = ref.removeprefix("refs/heads/")
        is_default_branch = branch == default_branch

        structlog.contextvars.bind_contextvars(
            branch=branch,
            is_default_branch=is_default_branch,
            after_sha=after_sha[:7],
        )

        # 10. Fetch and validate config (fail-fast)
        raw_yaml = fetch_ferry_config(github_client, repo, after_sha)
        parsed = parse_config(raw_yaml)
        config = validate_config(parsed)

        # 11. Detect changes
        is_initial_push = before_sha == "0" * 40
        if is_initial_push:
            # All resources affected on initial push
            affected = detect_config_changes(None, config)
        else:
            # PR branches: merge-base diff (default_branch...head)
            # Default branch: before...after (the merge commit landing)
            # Three-dot compare uses merge-base automatically for PR branches
            compare_base = before_sha if is_default_branch else default_branch
            changed_files = get_changed_files(
                github_client,
                repo,
                compare_base,
                after_sha,
            )
            affected = match_resources(config, changed_files)

            # Config diff if ferry.yaml itself changed
            if "ferry.yaml" in changed_files:
                try:
                    old_raw = fetch_ferry_config(
                        github_client,
                        repo,
                        before_sha,
                    )
                    old_parsed = parse_config(old_raw)
                    old_config = validate_config(old_parsed)
                except ConfigError:
                    old_config = None  # Old config invalid -> all new
                config_affected = detect_config_changes(
                    old_config,
                    config,
                )
                affected = merge_affected(affected, config_affected)

        log.info("changes_detected", affected_count=len(affected))

        # 12. Branch-dependent behavior
        # Default branch pushes: trigger dispatches
        if is_default_branch and affected:
            # For default branch, find merged PR number
            prs = find_open_prs(github_client, repo, after_sha)
            pr_number = str(prs[0]["number"]) if prs else ""
            tag = build_deployment_tag(pr_number, branch, after_sha)
            trigger_dispatches(
                github_client,
                repo,
                config,
                affected,
                after_sha,
                tag,
                pr_number,
                default_branch=default_branch,
            )
            log.info(
                "dispatches_triggered",
                count=len({r.resource_type for r in affected}),
            )

        # 13. Check Run for PRs (always, even with no changes)
        if not is_default_branch:
            prs = find_open_prs(github_client, repo, after_sha)
            if prs:
                create_check_run(
                    github_client,
                    repo,
                    after_sha,
                    affected,
                )

        return _response(
            200,
            {"status": "processed", "affected": len(affected)},
        )

    except ConfigError as exc:
        log.error("config_error", error=str(exc))
        # Surface config errors as PR comments (not Check Runs)
        comment_body = (
            f"**Ferry: Configuration Error**\n\nferry.yaml validation failed:\n```\n{exc!s}\n```"
        )
        # PR branches: comment on the open PR
        prs = find_open_prs(github_client, repo, after_sha)
        if prs:
            post_pr_comment(
                github_client,
                repo,
                prs[0]["number"],
                comment_body,
            )
        else:
            # Default branch: find the merged PR
            merged_pr = find_merged_pr(github_client, repo, after_sha)
            if merged_pr:
                post_pr_comment(
                    github_client,
                    repo,
                    merged_pr["number"],
                    comment_body,
                )
            else:
                log.warning(
                    "config_error_no_pr",
                    reason="no open or merged PR found for comment",
                )
        return _response(
            200,
            {"status": "config_error", "error": str(exc)},
        )

    except GitHubAuthError as exc:
        log.error("auth_error", error=str(exc), exc_info=True)
        return _response(
            500,
            {"status": "auth_error", "error": str(exc)},
        )

    except Exception as exc:
        log.error("unhandled_error", error=str(exc), exc_info=True)
        return _response(
            500,
            {"status": "internal_error", "error": "internal server error"},
        )


def _handle_pull_request(payload: dict, repo: str) -> dict:
    """Handle pull_request webhook events.

    Posts a sticky plan comment showing affected resources and creates a
    Check Run. Updates an existing plan comment on subsequent pushes.

    Args:
        payload: Parsed pull_request webhook payload.
        repo: Repository full name (owner/repo).

    Returns:
        Lambda Function URL response dict.
    """
    action = payload.get("action", "")
    if action not in {"opened", "synchronize", "reopened"}:
        log.info("pr_action_ignored", action=action)
        return _response(200, {"status": "ignored", "reason": "unsupported PR action"})

    pr = payload["pull_request"]
    pr_number = pr["number"]
    head_sha = pr["head"]["sha"]
    base_branch = pr["base"]["ref"]

    structlog.contextvars.bind_contextvars(
        pr_number=pr_number,
        head_sha=head_sha[:7],
        base_branch=base_branch,
    )

    try:
        # Authenticate as GitHub App installation
        jwt_token = generate_app_jwt(settings.app_id, settings.private_key)
        github_client.app_auth(jwt_token)
        inst_token = get_installation_token(
            github_client,
            jwt_token,
            settings.installation_id,
        )
        github_client.installation_auth(inst_token)

        # Fetch and validate config
        raw_yaml = fetch_ferry_config(github_client, repo, head_sha)
        parsed = parse_config(raw_yaml)
        config = validate_config(parsed)

        # Detect changes using base_branch as compare base
        changed_files = get_changed_files(
            github_client,
            repo,
            base_branch,
            head_sha,
        )
        affected = match_resources(config, changed_files)

        # Config diff if ferry.yaml itself changed
        if "ferry.yaml" in changed_files:
            try:
                old_raw = fetch_ferry_config(github_client, repo, base_branch)
                old_parsed = parse_config(old_raw)
                old_config = validate_config(old_parsed)
            except ConfigError:
                old_config = None
            config_affected = detect_config_changes(old_config, config)
            affected = merge_affected(affected, config_affected)

        log.info("pr_changes_detected", affected_count=len(affected))

        # Plan comment
        environment = resolve_environment(config, base_branch)
        if affected:
            body = format_plan_comment(affected, environment)
            upsert_plan_comment(github_client, repo, pr_number, body)
        else:
            # No changes: update existing comment to no-changes, or stay silent
            existing = find_plan_comment(github_client, repo, pr_number)
            if existing:
                body = format_no_changes_comment()
                upsert_plan_comment(github_client, repo, pr_number, body)

        # Check Run (always)
        create_check_run(
            github_client,
            repo,
            head_sha,
            affected,
            no_change_conclusion="neutral",
        )

        return _response(
            200,
            {"status": "processed", "affected": len(affected)},
        )

    except ConfigError as exc:
        log.error("pr_config_error", error=str(exc))
        comment_body = (
            f"**Ferry: Configuration Error**\n\nferry.yaml validation failed:\n```\n{exc!s}\n```"
        )
        upsert_plan_comment(github_client, repo, pr_number, comment_body)
        return _response(
            200,
            {"status": "config_error", "error": str(exc)},
        )

    except GitHubAuthError as exc:
        log.error("pr_auth_error", error=str(exc), exc_info=True)
        return _response(
            500,
            {"status": "auth_error", "error": str(exc)},
        )

    except Exception as exc:
        log.error("pr_unhandled_error", error=str(exc), exc_info=True)
        return _response(
            500,
            {"status": "internal_error", "error": "internal server error"},
        )


def _response(status_code: int, body: dict) -> dict:
    """Build Lambda Function URL response.

    Args:
        status_code: HTTP status code.
        body: Response body dict (will be JSON-serialized).

    Returns:
        Lambda Function URL response format.
    """
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
