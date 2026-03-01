# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-28)

**Core value:** When a developer pushes code, every affected serverless resource is automatically detected, built, and deployed -- with full visibility on the PR before merge.
**Current focus:** v1.1 Deploy to Staging — Phase 12: Shared IAM + Secrets

## Current Position

Phase: 12 of 14 (Shared IAM + Secrets)
Plan: 1 of 1 (Phase 12 COMPLETE)
Status: Phase Complete
Last activity: 2026-03-01 — Completed 12-01 (OIDC provider + IAM roles + Secrets Manager)

Progress: [##########################....] 83% (v1.0 complete, v1.1 Phases 11-12: 3/3 plans)

## Performance Metrics

**Velocity (v1.0):**
- Total plans completed: 20
- Average duration: 4min
- Total execution time: 1.27 hours

**v1.1:**
| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 11 | 01 | 1min | 2 | 10 |
| 11 | 02 | 1min | 1 | 1 |
| 12 | 01 | 3min | 2 | 11 |

## Accumulated Context

### Decisions

All v1.0 decisions logged in PROJECT.md Key Decisions table.
v1.1 decisions so far:
- Raw Terraform resources over terraform-aws-modules (5-6 resources, modules add overhead)
- Secrets Manager containers in TF, values populated manually via CLI (never in TF state)
- settings.py will load secrets from Secrets Manager ARNs at cold start (code change required)
- lifecycle { ignore_changes = [image_uri] } on Lambda — TF owns infra, GHA owns deployed code
- No assume_role in global bootstrap projects -- ambient credentials for one-time setup (Phase 11)
- default_tags on provider for ManagedBy + Project tags; resource-specific tags only where needed (Phase 11)
- aws_caller_identity data source for account ID in ECR outputs -- no hardcoded IDs (Phase 11)
- terraform -chdir= pattern and -input=false for non-interactive bootstrap execution (Phase 11)
- Idempotency via AWS API checks (head-bucket, describe-repos, describe-images) at each bootstrap step (Phase 11)
- kebab-case IAM naming (ferry-lambda-execution, ferry-gha-self-deploy) for consistency with project naming (Phase 12)
- Direct policy attachments over locals map pattern -- 9 attachments, direct is more readable at this scale (Phase 12)
- gha_ecr_auth policy shared between both GHA roles via separate attachment resources (Phase 12)
- No secret versions created -- empty Secrets Manager containers populated via CLI in Phase 14 (Phase 12)

### Pending Todos

None.

### Blockers/Concerns

- Python 3.14 arm64 Lambda base image availability on public.ecr.aws must be verified (fallback: Python 3.13 or custom base)
- AWS provider version should be verified at implementation time (research used ~5.80 range)
- OIDC trust policy `sub` claim is case-sensitive — verify with `aws sts get-caller-identity` on first GHA run

## Session Continuity

Last session: 2026-03-01
Stopped at: Completed 12-01-PLAN.md (OIDC + IAM + Secrets — Phase 12 complete)
Resume file: None
