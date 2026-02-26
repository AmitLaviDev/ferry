# Phase 4: Extended Resource Types - Research

**Researched:** 2026-02-26
**Domain:** AWS Step Functions deployment, AWS API Gateway deployment, envsubst-style variable substitution, content-hash skip logic
**Confidence:** HIGH

## Summary

Phase 4 adds two new deploy modules to the Ferry Action: Step Functions and API Gateway. Both follow the same structural patterns established by the Lambda deploy module in Phase 3, but they are fundamentally simpler -- no Docker build or ECR push needed. Step Functions deployment reads a JSON definition file, performs `${ACCOUNT_ID}` and `${AWS_REGION}` variable substitution, and calls `update_state_machine`. API Gateway deployment reads an OpenAPI spec (JSON or YAML), performs the same variable substitution, strips problematic fields (`host`, `schemes`, `basePath`), and calls `put_rest_api` + `create_deployment`.

The content-hash skip logic uses a SHA-256 hash of the substituted (and for APIGW, stripped) content stored as a resource tag (`ferry:content-hash`). This is analogous to Lambda's digest-based skip but uses tags instead of image digests. A critical moto limitation affects testing: API Gateway `tag_resource` and `get_tags` are NOT implemented in moto 5.1.21. Step Functions tagging IS fully supported. The API Gateway tag operations will need to be mocked manually in tests.

**Primary recommendation:** Build two independent deploy modules (`deploy_stepfunctions.py`, `deploy_apigw.py`) that mirror the structure of `deploy.py`, with a shared `envsubst.py` utility for variable substitution. Extract STS account ID resolution into a shared helper to cache across resources. New composite action YAML files (`action/deploy-stepfunctions/action.yml`, `action/deploy-apigw/action.yml`) follow the same pattern as the existing Lambda deploy action.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Configurable filename via `definition_file` field in ferry.yaml (required, no default)
- File lives relative to `source_dir` (e.g., `source_dir: pipelines/foo/definitions`, `definition_file: stepfunction.json`)
- envsubst-style variable substitution: replace `${ACCOUNT_ID}` and `${AWS_REGION}` in the definition
- Only these two variables -- no custom variables or full env passthrough
- JSONPath expressions (`$.path`) are safe because substitution only targets `${}` patterns
- Target state machine identified by `state_machine_name` in ferry.yaml (required, no default)
- Ferry constructs the full ARN via STS GetCallerIdentity after OIDC auth: `arn:aws:states:{region}:{account_id}:stateMachine:{name}`
- Configurable spec file via `spec_file` field in ferry.yaml (required, no default)
- Support both YAML and JSON format -- detect from file extension
- Same envsubst-style substitution: `${ACCOUNT_ID}` and `${AWS_REGION}`
- Strip known problematic OpenAPI fields before put-rest-api: `host`, `schemes`, `basePath`
- Must clearly document which fields are stripped and why in Ferry docs
- Target API Gateway identified by `rest_api_id` in ferry.yaml (required, no default)
- Target stage identified by `stage_name` in ferry.yaml (required, no default)
- Deploy via `put-rest-api` (upload spec) + `create-deployment` (push to stage)
- StepFunctionConfig new required fields: `state_machine_name`, `definition_file`
- ApiGatewayConfig new required fields: `rest_api_id`, `stage_name`, `spec_file`
- All fields required, no defaults -- explicit over magical
- Name-based identification for state machines (ARN resolved at deploy time via STS)
- Content hash comparison: hash the substituted definition/spec content (after envsubst, after field stripping for APIGW)
- Store hash in AWS resource tags: `ferry:content-hash` tag on the Step Function and API Gateway
- Skip deploy if hash matches -- same philosophy as Lambda's digest-based skip
- Log "Skipping deploy for X -- definition unchanged" when skipped
- Same GHA job summary table format as Lambda, with type-specific fields
- Same error hint pattern: catch known AWS errors, add one-liner remediation hints

