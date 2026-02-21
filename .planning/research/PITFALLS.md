# Domain Pitfalls

**Domain:** GitHub App + Serverless AWS Deployment Automation
**Project:** Ferry
**Researched:** 2026-02-21
**Overall confidence:** MEDIUM (training-data-based; web verification tools unavailable during research)

---

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or broken deployments in production.

---

### Pitfall 1: GitHub Webhook Delivery Is Not Guaranteed — Silent Drops

**What goes wrong:** GitHub webhooks are "at-least-once" delivery but not "exactly-once" or "guaranteed." Webhooks can be silently dropped if your endpoint returns a non-2xx within 10 seconds, if GitHub's webhook infrastructure experiences issues, or if your Lambda cold-starts exceed the timeout window. A dropped push webhook means a commit is merged but never deployed — the worst failure mode for a deployment tool, because nobody notices.

**Why it happens:** GitHub sends a webhook and expects a 2xx response within 10 seconds. Lambda cold starts (especially with Python + dependencies) can approach 3-5 seconds. If your function takes too long to process synchronously (read ferry.yaml, compute diffs, trigger dispatches), the total exceeds 10s, GitHub marks the delivery as failed. GitHub retries failed deliveries, but only a limited number of times. If all retries fail, the event is gone.

**Consequences:** Commits merged without deployment. Users lose trust in the system. Since there is no dashboard and no queue, there is zero visibility into missed events. This is an invisible failure — the most dangerous kind for a deployment tool.

**Prevention:**
1. **Respond immediately, process asynchronously.** Accept the webhook, validate the signature, write to DynamoDB, return 202 within 1-2 seconds. Do the heavy lifting (read ferry.yaml, compute diffs, trigger dispatches) in a second invocation or as a continuation. Even though the architecture says "no SQS," you can still use a second Lambda invocation (async invoke via `lambda:InvokeAsync` or DynamoDB Streams) to decouple acceptance from processing.
2. **Implement a reconciliation/polling fallback.** Periodically (or on a cron) check recent commits on main branches via the GitHub API and compare against your DynamoDB delivery log. If a commit was pushed but no delivery was recorded, trigger the deploy. This is your safety net.
3. **Monitor webhook delivery health.** Use the GitHub Webhook Deliveries API (`GET /app/hook/deliveries`) to check for failed deliveries. Expose a metric: "webhooks received in last hour" vs expected (based on commit activity).
4. **Keep cold starts fast.** Minimal dependencies in the webhook receiver Lambda. No heavy SDK imports at module level. Use Lambda SnapStart if available for Python (check — may be Java-only currently, in which case use provisioned concurrency for the webhook receiver).

**Detection:**
- A commit on main that has no corresponding DynamoDB record
- GitHub webhook delivery dashboard showing failures
- Users reporting "I merged but nothing deployed"

**Phase relevance:** Phase 1 (webhook receiver). This must be designed correctly from day one. Retrofitting async processing or reconciliation is painful.

**Confidence:** HIGH — this is well-documented GitHub App behavior.

---

### Pitfall 2: workflow_dispatch Is Fire-and-Forget — No Delivery Confirmation

**What goes wrong:** The `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches` API returns `204 No Content` on success. This means "GitHub accepted the request," NOT "a workflow run was created." There is no run ID in the response. You cannot confirm that the dispatch actually resulted in a workflow run. The workflow file must exist on the default branch, the inputs must match, and there must not be a concurrency conflict — any of these silently prevent the run from being created.

**Why it happens:** GitHub's workflow_dispatch API is intentionally fire-and-forget. The 204 response is returned before GitHub even evaluates whether the workflow file exists or the inputs are valid. This is by design for scalability, but it creates an observability gap for systems that depend on dispatches actually running.

**Consequences:** Ferry triggers a dispatch, records success (got 204), but the workflow never runs. The deploy silently fails. Combined with Pitfall 1, this creates a double-failure scenario: even if the webhook was received, the deployment might still not happen.

**Prevention:**
1. **Poll for the workflow run after dispatch.** After sending the dispatch, wait 5-10 seconds, then poll `GET /repos/{owner}/{repo}/actions/runs?event=workflow_dispatch` filtered by creation time. Look for a run that matches your dispatch. Record the run ID in DynamoDB.
2. **Use a unique identifier in dispatch inputs.** Include a `ferry_dispatch_id` in the workflow_dispatch inputs. The workflow can output this ID, making it possible to correlate dispatches with runs.
3. **Implement a "dispatch watchdog."** A scheduled Lambda (every 5 minutes) checks DynamoDB for dispatches that have no corresponding run ID after N minutes. These are flagged as failed and can be retried or alerted on.
4. **Validate workflow file existence before dispatching.** Use the Contents API to verify `.github/workflows/ferry.yml` exists on the default branch before dispatching. This eliminates one class of silent failure.

