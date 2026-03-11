---
phase: 26
slug: backend-batched-dispatch
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 26 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0 + pytest-httpx >=0.30 |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/test_backend/test_dispatch_trigger.py -v` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_backend/test_dispatch_trigger.py -v`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 26-01-01 | 01 | 1 | DISP-01 | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_multiple_types_batched -x` | ❌ W0 | ⬜ pending |
| 26-01-02 | 01 | 1 | DISP-01 | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_single_type_batched -x` | ❌ W0 | ⬜ pending |
| 26-01-03 | 01 | 1 | DISP-01 | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_batched_payload_format -x` | ❌ W0 | ⬜ pending |
| 26-01-04 | 01 | 1 | DISP-03 | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_fallback_on_oversized -x` | ❌ W0 | ⬜ pending |
| 26-01-05 | 01 | 1 | DISP-03 | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_fallback_uses_v1_payload -x` | ❌ W0 | ⬜ pending |
| 26-01-06 | 01 | 1 | DISP-01 | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_return_shape -x` | ❌ W0 | ⬜ pending |
| 26-01-07 | 01 | 1 | DISP-01 | unit | `uv run pytest tests/test_backend/test_dispatch_trigger.py::TestTriggerDispatches::test_trigger_dispatches_all_three_types -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Update existing tests in `tests/test_backend/test_dispatch_trigger.py` to expect batched behavior (single API call for multi-type)
- [ ] Add new tests for: batched payload format, fallback on oversized, fallback uses v1 format, all-three-types, return shape
- [ ] No framework install needed — pytest and pytest-httpx already configured

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