### Claude's Discretion
- envsubst implementation approach (regex, string replace, or actual envsubst)
- Exact content hashing algorithm (SHA256 likely)
- How to handle the STS call (cache account ID across resources or call per resource)
- Python module organization for the new deploy modules
- Which additional OpenAPI fields (if any) need stripping beyond host/schemes/basePath

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DEPLOY-02 | Ferry Action deploys Step Functions (update state machine definition with variable substitution for account ID and region) | `update_state_machine` API verified in boto3 docs; `tag_resource`/`list_tags_for_resource` supported in moto for content-hash skip; envsubst regex pattern researched |
| DEPLOY-03 | Ferry Action deploys API Gateways (put-rest-api with OpenAPI spec, create-deployment to push to stage) | `put_rest_api` and `create_deployment` APIs verified; moto supports both but NOT `tag_resource`/`get_tags` -- manual mocking needed for tag-based skip tests |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| boto3 | (already in ferry-action) | AWS Step Functions + API Gateway clients | Only AWS SDK for Python; already used for Lambda deploy |
| PyYAML | >=6.0.1 (via ferry-utils) | Parse YAML-format OpenAPI specs | Already a project dependency; needed for APIGW YAML specs |
| hashlib | stdlib | SHA-256 content hashing | Standard library, no additional dependency |
| re | stdlib | envsubst regex for `${VAR}` pattern matching | Standard library, no additional dependency |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| moto | 5.1.21 (installed) | Mock AWS for testing | Step Functions fully mocked; APIGW `put_rest_api` and `create_deployment` mocked; APIGW tags NOT mocked |
| json | stdlib | Parse/serialize JSON definitions and specs | Step Functions definitions are always JSON; APIGW specs may be JSON |
| pydantic | >=2.6 (via ferry-utils) | Updated config models (StepFunctionConfig, ApiGatewayConfig) | New required fields for ferry.yaml schema |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| regex for envsubst | `string.Template` | Template uses `$var` syntax (no braces), doesn't match `${VAR}` pattern; regex is simpler and more precise |
| regex for envsubst | `os.path.expandvars` / shell `envsubst` | Requires setting env vars, risk of leaking other env content; regex with a fixed dict is safer |
| regex for envsubst | `python-envsubst` PyPI package | Extra dependency for ~5 lines of code; not worth it |

**No new dependencies needed.** All required libraries are already in the project.

## Architecture Patterns

### Recommended Module Structure
```
action/
  deploy-stepfunctions/
    action.yml              # New composite action for SF deploy
  deploy-apigw/
    action.yml              # New composite action for APIGW deploy
  src/ferry_action/
    deploy.py               # (existing) Lambda deploy
    deploy_stepfunctions.py # NEW: Step Functions deploy
    deploy_apigw.py         # NEW: API Gateway deploy
    envsubst.py             # NEW: Shared variable substitution
    gha.py                  # (existing) GHA helpers
    parse_payload.py        # (existing) Payload parser -- extend for SF/APIGW

backend/src/ferry_backend/config/
  schema.py                 # MODIFY: Add fields to StepFunctionConfig, ApiGatewayConfig

tests/test_action/
  test_deploy.py            # (existing)
  test_deploy_stepfunctions.py  # NEW
  test_deploy_apigw.py          # NEW
  test_envsubst.py              # NEW
```

### Pattern 1: envsubst via Regex
**What:** Replace `${ACCOUNT_ID}` and `${AWS_REGION}` in a string using regex, leaving all other content untouched.
**When to use:** All definition/spec file processing before deployment.
**Recommendation:** Use `re.sub` with a strict pattern.

```python
import re

# Only matches ${ACCOUNT_ID} and ${AWS_REGION} -- nothing else
_ENVSUBST_PATTERN = re.compile(r"\$\{(ACCOUNT_ID|AWS_REGION)\}")

def envsubst(content: str, account_id: str, region: str) -> str:
    """Replace ${ACCOUNT_ID} and ${AWS_REGION} in content.

    Only these two variables are substituted. All other content
    (including JSONPath expressions like $.path) is left untouched.
    """
    replacements = {"ACCOUNT_ID": account_id, "AWS_REGION": region}
    return _ENVSUBST_PATTERN.sub(lambda m: replacements[m.group(1)], content)
```

**Why this is safe for JSONPath:** JSONPath uses `$.path` syntax (dollar-dot). The regex only matches `${...}` (dollar-brace). These patterns never overlap, so JSONPath expressions are never corrupted.

