# Roadmap: Ferry

## Milestones

- v1.0 MVP -- Phases 1-10 (shipped 2026-02-28)
- v1.1 Deploy to Staging -- Phases 11-14 (shipped 2026-03-03)
- v1.2 End-to-End Validation -- Phases 15-17 (shipped 2026-03-08)
- v1.3 Full-Chain E2E -- Phases 18-21 (shipped 2026-03-10)
- v1.4 Unified Workflow -- Consolidate three per-type workflow files into one `ferry.yml` (planned)
- v2.0 PR Integration -- Mid-workflow deployments with "ferry plan" and "ferry apply" (planned)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-10) -- SHIPPED 2026-02-28</summary>

- [x] Phase 1: Foundation and Shared Contract (3/3 plans) -- completed 2026-02-22
- [x] Phase 2: App Core Logic (3/3 plans) -- completed 2026-02-24
- [x] Phase 3: Build and Lambda Deploy (3/3 plans) -- completed 2026-02-26
- [x] Phase 4: Extended Resource Types (3/3 plans) -- completed 2026-02-26
- [x] ~~Phase 5: Integration and Error Reporting~~ -- Superseded
- [x] Phase 6: Fix Lambda function_name Pipeline (1/1 plan) -- completed 2026-02-27
- [x] Phase 7: Tech Debt Cleanup (3/3 plans) -- completed 2026-02-27
- [x] Phase 8: Error Surfacing and Failure Reporting (2/2 plans) -- completed 2026-02-28
- [x] Phase 9: Tech Debt Cleanup Round 2 (1/1 plan) -- completed 2026-02-28
- [x] Phase 10: Docs and Dead Code Cleanup (1/1 plan) -- completed 2026-02-28

Full details: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)

</details>

<details>
<summary>v1.1 Deploy to Staging (Phases 11-14) -- SHIPPED 2026-03-03</summary>

- [x] Phase 11: Bootstrap + Global Resources (2/2 plans) -- completed 2026-02-28
- [x] Phase 12: Shared IAM + Secrets (1/1 plan) -- completed 2026-03-01
- [x] Phase 12.1: IaC Directory Restructure (1/1 plan) -- completed 2026-03-02
- [x] Phase 13: Backend Core (1/1 plan) -- completed 2026-03-02
- [x] Phase 14: Self-Deploy + Manual Setup (3/3 plans) -- completed 2026-03-03

Full details: [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)

</details>

<details>
<summary>v1.2 End-to-End Validation (Phases 15-17) -- SHIPPED 2026-03-08</summary>

- [x] Phase 15: Deploy Ferry Infrastructure (3/3 plans) -- completed 2026-03-04
- [x] Phase 16: Provision Test Environment (3/3 plans) -- completed 2026-03-07
- [x] Phase 17: End-to-End Loop Validation (3/3 plans) -- completed 2026-03-08

Full details: [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)

</details>

<details>
<summary>v1.3 Full-Chain E2E (Phases 18-21) -- SHIPPED 2026-03-10</summary>

- [x] Phase 18: Tech Debt Cleanup (2/2 plans) -- completed 2026-03-08
- [x] Phase 19: Test Infrastructure for SF + APGW (1/1 plan) -- completed 2026-03-08
- [x] Phase 20: Test Repo Updates (1/1 plan) -- completed 2026-03-09
- [x] Phase 21: Full-Chain E2E Validation (3/3 plans) -- completed 2026-03-10

Full details: [milestones/v1.3-ROADMAP.md](milestones/v1.3-ROADMAP.md)

</details>

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation and Shared Contract | v1.0 | 3/3 | Complete | 2026-02-22 |
| 2. App Core Logic | v1.0 | 3/3 | Complete | 2026-02-24 |
| 3. Build and Lambda Deploy | v1.0 | 3/3 | Complete | 2026-02-26 |
| 4. Extended Resource Types | v1.0 | 3/3 | Complete | 2026-02-26 |
| 5. Integration and Error Reporting | v1.0 | -- | Superseded | -- |
| 6. Fix Lambda function_name Pipeline | v1.0 | 1/1 | Complete | 2026-02-27 |
| 7. Tech Debt Cleanup | v1.0 | 3/3 | Complete | 2026-02-27 |
| 8. Error Surfacing and Failure Reporting | v1.0 | 2/2 | Complete | 2026-02-28 |
| 9. Tech Debt Cleanup (Round 2) | v1.0 | 1/1 | Complete | 2026-02-28 |
| 10. Docs and Dead Code Cleanup | v1.0 | 1/1 | Complete | 2026-02-28 |
| 11. Bootstrap + Global Resources | v1.1 | 2/2 | Complete | 2026-02-28 |
| 12. Shared IAM + Secrets | v1.1 | 1/1 | Complete | 2026-03-01 |
| 12.1. IaC Directory Restructure | v1.1 | 1/1 | Complete | 2026-03-02 |
| 13. Backend Core | v1.1 | 1/1 | Complete | 2026-03-02 |
| 14. Self-Deploy + Manual Setup | v1.1 | 3/3 | Complete | 2026-03-03 |
| 15. Deploy Ferry Infrastructure | v1.2 | 3/3 | Complete | 2026-03-04 |
| 16. Provision Test Environment | v1.2 | 3/3 | Complete | 2026-03-07 |
| 17. End-to-End Loop Validation | v1.2 | 3/3 | Complete | 2026-03-08 |
| 18-21. Full-Chain E2E | v1.3 | 7/7 | Complete | 2026-03-10 |

## Future Milestones

### v1.4 Unified Workflow
**Goal:** Consolidate the three per-type workflow files (`ferry-lambdas.yml`, `ferry-step_functions.yml`, `ferry-api_gateways.yml`) into a single `ferry.yml` from the customer's perspective.

Users currently maintain one workflow file per resource type. v1.4 replaces this with a single `ferry.yml` that handles all types via conditional jobs. Backend still sends one dispatch per type (minimal backend change), all targeting the same `ferry.yml`. Touches: dispatch.py (workflow filename), setup action (type output), docs/templates, user workflow files.

### v2.0 PR Integration
**Goal:** Add PR-triggered deployments with a "ferry plan" / "ferry apply" model — preview what will deploy on PR open/update, deploy on merge or explicit approval.

Key capabilities:
- **ferry plan**: On `pull_request` events, show what resources would be built/deployed (diff preview in PR comment or Check Run)
- **ferry apply**: On merge to target branch (or explicit comment trigger), execute the actual build and deploy
- Mid-way deployments: deploy to staging/preview environments from PRs before merge
- Environment/branch mapping (e.g., `main` → prod, `develop` → staging)
