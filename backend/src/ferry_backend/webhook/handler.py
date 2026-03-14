"""Lambda Function URL entry point for GitHub webhook processing.

Wires together signature validation, deduplication, config loading,
change detection, dispatch triggering, Check Run creation, and
comment-driven /ferry plan and /ferry apply workflows.

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
    find_deploy_comment,
    format_apply_comment,
    format_apply_status_update,
    format_no_changes_comment,
    format_plan_comment,
    parse_ferry_command,
    resolve_environment,
)
from ferry_backend.checks.runs import (
    create_check_run,
    find_merged_pr,
    find_open_prs,
    post_pr_comment,
    update_pr_comment,
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
from ferry_utils.constants import WORKFLOW_FILENAME
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
    5. Filter non-supported events
    6. Deduplicate
    7. Route to event-specific handler

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
    if event_type not in {"push", "pull_request", "issue_comment", "workflow_run"}:
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

    # Route to event-specific handler
    if event_type == "pull_request":
        return _handle_pull_request(payload, repo)

    if event_type == "issue_comment":
        return _handle_issue_comment(payload, repo)

    if event_type == "workflow_run":
        return _handle_workflow_run(payload, repo)

    # --- Push event ---

    # Early return: branch deletion (before any API calls)
    ref = payload.get("ref", "")
    deleted = payload.get("deleted", False)

    if deleted:
        log.info("push_branch_deleted", ref=ref)
        return _response(200, {"status": "ignored", "reason": "branch deleted"})

    # Early return: tag push (not a branch ref)
    if not ref.startswith("refs/heads/"):
        log.info("push_tag_ignored", ref=ref)
        return _response(200, {"status": "ignored", "reason": "tag push"})

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
        default_branch = payload["repository"]["default_branch"]
        branch = ref.removeprefix("refs/heads/")

        structlog.contextvars.bind_contextvars(
            branch=branch,
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
            changed_files = get_changed_files(
                github_client,
                repo,
                before_sha,
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

        # 12. Environment-gated dispatch
        environment = resolve_environment(config, branch)

        if environment is None:
            log.info("push_no_environment_match", branch=branch)
            return _response(200, {"status": "processed", "affected": len(affected)})

        if not environment.auto_deploy:
            log.info(
                "push_auto_deploy_disabled",
                branch=branch,
                environment=environment.name,
            )
            return _response(200, {"status": "processed", "affected": len(affected)})

        # Match + auto_deploy: true -> dispatch + Check Run
        if affected:
            prs = find_open_prs(github_client, repo, after_sha)
            merged_pr = None
            if prs:
                pr_number = str(prs[0]["number"])
            else:
                merged_pr = find_merged_pr(github_client, repo, after_sha)
                pr_number = str(merged_pr["number"]) if merged_pr else ""
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
                mode="deploy",
                environment=environment.name,
                head_ref=after_sha,
                base_ref=branch,
            )
            log.info(
                "dispatches_triggered",
                count=len({r.resource_type for r in affected}),
                environment=environment.name,
            )

            # Post deploy comment on merged PR (reuse lookup from above)
            if merged_pr:
                deploy_body = format_apply_comment(
                    affected, environment, after_sha, merged_pr["number"], deployment_tag=tag
                )
                post_pr_comment(github_client, repo, merged_pr["number"], deploy_body)

        # Check Run (always for auto_deploy matched branches, even with no changes)
        create_check_run(github_client, repo, after_sha, affected)

        return _response(
            200,
            {"status": "processed", "affected": len(affected)},
        )

    except ConfigError as exc:
        log.error("config_error", error=str(exc))
        comment_body = (
            f"**Ferry: Configuration Error**\n\nferry.yaml validation failed:\n```\n{exc!s}\n```"
        )
        prs = find_open_prs(github_client, repo, after_sha)
        if prs:
            post_pr_comment(
                github_client,
                repo,
                prs[0]["number"],
                comment_body,
            )
        else:
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


# ---------------------------------------------------------------------------
# pull_request event handler
# ---------------------------------------------------------------------------


def _handle_pull_request(payload: dict, repo: str) -> dict:
    """Handle pull_request webhook events.

    Posts a new plan comment (non-sticky) showing affected resources and
    creates a Check Run.

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

        # Plan comment (new comment per event, not sticky)
        environment = resolve_environment(config, base_branch)
        if affected:
            comment_body = format_plan_comment(affected, environment)
        else:
            comment_body = format_no_changes_comment()
        post_pr_comment(github_client, repo, pr_number, comment_body)

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
        post_pr_comment(github_client, repo, pr_number, comment_body)
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