**Detection:**
- DynamoDB records with `dispatch_sent_at` but no `run_id` after 10 minutes
- Users reporting changes detected but not deployed

**Phase relevance:** Phase 2 (dispatch triggering). Must be addressed when implementing the dispatch mechanism. The correlation/watchdog pattern should be designed upfront.

**Confidence:** HIGH — the 204-with-no-run-ID behavior is documented GitHub API behavior.

---

### Pitfall 3: GitHub App JWT Expires After 10 Minutes — Token Caching Bugs

**What goes wrong:** GitHub App JWTs (used to authenticate as the App itself) expire after 10 minutes maximum. Installation access tokens expire after 1 hour. If you cache a JWT and reuse it near its expiry boundary, API calls fail with 401. If you generate a new JWT for every single API call, you waste time on crypto operations. The common mistake is caching the JWT for "about 10 minutes" without accounting for clock skew between your Lambda and GitHub's servers.

**Why it happens:** Lambda execution environments have clocks that can drift. GitHub recommends setting JWT `iat` (issued at) to 60 seconds in the past and `exp` to no more than 10 minutes ahead. Most developers set `exp = now + 600` without the `iat` backdating, then cache aggressively. When the cached token hits the boundary, calls fail intermittently.

**Consequences:** Intermittent 401 errors. The webhook receiver cannot read ferry.yaml. Dispatch triggering fails. These are transient and hard to reproduce, creating "works sometimes" bugs that erode trust.

**Prevention:**
1. **Generate a fresh JWT for each webhook processing cycle.** JWTs are cheap to generate (RS256 sign). Do not cache across invocations. Since each webhook triggers one processing cycle, generate a fresh JWT at the start.
2. **Always backdate `iat` by 60 seconds.** `iat = now - 60`, `exp = now + (9 * 60)`. This accounts for clock skew.
3. **Cache installation access tokens, not JWTs.** Installation tokens last 1 hour and are expensive (one API call to create). Cache these in DynamoDB with TTL. Refresh when they have less than 5 minutes remaining.
4. **Retry with fresh token on 401.** Any 401 response should trigger immediate token refresh and retry (once). Do not retry infinitely.

**Detection:**
- Sporadic 401 errors in CloudWatch logs
- ferry.yaml reads that fail intermittently
- Pattern of failures clustered around token expiry boundaries

**Phase relevance:** Phase 1 (GitHub API authentication). Get this right from the start. A token management module should be one of the first things built.

**Confidence:** HIGH — JWT expiry and `iat` backdating are documented in GitHub's official App auth docs.

---

### Pitfall 4: Lambda Deployment Races — Concurrent Deploys to Same Function

**What goes wrong:** Two rapid pushes to main (or a push and a manual dispatch) trigger two Ferry Action runs. Both runs build and push different images to ECR, then both call `update-function-code` on the same Lambda. The second `update-function-code` overwrites the first. If the first push should have been deployed (it was merged first), the Lambda ends up running the second push's code. Worse, if both runs then call `publish-version` and `update-alias`, the alias might point to the wrong version.

**Why it happens:** GitHub Actions runs are not inherently serialized. Even with concurrency groups (`concurrency: { group: deploy-${{ inputs.resource_name }} }`), there is a race window. The `cancel-in-progress` option cancels the older run, which might be the correct one to deploy. Without `cancel-in-progress`, both runs execute and race.

**Consequences:** Wrong code deployed. Alias points to wrong version. In the worst case, a rollback-worthy bug that was supposed to be fixed by the second push is actually deployed because the first push's deploy completed last.

**Prevention:**
1. **Use GitHub Actions concurrency groups without cancel-in-progress.** `concurrency: { group: ferry-deploy-${{ inputs.resource_name }} }`. This queues the second run and executes it after the first completes. The second run always "wins" because it runs last with the latest code.
2. **Verify image digest before updating alias.** After `update-function-code`, check that the function's `CodeSha256` matches the expected image digest. If it does not, another deploy may have raced in — abort and let the other run handle it.
3. **Use `RevisionId` for optimistic locking.** The Lambda `update-function-code` and `update-function-configuration` APIs accept a `RevisionId` parameter. If the function was modified by another call since you read it, the update fails with a conflict error. Catch this and decide whether to retry or abort.
4. **Include commit SHA in deployment tags.** Tag the ECR image and Lambda version with the commit SHA. This creates an audit trail of which commit is actually deployed.