### Pattern 2: Content-Hash Skip Logic
**What:** Hash the post-substitution content with SHA-256, compare against a tag on the AWS resource, skip deploy if identical.
**When to use:** Before every SF/APIGW deploy.

```python
import hashlib

def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content for change detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def get_content_hash_tag(tags: list[dict]) -> str | None:
    """Extract ferry:content-hash from a list of AWS tags."""
    for tag in tags:
        if tag.get("key") == "ferry:content-hash" or tag.get("Key") == "ferry:content-hash":
            return tag.get("value") or tag.get("Value")
    return None
```

Note: Step Functions tags use `{"key": "...", "value": "..."}` format. API Gateway tags use `{"string": "string"}` dict format. The helper must handle both.

### Pattern 3: Deploy Module Structure (Consistent with Lambda)
**What:** Each deploy module follows the same pattern: `main()` reads env vars, gets client, checks skip, deploys, writes outputs + summary.
**When to use:** All deploy modules.

Each deploy module should have:
1. A skip-check function (content hash comparison)
2. A core deploy function (the AWS API calls)
3. A `main()` orchestrator (reads env, calls skip/deploy, writes GHA outputs)
4. Error handling with hint dict for common AWS errors

### Pattern 4: OpenAPI Field Stripping for APIGW
**What:** Remove fields that cause `put_rest_api` to fail or behave unexpectedly.
**When to use:** Before uploading OpenAPI spec to API Gateway.

```python
def strip_openapi_fields(spec: dict) -> dict:
    """Remove fields that conflict with put_rest_api.

    Strips:
    - host: API Gateway manages the host/endpoint
    - schemes: API Gateway manages HTTPS
    - basePath: API Gateway uses stage-level path mapping

    These fields are AWS-managed and will cause conflicts or
    unexpected behavior if included in the spec upload.
    """
    stripped = dict(spec)  # shallow copy
    for field in ("host", "schemes", "basePath"):
        stripped.pop(field, None)
    return stripped
```

**Additional fields to consider stripping:** Based on research, the three specified fields (`host`, `schemes`, `basePath`) are the standard ones that cause issues. The `servers` field in OpenAPI 3.x is the equivalent of `host`+`schemes`+`basePath` from Swagger 2.0. Recommendation: also strip `servers` if present (OpenAPI 3.x support), as API Gateway manages this via stages. This is a Claude's Discretion item.

### Pattern 5: STS Account ID Caching
**What:** Call STS `GetCallerIdentity` once and reuse the account ID across resources.
**When to use:** In `main()` of each deploy module. Since each module runs as a separate process (one per composite action invocation) and each invocation handles one resource at a time (matrix fan-out), caching across resources is not applicable. Each invocation gets its own STS call, which is fine.

**Recommendation:** Call STS once at the top of `main()`, same as `build.py` does. No cross-process caching needed.

### Anti-Patterns to Avoid
- **Do NOT use `os.environ` for envsubst variables:** The decision explicitly says no full env passthrough. Use a fixed dict with only ACCOUNT_ID and AWS_REGION.
- **Do NOT parse JSONPath or ASL definitions:** Just do string-level regex substitution. Parsing the definition as structured data is unnecessary and risky.
- **Do NOT use `mode='overwrite'` with `put_rest_api` by default:** Overwrite deletes all existing resources not in the spec. Use `mode='overwrite'` as the decision specifies uploading the full spec, but document the implications. Actually, `merge` is safer as a default; re-evaluate based on the pipelines-hub reference which uses the default merge mode.
- **Do NOT share boto3 clients across resource types:** Each deploy module creates its own client. This matches the existing pattern.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Variable substitution | Custom parser | `re.sub` with strict `${VAR}` pattern | 5 lines of regex vs. complex parser; proven safe with JSONPath |
| SHA-256 hashing | Custom hash | `hashlib.sha256` | Standard library, reliable |
| YAML parsing | Custom parser | `yaml.safe_load` (PyYAML) | Already a dependency; handles all YAML edge cases |
| JSON serialization for hash | Custom serialization | `json.dumps(obj, sort_keys=True, separators=(',',':'))` | Deterministic output for consistent hashing |
| AWS error classification | Complex error tree | Simple dict mapping error codes to hints | Matches Lambda deploy pattern exactly |

