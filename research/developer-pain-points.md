# Developer Pain Points: Serverless Deployments

## Top Pain Themes

### 1. Configuration Drift — The Silent Production Killer
> "Your team deploys a Lambda with 128MB memory via CloudFormation. During an outage, an engineer increases to 512MB through the Console. Later, another dev updates the template to 256MB — CloudFormation unexpectedly reduces memory, causing the outage to recur." — Firefly Engineering Blog

- ClickOps (manual Console changes) bypasses version control, audit trails, peer review
- Violates SOC 2 and ISO 27001 compliance requirements
- Less than 50% of orgs can fix drift within 24 hours (Firefly 2024)
- Less than 1/3 continuously monitor for drift

### 2. Rollback Is Fundamentally Broken
> "Serverless Framework artifacts are not immutable — making traditional rollback strategies completely ineffective." — Seed.run

- Plugins cause side effects during deployment; all must be reinstalled even for rollback
- Source code required for rollbacks (unlike containers where you redeploy old image)
- Can't reuse artifacts across stages
- CLI rollback output is unparseable for automation (GitHub Issue #3894 — closed in 2019 unresolved)
- CloudFormation enters UPDATE_ROLLBACK_FAILED state — stack permanently stuck

### 3. Nobody Knows What's Running
> "Getting coherent logs out of CloudFront → API Gateway → Lambda is CRAP." — HN

- No single source of truth for what version is deployed where
- Datadog built a dedicated "Deployment Tracking" product — evidence the gap is commercially significant
- `sls deploy list` shows timestamps only — no commit SHA, no author, no environment context
- Multi-developer teams deploy from local machines to shared environments — zero traceability

### 4. Environment Variables Are a Security Nightmare
> "Environment variables are available in every process within the execution context — even if the process has no need to use it." — Trend Micro

- Set at deploy time, not runtime — changing a DB connection string requires redeploying all services
- `serverless.yml` in repo exposes secrets to anyone with repo access
- No standard secret management integration

### 5. Concurrent Deployments Break Everything
- Two devs deploying to same environment simultaneously → CloudFormation resource conflicts
- GitHub Actions has no automatic deployment queueing (unlike CodePipeline)
- Log groups already exist → deployment fails for second person

### 6. Tooling Fragmentation
> "Serverless hasn't had its Rails moment yet — ecosystem remains fragmented with immature tools requiring custom workarounds." — HN

- SAM, CDK, SST, Serverless Framework, Terraform — too many options, no standard
- Each has different trade-offs, none has full coverage
- Teams assemble custom toolchains, creating maintenance burden

## What Developers Explicitly Want (from GitHub Issues & Forums)

1. **Deployment metadata tied to commits** — store commit SHA with every deployment
2. **Machine-readable rollback output** — programmatic APIs, not CLI with hard-to-parse output
3. **Numeric rollback syntax** — `sls rollback -n 4` instead of timestamp-based
4. **Artifact immutability** — deploy old artifact without source code
5. **Concurrent deployment safety** — queue deployments, don't fail

## What Developers Implicitly Need

6. **A reconciliation loop** — continuously compare Git state to actual Lambda state
7. **Unified deployment dashboard** — one place: version, environment, deployer, commit
8. **ClickOps prevention** — detect console changes, revert or promote to Git
9. **Environment parity enforcement** — verify dev/staging/prod match
10. **Compliance-ready audit trails** — Git-backed, immutable history satisfying SOC 2 / ISO 27001

## Case Study: Unkey's Serverless Exodus (Dec 2025)
- API platform built entirely on Cloudflare Workers
- Abandoned serverless — "spent more time evaluating SaaS products than building features"
- Built elaborate caching workarounds that replicated what stateful servers provide
- Self-hosting became impossible
- Root cause: operational overhead exceeded development velocity gains
