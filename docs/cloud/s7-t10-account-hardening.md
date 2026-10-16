# S7-T10 AWS account hardening

Scope: identity, cost protection, alarms, auditing, IAM review, and Fargate spend
safeguards for the single development account `396765697713` (alias
`aws-rehan-v4`, region `ap-southeast-1`). No application code, queue, worker,
authentication, or networking changed. Applied through Terraform
(`infrastructure/aws/hardening.tf`): **19 added, 2 changed, 0 destroyed**, then a
drift plan of 0/0/0. The hosted API was not disabled.

## Findings

| # | Severity | Finding | Status |
| --- | --- | --- | --- |
| 1 | **High** | IAM user `rehan` has AdministratorAccess (group `admin`), a console password, **no MFA device**, and an active access key (`AKIAVYYI…FVIZ`, created 2026-10-08, used continuously). A leaked key or password is full account control. | Manual action + lockout-prone follow-up (below) |
| 2 | **High** | The hosted API is public on the internet (`https://1vdojhtkg8.execute-api.ap-southeast-1.amazonaws.com`) and protected only by two demo bearer tokens. Each unauthenticated request is cheap (a 401), but a leaked token allows job creation and Fargate runs. Throttled (2 req/s) and bounded (below), not eliminated. | Accepted; recommend disabling between sessions |
| 3 | Medium | `ChordSyncTerraformRole` carries `AdministratorAccess` in addition to the custom provisioning policy, and its trust (user `rehan`) has no MFA condition, so the access key reaches admin through the role even if the user is MFA-guarded. | Recommendation (lockout-prone) |
| 4 | Medium | Alarms and budget had nowhere to deliver: no SNS topic or subscriber, and no budget existed. | Fixed except the address (needs your email) |
| 5 | Medium | No CloudTrail trail (only the 90-day Event history). | Fixed |
| 6 | Medium | A running Fargate worker has no hard time limit (see Fargate safeguards). | Recommendation |
| 7 | Low | Inactive access key `AKIAVYYI…HSO5` (created 2025-10-10, last used 2026-05-24, CloudFormation, ap-south-1). | Recommend deleting |
| 8 | Low | Group `new-admin` holds AdministratorAccess and has no members. | Recommend deleting |
| 9 | Low | No account password policy. | Fixed |
| 10 | Low | Unused legacy roles from earlier projects (`challenge1-role-*`, `my-lambda-function-role-*`, `sam-first-project-*`, `todo-crud-app-*`, `DemoRoleForEC2`) and the unused Terraform-managed `chordsync-student-demo-api-task` role. | Recommend cleanup |
| 11 | Low | Worker role grants `dynamodb:UpdateItem`, which the code never calls. | Recommendation (needs a smoke run) |
| ok | – | Root account: **MFA enabled** (virtual device `Authapp`), **no root access keys**. | No action |

## Identity

Root MFA is on and root has no keys, so the root target state is already met.
There is one IAM user (`rehan`) and one role used for provisioning
(`ChordSyncTerraformRole`, trust: user `rehan`, 1-hour sessions). The CLI profile
`chordsync-base` holds the user's key; `chordsync-terraform` assumes the role. No key,
password, or MFA seed was read or written.

**Manual action required (not done, cannot be automated safely):** register an MFA
device for IAM user `rehan`:

1. Sign in to the console as `rehan`; open IAM → Users → `rehan` → Security
   credentials → Multi-factor authentication → Assign MFA device.
2. Choose "Authenticator app", scan the QR code, enter two consecutive codes.
3. Sign out and back in with MFA to confirm.

**Then, in this order** (each step is reversible; do not skip the checks):

1. `terraform apply -var enforce_admin_mfa=true` (with the usual deployment
   variables). It attaches a deny-unless-MFA policy to group `admin`. It excludes
   the actions needed to register a device and `sts:AssumeRole`, so the Terraform
   role workflow keeps working. Before this step a console sign-in without MFA would
   be limited to registering a device, which is why it is **off by default**.
2. To make the access key stop being an admin credential, require MFA in the
   `ChordSyncTerraformRole` trust policy (`"Bool": {"aws:MultiFactorAuthPresent":
   "true"}`) and add `mfa_serial = arn:aws:iam::396765697713:mfa/<device>` to the
   `chordsync-terraform` profile; verify `aws sts assume-role` works with a code
   **before** relying on it. Trade-off: every session needs a code, including
   agent-driven runs. The role is not Terraform-managed, so this is a manual edit.
