# Phase 2: App Core Logic - Context

**Gathered:** 2026-02-23
**Status:** Ready for planning

<domain>
## Phase Boundary

When a developer pushes code, Ferry App reads the repo configuration (ferry.yaml), identifies which serverless resources changed, triggers the correct workflow_dispatch events (one per resource type), and shows affected resources on the PR via a Check Run before merge. This phase covers: CONF-01, CONF-02, DETECT-01, DETECT-02, ORCH-01, ORCH-02.

Dispatches fire only on default branch pushes. PR pushes get preview Check Runs only. Comment-triggered deploys ("ferry deploy") are deferred to a future phase.

</domain>

<decisions>
## Implementation Decisions

### ferry.yaml Schema & Validation
- **Fail-fast validation**: Any validation error in ferry.yaml (missing required field, unknown type, malformed YAML) fails the entire push — nothing gets dispatched. Post a failed Check Run with the specific validation error.
- **Required Lambda fields**: Only `name`, `source_dir`, `ecr_repo`. Everything else is optional.
- **Default runtime**: `python3.10` when runtime is not specified in ferry.yaml.
- **Function name mapping**: Optional `function_name` field per resource that defaults to `name`. Allows AWS Lambda function name to differ from the Ferry resource name.
- **Resource types**: `lambdas`, `step_functions`, `api_gateways` as top-level sections (already decided).
- **No defaults block**: Explicit — what you see is what you get (already decided).

### Change Detection
- **source_dir only**: Only files under a resource's `source_dir` trigger that resource. No additional watch paths or shared dependency tracking in v1.
- **ferry.yaml config diffing**: When ferry.yaml itself changes, compare old vs new config — only dispatch resources whose config entry actually changed (not all resources).
- **GitHub Compare API**: Use the Compare API (base...head) for change detection. One API call, reliable diff.
- **Branch behavior**: Default branch pushes trigger dispatches (actual deploys). PR branch pushes trigger Check Runs only (preview, no deploy).

### Dispatch (Locked from Architecture)
- One `workflow_dispatch` per affected resource **type** (not per resource, not monolithic).
- Pydantic payload: resource type, resource list, trigger SHA, deployment tag, PR number.
- These decisions were locked during architecture and are not revisited here.

### PR Check Run Display
- **Check Run name**: "Ferry: Deployment Plan"
- **Content**: Summary line per resource (type + change indicator: `~` modified, `+` new) with changed file list below each. Terraform-plan-like output.
- **No changes**: Always post the Check Run, even when no resources are affected. Body says "No resources affected by this change." — keeps Ferry visible.
- **Timing**: Every push to a branch with an open PR triggers a Check Run update. Always current.

### Claude's Discretion
- Exact Check Run markdown formatting and layout
- Error message wording for validation failures
- Compare API pagination handling for large diffs
- How to detect if a branch has an open PR

</decisions>

<specifics>
## Specific Ideas

- Check Run should feel like Terraform plan output: clear before/after indicators showing what will happen if merged
- The `~` (modified) and `+` (new resource) notation from Terraform plans
- Summary line per resource at top, expandable file details below — like GitHub's own diff summary

</specifics>

<deferred>
## Deferred Ideas

- **"ferry deploy" comment trigger**: Digger-style PR comment command that triggers deployment from a feature branch for pre-merge testing in dev/staging. Requires handling `issue_comment` webhooks, branch-aware deployment, and potentially environment mapping. Should be its own phase (possibly Phase 2.1 or later).
- **Deployed-state-aware diff**: Show current deployed version vs proposed version in Check Run (requires AWS access from Ferry App, which is currently out of scope — Ferry App only has Git context).

</deferred>

---

*Phase: 02-app-core-logic*
*Context gathered: 2026-02-23*
