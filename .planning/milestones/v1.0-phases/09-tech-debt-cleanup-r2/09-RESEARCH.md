# Phase 9: Tech Debt Cleanup (Round 2) - Research

**Researched:** 2026-02-28
**Domain:** Dependency hygiene, docstring accuracy, dead export cleanup
**Confidence:** HIGH

## Summary

Phase 9 resolves five low-severity tech debt items identified by the second milestone audit (v1.0-MILESTONE-AUDIT.md). All five are localized, mechanical fixes with no architectural implications -- docstring updates, dependency moves, dead export removal, and extras declarations.

Every item is fully understood from codebase inspection. No external library research or API documentation is needed. The fixes touch pyproject.toml files (dependency declarations), Python `__init__.py` files (exports), and one docstring in parse_payload.py.

**Primary recommendation:** Execute all five fixes in a single plan. Each is a 1-3 line change with clear success criteria. No new libraries, no new patterns, no risk of regression.

## Standard Stack

Not applicable -- this phase introduces no new libraries. It removes, moves, or corrects existing dependency declarations.

### Dependency Changes Summary

| Change | From | To | Rationale |
|--------|------|----|-----------|
| Remove `tenacity>=8.3` | `backend/pyproject.toml` | Nowhere (phantom) | Never imported in any backend source file |
| Move `PyYAML>=6.0.1` | `utils/pyproject.toml` | `backend/pyproject.toml` | YAML parsing happens in `backend/src/ferry_backend/config/loader.py`, not in `utils/` |
| Add `stepfunctions` to moto extras | `pyproject.toml` (root) | `moto[dynamodb,apigateway,stepfunctions]>=5.0` | Tests in `test_deploy_stepfunctions.py` use `mock_aws()` with sfn clients |

**Key detail on PyYAML:** The `action/pyproject.toml` already has `pyyaml>=6.0` for `deploy_apigw.py`. The move is specifically from `utils/` to `backend/`. The `utils/` package has zero YAML imports.

## Architecture Patterns

### Pattern 1: Correct Dependency Placement

**What:** Each workspace member declares only the dependencies it directly imports.

**Current violations:**
- `utils/pyproject.toml` declares `PyYAML>=6.0.1` but no file in `utils/src/` imports `yaml`
- `backend/pyproject.toml` declares `tenacity>=8.3` but no file in `backend/src/` imports `tenacity`
- `backend/pyproject.toml` does NOT declare `PyYAML` but `backend/src/ferry_backend/config/loader.py` does `import yaml`

**Fix:** Move PyYAML to backend, remove tenacity from backend. Each package's dependencies should match its actual imports.

### Pattern 2: Export Hygiene

**What:** Public `__all__` exports should contain only symbols consumed by downstream code.

**Current state:**
- `PushEvent` and `WebhookHeaders` are defined in `utils/src/ferry_utils/models/webhook.py`
- Re-exported in `utils/src/ferry_utils/models/__init__.py` and `utils/src/ferry_utils/__init__.py`
- `PushEvent` appears in `__all__` in both `__init__.py` files
- `WebhookHeaders` appears in `__all__` in both `__init__.py` files
- **Neither is imported in any production code** (`backend/src/` or `action/src/`)
- The webhook handler (`backend/src/ferry_backend/webhook/handler.py`) parses raw dicts directly -- it never constructs `PushEvent` or `WebhookHeaders` models

**Decision required:** Remove from exports (and optionally from the module itself), or keep the models but remove from `__all__`. The success criteria says "either consumed in production code or removed from exports."

**Recommendation:** Remove from `__all__` and from the re-export imports in both `__init__.py` files. Keep the model definitions in `webhook.py` and the test file -- the models are well-tested and could be useful for v2 typed webhook parsing. Removing them from exports signals "internal/unused" without destroying code.

### Anti-Patterns to Avoid

- **Transitive dependency reliance:** Backend currently gets PyYAML only because it depends on `ferry-utils` which declares it. If `utils` drops PyYAML (which this phase does), backend would break without adding it directly. The fix must be atomic: add to backend AND remove from utils in the same commit.
- **Removing model source files:** The `webhook.py` models and their tests are valid code. Only the re-exports need cleanup. Don't delete `webhook.py` or `test_webhook_models.py`.

## Don't Hand-Roll

Not applicable -- all changes are configuration/declaration edits, not code logic.

## Common Pitfalls

### Pitfall 1: Non-Atomic PyYAML Move

**What goes wrong:** If PyYAML is removed from `utils/pyproject.toml` but not added to `backend/pyproject.toml` (or vice versa), `uv sync` will fail or `import yaml` will break at runtime.
**Why it happens:** Editing two files in sequence without testing between.
**How to avoid:** Make both edits, then run `uv sync --all-packages && python -c "from ferry_backend.config.loader import parse_config"` to verify.
**Warning signs:** `ModuleNotFoundError: No module named 'yaml'` in tests.

### Pitfall 2: Breaking Test Imports

