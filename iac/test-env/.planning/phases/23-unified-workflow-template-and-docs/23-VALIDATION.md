---
phase: 23
slug: unified-workflow-template-and-docs
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (regression only — no new tests for YAML/Markdown phase) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 23-01-01 | 01 | 1 | WF-01 | manual | Inspect YAML structure | N/A (new inline block) | ⬜ pending |
| 23-01-02 | 01 | 1 | WF-02 | manual | Inspect YAML | N/A | ⬜ pending |
| 23-01-03 | 01 | 1 | WF-03 | manual | Inspect YAML | N/A | ⬜ pending |
| 23-01-04 | 01 | 1 | WF-04 | manual | Inspect YAML | N/A | ⬜ pending |
| 23-01-05 | 01 | 1 | WF-05 | manual | Inspect YAML | N/A | ⬜ pending |
| 23-01-06 | 01 | 1 | WF-06 | manual | Inspect YAML | N/A | ⬜ pending |
| 23-02-01 | 02 | 1 | DOC-01 | manual | Read `docs/setup.md` | Yes | ⬜ pending |
| 23-02-02 | 02 | 1 | DOC-02 | manual | Read type pages | Yes | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test files needed — Phase 23 is YAML template authoring and Markdown editing only. The Python test suite (50 tests) provides regression coverage.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `ferry.yml` has setup + 3 deploy jobs | WF-01 | YAML template in docs, not executable code | Inspect code block in `docs/setup.md` for 4 jobs |
| Lambda job uses matrix strategy | WF-02 | YAML structure check | Verify `strategy.matrix` in deploy-lambda job |
| SF job uses matrix strategy | WF-03 | YAML structure check | Verify `strategy.matrix` in deploy-step-function job |
| APGW job uses matrix strategy | WF-04 | YAML structure check | Verify `strategy.matrix` in deploy-api-gateway job |
| `run-name` shows resource type | WF-05 | YAML structure check | Verify `run-name` field references `resource_type` |
| No workflow-level concurrency | WF-06 | YAML structure check | Confirm no top-level `concurrency:` key; job-level groups exist |
| `setup.md` has template + migration guide | DOC-01 | Documentation content | Read `docs/setup.md` for template section and migration section |
| Type pages have workflow sections removed | DOC-02 | Documentation content | Check `lambdas.md`, `step-functions.md`, `api-gateways.md` no longer have `## Workflow File` sections |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
