# Phase 2: App Core Logic - Research

**Researched:** 2026-02-24
**Domain:** GitHub API integration (Contents, Compare, Checks, Dispatches), YAML config parsing + Pydantic v2 validation, change detection algorithms
**Confidence:** HIGH

## Summary

Phase 2 transforms Ferry App from a webhook-accepting stub into a fully functional orchestrator. The handler currently stops at "accepted" after dedup (Phase 1 stub at line 94 of `handler.py`). This phase extends it to: (1) read ferry.yaml from the user's repo at the pushed commit SHA, (2) validate it with Pydantic v2 models, (3) detect which resources changed by comparing the commit diff against source_dir mappings, (4) fire one workflow_dispatch per affected resource type on default branch pushes, and (5) post a "Ferry: Deployment Plan" Check Run on PR branches.

The GitHub APIs needed are well-documented and straightforward: Contents API for ferry.yaml, Compare API for changed files, Checks API for PR previews, and Actions workflow dispatch API for triggering deploys. The existing `GitHubClient` (httpx wrapper) only needs `get` and `post` methods, which are already implemented. PyYAML is already a dependency of `ferry-utils`. Pydantic v2's `model_validate()` provides the schema validation layer. The main engineering challenge is the change detection logic: mapping Compare API file paths to ferry.yaml resource source_dirs, handling the 300-file API limit, and correctly diffing ferry.yaml config changes.

**Primary recommendation:** Build this as four composable modules under `ferry_backend/`: `config/` (YAML parse + validate), `detect/` (change detection), `dispatch/` (workflow_dispatch triggering), `checks/` (Check Run creation). Each module is pure-function testable with clear inputs/outputs, composed in the handler.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Fail-fast validation**: Any validation error in ferry.yaml (missing required field, unknown type, malformed YAML) fails the entire push -- nothing gets dispatched. Post a failed Check Run with the specific validation error.
- **Required Lambda fields**: Only `name`, `source_dir`, `ecr_repo`. Everything else is optional.
- **Default runtime**: `python3.10` when runtime is not specified in ferry.yaml.
- **Function name mapping**: Optional `function_name` field per resource that defaults to `name`. Allows AWS Lambda function name to differ from the Ferry resource name.
- **Resource types**: `lambdas`, `step_functions`, `api_gateways` as top-level sections (already decided).
- **No defaults block**: Explicit -- what you see is what you get (already decided).
- **source_dir only**: Only files under a resource's `source_dir` trigger that resource. No additional watch paths or shared dependency tracking in v1.
- **ferry.yaml config diffing**: When ferry.yaml itself changes, compare old vs new config -- only dispatch resources whose config entry actually changed (not all resources).
- **GitHub Compare API**: Use the Compare API (base...head) for change detection. One API call, reliable diff.
- **Branch behavior**: Default branch pushes trigger dispatches (actual deploys). PR branch pushes trigger Check Runs only (preview, no deploy).
- **One workflow_dispatch per affected resource type** (not per resource, not monolithic).
- **Pydantic payload**: resource type, resource list, trigger SHA, deployment tag, PR number.
- **Check Run name**: "Ferry: Deployment Plan"
- **Content**: Summary line per resource (type + change indicator: `~` modified, `+` new) with changed file list below each. Terraform-plan-like output.
- **No changes**: Always post the Check Run, even when no resources are affected. Body says "No resources affected by this change." -- keeps Ferry visible.
- **Timing**: Every push to a branch with an open PR triggers a Check Run update. Always current.

### Claude's Discretion
- Exact Check Run markdown formatting and layout
- Error message wording for validation failures
- Compare API pagination handling for large diffs
- How to detect if a branch has an open PR