**What goes wrong:** `test_webhook_models.py` imports `from ferry_utils.models.webhook import PushEvent, WebhookHeaders` directly (not via `__init__.py`). This import is safe even after removing from `__all__`. But if someone imports via `from ferry_utils import PushEvent`, that would break.
**How to avoid:** Only remove from `__init__.py` re-exports and `__all__`. Don't touch `webhook.py` itself.
**Warning signs:** Grep for `from ferry_utils import.*PushEvent` and `from ferry_utils import.*WebhookHeaders` to confirm no production imports exist (already verified: none exist).

### Pitfall 3: Moto Extras and Lock File

**What goes wrong:** Adding `stepfunctions` to moto extras in `pyproject.toml` requires a `uv lock` / `uv sync` to actually install the extra. If the lock file isn't regenerated, CI may not have the stepfunctions mock support.
**How to avoid:** Run `uv lock && uv sync --all-packages` after editing.
**Warning signs:** `NotImplementedError` from moto when creating step functions in tests (though moto 5.x may include stepfunctions in base install -- the extras declaration is still correct for explicitness).

## Code Examples

### Fix 1: build_matrix Docstring Update

Current state in `action/src/ferry_action/parse_payload.py` (line 99):
```python
        - **lambda**: name, source, ecr, function_name, trigger_sha, deployment_tag, runtime
```

This line already includes `function_name`. Checking the success criteria: "build_matrix docstring in parse_payload.py includes function_name in the lambda field list." **This appears to already be satisfied.** The docstring at line 99 lists: `name, source, ecr, function_name, trigger_sha, deployment_tag, runtime`.

The audit note referenced the state at Phase 6 verification time. Phase 7 (07-03) may have already fixed this. Need to verify during planning whether this is already done.

### Fix 2: Remove PushEvent/WebhookHeaders from Exports

In `utils/src/ferry_utils/__init__.py`:
```python
# Remove these lines:
from ferry_utils.models.webhook import PushEvent, WebhookHeaders

# Remove from __all__:
"PushEvent",
"WebhookHeaders",
```

In `utils/src/ferry_utils/models/__init__.py`:
```python
# Remove from imports:
from ferry_utils.models.webhook import (
    PushEvent,
    WebhookHeaders,
)

# Remove from __all__:
"PushEvent",
"WebhookHeaders",
```

Keep `Pusher` and `Repository` only if they're consumed elsewhere (need to verify -- they may also be unused).

### Fix 3: Remove tenacity from backend

In `backend/pyproject.toml`:
```toml
# Remove this line:
    "tenacity>=8.3",
```

### Fix 4: Move PyYAML from utils to backend

In `utils/pyproject.toml`:
```toml
# Remove:
    "PyYAML>=6.0.1",
```

In `backend/pyproject.toml`:
```toml
# Add:
    "PyYAML>=6.0.1",
```

### Fix 5: Add stepfunctions to moto extras

In root `pyproject.toml`:
```toml
# Change:
    "moto[dynamodb,apigateway]>=5.0",
# To:
    "moto[dynamodb,apigateway,stepfunctions]>=5.0",
```

## State of the Art

Not applicable -- no library version changes or new technology adoption.

## Open Questions

1. **Is the build_matrix docstring already fixed?**
   - What we know: The current docstring at line 99 of `parse_payload.py` reads `name, source, ecr, function_name, trigger_sha, deployment_tag, runtime` which DOES include `function_name`.
   - What's unclear: Whether the audit noted a stale state that was subsequently fixed by Phase 7's docstring cleanup (07-03).
   - Recommendation: Verify during planning. If already correct, mark as pre-satisfied and skip.

2. **Should Pusher and Repository also be cleaned from exports?**
   - What we know: `Pusher` and `Repository` are in `__all__` in both init files, similar to `PushEvent`/`WebhookHeaders`.
   - What's unclear: Whether they're consumed in production code (quick grep shows they aren't).
   - Recommendation: The success criteria only mentions `PushEvent` and `WebhookHeaders`. Clean only what's specified. If `Pusher`/`Repository` are also unused, note it but don't scope-creep.

3. **Should webhook.py itself be removed?**
   - What we know: None of its models are used in production. Tests exist (`test_webhook_models.py`).
   - Recommendation: No. The success criteria says "removed from exports" not "removed from codebase." Keep the models and tests for potential v2 use.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection of all affected files
- `action/src/ferry_action/parse_payload.py` -- current docstring verified
- `utils/src/ferry_utils/__init__.py` -- current exports verified
- `utils/src/ferry_utils/models/__init__.py` -- current exports verified
- `backend/pyproject.toml` -- current dependencies verified
- `utils/pyproject.toml` -- current dependencies verified
- `pyproject.toml` (root) -- current moto extras verified
- `backend/src/ferry_backend/webhook/handler.py` -- confirmed no PushEvent/WebhookHeaders usage
- `backend/src/ferry_backend/config/loader.py` -- confirmed `import yaml` usage
- Grep results confirming no `import tenacity` or `from tenacity` in any `.py` file
- `.planning/v1.0-MILESTONE-AUDIT.md` -- source of all tech debt items

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new libraries; all changes are edits to existing declarations
- Architecture: HIGH - No architectural changes; all fixes are localized
- Pitfalls: HIGH - Only risk is non-atomic PyYAML move, well understood

**Research date:** 2026-02-28
**Valid until:** Indefinite (tech debt items are stable facts about current codebase state)