# ---------------------------------------------------------------------------
# issue_comment event handler (/ferry plan, /ferry apply)
# ---------------------------------------------------------------------------


def _handle_issue_comment(payload: dict, repo: str) -> dict:
    """Handle issue_comment webhook events for /ferry commands.

    Processes /ferry plan and /ferry apply commands on PR comments.
    Ignores comments on regular issues, edited/deleted comments, and
    non-ferry commands.

    Args:
        payload: Parsed issue_comment webhook payload.
        repo: Repository full name (owner/repo).

    Returns:
        Lambda Function URL response dict.
    """
    # 1. Filter: only action=created
    action = payload.get("action", "")
    if action != "created":
        log.info("comment_action_ignored", action=action)
        return _response(200, {"status": "ignored", "reason": "not a new comment"})

    # 2. Parse command
    comment = payload["comment"]
    comment_body = comment["body"]
    command = parse_ferry_command(comment_body)
    if command is None:
        log.info("comment_not_ferry_command")
        return _response(200, {"status": "ignored", "reason": "not a ferry command"})

    # 3. Guard: must be on a PR (not a plain issue) -> DEPLOY-04
    issue = payload["issue"]
    if "pull_request" not in issue:
        log.info("comment_on_issue_ignored", command=command)
        return _response(200, {"status": "ignored", "reason": "comment on issue, not PR"})

    pr_number = issue["number"]
    comment_id = comment["id"]

    structlog.contextvars.bind_contextvars(
        pr_number=pr_number,
        comment_id=comment_id,
        command=command,
    )

    try:
        # 4. Auth
        jwt_token = generate_app_jwt(settings.app_id, settings.private_key)
        github_client.app_auth(jwt_token)
        inst_token = get_installation_token(
            github_client,
            jwt_token,
            settings.installation_id,
        )
        github_client.installation_auth(inst_token)

        # 5. Add eyes reaction (always, even for closed PR or no resources)
        github_client.post(
            f"/repos/{repo}/issues/comments/{comment_id}/reactions",
            json={"content": "eyes"},
        )

        # 6. Guard: PR must be open
        if issue.get("state") != "open":
            refusal = (
                f"**Ferry:** PR #{pr_number} is not open -- `/ferry {command}` requires an open PR."
            )
            post_pr_comment(github_client, repo, pr_number, refusal)
            return _response(200, {"status": "refused", "reason": "PR not open"})

        # 7. Fetch fresh PR data (head SHA + base branch)
        pr_resp = github_client.get(f"/repos/{repo}/pulls/{pr_number}")
        pr_data = pr_resp.json()
        head_sha = pr_data["head"]["sha"]
        head_branch = pr_data["head"]["ref"]
        base_branch = pr_data["base"]["ref"]
        default_branch = payload["repository"]["default_branch"]

        structlog.contextvars.bind_contextvars(
            head_sha=head_sha[:7],
            base_branch=base_branch,
        )

        # 8. Fetch and validate config
        raw_yaml = fetch_ferry_config(github_client, repo, head_sha)
        parsed = parse_config(raw_yaml)
        config = validate_config(parsed)

        # 9. Detect changes
        changed_files = get_changed_files(github_client, repo, base_branch, head_sha)
        affected = match_resources(config, changed_files)

        if "ferry.yaml" in changed_files:
            try:
                old_raw = fetch_ferry_config(github_client, repo, base_branch)
                old_parsed = parse_config(old_raw)
                old_config = validate_config(old_parsed)
            except ConfigError:
                old_config = None
            config_affected = detect_config_changes(old_config, config)
            affected = merge_affected(affected, config_affected)

        log.info("comment_changes_detected", affected_count=len(affected))
        environment = resolve_environment(config, base_branch)

        # 10. Route by command
        if command == "plan":
            return _handle_plan_command(
                repo,
                pr_number,
                head_sha,
                affected,
                environment,
                config,
            )
        # command == "apply"
        return _handle_apply_command(
            repo,
            pr_number,
            head_sha,
            head_branch,
            base_branch,
            default_branch,
            affected,
            environment,
            config,
        )

    except ConfigError as exc:
        log.error("comment_config_error", error=str(exc))
        error_body = (
            f"**Ferry: Configuration Error**\n\nferry.yaml validation failed:\n```\n{exc!s}\n```"
        )
        post_pr_comment(github_client, repo, pr_number, error_body)
        return _response(200, {"status": "config_error", "error": str(exc)})

    except GitHubAuthError as exc:
        log.error("comment_auth_error", error=str(exc), exc_info=True)
        return _response(500, {"status": "auth_error", "error": str(exc)})

    except Exception as exc:
        log.error("comment_unhandled_error", error=str(exc), exc_info=True)
        return _response(500, {"status": "internal_error", "error": "internal server error"})