3. Optionally detach `AdministratorAccess` from the role once a plan/apply run shows
   `ChordSyncTerraformProvisioningPolicy` is enough (the user keeps admin through
   group `admin`, so re-attaching stays possible).
4. Delete the inactive key `…HSO5` and the empty group `new-admin` when convenient.

Why no admin role was added: with one developer, a second admin principal adds
moving parts without removing the real risk (the long-lived key). The simplest secure
model is MFA on the user plus MFA-gated role assumption, as above.

## Cost protection

- **Budget** `chordsync-student-demo-monthly`: USD 20 a month, tracked now.
  Expected spend is about US$3–4 at 100 analyses, so USD 20 is a ceiling for a
  runaway, not a target. Alerts (once an address is set): actual-spend emails at
  25% (USD 5), 50% (10), 80% (16), 100% (20), plus a forecasted-100% email.
  Budgets alert; they never stop spending.
- **Pending your input:** neither the budget alerts nor the alarms deliver anywhere
  yet. Set `alert_email` (a variable, never hard-coded) and apply; AWS then emails a
  subscription confirmation that must be clicked. No address was invented or taken
  from account metadata.
- Exposure by service: Fargate dominates (about US$0.01 per analysis, 4 vCPU and
  16 GB for ~2.5 minutes); Lambda, API Gateway, EventBridge, SQS, DynamoDB
  (on-demand), and CloudWatch are free-tier-sized; S3 is cents (a 2.9 MB source,
  playback copy, and result per job; sources expire in 2 days); ECR about
  US$0.015 for the two API images. No NAT, load balancer, or endpoints.

## Monitoring

All alarms notify the `chordsync-student-demo-alerts` SNS topic (open to CloudWatch
and EventBridge from this account only).

| Created | Why it matters |
| --- | --- |
| Queue depth (existing, now notifying) | work stuck for 15 minutes |
| DLQ non-empty (existing, now notifying) | a job exhausted its retries |
| API Lambda `Errors` ≥ 1 / 5 min | unhandled exceptions or timeouts |
| Dispatcher Lambda `Errors` ≥ 1 / 5 min | configuration or runtime failure |
| `dispatcher-failures` (log metric `run_task_failed` or `dependency_unavailable`) ≥ 1 / 15 min | Lambda sees these as normal returns, so only the log reveals a persistent RunTask/capacity/SSM failure |
| `worker-start-burst` (log metric `worker_started`) ≥ 10 / hour | loop detector; one start per job is normal |
| EventBridge rule: worker task stopped with a non-zero exit or `TaskFailedToStart` → SNS | a failed analysis worker, with no polling |

Both log filters and the event pattern were checked with the read-only test APIs
before applying. Deliberately not created: Lambda throttle alarms (API Gateway
limits traffic to 2 req/s and no reserved concurrency exists to throttle), latency
and 4xx/5xx-rate alarms (the 401s and 404s are expected behavior), Container
Insights (billed per task), and a "task running too long" alarm (no native metric;
see below). Six metric alarms and two custom metrics stay inside the CloudWatch free
tier.

## CloudTrail

Trail `chordsync-management-events`: multi-region, global service events,
management events (read and write), log-file validation on, logging active.
Destination: new private bucket `chordsync-student-demo-cloudtrail-f2c8a14f67cdd110a3603679ee`
(all public access blocked, SSE-S3, BucketOwnerEnforced, HTTPS-only, writable only by
CloudTrail for this trail). Logs expire after 90 days. No data events (S3 objects,
Lambda invokes), no insights, no CloudWatch Logs delivery, no KMS. Cost: the first
copy of management events is free; storage is a few megabytes a month. Not
organization-wide (no Organization exists).

## IAM least-privilege review

Reviewed against the proven workflow (HEAD 404 before upload, confirm, dispatcher
start, worker publish, result read) and the code's real calls.

