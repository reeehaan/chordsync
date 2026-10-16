# S7-T04 Automatic worker dispatcher

A small Lambda that starts **one** one-shot Fargate worker when the analysis
queue has work and no worker is running. It reads SQS queue attributes only; the
worker stays the only thing that receives, extends, deletes, or releases a
message. Nothing here is deployed: the Lambda and its role exist only as
Terraform behind `dispatcher_enabled = false`, and no schedule is created.

## What happens today (before and after this ticket)

| Case | Behavior |
| --- | --- |
| A. new job queued | Confirm (or multipart create) writes `queued` + `dispatch_pending`, sends the SQS message, clears `dispatch_pending`. No compute starts; before S7-T04 a person ran `ecs run-task`. |
| B. worker succeeds | `analysis_worker_consumer --once` receives one message (visibility timeout, heartbeat extends it), claims `queued → processing`, publishes artifacts, deletes the message, and exits. |
| C. worker releases for retry | A retryable failure goes `processing → failed → queued` (`retry_queued`) and the message is released with timeout 0, so it is visible again at once. The task exits after one delivery, so **nothing is left to pick it up**. This is the gap the dispatcher closes: the next trigger sees `visible > 0` and no worker, and starts one. After `maxReceiveCount = 3` the message goes to the DLQ. |
| D. worker crashes | Heartbeats stop, the message reappears after its visibility timeout, and the job stays `processing`. The next worker sees `processing`, releases the message for 60 s, and the cycle repeats until the DLQ. The dispatcher starts the worker that discovers this, but it does not repair a stuck `processing` job; a reaper is separate future work. |
| E. API queued the job but compute was not started | `queued` + message exist; only compute is missing. The scheduled reconcile starts it. If the *message* send failed, `dispatch_pending` stays set and `reconcile_dispatch --once` resends it (then the dispatcher sees the message). |

The dispatcher adds the missing "start compute" step; it does not touch the
job state machine, the message, or retry counts.

## Responsibility and boundary

The dispatcher answers one question: is work waiting, and is a worker already
active? If work waits and none is active it calls `ecs:RunTask` once; otherwise
it succeeds doing nothing. It never calls `ReceiveMessage`, `DeleteMessage`, or
`ChangeMessageVisibility`, never reads or writes job results or model assets.

The existing `DispatchReconciler` stays responsible only for **re-sending SQS
messages** for `dispatch_pending` jobs (it needs DynamoDB `Scan`). The two are
deliberately separate: "send a missing message" and "start compute" need
different permissions and fail differently. The reconciler accepts an optional
trigger and nudges the dispatcher after it actually sent something.

## Triggers

The same handler serves both; the event is advisory and only `reason` is read.

- **API:** `{"reason": "job_dispatched"}`, sent asynchronously (`InvocationType=Event`)
  after the SQS message is committed.
- **Schedule:** `{"reason": "scheduled_reconcile"}` from an EventBridge rule
  (Terraform, `dispatcher_schedule_enabled`, default 5 minutes).

Behavior is identical except one detail: SQS counters trail a just-sent message
by seconds, so an API-triggered call that sees an empty-looking queue (visible,
in-flight, and delayed all zero) re-reads up to 2 more times, 3 s apart. A
scheduled call does not wait.

## Work detection

`GetQueueAttributes` for `ApproximateNumberOfMessages` (visible),
`…NotVisible` (in flight), and `…Delayed`.

- `visible > 0` → work exists.
- `visible = 0` → no-op, including `in_flight > 0`: a live worker holds it, or
  it returns by itself when its visibility timeout ends and the next trigger
  sees it. The counters are approximate and are never treated as exact truth.

## Worker detection

`ListTasks(cluster, family=chordsync-student-demo-worker, desiredStatus=RUNNING)`
(paginated), then `DescribeTasks`. A task counts when its family matches and
`lastStatus` is `PROVISIONING`, `PENDING`, `ACTIVATING`, or `RUNNING`.
**PENDING counts as active** so a worker that is still starting blocks a second
one. Stopping or stopped tasks and other families are ignored.
Limit: `CHORDSYNC_MAX_WORKER_TASKS` (default **1**, allowed 1–5); at or above it
the result is `worker_already_active` and `RunTask` is not called.