### Deferred Ideas (OUT OF SCOPE)
- **"ferry deploy" comment trigger**: Digger-style PR comment command that triggers deployment from a feature branch for pre-merge testing in dev/staging. Requires handling `issue_comment` webhooks, branch-aware deployment, and potentially environment mapping. Should be its own phase (possibly Phase 2.1 or later).
- **Deployed-state-aware diff**: Show current deployed version vs proposed version in Check Run (requires AWS access from Ferry App, which is currently out of scope -- Ferry App only has Git context).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CONF-01 | Ferry App reads and validates ferry.yaml from user's repo at the pushed commit SHA via GitHub Contents API | Contents API (`GET /repos/{owner}/{repo}/contents/{path}?ref={sha}`) returns base64-encoded file content; PyYAML `safe_load` + Pydantic `model_validate` for parsing and validation |
| CONF-02 | ferry.yaml supports lambdas, step_functions, and api_gateways as top-level resource types with type-specific fields | Pydantic v2 models with per-type field sets; discriminated unions already established in Phase 1 dispatch models |
| DETECT-01 | Ferry App compares commit diff (via GitHub Compare API) against ferry.yaml path mappings to identify changed resources | Compare API (`GET /repos/{owner}/{repo}/compare/{base}...{head}`) returns up to 300 changed files with `filename` and `status` fields; prefix matching against `source_dir` |
| DETECT-02 | Ferry App posts a GitHub Check Run on PRs showing which resources will be affected before merge | Checks API (`POST /repos/{owner}/{repo}/check-runs`) with `output.title`, `output.summary`, `output.text` (Markdown, 65535 char limit); requires GitHub App auth |
| ORCH-01 | Ferry App triggers one workflow_dispatch per affected resource type with a versioned payload contract | Dispatch API (`POST /repos/{owner}/{repo}/actions/workflows/{id}/dispatches`) with `ref` and `inputs`; max 25 inputs, 1024 chars per input value |
| ORCH-02 | Dispatch payload includes resource type, resource list, trigger SHA, deployment tag, and PR number | Existing `DispatchPayload` Pydantic model in `ferry_utils.models.dispatch`; serialize to JSON string for single `inputs.payload` field |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyYAML | >=6.0.1 | Parse ferry.yaml from raw content | Already a dependency of ferry-utils; `safe_load` prevents code execution; standard Python YAML parser |
| pydantic | >=2.6 | Validate ferry.yaml schema, config models | Already in project; `model_validate()` gives typed errors with field paths; frozen models established in Phase 1 |
| httpx | >=0.27 | GitHub API calls via GitHubClient | Already in project; `GitHubClient` wraps get/post with auth headers |
| structlog | >=24.1 | Structured logging throughout pipeline | Already in project; context vars for delivery_id, repo, etc. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-httpx | >=0.30 | Mock httpx responses for GitHub API tests | All tests that call GitHubClient methods |
| pydantic-settings | >=2.2 | Settings loading (already used) | No new usage; existing Settings class sufficient |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyYAML | ruamel.yaml | Better YAML 1.2 compliance, round-trip editing; unnecessary for read-only config parsing |
| httpx (direct) | PyGithub / ghapi | Higher-level GitHub SDK; adds large dependency, Ferry only uses ~6 endpoints; ~150-line wrapper is more maintainable |
| Pydantic models | jsonschema | Separate validation layer; Pydantic gives typed Python objects and validation in one step |

**Installation:**
No new packages required. All dependencies already present in `ferry-utils` (`pydantic`, `PyYAML`) and `ferry-backend` (`httpx`, `structlog`, `pydantic-settings`).

## Architecture Patterns

### Recommended Module Structure
```
backend/src/ferry_backend/
├── webhook/
│   ├── handler.py       # Existing -- extend Phase 1 stub (line 93-94)
│   ├── signature.py     # Existing (Phase 1)
│   └── dedup.py         # Existing (Phase 1)
├── config/
│   ├── __init__.py
│   ├── loader.py        # fetch_config(client, repo, sha) -> raw YAML string
│   └── schema.py        # FerryConfig Pydantic model + validate_config()
├── detect/
│   ├── __init__.py
│   └── changes.py       # detect_changes(config, changed_files) -> list[AffectedResource]
├── dispatch/
│   ├── __init__.py
│   └── trigger.py       # trigger_dispatches(client, repo, resources, sha, tag, pr)
├── checks/
│   ├── __init__.py
│   └── runs.py          # create_check_run(client, repo, sha, affected_resources)
├── github/
│   ├── client.py        # Existing (Phase 1) -- no changes needed
│   └── __init__.py
├── auth/                # Existing (Phase 1)
├── settings.py          # Existing (Phase 1)
└── logging.py           # Existing (Phase 1)
```