**Detection:**
- Lambda alias pointing to an unexpected version/digest
- Two GHA runs for the same resource completing within seconds of each other
- Deployment logs showing "function updated" but the deployed code does not match HEAD

**Phase relevance:** Phase 3 (Lambda deployment in Ferry Action). Must be designed into the deploy logic from the beginning. The `int128/deploy-lambda-action` used in pipelines-hub handles some of this (digest-based skip), but Ferry's own action needs explicit race protection.

**Confidence:** HIGH — Lambda deployment race conditions are a well-known operational issue.

---

### Pitfall 5: ECR Authentication Expires Mid-Build — Long Docker Builds Fail

**What goes wrong:** `aws ecr get-login-password` returns a token valid for 12 hours. However, if you authenticate Docker to ECR at the start of a build and the build takes a long time (large dependency installs, slow network), the push at the end can fail if something causes the token to be invalidated (e.g., role session expiry from the OIDC exchange). More commonly: the OIDC token exchange produces a session with a 1-hour max duration. If the docker build + push exceeds 1 hour (unlikely but possible with many resources), the AWS session expires and the ECR push fails.

**Why it happens:** The OIDC-to-STS token chain: GitHub OIDC token (valid ~5 min) -> `AssumeRoleWithWebIdentity` (session duration typically 1 hour) -> role chain to target account (session duration typically 1 hour, but capped by the minimum of the chain). The ECR auth token is bound to these credentials. If the STS session expires, the ECR token effectively expires too.

**Consequences:** Docker build succeeds but `docker push` fails. The GHA run fails late in execution, wasting all the build time. On retry, the entire build must re-run.

**Prevention:**
1. **Authenticate to ECR immediately before each push, not at the start of the workflow.** Do the ECR login right before `docker push`, not before `docker build`.
2. **Build and push resources sequentially, not in a massive parallel batch.** For each resource: build -> authenticate -> push -> deploy. This keeps each ECR auth fresh.
3. **Set explicit session duration on OIDC role assumption.** Request a 1-hour session (the default) and ensure total workflow time stays well under that. Monitor workflow duration.
4. **Cache Docker layers in ECR or GHA cache.** Faster builds mean less time for tokens to expire. Use `--cache-from` with the previous ECR image.

**Detection:**
- `docker push` failures with "token expired" or "no basic auth credentials"
- Build succeeds but deploy step fails with AWS credential errors
- Failures correlate with builds that took unusually long

**Phase relevance:** Phase 3 (container build + ECR push in Ferry Action). Must be addressed in the build/push sequence design.

**Confidence:** MEDIUM — the OIDC session duration issue is real but the exact behavior depends on role trust policy configuration which varies by setup.

---

### Pitfall 6: DynamoDB Conditional Write Dedup Is Not Enough — Replay Storms

**What goes wrong:** GitHub can replay the same webhook delivery multiple times (retries on timeout, manual redelivery from the UI, or infrastructure issues causing duplicates). Using `PutItem` with a condition expression on the delivery ID (`attribute_not_exists(delivery_id)`) correctly deduplicates by delivery ID. But if GitHub creates a *new* delivery for the same event (different delivery ID, same push event), the dedup misses it. This happens during GitHub infrastructure issues where webhooks are re-queued with new delivery IDs.

**Why it happens:** GitHub's `X-GitHub-Delivery` header is unique per delivery attempt, not per logical event. If GitHub's infrastructure re-queues an event, it gets a new delivery ID. Your dedup catches retries of the same delivery but not re-queues of the same event.

**Consequences:** The same push triggers multiple deploy cycles. Two parallel deployments for the same commit cause the race condition in Pitfall 4. Resource waste and potential deployment corruption.

**Prevention:**
1. **Dedup on both delivery ID AND event content.** Create a composite dedup key: `{repo_id}#{event_type}#{after_sha}` for push events. If this key already exists and was processed successfully, skip processing even if the delivery ID is new.
2. **Use a TTL on dedup records.** Set DynamoDB TTL to 24 hours. Old dedup records are cleaned up automatically. This prevents the table from growing unboundedly.
3. **Idempotent processing.** Design the entire pipeline to be safe to re-run. If a dispatch was already sent for a commit SHA, do not send it again. Check before dispatching.
4. **Record processing state.** Track each event through states: `received -> processing -> dispatched -> completed`. If a duplicate arrives and the original is already in `dispatched` or `completed`, skip it.

**Detection:**
- Multiple DynamoDB records for the same commit SHA with different delivery IDs
- Multiple workflow runs triggered for the same commit
- CloudWatch logs showing "already dispatched for commit {sha}" (if implemented)

**Phase relevance:** Phase 1 (webhook dedup). The dedup key design is a day-one decision. Changing the dedup key later requires a migration.

