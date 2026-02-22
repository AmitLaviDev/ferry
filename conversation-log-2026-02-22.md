# Ferry - PRD Working Session Log
**Date:** 2026-02-22
**Context:** Claude Code for PMs course, Module 2.1 (Write a PRD) — applied to real project

---

## Session Summary

Used the ccforpms course Module 2.1 as a guide to build a real PRD for Ferry. Course materials stay in `claude-courses/`, all Ferry work goes in `projects/ferry/`.

---

## What is Ferry?

**ArgoCD for Serverless** — a GitOps tool that makes git the single source of truth for serverless infrastructure. Like what ArgoCD does for Kubernetes, but for AWS Lambda, Step Functions, and API Gateway.

### Core Value Props
- Git as single source of truth for serverless
- Auto-deploy watchdog — listens to code changes, deploys via CI/CD
- Version control, history, audit trail built-in
- Easy rollback (git revert = infrastructure rollback)
- Disaster recovery — rebuild from repo
- ACLs through git — no direct cluster permissions needed
- Secure external tool access — tools touch code, not the cluster
- Leverage K8s tools patterns for CI/CD with UI

---

## Socratic Questions & Answers

### Q1: Problem Statement
**Answer (Option C - Combined):**
> Serverless teams face a double problem: operationally, they're stuck with manual zip-file deploys, no version control, and no rollback. Strategically, they have zero governance - no audit trail, no ACLs, no disaster recovery plan. The infrastructure exists only in the cloud console, not in code. If it breaks, you're rebuilding from memory.

### Q2: Target User
**Answer (Custom):**
NOT platform teams at scale. Instead: developers WITHOUT a dedicated DevOps/platform team — backend devs, infra devs, data engineers, full-stack engineers. Every entity that works with code and doesn't have a legit devops/platform team. **Ferry replaces the need for a platform team.**

### Q3: V1 Scope
**Answer (Modified Option A):**
AWS-first, core GitOps only — BUT also supports Step Functions and API Gateway in V1 (not just Lambda).

### Q4: Strategic Timing
**Answer (Option C - Ecosystem Readiness):**
GitOps is now a proven pattern thanks to ArgoCD and Flux. Platform engineers already think in terms of declarative config and reconciliation loops. The mental model exists - it just hasn't been applied to serverless. Wait 6 months and you're competing with someone who had the same realization.

---

## Phase 1 Technical Approach

Based on the OpenTaco/Digger model (https://docs.opentaco.dev/readme/introduction):
- **Git application** (Ferry backend) — GitHub App that watches repos
- **PR automation** — auto-run plans on PR, apply on merge
- **Drift detection** — continuously scan for config drift, create GitHub issues
- **State management** — centralized, with versioning and rollback
- **Workflows defined in repos** — declarative config (`ferry.yml`) in the repo itself

**What OpenTaco does for Terraform, Ferry does for serverless.**

---

## Research Conducted

Three parallel research agents ran covering:

### 1. Competitor Analysis (`ferry/research/competitor-analysis.md`)
Key finding: **Every single existing tool is push-based. No tool provides continuous reconciliation for serverless.**

Tools analyzed: Serverless Framework, AWS SAM, SST, Terraform/OpenTofu, Pulumi, AWS CDK, Seed.run, Spacelift, env0, Atlantis, AWS CodeDeploy, Harness.

### 2. Developer Pain Points (`ferry/research/developer-pain-points.md`)
Key findings:
- Config drift is "silent production killer" — <50% of orgs can fix drift within 24 hours
- Rollback is fundamentally broken (artifacts aren't immutable)
- Nobody knows what's actually running (no commit-to-deployment traceability)
- Tooling fragmentation — "Serverless hasn't had its Rails moment"

### 3. Market Analysis (`ferry/research/market-analysis.md`)
Key numbers:
- Serverless market: $25-28B, 14-15% CAGR
- 1.8M monthly active Lambda customers, 15T+ invocations/month
- 70% AWS customers use serverless, 0% have GitOps for it
- GitOps platforms market: $1.62B growing 22.4% CAGR
- ArgoCD: 60% K8s adoption, NPS 79, Akuity raised $24M Series A

---

## PRD Versions Generated

### 3 Strategic Versions (for comparison)
1. **ferry-prd-v1-devex.md** — Developer Experience First ("You don't need a DevOps team")
2. **ferry-prd-v2-governance.md** — Security & Governance First (audit, compliance, ACLs)
3. **ferry-prd-v3-migration.md** — Migration Path (meet you where you are, gradual GitOps adoption)

### Final MVP PRD
4. **ferry-prd-mvp.md** — The chosen direction. Pragmatic, focused, ~2400 words.

**Decision rationale:**
- Governance can come later — it's a feature, not the wedge
- DevEx is the right angle but V1 was over-engineered
- Time-to-setup metrics are vanity — what matters is: does it work reliably?
- Open source MVP — get it in hands, get feedback, iterate

### MVP Scope (5 things only):
1. GitHub App watches repo — PR automation (plan on PR, apply on merge)
2. Declarative config in repo (`ferry.yml`)
3. Reliable deploy loop — Lambda + Step Functions + APIGW
4. Drift detection — detect changes outside git, create GitHub issues
5. Rollback — git revert = infrastructure rollback

---

## SST Comparison

Reviewed SST docs (https://sst.dev/docs/). **SST does NOT solve Ferry's problem.** They're complementary:

| | SST | Ferry |
|---|---|---|
| What | Deployment framework (push-based) | GitOps operator (pull-based) |
| Drift detection | None | Core feature |
| Continuous reconciliation | None | Core feature |
| PR automation | None | Built-in |
| Rollback | Manual re-deploy | Git revert = auto rollback |
| Audit trail | None | Built-in |

**SST could be a deployment engine that Ferry orchestrates** — like how ArgoCD doesn't replace Helm but uses it.

---

## Open Question (to pick up next time)

**Should Ferry's `ferry.yml` define infrastructure from scratch (like SST does), or should Ferry wrap existing tools (SST, SAM, CDK, Serverless Framework) and add the GitOps layer on top?**

This is an important architectural decision that was raised but not answered.

---

## File Structure

```
C:\Users\itama\Projects\ferry\
├── conversation-log-2026-02-22.md    ← this file
├── research\
│   ├── competitor-analysis.md
│   ├── developer-pain-points.md
│   └── market-analysis.md
└── prd\
    ├── ferry-prd-v1-devex.md          (reference)
    ├── ferry-prd-v2-governance.md     (reference)
    ├── ferry-prd-v3-migration.md      (reference)
    └── ferry-prd-mvp.md              ← chosen direction
```

---

## Course Progress

- **Module 2.1 (Write a PRD):** In progress — completed research, Socratic questions, 3 draft versions, MVP PRD. Remaining: agent reviews (engineer/executive/user researcher feedback) and final refinement.
- **Next module:** 2.2 (Analyze Data) — `/start-2-2`
