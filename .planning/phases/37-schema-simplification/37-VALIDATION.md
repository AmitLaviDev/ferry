---
phase: 37
slug: schema-simplification
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-14
---

# Phase 37 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml (root) |
| **Quick run command** | `.venv/bin/python -m pytest tests/ -x -q` |
| **Full suite command** | `.venv/bin/python -m pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/ -x -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 37-01-01 | 01 | 1 | SCHEMA-01a | unit | `.venv/bin/python -m pytest tests/test_backend/test_config_schema.py -x` | Exists (needs update) | ⬜ pending |
| 37-01-02 | 01 | 1 | SCHEMA-01b | unit | `.venv/bin/python -m pytest tests/test_backend/test_config_schema.py -x` | Exists (needs update) | ⬜ pending |
| 37-01-03 | 01 | 1 | SCHEMA-01c | unit | `.venv/bin/python -m pytest tests/test_backend/test_config_schema.py -x` | Exists (no change) | ⬜ pending |
| 37-01-04 | 01 | 1 | SCHEMA-01d | unit | `.venv/bin/python -m pytest tests/test_action/ -x` | Exists (needs update) | ⬜ pending |
| 37-01-05 | 01 | 1 | SCHEMA-01e | unit | `.venv/bin/python -m pytest tests/test_backend/test_config_schema.py -x` | Needs new tests | ⬜ pending |
| 37-01-06 | 01 | 1 | SCHEMA-01f | unit | `.venv/bin/python -m pytest tests/test_utils/test_dispatch_models.py -x` | Exists (needs update) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. New backward-compat tests added during implementation.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ferry-test-app ferry.yaml migration | SCHEMA-01 | Requires push to real repo | Update ferry.yaml, push, verify plan comment |

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-14