**Confidence:** MEDIUM — the "new delivery ID for same event" scenario is based on observed GitHub behavior during outages, not officially documented.

---

### Pitfall 7: GitHub API Rate Limits — Installation Token Limits Are Per-Repo

**What goes wrong:** GitHub App installation access tokens have rate limits: 5,000 requests per hour per installation for standard apps (not "server-to-server" which gets more). For a monorepo with many resources, a single push could trigger: 1 Contents API call (ferry.yaml), 1 Compare API call (diff), N dispatch calls, N status check updates. If many pushes happen in a short window (active development), you hit rate limits. Worse, the rate limit is shared across ALL API calls made with that installation token — including calls from the Ferry Action.

**Why it happens:** The Ferry App and Ferry Action both use the same GitHub App installation. Their API calls share the same rate limit pool. If the Action is posting status updates, reading files, and the App is processing webhooks simultaneously, they compete for the same 5,000/hour budget.

**Consequences:** 403 rate limit errors. Webhook processing fails. Dispatches fail. Status updates fail. The system degrades during the busiest periods — exactly when users need it most.

**Prevention:**
1. **Minimize API calls per webhook.** Cache ferry.yaml (with commit SHA as cache key in DynamoDB). Only fetch it when the SHA changes. Use a single Compare API call to get all changed files, not per-file calls.
2. **Batch status check updates.** Instead of updating the check run after each step, update it once with the full result.
3. **Track rate limit headers.** Every GitHub API response includes `X-RateLimit-Remaining` and `X-RateLimit-Reset`. Log these. If remaining drops below 500, switch to conservative mode (skip non-essential API calls like status updates).
4. **Separate concerns between App and Action API usage.** The Ferry Action should use the user's GITHUB_TOKEN (which has its own rate limit) for non-App-specific operations, and only use the App installation token for operations that require App permissions.
5. **Implement exponential backoff on 403/429.** Respect the `Retry-After` header. Do not retry immediately.

**Detection:**
- `X-RateLimit-Remaining` dropping below 1000
- 403 responses with `rate_limit` error type
- Increasing API call counts per webhook event (feature creep)

**Phase relevance:** Phase 1-2 (all GitHub API interactions). Design for API efficiency from the start. Caching and batching are easier to build in than to retrofit.

**Confidence:** HIGH — rate limits are well-documented. The 5,000/hour figure is from GitHub's official docs for App installations.

---

## Moderate Pitfalls

---

### Pitfall 8: Step Function Definition Validation Happens at Deploy Time — No Pre-Flight Check

**What goes wrong:** `aws stepfunctions update-state-machine` accepts any JSON as a definition but only validates it partially. Some ASL (Amazon States Language) errors are only caught at execution time, not at update time. The `envsubst` pattern (replacing `${ACCOUNT_ID}`, `${AWS_REGION}`) can silently produce invalid JSON if the template contains other `${}` patterns or if envsubst is not available/configured correctly.

**Why it happens:** The Step Functions API does basic schema validation on update, but semantic errors (invalid state references, missing required fields in certain state types, incorrect resource ARNs) may not be caught. The envsubst tool replaces ALL `${VAR}` patterns by default — including ones in the state machine definition that are meant to be literal (like JSONPath expressions `$.variable`).

**Consequences:** State machine updates successfully but fails at runtime. Users discover the bug only when the Step Function executes, which could be hours or days later. The bad definition is live, and the previous version is lost (Step Functions does not have version history — though Express workflows now have versioning).

**Prevention:**
1. **Use `aws stepfunctions validate-state-machine-definition` before updating.** This API exists as of late 2023 and catches most ASL errors pre-deployment.
2. **Use selective variable substitution, not blanket envsubst.** Instead of `envsubst`, use `sed` or a Python template engine that only replaces explicitly listed variables: `ACCOUNT_ID`, `AWS_REGION`. This prevents accidental replacement of `$` in JSONPath expressions.
3. **Preserve the previous definition.** Before updating, read the current definition with `describe-state-machine` and store it (in DynamoDB or as a GHA artifact). This enables manual rollback.
4. **Validate JSON structure after envsubst.** Parse the output with `json.loads()` before sending it to AWS. Catch malformed JSON early.

**Detection:**
- `update-state-machine` succeeds but subsequent Step Function executions fail
- envsubst output contains unresolved `${}` patterns or missing values
- State machine definition has empty strings where account IDs should be

**Phase relevance:** Phase 4 (Step Function deployment). Can be addressed when implementing the Step Function deploy path.

**Confidence:** MEDIUM — `validate-state-machine-definition` API availability confirmed from training data but exact validation coverage may vary.

---