## Race protection

List-then-start races (ECS lists a new task late), so a DynamoDB **lease** guards
the start:

- Item `PK = LOCK#worker-dispatch` in the existing jobs table (no new table; job
  scans filter on `status`, which this item lacks).
- Acquire: one conditional `PutItem`, `attribute_not_exists(PK) OR expires_at < :now`,
  with `owner` and `expires_at = now + 60 s`. Release: conditional `DeleteItem` on
  `owner`.
- Order: queue check → active-worker check (no lock if either says stop) →
  acquire → **re-check active workers under the lock** → `RunTask`.
- After a **successful** start the lease is deliberately *kept* until it expires:
  a cool-down covering ECS's eventually consistent task list. After a failure,
  a lost race, or a no-op under the lock it is released at once.
- A crashed holder blocks starts for at most 60 s (`CHORDSYNC_DISPATCH_LEASE_SECONDS`,
  30–300); there is no permanent lock. The lease is not a worker-run lock, so it
  does not need to outlive a job.
- Consequence of the cool-down: a job queued within 60 s of a worker start waits
  for the next scheduled reconcile (or the worker already running). Acceptable
  for a demo; shorten the lease to tighten it.
- Not used: Lambda reserved concurrency. A new account's default unreserved
  pool is small and reserving would be refused or starve other functions; the
  lease is the guard.

## RunTask configuration

Fixed by environment (validated at cold start; a bad value fails the invocation):

| Setting | Value |
| --- | --- |
| cluster | `chordsync-student-demo-analysis` |
| task definition | the **family** `chordsync-student-demo-worker` (ECS runs its latest ACTIVE revision; no revision is pinned; a `family:revision` value is refused) |
| launch type / count | `FARGATE` / 1 |
| subnets | the worker public subnets (`aws_subnets.worker_public`) |
| security group | `chordsync-analysis-worker` (egress-only) |
| assignPublicIp | `ENABLED` |
| startedBy | `chordsync-dispatcher` |

The call carries no `overrides`, `tags`, or environment. The invocation event
cannot change any of it (tested with a hostile event).

## Failure and recovery

`RunTask` raising, throttling, an ECS `failures[]` entry (for example
`RESOURCE:FARGATE`, "Capacity is unavailable"), or an empty `tasks[]` all return
`run_task_failed` with a short code, release the lease, and leave the queue
untouched. Queue-attribute, ECS-listing, and lease-table errors return
`dependency_unavailable` and start nothing. These are controlled returns, not
Lambda errors, so asynchronous invocation does not retry them; the next
scheduled run does. **No job is marked failed** because the dispatcher failed:
it never touches job state. Configuration errors raise and fail the invocation
loudly.

## API integration seam

`services/worker_dispatch_trigger.py`: `WorkerDispatchTrigger.notify(reason)`,
a no-op default, and `LambdaWorkerDispatchTrigger` (asynchronous invoke, every
error logged and swallowed). `QueueBackedDispatcher` takes an optional trigger
and calls it **after** the message is queued and the job marked dispatched;
exceptions are swallowed, and nothing is called when the enqueue itself failed.
The API response never depends on the dispatcher. It is **not wired** into
`cloud_runtime` composition yet; the API-stack ticket supplies the function name.

## IAM (future Terraform, in `infrastructure/aws/dispatcher.tf`)

| Service | Actions | Scope |
| --- | --- | --- |
| SQS | `GetQueueAttributes` | the analysis queue |
| ECS | `ListTasks` | `*` limited by `ecs:cluster` = the analysis cluster (the API requires `*`) |
| ECS | `DescribeTasks` | `task/<cluster>/*` |
| ECS | `RunTask` | `task-definition/chordsync-student-demo-worker:*`, with `ecs:cluster` condition |
| IAM | `PassRole` | only the worker task role and the ECS execution role, `iam:PassedToService = ecs-tasks.amazonaws.com` |
| DynamoDB | `PutItem`, `DeleteItem` | the jobs table, `dynamodb:LeadingKeys = LOCK#worker-dispatch` |
| Logs | `CreateLogStream`, `PutLogEvents` | its own log group |