### Pattern 1: Config Loading Pipeline
**What:** Fetch ferry.yaml from GitHub Contents API at exact commit SHA, parse YAML, validate with Pydantic.
**When to use:** Every webhook processing cycle, after dedup passes.
**Example:**
```python
# config/loader.py
import base64
import yaml
from ferry_utils.errors import ConfigError

def fetch_ferry_config(client: GitHubClient, repo: str, sha: str) -> str:
    """Fetch ferry.yaml content from repo at specific commit SHA.

    Uses GitHub Contents API with ref=sha parameter.
    Returns raw YAML string.
    Raises ConfigError if file not found or API error.
    """
    resp = client.get(
        f"/repos/{repo}/contents/ferry.yaml",
        params={"ref": sha},
    )
    if resp.status_code == 404:
        raise ConfigError("ferry.yaml not found in repository root")
    resp.raise_for_status()

    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content


def parse_config(raw_yaml: str) -> dict:
    """Parse YAML string, raising ConfigError on malformed YAML."""
    try:
        return yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Malformed ferry.yaml: {exc}") from exc
```
**Source:** [GitHub Contents API docs](https://docs.github.com/en/rest/repos/contents)

### Pattern 2: Pydantic Config Schema
**What:** Typed ferry.yaml models with fail-fast validation. Each resource type has its own model with type-specific required/optional fields.
**When to use:** After YAML parsing, before any business logic.
**Example:**
```python
# config/schema.py
from pydantic import BaseModel, ConfigDict, model_validator

class LambdaConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str            # Resource name (used as key in ferry.yaml)
    source_dir: str      # Path to source directory
    ecr_repo: str        # ECR repository name
    runtime: str = "python3.10"
    function_name: str | None = None  # Defaults to name if not set

    @model_validator(mode="after")
    def set_function_name_default(self) -> "LambdaConfig":
        if self.function_name is None:
            # frozen model: use object.__setattr__ in validator
            object.__setattr__(self, "function_name", self.name)
        return self

class StepFunctionConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source_dir: str  # Path to definition file or directory

class ApiGatewayConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source_dir: str  # Path to OpenAPI spec

class FerryConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    lambdas: dict[str, LambdaConfig] = {}
    step_functions: dict[str, StepFunctionConfig] = {}
    api_gateways: dict[str, ApiGatewayConfig] = {}

def validate_config(raw: dict) -> FerryConfig:
    """Validate parsed YAML dict against ferry.yaml schema."""
    return FerryConfig.model_validate(raw)
```
**Key detail:** `extra="forbid"` catches typos in field names. Frozen models match Phase 1 pattern.

### Pattern 3: Change Detection via Compare API
**What:** Fetch changed files between before/after SHAs, match against resource source_dirs using path prefix matching.
**When to use:** After config is validated, to determine which resources are affected.
**Example:**
```python
# detect/changes.py
from dataclasses import dataclass

@dataclass(frozen=True)
class AffectedResource:
    name: str
    resource_type: str  # "lambda", "step_function", "api_gateway"
    change_kind: str    # "modified" or "new"
    changed_files: list[str]

def get_changed_files(client: GitHubClient, repo: str, base: str, head: str) -> list[str]:
    """Get list of changed file paths using Compare API.

    Returns list of filenames from the comparison.
    Handles the 300-file limit by also checking the diff format.
    """
    resp = client.get(f"/repos/{repo}/compare/{base}...{head}")
    resp.raise_for_status()
    data = resp.json()
    return [f["filename"] for f in data.get("files", [])]

def match_resources(config: FerryConfig, changed_files: list[str]) -> list[AffectedResource]:
    """Match changed files to ferry.yaml resources by source_dir prefix."""
    affected = []
    for name, resource in config.lambdas.items():
        matching = [f for f in changed_files if f.startswith(resource.source_dir.rstrip("/") + "/")]
        if matching:
            affected.append(AffectedResource(
                name=name, resource_type="lambda",
                change_kind="modified", changed_files=matching,
            ))
    # Repeat for step_functions, api_gateways
    return affected
```
**Source:** [GitHub Compare API docs](https://docs.github.com/en/rest/commits/commits#compare-two-commits)

### Pattern 4: Workflow Dispatch Triggering
**What:** Group affected resources by type, serialize DispatchPayload to JSON, send as single `inputs.payload` string via workflow_dispatch API.
**When to use:** Only on default branch pushes (not PR branches).
**Example:**
```python
# dispatch/trigger.py
from ferry_utils.models import DispatchPayload
from ferry_utils.constants import ResourceType, RESOURCE_TYPE_WORKFLOW_MAP

def trigger_dispatches(
    client: GitHubClient,
    repo: str,
    affected: list[AffectedResource],
    sha: str,
    deployment_tag: str,
    pr_number: str,
) -> list[dict]:
    """Fire one workflow_dispatch per affected resource type.

    Returns list of dispatch results (for logging/status).
    """
    # Group by resource type
    by_type: dict[str, list] = {}
    for resource in affected:
        by_type.setdefault(resource.resource_type, []).append(resource)

    results = []
    for rtype, resources in by_type.items():
        payload = DispatchPayload(
            resource_type=rtype,
            resources=[...],  # Convert AffectedResource to dispatch Resource models
            trigger_sha=sha,
            deployment_tag=deployment_tag,
            pr_number=pr_number,
        )
        # Workflow file named by resource type
        workflow_file = f"ferry-{RESOURCE_TYPE_WORKFLOW_MAP[ResourceType(rtype)]}.yml"
        resp = client.post(
            f"/repos/{repo}/actions/workflows/{workflow_file}/dispatches",
            json={
                "ref": "main",  # Always dispatch on default branch
                "inputs": {"payload": payload.model_dump_json()},
            },
        )
        results.append({"type": rtype, "status": resp.status_code})
    return results
```
**Critical:** The `inputs` field allows max 25 keys, each value max 1024 characters. A single `payload` JSON string is the correct approach. For a typical deployment with a handful of resources, the JSON will be well under 1024 chars. If it ever exceeds 1024, that indicates an unusually large number of resources of one type -- which is unlikely in v1 but should be handled with a clear error.

### Pattern 5: Check Run Creation
**What:** Post a GitHub Check Run showing the deployment plan (Terraform-plan-like output).
**When to use:** On every push to a branch with an open PR, and on validation errors.
**Example:**
```python
# checks/runs.py
def create_check_run(
    client: GitHubClient,
    repo: str,
    sha: str,
    affected: list[AffectedResource],
    error: str | None = None,
) -> None:
    """Create a 'Ferry: Deployment Plan' Check Run."""
    if error:
        output = {
            "title": "Configuration Error",
            "summary": f"ferry.yaml validation failed",
            "text": f"```\n{error}\n```",
        }
        conclusion = "failure"
    elif not affected:
        output = {
            "title": "No Changes Detected",
            "summary": "No resources affected by this change.",
            "text": "",
        }
        conclusion = "success"
    else:
        summary, text = format_deployment_plan(affected)
        output = {
            "title": "Deployment Plan",
            "summary": summary,
            "text": text,
        }
        conclusion = "success"

    client.post(
        f"/repos/{repo}/check-runs",
        json={
            "name": "Ferry: Deployment Plan",
            "head_sha": sha,
            "status": "completed",
            "conclusion": conclusion,
            "output": output,
        },
    )
```
**Source:** [GitHub Checks API docs](https://docs.github.com/en/rest/checks/runs)

### Pattern 6: Detecting Open PRs for a Branch
**What:** Determine if the current push is to a branch with an open PR (needed to decide whether to create a Check Run).
**When to use:** After change detection, before Check Run creation on non-default branches.
**Recommendation:** Use `GET /repos/{owner}/{repo}/commits/{sha}/pulls` to find PRs associated with the pushed commit SHA. This returns both open and merged PRs. Filter for `state == "open"`. This is simpler than listing PRs by branch name because the push event has the SHA readily available.
**Source:** [GitHub Commits API: List PRs for a commit](https://docs.github.com/en/rest/commits/commits#list-pull-requests-associated-with-a-commit)

### Anti-Patterns to Avoid
- **Parsing ferry.yaml at module load time:** Config must be fetched per-webhook, not cached across Lambda invocations. Each push may change ferry.yaml.
- **Dispatching on PR branches:** Only default branch pushes trigger dispatches. PR branches get preview Check Runs only. Mixing these up deploys untested code.
- **Using `ref` for branch detection instead of comparing against `repository.default_branch`:** The push event's `ref` is `refs/heads/{branch}`. Must strip prefix and compare to `repository.default_branch`, not hardcode "main".
- **Building the full dispatch payload in the config module:** Keep concerns separated. Config module validates ferry.yaml. Detect module identifies changes. Dispatch module builds payloads and sends them.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing | Custom tokenizer/parser | `yaml.safe_load()` (PyYAML) | YAML spec is complex; safe_load prevents arbitrary code execution |
| Config validation | Manual field checking with if/else | `pydantic.BaseModel.model_validate()` | Type coercion, error messages with field paths, nested validation |
| HMAC signature | Custom crypto | Already done in Phase 1 `signature.py` | -- |
| HTTP client | Raw httpx calls everywhere | Existing `GitHubClient` wrapper | Consistent auth, headers, base URL |
| JSON serialization for dispatch | Manual dict building | `DispatchPayload.model_dump_json()` | Type-safe, versioned, schema-enforced |

**Key insight:** The entire config-validate-detect-dispatch pipeline can be built from existing project patterns and dependencies. No new libraries needed.

## Common Pitfalls

### Pitfall 1: Compare API 300-File Limit
**What goes wrong:** The Compare API returns at most 300 files. Pushes with more than 300 changed files silently miss resources.
**Why it happens:** GitHub's Compare API enforces a hard 300-file limit per response. This is not paginated -- it's truncated.
**How to avoid:** Check if the Compare API response has `"total_commits"` and if the files array length equals 300 (the truncation signal). If truncated, fall back to the diff format (`Accept: application/vnd.github.diff`) which returns all filenames (though without structured status), or use the PR files API for PR contexts (which is paginated up to 3000 files). For v1, log a warning if truncated -- monorepos with >300 changed files in a single push are unusual.
**Warning signs:** `len(files) == 300` in the Compare API response.

### Pitfall 2: Base64 Content Decoding from Contents API
**What goes wrong:** The Contents API returns file content as base64 with embedded newlines (`\n` line breaks in the base64 string). Standard `base64.b64decode` handles this, but some implementations strip newlines manually first.
**Why it happens:** GitHub formats base64 content with 76-character line wrapping per RFC 2045.
**How to avoid:** Python's `base64.b64decode()` handles embedded whitespace correctly (ignores `\n`). Just pass the content string directly -- no manual stripping needed.
**Warning signs:** Corrupted YAML content after decoding.

### Pitfall 3: ferry.yaml Config Diff Logic Complexity
**What goes wrong:** When ferry.yaml itself changes, naive approach dispatches ALL resources. Correct approach diffs old vs new config to find only changed resources.
**Why it happens:** CONTEXT.md locks the decision: "only dispatch resources whose config entry actually changed."
**How to avoid:** If `ferry.yaml` is in the changed files list: (1) fetch the old version at `before` SHA, (2) fetch the new version at `after` SHA, (3) parse both, (4) compare resource entries. A resource is "changed" if its config dict differs between old and new. A resource is "new" if it exists in new but not old. A resource is "removed" if it exists in old but not new (no dispatch needed for removals).
**Warning signs:** Every ferry.yaml change triggers all resources instead of just the changed ones.

### Pitfall 4: Workflow Dispatch Input Size Limit
**What goes wrong:** The workflow_dispatch API limits each input value to 1024 characters. A JSON-serialized DispatchPayload with many resources could exceed this.
**Why it happens:** GitHub enforces a hard 1024-character limit per input string.
**How to avoid:** Monitor payload size. For typical deployments (1-10 resources of one type), the payload is ~200-500 chars. If it approaches 1024, either split into multiple dispatches or truncate the resource list with a "too many resources" error. In practice, a monorepo with >15 Lambda functions changing in one push is unusual -- flag it as an error rather than silently truncating.
**Warning signs:** 422 Unprocessable Entity from the dispatch API.

### Pitfall 5: Push to Default Branch vs PR Branch Detection
**What goes wrong:** Using `ref == "refs/heads/main"` hardcodes the branch name. Some repos use `master`, `develop`, or custom default branches.
**Why it happens:** Developer assumes "main" is universal.
**How to avoid:** Compare the pushed branch (extracted from `ref` by stripping `refs/heads/`) against `payload.repository.default_branch`. The push event payload always includes the repo's configured default branch.
**Warning signs:** Ferry works in repos with `main` but silently fails in repos with other default branches.

### Pitfall 6: Check Run Requires GitHub App Authentication
**What goes wrong:** Creating Check Runs fails with 403 because the token doesn't have the right permissions.
**Why it happens:** Check Runs can only be created by GitHub Apps (not OAuth apps, not PATs). The installation token must include `checks: write` permission.
**How to avoid:** The existing `get_installation_token` in Phase 1 already requests `checks: write` permission. Use the installation token (not the App JWT) for Check Run creation.
**Warning signs:** 403 Forbidden on POST to check-runs endpoint.

### Pitfall 7: Naming Inconsistency Between Config and Dispatch Models
**What goes wrong:** The ferry.yaml config uses field names like `source_dir` and `ecr_repo`, but the existing dispatch models use `source` and `ecr`. If not reconciled, the mapping between config and dispatch models becomes confusing.
**Why it happens:** Config models (new in Phase 2) and dispatch models (created in Phase 1) were designed at different times.
**How to avoid:** Keep the config models faithful to ferry.yaml field names (`source_dir`, `ecr_repo`). Keep the dispatch models as-is (they're the wire format for the Action). Add explicit mapping in the detect/dispatch layer: `config.source_dir -> dispatch.source`, `config.ecr_repo -> dispatch.ecr`. Document the mapping clearly.
**Warning signs:** Field name confusion when building dispatch payloads from config data.

## Code Examples

### Complete Handler Flow (Phase 2 Extension)
```python
# handler.py -- replacing the Phase 1 stub (lines 93-94)
# After dedup check passes:

from ferry_backend.auth.jwt import generate_app_jwt
from ferry_backend.auth.tokens import get_installation_token
from ferry_backend.config.loader import fetch_ferry_config, parse_config
from ferry_backend.config.schema import validate_config
from ferry_backend.detect.changes import get_changed_files, match_resources, detect_config_changes
from ferry_backend.dispatch.trigger import trigger_dispatches
from ferry_backend.checks.runs import create_check_run

# Authenticate as GitHub App installation
jwt_token = generate_app_jwt(settings.app_id, settings.private_key)
github_client.app_auth(jwt_token)
inst_token = get_installation_token(github_client, jwt_token, settings.installation_id)
github_client.installation_auth(inst_token)

# 1. Fetch and validate config
try:
    raw_yaml = fetch_ferry_config(github_client, repo, after_sha)
    parsed = parse_config(raw_yaml)
    config = validate_config(parsed)
except ConfigError as exc:
    # Post failed Check Run with validation error
    create_check_run(github_client, repo, after_sha, [], error=str(exc))
    return _response(200, {"status": "config_error", "error": str(exc)})

# 2. Detect changes
changed_files = get_changed_files(github_client, repo, before_sha, after_sha)
affected = match_resources(config, changed_files)

# Handle ferry.yaml config changes
if "ferry.yaml" in changed_files:
    config_affected = detect_config_changes(github_client, repo, before_sha, after_sha)
    affected = merge_affected(affected, config_affected)

# 3. Branch-dependent behavior
branch = ref.removeprefix("refs/heads/")
is_default = branch == payload["repository"]["default_branch"]

if is_default and affected:
    # Default branch: dispatch deploys
    tag = f"pr-{pr_number}" if pr_number else f"{branch}-{after_sha[:7]}"
    trigger_dispatches(github_client, repo, affected, after_sha, tag, pr_number)

# 4. Check Run for PRs (always, even if no changes)
# Find if this commit is part of an open PR
prs = find_open_prs(github_client, repo, after_sha)
if prs:
    create_check_run(github_client, repo, after_sha, affected)
```

### ferry.yaml Full Example (All Resource Types)
```yaml
version: 1
lambdas:
  order-processor:
    source_dir: services/order-processor
    ecr_repo: ferry/order-processor
    runtime: python3.12
    function_name: OrderProcessorLambda
  payment-handler:
    source_dir: services/payment-handler
    ecr_repo: ferry/payment-handler
    # runtime defaults to python3.10
    # function_name defaults to "payment-handler"
step_functions:
  checkout-flow:
    source_dir: workflows/checkout
api_gateways:
  main-api:
    source_dir: definitions/api_gateway.yaml
```

### Check Run Markdown Format (Terraform-Plan-Like)
```markdown
### Deployment Plan

**2 resources** will be affected by this change.

---

#### Lambdas

  ~ **order-processor** _(modified)_
    - `services/order-processor/main.py`
    - `services/order-processor/requirements.txt`

  + **notification-sender** _(new)_
    - `services/notification-sender/main.py`
    - `services/notification-sender/requirements.txt`

#### Step Functions

  ~ **checkout-flow** _(modified)_
    - `workflows/checkout/stepfunction.json`

---
_Ferry will deploy these resources when this PR is merged._
```

### Deployment Tag Construction
```python
# From pipelines-hub reference:
# Push to main with PR: "pr-{number}"
# Push to main without PR: "{branch}-{short_sha}"
def build_deployment_tag(pr_number: str, branch: str, sha: str) -> str:
    if pr_number:
        return f"pr-{pr_number}"
    return f"{branch}-{sha[:7]}"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| workflow_dispatch returns 204 (no run ID) | `return_run_details=true` returns 200 with workflow_run_id | Feb 2026 | Can track dispatched runs without polling; ferry can log run URLs |
| workflow_dispatch max 10 inputs | Max 25 inputs | Dec 2025 | More headroom, but Ferry still uses single `payload` input |
| GitHub Checks API (only for Apps) | Still Apps-only | Unchanged | Confirms Ferry App architecture is correct -- PATs can't create Check Runs |

**Deprecated/outdated:**
- The old `workflow_dispatch` response format (204 No Content) is still supported but `return_run_details=true` is strictly better for traceability. Use it.

## Open Questions

1. **ferry.yaml field naming: `source_dir`/`ecr_repo` vs `source`/`ecr`**
   - What we know: CONTEXT.md says required Lambda fields are `name`, `source_dir`, `ecr_repo`. The existing dispatch models (Phase 1) use `source` and `ecr`. The PROJECT.md ferry.yaml example uses `source:` and `ecr:`.
   - What's unclear: Whether the ferry.yaml field names should match the dispatch model (`source`, `ecr`) or use the CONTEXT.md names (`source_dir`, `ecr_repo`).
   - Recommendation: Use CONTEXT.md names in ferry.yaml (they're more descriptive: `source_dir` clearly indicates a directory, `ecr_repo` clearly indicates a repo name). Map to dispatch model names (`source`, `ecr`) at the dispatch boundary. The config models are the user-facing contract; the dispatch models are the internal wire format.

2. **PR number extraction from default branch pushes**
   - What we know: pipelines-hub uses `pr-{number}` as the deployment tag. The push event to the default branch is typically a merge commit, and the PR number needs to be extracted.
   - What's unclear: How reliably the "list PRs for a commit" API returns the merged PR for merge commits on the default branch.
   - Recommendation: Use `GET /repos/{owner}/{repo}/commits/{sha}/pulls` which "lists the merged pull request that introduced the commit to the repository." If no PR found, fall back to `{branch}-{sha[:7]}` tag format.

3. **Config change detection: new resources**
   - What we know: When ferry.yaml adds a new resource, it should be dispatched even though no source files changed (the resource directory may already exist).
   - What's unclear: Whether a new resource in ferry.yaml should always dispatch (even if source_dir has no files yet).
   - Recommendation: Yes, dispatch new resources found in config diff. The source files may already exist from a previous commit. The Action will handle the "empty directory" case.

4. **Compare API for initial commits (before SHA is all zeros)**
   - What we know: The push event's `before` field is `0000000000000000000000000000000000000000` for the first push to a branch (or repo initialization).
   - What's unclear: How Compare API handles a null/zero base SHA.
   - Recommendation: When `before` is all zeros, treat all resources in ferry.yaml as affected (dispatch everything). This is the correct behavior for initial setup.

## Sources

### Primary (HIGH confidence)
- [GitHub Contents API](https://docs.github.com/en/rest/repos/contents) - File content retrieval, ref parameter, base64 encoding, size limits
- [GitHub Compare API](https://docs.github.com/en/rest/commits/commits#compare-two-commits) - Changed file detection, 300-file limit, response format
- [GitHub Checks API](https://docs.github.com/en/rest/checks/runs) - Check Run creation/update, output format, 65535 char limit, Apps-only restriction
- [GitHub Dispatch API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event) - workflow_dispatch triggering, 25 inputs max, 1024 chars per input
- [GitHub Commits API: PRs for commit](https://docs.github.com/en/rest/commits/commits#list-pull-requests-associated-with-a-commit) - Finding PRs associated with a commit SHA

### Secondary (MEDIUM confidence)
- [GitHub Changelog: workflow_dispatch returns run IDs](https://github.blog/changelog/2026-02-19-workflow-dispatch-api-now-returns-run-ids/) - `return_run_details` parameter (Feb 2026)
- [GitHub Community Discussion #120093](https://github.com/orgs/community/discussions/120093) - workflow_dispatch input string length limit (1024 chars)
- [Pydantic Unions documentation](https://docs.pydantic.dev/latest/concepts/unions/) - Discriminated union patterns in v2
- [Digger source code](https://github.com/diggerhq/digger) - Reference architecture patterns for GitHub App + dispatch model

### Tertiary (LOW confidence)
- [GitHub Docs Issue #35252](https://github.com/github/docs/issues/35252) - Check Run output.text limit is 65535 characters (reported in issues, not formally documented in API reference)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in project, no new dependencies needed
- Architecture: HIGH - Patterns directly map from existing Phase 1 code and clear API documentation
- Pitfalls: HIGH - 300-file limit, input size limit, and auth requirements well-documented by community reports
- Config diffing: MEDIUM - The ferry.yaml config diff logic is novel to Ferry (no reference implementation); needs careful testing
- Open questions: MEDIUM - Field naming inconsistency and PR number extraction need decisions during planning

**Research date:** 2026-02-24
**Valid until:** 2026-03-24 (GitHub APIs are stable; 30-day validity appropriate)