**Key insight:** The new deploy modules are simpler than Lambda deploy (no Docker, no ECR, no waiter). The primary complexity is in the envsubst + field stripping pipeline, which is well-understood string processing.

## Common Pitfalls

### Pitfall 1: Non-Deterministic Content Hashing
**What goes wrong:** The content hash differs between runs even though the definition hasn't changed, causing unnecessary deploys.
**Why it happens:** YAML parsing + JSON re-serialization can produce different key ordering. Dict ordering varies.
**How to avoid:** For JSON input, hash the raw file content after envsubst (don't parse and re-serialize). For YAML input (APIGW only), parse to dict, strip fields, then serialize with `json.dumps(sort_keys=True, separators=(',',':'))` for a canonical form before hashing.
**Warning signs:** Every deploy shows "definition changed" even when no source files were modified.

### Pitfall 2: put_rest_api Body Must Be Bytes
**What goes wrong:** `put_rest_api` receives a string instead of bytes and fails.
**Why it happens:** The `body` parameter requires `bytes` or a file-like object, not a string.
**How to avoid:** Always `.encode("utf-8")` the serialized spec before passing to `put_rest_api`.
**Warning signs:** `TypeError` or `SerializationError` from botocore.

### Pitfall 3: API Gateway Tagging ARN Format
**What goes wrong:** `tag_resource` fails with `NotFoundException` because the ARN format is wrong.
**Why it happens:** API Gateway ARNs have an unusual format with empty account ID: `arn:aws:apigateway:{region}::/restapis/{id}`.
**How to avoid:** Use the correct format: `arn:aws:apigateway:{region}::/restapis/{rest_api_id}`. Note the double colon (`::`) for the empty account ID field.
**Warning signs:** `NotFoundException` when calling `tag_resource` even though the API exists.

### Pitfall 4: Step Functions ARN Construction
**What goes wrong:** `update_state_machine` fails with `StateMachineDoesNotExist` because the ARN is wrong.
**Why it happens:** Region or account ID mismatch, or incorrect ARN format.
**How to avoid:** Construct ARN strictly as `arn:aws:states:{region}:{account_id}:stateMachine:{name}`. Get region from `AWS_REGION` env var (set by `configure-aws-credentials`). Get account_id from STS.
**Warning signs:** `InvalidArn` or `StateMachineDoesNotExist` errors.

### Pitfall 5: Moto Does Not Support API Gateway Tags
**What goes wrong:** Tests using `tag_resource` / `get_tags` on API Gateway fail with `NotImplementedError`.
**Why it happens:** Moto 5.1.21 has not implemented these operations for API Gateway (39 operations remain unimplemented).
**How to avoid:** Mock `tag_resource` and `get_tags` manually using `unittest.mock.patch` for API Gateway tag tests. Step Functions tags work fine with moto.
**Warning signs:** `NotImplementedError` in tests.

### Pitfall 6: OpenAPI 3.x vs Swagger 2.0 Field Differences
**What goes wrong:** Stripping `host`/`schemes`/`basePath` doesn't help because the spec uses OpenAPI 3.x which has `servers` instead.
**Why it happens:** OpenAPI 3.x replaced `host`, `schemes`, and `basePath` with a single `servers` array.
**How to avoid:** Strip both Swagger 2.0 fields (`host`, `schemes`, `basePath`) AND OpenAPI 3.x fields (`servers`). Check the `openapi` or `swagger` key in the spec to determine version if needed (but stripping all of them unconditionally is safe).
**Warning signs:** `put_rest_api` returns warnings about server configuration conflicts.

### Pitfall 7: update_state_machine Requires At Least One Modifiable Field
**What goes wrong:** `update_state_machine` fails with `MissingRequiredParameter` when called with only the ARN.
**Why it happens:** The API requires at least one of `definition` or `roleArn`.
**How to avoid:** Always pass the `definition` parameter. We always have the definition content to deploy.
**Warning signs:** `MissingRequiredParameter` error.

## Code Examples

### Step Functions Deploy Sequence
```python
# Source: verified against boto3 docs
# https://docs.aws.amazon.com/boto3/latest/reference/services/stepfunctions/client/update_state_machine.html

import boto3

sfn_client = boto3.client("stepfunctions")

# 1. Construct ARN from name + STS identity
sts = boto3.client("sts")
identity = sts.get_caller_identity()
account_id = identity["Account"]
region = "us-east-1"  # from AWS_REGION env var
state_machine_arn = f"arn:aws:states:{region}:{account_id}:stateMachine:{state_machine_name}"

# 2. Read and substitute definition
definition = Path(source_dir, definition_file).read_text()
definition = envsubst(definition, account_id, region)

# 3. Check content hash for skip
current_tags = sfn_client.list_tags_for_resource(resourceArn=state_machine_arn)["tags"]
current_hash = get_content_hash_tag(current_tags)
new_hash = compute_content_hash(definition)
if current_hash == new_hash:
    print(f"Skipping deploy for {name} -- definition unchanged")
    return

# 4. Update state machine with publish
response = sfn_client.update_state_machine(
    stateMachineArn=state_machine_arn,
    definition=definition,
    publish=True,
    versionDescription=f"Deployed by Ferry: {deployment_tag}",
)
version_arn = response.get("stateMachineVersionArn", "")

# 5. Update content hash tag
sfn_client.tag_resource(
    resourceArn=state_machine_arn,
    tags=[{"key": "ferry:content-hash", "value": new_hash}],
)
```

**Note on moto:** `publish_state_machine_version` is NOT implemented in moto, but `update_state_machine` with `publish=True` IS supported and returns `stateMachineVersionArn`. However, moto may return an empty string for this field. Tests should verify the update call was made correctly rather than asserting on the version ARN value.

### API Gateway Deploy Sequence
```python
# Source: verified against boto3 docs
# https://docs.aws.amazon.com/boto3/latest/reference/services/apigateway/client/put_rest_api.html
# https://docs.aws.amazon.com/boto3/latest/reference/services/apigateway/client/create_deployment.html

import json
import yaml
import boto3

apigw_client = boto3.client("apigateway")

# 1. Read spec file (detect format from extension)
spec_path = Path(source_dir, spec_file)
raw_content = spec_path.read_text()
if spec_path.suffix in (".yaml", ".yml"):
    spec_dict = yaml.safe_load(raw_content)
else:
    spec_dict = json.loads(raw_content)

# 2. Substitute variables
# For YAML: substitute in raw text, then parse
# For JSON: substitute in raw text, then parse
# (substitute before parsing to handle vars in any field)
substituted_content = envsubst(raw_content, account_id, region)
if spec_path.suffix in (".yaml", ".yml"):
    spec_dict = yaml.safe_load(substituted_content)
else:
    spec_dict = json.loads(substituted_content)

# 3. Strip problematic fields
spec_dict = strip_openapi_fields(spec_dict)

# 4. Serialize to canonical JSON for hashing and upload
canonical = json.dumps(spec_dict, sort_keys=True, separators=(",", ":"))
new_hash = compute_content_hash(canonical)

# 5. Check content hash (tag on the REST API resource)
# ARN format: arn:aws:apigateway:{region}::/restapis/{rest_api_id}
rest_api_arn = f"arn:aws:apigateway:{region}::/restapis/{rest_api_id}"
current_tags = apigw_client.get_tags(resourceArn=rest_api_arn)["tags"]
current_hash = current_tags.get("ferry:content-hash")
if current_hash == new_hash:
    print(f"Skipping deploy for {name} -- spec unchanged")
    return

# 6. Upload spec
apigw_client.put_rest_api(
    restApiId=rest_api_id,
    mode="overwrite",
    failOnWarnings=False,
    body=canonical.encode("utf-8"),
)

# 7. Create deployment to push changes to stage
deploy_response = apigw_client.create_deployment(
    restApiId=rest_api_id,
    stageName=stage_name,
    description=f"Deployed by Ferry: {deployment_tag}",
)
deployment_id = deploy_response["id"]

# 8. Update content hash tag
apigw_client.tag_resource(
    resourceArn=rest_api_arn,
    tags={"ferry:content-hash": new_hash},
)
```

### envsubst Implementation
```python
import re

_ENVSUBST_PATTERN = re.compile(r"\$\{(ACCOUNT_ID|AWS_REGION)\}")

def envsubst(content: str, account_id: str, region: str) -> str:
    """Replace ${ACCOUNT_ID} and ${AWS_REGION} in content.

    Only these two variables are substituted. JSONPath expressions
    ($.path) and other dollar-prefixed content are left untouched
    because this regex only matches ${...} patterns with known variable names.
    """
    replacements = {"ACCOUNT_ID": account_id, "AWS_REGION": region}
    return _ENVSUBST_PATTERN.sub(lambda m: replacements[m.group(1)], content)
```

### Updated ferry.yaml Config Models
```python
# Addition to backend/src/ferry_backend/config/schema.py

class StepFunctionConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source_dir: str
    state_machine_name: str   # NEW: required
    definition_file: str      # NEW: required

class ApiGatewayConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source_dir: str
    rest_api_id: str          # NEW: required
    stage_name: str           # NEW: required
    spec_file: str            # NEW: required
```

### Updated parse_payload.py Pattern
```python
# The parse_payload.py currently only handles Lambda resources.
# For SF/APIGW, the setup action needs to output different matrix fields.
# Option A: Extend parse_payload to handle all types (detect from payload.resource_type)
# Option B: Create separate parse scripts per type
#
# Recommendation: Option A -- extend parse_payload.py to detect resource_type
# and output type-appropriate matrix fields.

def build_matrix(payload_str: str) -> dict:
    payload = DispatchPayload.model_validate_json(payload_str)

    if payload.resource_type == "lambda":
        # existing lambda matrix logic
        ...
    elif payload.resource_type == "step_function":
        include = [
            {
                "name": r.name,
                "source": r.source,
                "trigger_sha": payload.trigger_sha,
                "deployment_tag": payload.deployment_tag,
            }
            for r in payload.resources
            if isinstance(r, StepFunctionResource)
        ]
    elif payload.resource_type == "api_gateway":
        include = [
            {
                "name": r.name,
                "source": r.source,
                "trigger_sha": payload.trigger_sha,
                "deployment_tag": payload.deployment_tag,
            }
            for r in payload.resources
            if isinstance(r, ApiGatewayResource)
        ]

    return {"include": include}
```

**Important:** The matrix for SF/APIGW does NOT include `ecr` or `runtime` fields (those are Lambda-specific). The deploy actions will read `definition_file`, `state_machine_name`, `rest_api_id`, `stage_name`, `spec_file` from ferry.yaml config (fetched via the dispatch payload's resource name lookup, or passed through the matrix). However, the current dispatch payload for SF/APIGW only carries `name` and `source`. The type-specific config fields (`state_machine_name`, `definition_file`, etc.) are NOT in the dispatch payload. Two approaches:

1. **Add config fields to dispatch payload models** -- Extend `StepFunctionResource` and `ApiGatewayResource` to include the deploy-specific fields
2. **Read ferry.yaml in the action** -- Have the action fetch ferry.yaml from the repo and look up config by resource name

Recommendation: **Approach 1** -- Add fields to the dispatch models. This is consistent with how Lambda already works (LambdaResource carries `ecr` from config). The dispatch payload should carry everything the action needs. The backend already does the config lookup in `_build_resource()` in `trigger.py`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Shell `envsubst` command | Python `re.sub` with fixed variable set | Always applicable | No shell dependency, explicit variable control, safer |
| Import REST API via console | `put_rest_api` programmatic upload | AWS API available since 2015 | Fully automatable |
| Step Functions versioning via manual snapshots | `publish=True` in `update_state_machine` | December 2023 | Immutable versions + aliases (similar to Lambda) |

**Deprecated/outdated:**
- Step Functions `publish_state_machine_version` as a separate call: Can use `publish=True` directly in `update_state_machine` instead (simpler, atomic)
- Swagger 2.0 exclusively: API Gateway now supports OpenAPI 3.x -- strip `servers` field in addition to Swagger 2.0 fields

## Open Questions

1. **put_rest_api mode: 'merge' vs 'overwrite'**
   - What we know: `merge` keeps existing resources not in the spec; `overwrite` replaces everything. The pipelines-hub reference repo appears to use the default (merge).
   - What's unclear: Whether user specs are always complete (overwrite-safe) or incremental (merge-needed).
   - Recommendation: Use `overwrite` mode. Ferry's philosophy is "what you see is what you get" -- the spec file should be the complete source of truth. Document this clearly.

2. **moto support for `update_state_machine` with `publish=True`**
   - What we know: `update_state_machine` is implemented in moto. `publish_state_machine_version` is NOT.
   - What's unclear: Whether moto returns a meaningful `stateMachineVersionArn` when `publish=True` is passed to `update_state_machine`.
   - Recommendation: Test this during implementation. If moto ignores the `publish` parameter, assert on the update call parameters rather than the version ARN response. The version ARN is a nice-to-have for the summary, not a deploy-critical value.

3. **OpenAPI 3.x `servers` field stripping**
   - What we know: `host`, `schemes`, `basePath` are Swagger 2.0 fields. OpenAPI 3.x uses `servers` instead.
   - What's unclear: Whether API Gateway handles `servers` gracefully or if it causes issues.
   - Recommendation: Strip `servers` in addition to the Swagger 2.0 fields. It's a safe default -- API Gateway manages endpoints via stages. This falls under Claude's Discretion.

## Sources

### Primary (HIGH confidence)
- [boto3 Step Functions update_state_machine](https://docs.aws.amazon.com/boto3/latest/reference/services/stepfunctions/client/update_state_machine.html) - Full API parameters, return type, exceptions verified
- [boto3 Step Functions describe_state_machine](https://docs.aws.amazon.com/boto3/latest/reference/services/stepfunctions/client/describe_state_machine.html) - Return structure with definition field
- [boto3 Step Functions tag_resource](https://docs.aws.amazon.com/boto3/latest/reference/services/stepfunctions/client/tag_resource.html) - Tag format: `[{"key": "...", "value": "..."}]`
- [boto3 Step Functions list_tags_for_resource](https://docs.aws.amazon.com/boto3/latest/reference/services/stepfunctions/client/list_tags_for_resource.html) - Returns tags array
- [boto3 API Gateway put_rest_api](https://docs.aws.amazon.com/boto3/latest/reference/services/apigateway/client/put_rest_api.html) - Body must be bytes, mode merge/overwrite, max 6MB
- [boto3 API Gateway create_deployment](https://docs.aws.amazon.com/boto3/latest/reference/services/apigateway/client/create_deployment.html) - stageName, description parameters
- [boto3 API Gateway tag_resource](https://docs.aws.amazon.com/boto3/latest/reference/services/apigateway/client/tag_resource.html) - Tags are `{"string": "string"}` dict format
- [boto3 API Gateway get_tags](https://docs.aws.amazon.com/boto3/latest/reference/services/apigateway/client/get_tags.html) - Returns `{"tags": {"key": "value"}}` dict
- [Moto Step Functions implementation status](https://docs.getmoto.org/en/latest/docs/services/stepfunctions.html) - update_state_machine, tag_resource, list_tags_for_resource all implemented
- [Moto API Gateway implementation status](https://docs.getmoto.org/en/latest/docs/services/apigateway.html) - put_rest_api and create_deployment implemented; tag_resource and get_tags NOT implemented
- [AWS API Gateway ARN format](https://docs.aws.amazon.com/apigateway/latest/developerguide/arn-format-reference.html) - `arn:aws:apigateway:{region}::/restapis/{id}` (empty account ID)

### Secondary (MEDIUM confidence)
- Existing project code: `deploy.py`, `build.py`, `gha.py`, `trigger.py` patterns verified by reading source
- pipelines-hub-analysis.md in project memory -- reference implementation patterns for envsubst and field stripping

### Tertiary (LOW confidence)
- moto behavior for `publish=True` in `update_state_machine` -- needs empirical validation during implementation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in project, APIs verified against official docs
- Architecture: HIGH - Follows established patterns from Phase 3 Lambda deploy; clear parallel structure
- Pitfalls: HIGH - API differences verified against official docs; moto limitations confirmed against moto's own documentation
- Testing: MEDIUM - Step Functions testing straightforward with moto; API Gateway tag testing requires manual mocking (confirmed limitation)

**Research date:** 2026-02-26
**Valid until:** 2026-03-26 (stable -- AWS APIs and moto coverage unlikely to change in 30 days)