Not granted: `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`,
`SendMessage`, any S3, model, `ecs:*`, `iam:PassRole *`, DynamoDB reads or scans.
The API's Lambda role will additionally need `lambda:InvokeFunction` on this
function (API-stack ticket).

## Configuration

`AWS_REGION` (set by the Lambda runtime), `CHORDSYNC_ECS_CLUSTER`,
`CHORDSYNC_WORKER_TASK_DEFINITION`, `CHORDSYNC_WORKER_SUBNET_IDS`,
`CHORDSYNC_WORKER_SECURITY_GROUP_ID`, `CHORDSYNC_SQS_ANALYSIS_QUEUE_URL`,
`CHORDSYNC_DYNAMODB_JOB_TABLE`, optional `CHORDSYNC_MAX_WORKER_TASKS` (1) and
`CHORDSYNC_DISPATCH_LEASE_SECONDS` (60). All IDs are pattern-checked; no
credential is read or accepted.

## Packaging

`backend/dispatcher/` (`config`, `dispatcher`, `aws`, `handler`), standard
library plus `boto3` from the Lambda runtime. Handler
`backend.dispatcher.handler.lambda_handler`, **Python 3.13, arm64, 128 MB, 30 s**.
`scripts/build_dispatcher_package.py` makes a reproducible zip of just those
files: **7.9 KB** (no container image). It does not import the API package.
boto3 is the runtime's version, not pinned (the calls used are stable; the tests
validate request shapes against the installed botocore models).

## Logging

One JSON line per invocation: `no_work`, `worker_already_active`,
`lock_not_acquired`, `worker_started` (with `task_arn`), `run_task_failed` (with
a short code or ECS reason), `dependency_unavailable`, plus queue counts and the
trigger reason. No credentials, message bodies, receipt handles, or raw AWS error
text.

## Tests

`tests/test_worker_dispatcher.py` (76): no work, one message, many messages,
in-flight only; PENDING/RUNNING/PROVISIONING/ACTIVATING block, stopped and
other-family tasks ignored; exact `RunTask` arguments and a hostile event;
**8 simultaneous dispatchers (slow `RunTask`, unlisted new task) start exactly
one task**; cool-down, lease expiry, crashed holder, release when a worker
appears under the lock; `RunTask` exception and `failures[]`; queue, ECS, and
lease-table errors; API vs schedule parity and bounded re-reads; request shapes
checked with botocore stubs against the real service models; configuration
validation; zip contents and standalone import; IAM and Terraform guards; the
real `lambda_handler` for no-work / work / active worker; the API seam and the
reconciler boundary. Mutating the lease guard (no condition, ignored result, no
re-check, failure not released), PENDING counting, and the work check each fail
tests; removing the lease makes the 8-way test see 8 `RunTask` calls.

Not run: the Lambda runtime emulator (the handler was invoked directly with fake
clients) and anything against real AWS.

## Cost

The scheduled no-work path is one `GetQueueAttributes` call, about 8,600 a month
at a 5-minute rate (free-tier SQS requests are 1 M). Lambda: ~0.1–0.3 s at
128 MB, a few hundred GB-seconds a month, inside the free tier. ECS List/Describe
calls are free. DynamoDB is touched only when work exists. Fargate cost is
unchanged: one task per run, scale to zero. Logs are a few lines per run at
7-day retention.

## Terraform

`dispatcher.tf` is new and validated (`terraform validate`: valid). A read-only
plan (`-lock=false`, nothing applied) with defaults shows **no resource changes**
and a single new empty output; with `dispatcher_enabled=true` it adds 4
resources, and with the schedule 7. No resource starts compute (no ECS service,
no task, no `RunTask` at apply time). Terraform was not applied.

## Limitations

- SQS counters are approximate; the schedule is the backstop for lag.
- A stuck `processing` job after a worker crash is not recovered (case D).
- Worker concurrency 1 means a long job delays other jobs; the queue holds them.
- The cool-down can delay a very recent job to the next scheduled run.
- The first deployment must prove `RunTask` permissions and PassRole against real ECS.

## Next

The Terraform API stack (HTTP API, hosted Lambda role with `lambda:InvokeFunction`
on the dispatcher, throttling, the demo-token SSM parameter, S3 lifecycle rules,
and the `ListBucket`/403 decision from S7-T03), then demo-token auth.