def _handle_plan_command(
    repo: str,
    pr_number: int,
    head_sha: str,
    affected: list,
    environment: object,
    config: object,
) -> dict:
    """Execute /ferry plan: post plan comment + check run.

    Args:
        repo: Repository full name.
        pr_number: PR number.
        head_sha: Current PR head SHA.
        affected: Detected affected resources.
        environment: Resolved environment mapping (or None).
        config: Validated FerryConfig.

    Returns:
        Lambda Function URL response dict.
    """
    comment_body = (
        format_plan_comment(affected, environment) if affected else format_no_changes_comment()
    )
    post_pr_comment(github_client, repo, pr_number, comment_body)
    create_check_run(github_client, repo, head_sha, affected, no_change_conclusion="neutral")
    return _response(200, {"status": "processed", "command": "plan", "affected": len(affected)})


def _handle_apply_command(
    repo: str,
    pr_number: int,
    head_sha: str,
    head_branch: str,
    base_branch: str,
    default_branch: str,
    affected: list,
    environment: object,
    config: object,
) -> dict:
    """Execute /ferry apply: dispatch deploy + post apply comment + check run.

    Args:
        repo: Repository full name.
        pr_number: PR number.
        head_sha: Current PR head SHA.
        head_branch: PR head branch name (dispatch ref for checkout).
        base_branch: PR base branch name.
        default_branch: Repository default branch.
        affected: Detected affected resources.
        environment: Resolved environment mapping (or None).
        config: Validated FerryConfig.

    Returns:
        Lambda Function URL response dict.
    """
    if not affected:
        body = "**Ferry:** No Ferry-managed resources affected -- nothing to deploy."
        post_pr_comment(github_client, repo, pr_number, body)
        return _response(200, {"status": "processed", "command": "apply", "affected": 0})

    env_name = environment.name if environment else ""
    tag = build_deployment_tag(str(pr_number), base_branch, head_sha)
    trigger_dispatches(
        github_client,
        repo,
        config,
        affected,
        head_sha,
        tag,
        str(pr_number),
        default_branch=head_branch,
        mode="deploy",
        environment=env_name,
        head_ref=head_sha,
        base_ref=base_branch,
    )
    display_tag = f"{head_branch}-{head_sha[:4]}"
    body = format_apply_comment(
        affected, environment, head_sha, pr_number, deployment_tag=display_tag
    )
    post_pr_comment(github_client, repo, pr_number, body)
    create_check_run(github_client, repo, head_sha, affected)
    log.info("apply_dispatched", affected_count=len(affected))
    return _response(
        200,
        {"status": "processed", "command": "apply", "affected": len(affected)},
    )