| Role | Verdict |
| --- | --- |
| `…-api-lambda` | Matches use: S3 put/tag/get/delete on source, get on results, one narrow `ListBucket`, DynamoDB `GetItem`/`PutItem`, `SendMessage`, invoke the dispatcher, read the one SSM parameter, own logs. No change. |
| `…-worker-dispatcher-lambda` | Minimal: `GetQueueAttributes`, cluster-scoped ECS actions, `PassRole` for two roles to `ecs-tasks` only, lock-item `PutItem`/`DeleteItem`, own logs. No change. |
| `…-worker-task` | Needs queue consume, source read, playback/results write, model read. `dynamodb:UpdateItem` is unused (the repository uses only `get_item`, conditional `put_item`; there is no `update_item` anywhere in `backend/`). Removal is justified, but it edits the live worker's role, so verify with one real job. **Retained for now.** |
| `…-ecs-execution` | Pull from the worker repository, write worker logs; `ecr:GetAuthorizationToken` must be `*`. No change. |
| `…-api-task` (old ECS-style) | Unused by anything; broader (`Scan`, `UpdateItem`, source `PutObject`). Safe to destroy via Terraform (2 resources), but destroys are not applied automatically. Recommend removal. |

Nothing was narrowed in this ticket, so the S3 behaviors, job-owner isolation, and
worker pipeline are untouched.

## Fargate spend safeguards

Existing controls, confirmed in code and by the S7-T08 run: concurrency 1 (any
PENDING/RUNNING worker blocks a new one); a DynamoDB lease with a 60-second
cool-down and a recheck under the lock; queue visible-count gating (no work means no
RunTask); `maxReceiveCount` 3 to the DLQ; the worker exits after one delivery;
visibility heartbeats stop after 3600 s; a 5-minute schedule (at most 288 dispatcher
runs a day).

| Failure mode | Behavior | Bound |
| --- | --- | --- |
| Poison message or crash loop | each receive is one worker; the third receive moves it to the DLQ (alarm fires) | ≤ 3 tasks, about US$0.03 |
| A job left `processing` by a crash | later workers see `processing`, release for 60 s, and each counts as a receive | ends at the DLQ |
| Counters show work that is already gone | a task starts, polls 20 s, exits | about US$0.01 per 5 minutes only while counters stay wrong; the burst alarm flags it |
| Lease expiry race | the lease outlives ListTasks lag; a recheck runs under it | duplicate start not seen |
| Uncertain RunTask (timeout after ECS accepted it) | the exception path releases the lease at once; a retry could start a second task before ECS lists the first | at most one extra US$0.01 task; the recommended fix is to keep the lease on an exception whose outcome is unknown (release only on a definite `failures[]`) |
| Scheduler plus API nudge together | the lease serializes them | none |
| Async invoke retries | the dispatcher returns normally on RunTask errors, so Lambda does not retry them | none |
| **A hung worker** | heartbeats stop after an hour, but nothing stops the task: it bills (about US$0.19 an hour) until it exits | **no hard cap today**; the budget alerts are the only guard |

No flaw requires redesign. Smallest safeguards recommended (none changed here, since
they touch dispatcher or worker task behavior): (1) a wall-clock limit on the worker
(for example wrapping the task command in `timeout 4500`, or letting the dispatcher
`StopTask` workers older than about 75 minutes, which adds `ecs:StopTask`); (2) keep the
lease after an uncertain RunTask exception. Both are small, testable follow-ups.

## Terraform

Applied the saved plan exactly: **19 added, 2 changed, 0 destroyed**.

Added: SNS topic and its policy; budget; API-errors, dispatcher-errors,
dispatcher-failures and worker-start-burst alarms; two log metric filters; the
failed-worker EventBridge rule and target; the CloudTrail bucket (public access
block, SSE, ownership, lifecycle, policy), the trail; the account password policy.
Changed: the two existing SQS alarms (notification action only). The MFA guard
(`enforce_admin_mfa`) and the email subscription exist only when their variables are
set. No application resources, roles, or policies changed; the post-apply drift plan
is 0 to add, 0 to change, 0 to destroy. `terraform.tfvars.example` and the README
now describe `alert_email` instead of `budget_alert_email`.

## State afterwards

ECS running tasks 0; queue and DLQ empty; `/health` 200; protected routes still 401
without a token; both Lambdas present on the same code; no compute started; all six
alarms in OK; the SNS topic has no subscribers yet.

## Remaining risks

1. The public hosted endpoint, token-gated only (high). Disable between sessions with
   `terraform apply -var hosted_api_enabled=false -var dispatcher_enabled=false`.
2. The IAM user `rehan` has no MFA and an active admin-capable key (high): manual.
3. No notification address (alerts have no recipient until `alert_email` is set).
4. Credential cleanup: the inactive key, the empty `new-admin` group, legacy roles.
5. No hard time limit on a running worker.
