# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-28)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** v1.1 Deploy to Staging — Phase 11: Bootstrap + Global Resources

## Current Position

Phase: 11 of 14 (Bootstrap + Global Resources)
Plan: — (not yet planned)
Status: Ready to plan
Last activity: 2026-02-28 — Roadmap created for v1.1 milestone

Progress: [####################..........] 67% (v1.0 complete, v1.1 0/4 phases)

## Performance Metrics

**Velocity (v1.0):**
- Total plans completed: 20
- Average duration: 4min
- Total execution time: 1.27 hours

**v1.1:** No plans executed yet.

## Accumulated Context

### Decisions

All v1.0 decisions logged in PROJECT.md Key Decisions table.
v1.1 decisions so far:
- Raw Terraform resources over terraform-aws-modules (5-6 resources, modules add overhead)
- Secrets Manager containers in TF, values populated manually via CLI (never in TF state)
- settings.py will load secrets from Secrets Manager ARNs at cold start (code change required)
- lifecycle { ignore_changes = [image_uri] } on Lambda — TF owns infra, GHA owns deployed code

### Pending Todos

None.

### Blockers/Concerns

- Python 3.14 arm64 Lambda base image availability on public.ecr.aws must be verified (fallback: Python 3.13 or custom base)
- AWS provider version should be verified at implementation time (research used ~5.80 range)
- OIDC trust policy `sub` claim is case-sensitive — verify with `aws sts get-caller-identity` on first GHA run

## Session Continuity

Last session: 2026-02-28
Stopped at: v1.1 roadmap created, ready to plan Phase 11
Resume file: None