### Pitfall 9: API Gateway put-rest-api Overwrites the Entire API — Partial Updates Are Dangerous

**What goes wrong:** `aws apigateway put-rest-api` with mode `overwrite` replaces the entire API definition. If the OpenAPI spec submitted is incomplete (missing endpoints, missing authorizers), those resources are deleted. If another system or manual change added endpoints, they are wiped. Unlike Lambda (where you can update code independently), API Gateway's REST API update is all-or-nothing.

**Why it happens:** API Gateway REST APIs do not support incremental updates via the put-rest-api path. The `merge` mode exists but has its own problems (it can leave orphaned resources). Most teams use `overwrite` mode for predictability, but this means the submitted spec must be complete.

**Consequences:** Endpoints disappear from the API. 404 errors in production. Authorizer configurations lost. CORS settings reset. API keys and usage plans may be affected.

**Prevention:**
1. **Treat the OpenAPI spec as the single source of truth.** Never manually modify the API Gateway in the console. All changes go through the spec file.
2. **Use `overwrite` mode, not `merge`.** Merge mode has unpredictable behavior with complex APIs. Overwrite is predictable but requires the spec to be complete.
3. **Validate the spec before deployment.** Use an OpenAPI linter (like `spectral` or `openapi-generator validate`) to catch structural issues.
4. **Always create a deployment after put-rest-api.** The `put-rest-api` call updates the API definition but does NOT deploy it. You must call `create-deployment` to make changes live. A common bug is forgetting `create-deployment` — the API definition is updated but the live stage still serves the old version.
5. **Use stage variables for environment-specific values.** This avoids needing separate API specs per environment.

**Detection:**
- API endpoints returning 404 after deployment
- `put-rest-api` succeeding but no `create-deployment` call in logs
- API definition in console missing endpoints that exist in the spec

**Phase relevance:** Phase 5 (API Gateway deployment). Can be addressed when implementing the API Gateway deploy path.

**Confidence:** HIGH — API Gateway put-rest-api behavior is well-documented.

---

### Pitfall 10: Magic Dockerfile COPY Glob Trick Is Fragile — Docker BuildKit Behavior

**What goes wrong:** The Magic Dockerfile uses `COPY system-requirements.tx[t] /tmp/` to make the COPY optional (the glob matches if the file exists, and is a no-op if it does not). This behavior depends on the Docker builder being used. Classic Docker builder handles this correctly. BuildKit (the default since Docker 23.0+) also handles it correctly as of recent versions, BUT: if the glob matches zero files and there is no other source in the COPY, older BuildKit versions would fail. Additionally, if the `.dockerignore` file is misconfigured (e.g., `*.txt` pattern), the glob trick silently stops working.

**Why it happens:** The glob trick is a clever hack, not an official Docker feature for optional COPY. Its behavior is an implementation detail of the COPY instruction's glob handling, not a documented guarantee. Docker's behavior around globs has changed between engine versions.

**Consequences:** Docker build fails with "COPY failed: no source files were specified" on certain Docker versions. Or worse, the optional file is silently ignored even when it exists (due to .dockerignore), leading to missing system dependencies at runtime.

**Prevention:**
1. **Pin the Docker version in the GHA workflow.** Use `docker/setup-buildx-action` with a specific version to ensure consistent behavior.
2. **Test the glob trick explicitly in CI.** Have a test that builds the Magic Dockerfile both with and without optional files on the target Docker version.
3. **Consider a multi-stage build alternative.** Use a small script that checks for the file and copies it, rather than relying on glob behavior:
   ```dockerfile
   COPY . /tmp/build-context/
   RUN if [ -f /tmp/build-context/system-requirements.txt ]; then \
       xargs -a /tmp/build-context/system-requirements.txt yum install -y; fi
   ```
   This is more robust but changes the layer caching behavior.
4. **Ensure .dockerignore does not interfere.** The .dockerignore must not exclude `system-requirements.txt` or `system-config.sh`.

**Detection:**
- Docker build failures mentioning "no source files"
- Lambda runtime errors for missing system libraries (system-requirements.txt was silently not copied)
- Inconsistent builds between local and GHA environments

**Phase relevance:** Phase 3 (Magic Dockerfile / container build). Must be validated on the exact Docker version used in GHA runners.

**Confidence:** MEDIUM — the glob trick works in practice (pipelines-hub uses it successfully), but its reliance on implementation detail is a risk as Docker evolves.

---

### Pitfall 11: OIDC Role Chaining Session Duration Limits

