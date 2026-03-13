---
phase: 34-workflow-template-and-github-environments
plan: 01
status: complete
completed: 2026-03-13
---

# Plan 34-01 Summary: Workflow Template and GitHub Environments

## What was done

Updated `docs/setup.md` with the v2.0 workflow template and supporting documentation:

1. **ferry.yaml example**: Added `environments:` section showing branch-to-environment mapping (staging/production)
2. **Environments docs**: New section explaining `branch`, `auto_deploy` fields and GitHub Environment setup
3. **v2.0 workflow template**: Updated with:
   - `run-name` includes environment with arrow notation (e.g., "Ferry Deploy: lambda → staging")
   - Setup job outputs `mode` and `environment`
   - All deploy jobs have `environment: ${{ needs.setup.outputs.environment }}`
   - All deploy jobs have `mode == 'deploy'` guard in `if:` conditions
4. **Migration from v1.x**: Replaced per-type dispatch migration note with v1.x → v2.0 migration guide
5. **Webhook events checklist**: New section documenting required GitHub App webhook subscriptions (push, pull_request, issue_comment, workflow_run)

## Requirements satisfied

- **GHENV-01**: Deploy jobs use `environment:` key for GHA native secret injection
- **GHENV-02**: Automatic from GHENV-01 — GHA injects environment-level secrets when environment is set
- **COMPAT-03**: Documentation includes updated workflow template, webhook events checklist, and migration notes

## Files modified

- `docs/setup.md` (only file changed — docs-only update)