# ---------------------------------------------------------------------------
# workflow_run event handler (apply status update)
# ---------------------------------------------------------------------------


def _handle_workflow_run(payload: dict, repo: str) -> dict:
    """Handle workflow_run webhook events for deploy status updates.

    When a Ferry workflow_dispatch run completes, finds and updates the
    corresponding apply comment with the final conclusion and run link.

    Args:
        payload: Parsed workflow_run webhook payload.
        repo: Repository full name (owner/repo).

    Returns:
        Lambda Function URL response dict.
    """
    action = payload.get("action", "")
    if action != "completed":
        log.info("workflow_run_action_ignored", action=action)
        return _response(200, {"status": "ignored", "reason": "not completed"})

    wf_run = payload["workflow_run"]

    # Filter: only workflow_dispatch-triggered runs
    if wf_run.get("event") != "workflow_dispatch":
        log.info("workflow_run_not_dispatch", trigger_event=wf_run.get("event"))
        return _response(200, {"status": "ignored", "reason": "not dispatch-triggered"})

    # Filter: only Ferry workflow
    expected_path = f".github/workflows/{WORKFLOW_FILENAME}"
    if wf_run.get("path") != expected_path:
        log.info("workflow_run_not_ferry", path=wf_run.get("path"))
        return _response(200, {"status": "ignored", "reason": "not ferry workflow"})

    run_id = wf_run["id"]
    conclusion = wf_run.get("conclusion", "unknown")
    run_url = wf_run.get("html_url", "")

    structlog.contextvars.bind_contextvars(
        run_id=run_id,
        conclusion=conclusion,
    )

    try:
        # Auth
        jwt_token = generate_app_jwt(settings.app_id, settings.private_key)
        github_client.app_auth(jwt_token)
        inst_token = get_installation_token(
            github_client,
            jwt_token,
            settings.installation_id,
        )
        github_client.installation_auth(inst_token)

        # Correlate run → PR via head_sha → commit/pulls API
        trigger_sha = wf_run.get("head_sha", "")
        if not trigger_sha:
            log.info("workflow_run_no_head_sha")
            return _response(200, {"status": "ignored", "reason": "no head_sha"})

        prs_resp = github_client.get(f"/repos/{repo}/commits/{trigger_sha}/pulls")
        pr_number = None
        if prs_resp.status_code == 200:
            for pr in prs_resp.json():
                pr_number = pr["number"]
                if pr.get("state") == "open":
                    break  # prefer open PR

        if pr_number is None:
            log.info(
                "workflow_run_no_correlation",
                trigger_sha=trigger_sha[:7],
            )
            return _response(200, {"status": "ignored", "reason": "no correlation data"})

        # Find deploy comment by SHA (each /ferry apply creates a new one)
        existing = find_deploy_comment(github_client, repo, pr_number, sha=trigger_sha)
        if existing:
            updated_body = format_apply_status_update(existing["body"], conclusion, run_url)
            update_pr_comment(github_client, repo, existing["id"], updated_body)
            log.info(
                "deploy_comment_updated",
                pr_number=pr_number,
                conclusion=conclusion,
            )
        else:
            log.warning(
                "deploy_comment_not_found",
                pr_number=pr_number,
                trigger_sha=trigger_sha[:7],
            )

        return _response(200, {"status": "processed", "conclusion": conclusion})

    except GitHubAuthError as exc:
        log.error("workflow_run_auth_error", error=str(exc), exc_info=True)
        return _response(500, {"status": "auth_error", "error": str(exc)})

    except Exception as exc:
        log.error("workflow_run_unhandled_error", error=str(exc), exc_info=True)
        return _response(500, {"status": "internal_error", "error": "internal server error"})


# ---------------------------------------------------------------------------
# Response helper
# ---------------------------------------------------------------------------


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