**What goes wrong:** The OIDC auth pattern is: GitHub OIDC token -> `AssumeRoleWithWebIdentity` (management role) -> `AssumeRole` (target account role). Each hop in the chain has its own session duration. Critically, role chaining (when the second AssumeRole uses credentials from the first) caps the session duration at 1 hour maximum, regardless of the MaxSessionDuration setting on the target role. This is an AWS limitation, not configurable.

**Why it happens:** AWS enforces a 1-hour max session duration for chained role assumptions (documented in the STS docs). The first `AssumeRoleWithWebIdentity` can have a longer session, but the chained `AssumeRole` is capped at 3600 seconds. If the workflow takes longer than 1 hour (building many resources), credentials expire mid-run.

**Consequences:** Build succeeds for the first few resources, then ECR push or Lambda deploy fails with `ExpiredTokenException`. The workflow fails partway through, leaving some resources deployed and others not — an inconsistent state.

**Prevention:**
1. **Design for sub-60-minute workflow runs.** If many resources change, split into multiple dispatches (Ferry already does per-type dispatching, but a type with 20 Lambda changes could still exceed 1 hour).
2. **Re-authenticate mid-workflow if needed.** For long-running workflows, the Ferry Action can re-execute the OIDC -> role chain exchange. The GitHub OIDC token can be re-requested within the same workflow run.
3. **Parallelize builds where possible.** Build multiple containers in parallel to reduce total wall time.
4. **Consider direct role assumption without chaining.** If possible, configure the target account role to trust the GitHub OIDC provider directly (eliminating the management account hop). This removes the 1-hour chain cap, allowing up to 12-hour sessions.

**Detection:**
- `ExpiredTokenException` errors in GHA logs, appearing only for later resources in a batch
- Workflows consistently failing after ~55-60 minutes
- Partial deployment state (some resources updated, others not)

**Phase relevance:** Phase 2-3 (AWS auth setup, build/deploy execution). The auth pattern must be designed with session duration in mind.

**Confidence:** HIGH — the 1-hour role chaining cap is documented in AWS STS official documentation.

---

### Pitfall 12: Lambda update-function-code Is Async — Checking Too Early

**What goes wrong:** `update-function-code` returns immediately, but the function update is asynchronous. The function enters `LastUpdateStatus: InProgress` state. If you immediately call `publish-version` or `update-alias`, the operation may fail or publish the OLD code version. The `int128/deploy-lambda-action` handles this by waiting for the update to complete, but a custom implementation might not.

**Why it happens:** Lambda code updates are not instantaneous. AWS must download the image from ECR, verify it, and prepare the execution environment. This can take 10-60 seconds for container images. The API returns success before this process completes.

**Consequences:** `publish-version` publishes the old code. The alias points to a version with old code. The deploy appears successful but the wrong code is running.

**Prevention:**
1. **Wait for `LastUpdateStatus: Successful` after `update-function-code`.** Use `get-function` or `get-function-configuration` in a polling loop. The `aws lambda wait function-updated-v2` CLI command does this automatically.
2. **Verify image digest after update.** Compare the function's `CodeSha256` against the expected ECR image digest.
3. **Only then call `publish-version` and `update-alias`.** Sequence must be: update-function-code -> wait for update complete -> publish-version -> update-alias.

**Detection:**
- Published Lambda version has wrong code (CodeSha256 mismatch)
- `publish-version` called within seconds of `update-function-code` (timing in logs)
- Intermittent "function is being updated" errors

**Phase relevance:** Phase 3 (Lambda deployment). Must be built into the deploy sequence from the start.

**Confidence:** HIGH — Lambda async update behavior is well-documented.

---

### Pitfall 13: ferry.yaml Reading from Wrong Ref — PR vs Push Confusion

**What goes wrong:** When processing a push event, Ferry reads ferry.yaml from the repository. The question is: which ref? If you read from HEAD of the default branch, you get the just-pushed version. But if the push was to a non-default branch (for PR preview), you need to read from that branch. If you read from the wrong ref, Ferry detects changes against the wrong ferry.yaml (which might have different resource definitions).

**Why it happens:** Push events include the `ref` (branch) and `after` (commit SHA). But the ferry.yaml might have been modified in the same push. Reading ferry.yaml from the `before` commit gives the old config; reading from `after` gives the new config. For a push that adds a new resource to ferry.yaml AND adds the resource's code, you MUST read from the `after` commit to see the new resource definition.

**Consequences:** New resources added to ferry.yaml are not detected. Modified ferry.yaml configurations (changed source paths, ECR names) cause incorrect change detection. Silent misconfiguration.

**Prevention:**
1. **Always read ferry.yaml from the `after` commit SHA, not from branch HEAD.** Use the Contents API with `ref` parameter: `GET /repos/{owner}/{repo}/contents/ferry.yaml?ref={after_sha}`. This ensures you see the exact state of ferry.yaml as of the pushed commit.
2. **Handle the case where ferry.yaml does not exist at that ref.** If a push occurs on a branch before ferry.yaml is added, the API returns 404. This is not an error — it means the repo is not yet configured for Ferry.
3. **Cache ferry.yaml by commit SHA.** Since a commit SHA is immutable, the ferry.yaml at that SHA never changes. Safe to cache in DynamoDB.

**Detection:**
- New resources in ferry.yaml not being deployed
- Change detection finding changes in resources that were not modified
- ferry.yaml cache returning stale configurations

**Phase relevance:** Phase 1-2 (webhook processing, change detection). Must be correct in the initial implementation.

**Confidence:** HIGH — GitHub Contents API ref parameter is well-documented.

---

## Minor Pitfalls

---

### Pitfall 14: DynamoDB Conditional Write ConditionalCheckFailedException Is Not an Error

**What goes wrong:** When deduplicating webhooks, the `PutItem` with `attribute_not_exists(pk)` condition throws `ConditionalCheckFailedException` when the item already exists (duplicate delivery). New developers treat this as an error, log it at ERROR level, and sometimes let it propagate as an unhandled exception (which causes the Lambda to return 500, which causes GitHub to retry, which creates more duplicates).

**Prevention:**
1. **Catch `ConditionalCheckFailedException` explicitly.** This is the expected, happy-path behavior for a duplicate delivery. Log at INFO or DEBUG level.
2. **Return 200 to GitHub even for duplicates.** A duplicate delivery is a success from GitHub's perspective.

**Phase relevance:** Phase 1. Basic but easy to get wrong.

**Confidence:** HIGH.

---

### Pitfall 15: Docker Build Secret Syntax Varies by BuildKit Version

**What goes wrong:** The Magic Dockerfile uses `RUN --mount=type=secret,id=org_repos_token` for private repo access. This requires BuildKit. The secret must be passed via `docker build --secret id=org_repos_token,src=<file>` or equivalent. In GHA, the syntax for passing secrets to Docker build steps varies between `docker/build-push-action` versions and raw `docker build` commands.

**Prevention:**
1. **Use `docker/build-push-action` with the `secrets` input.** This handles the BuildKit secret passing correctly.
2. **Test secret availability inside the build.** A build that silently fails to access the secret will fail at `pip install` time (private package not found), which is a confusing error message.
3. **Do not embed secrets in build args.** Build args are visible in the image history. Secrets via `--mount=type=secret` are not persisted in the image.

**Phase relevance:** Phase 3 (container build). Must be validated in GHA environment.

**Confidence:** MEDIUM.

---

### Pitfall 16: GitHub Checks API Status Updates After Merge Are Invisible

**What goes wrong:** Ferry posts check runs / commit statuses to PRs showing what will deploy. If the status update is posted after the PR is already merged, it appears on the commit but NOT in the PR's checks UI (the PR is already closed). Users never see the deployment status unless they go to the commit directly.

**Prevention:**
1. **Post status checks during PR processing, not after merge.** The preview of "what will deploy" should be posted when changes are detected on the PR, before merge.
2. **For post-merge deployment status, use a different mechanism.** Consider using GitHub Deployments API (which has its own status model) or simply posting a PR comment with the result.
3. **Post deployment results as PR comments.** Even on merged PRs, comments are visible. Use the Issues API to post a summary: "Deployed: order-processor (Lambda), checkout-flow (Step Function)."

**Phase relevance:** Phase 2 (PR status checks). Design the status update strategy with the PR lifecycle in mind.

**Confidence:** MEDIUM — the visibility of check runs on merged PRs depends on the GitHub UI, which can change.

---

### Pitfall 17: Lambda Container Image Size Limits

**What goes wrong:** Lambda container images have a 10 GB uncompressed size limit. The Magic Dockerfile, when combined with large system dependencies (e.g., `system-requirements.txt` with scientific computing libraries, ML frameworks), can produce images that approach or exceed this limit. The build succeeds, the push to ECR succeeds, but `update-function-code` fails with a size error.

**Prevention:**
1. **Monitor image sizes in the build step.** After building, check `docker image inspect --format='{{.Size}}'` and warn if over 5 GB.
2. **Use multi-stage builds for heavy dependencies.** Compile dependencies in a builder stage, copy only runtime artifacts to the final stage.
3. **Document the 10 GB limit in Ferry's user docs.** Users need to know this constraint when designing their Lambda functions.

**Phase relevance:** Phase 3 (container build). A validation check, not a design change.

**Confidence:** HIGH — 10 GB Lambda container size limit is documented.

---

### Pitfall 18: Webhook Signature Validation Gotcha — Raw Body Required

**What goes wrong:** GitHub webhook signature validation (HMAC-SHA256) requires the raw request body bytes. If your Lambda handler (behind API Gateway or Lambda Function URL) parses the body as JSON before validation, the re-serialized JSON may not match the original bytes (different whitespace, key ordering). The signature check fails on valid webhooks.

**Prevention:**
1. **Validate the signature against the raw body, before any JSON parsing.** In API Gateway + Lambda, the `event['body']` is the raw string (or base64-encoded if binary). Use this directly.
2. **If using Lambda Function URLs, the body is available as a string in the event.** Use `event['body']` directly with `hmac.compare_digest`.
3. **Use `hmac.compare_digest` (constant-time comparison), not `==`.** Prevents timing attacks.

**Phase relevance:** Phase 1 (webhook validation). Day-one requirement.

**Confidence:** HIGH — well-documented requirement in GitHub's webhook security docs.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation | Severity |
|-------------|---------------|------------|----------|
| Phase 1: Webhook Receiver | Dropped webhooks (Pitfall 1) | Respond fast, reconciliation fallback | CRITICAL |
| Phase 1: Webhook Receiver | Signature validation raw body (Pitfall 18) | Validate before JSON parse | HIGH |
| Phase 1: Webhook Receiver | DynamoDB dedup key design (Pitfall 6) | Dedup on event content, not just delivery ID | HIGH |
| Phase 1: Webhook Receiver | ConditionalCheckFailed handling (Pitfall 14) | Catch explicitly, return 200 | MODERATE |
| Phase 2: GitHub API + Dispatch | JWT token expiry (Pitfall 3) | Fresh JWT per cycle, backdate iat | HIGH |
| Phase 2: GitHub API + Dispatch | workflow_dispatch fire-and-forget (Pitfall 2) | Poll for run, dispatch watchdog | CRITICAL |
| Phase 2: GitHub API + Dispatch | Rate limits (Pitfall 7) | Cache ferry.yaml, minimize calls, track headers | HIGH |
| Phase 2: GitHub API + Dispatch | Wrong ref for ferry.yaml (Pitfall 13) | Read from after commit SHA | HIGH |
| Phase 2: GitHub API + Dispatch | Check status after merge invisible (Pitfall 16) | Post as PR comments | MODERATE |
| Phase 3: Container Build | ECR auth expiry mid-build (Pitfall 5) | Auth before push, not before build | HIGH |
| Phase 3: Container Build | Docker glob trick fragility (Pitfall 10) | Pin Docker version, test both paths | MODERATE |
| Phase 3: Container Build | Build secret syntax (Pitfall 15) | Use docker/build-push-action | MODERATE |
| Phase 3: Container Build | Image size limit (Pitfall 17) | Monitor and warn at build time | LOW |
| Phase 3: Lambda Deploy | Deployment races (Pitfall 4) | Concurrency groups, RevisionId locking | CRITICAL |
| Phase 3: Lambda Deploy | Async update-function-code (Pitfall 12) | Wait for LastUpdateStatus: Successful | HIGH |
| Phase 3: AWS Auth | OIDC role chain 1-hour cap (Pitfall 11) | Design for sub-60-min runs | HIGH |
| Phase 4: Step Functions | No pre-flight validation (Pitfall 8) | Use validate-state-machine-definition API | MODERATE |
| Phase 4: Step Functions | envsubst over-replacement | Selective variable substitution | MODERATE |
| Phase 5: API Gateway | put-rest-api overwrites everything (Pitfall 9) | Spec is single source of truth, always create-deployment | HIGH |

---

## Sources

- GitHub Docs: Webhooks, GitHub App Authentication, REST API Rate Limits, Workflow Dispatch API (training data, not live-verified -- official docs URLs: docs.github.com/en/apps, docs.github.com/en/rest)
- AWS Docs: Lambda Container Image Support, STS AssumeRole Session Duration, ECR Authentication, Step Functions API, API Gateway REST API Import (training data -- official docs URLs: docs.aws.amazon.com)
- Digger project (github.com/diggerhq/digger) — reference architecture for GitHub App + IaC dispatch pattern
- pipelines-hub analysis from project memory

**Note:** Web verification tools (WebSearch, WebFetch, Brave Search) were unavailable during this research session. All findings are based on training data knowledge of GitHub and AWS APIs. Confidence levels reflect this limitation. Key claims to verify with live docs:
- `validate-state-machine-definition` API availability and coverage
- Current BuildKit behavior for COPY globs with zero matches
- Exact GitHub webhook retry policy (number of retries, backoff schedule)
- Lambda SnapStart availability for Python runtime
