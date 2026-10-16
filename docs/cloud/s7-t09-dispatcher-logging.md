# S7-T09 Dispatcher structured logging fix

The deployed dispatcher now writes its structured INFO events to CloudWatch.
Only the dispatcher function's code changed in AWS. No analysis ran and no
compute started.

## Root cause

The dispatcher logs one JSON line per invocation through
`logging.getLogger("chordsync.dispatcher")` (`no_work`, `worker_started`,
`worker_already_active`, `lock_not_acquired`, and the error events). That logger
had no level of its own, so it inherited the root logger's. The Lambda Python
runtime leaves the root logger at WARNING (the function uses `LogFormat: Text`
with no application log level, and `AWS_LAMBDA_LOG_LEVEL` is unset). Every
`logger.info(...)` call was therefore dropped before reaching the runtime's
handler, while warnings and errors still appeared. A small simulation of the
runtime's setup (root handler, root level WARNING) reproduced it exactly. This is
why S7-T08 showed only START/REPORT lines even though the worker was started.

## Fix

One line in `backend/dispatcher/dispatcher.py`:
`logger.setLevel(logging.INFO)`, on the dispatcher's own logger. A record created
at INFO then passes this logger's check and reaches the runtime's handler (handlers
do not re-check the root level). Chosen over the Terraform route (`logging_config`
with `application_log_level`) because that requires switching the function to JSON
log format, which would wrap our JSON lines inside another JSON object and is a
resource change. The code fix needs no Terraform logging change.

Not touched: the root logger, boto3, botocore, urllib3 (none enabled for DEBUG),
the event contents, or the log schema. Events carry only `event`, `reason`,
`task_arn`, `detail`, and the three queue counts; no tokens, message bodies,
receipt handles, credentials, verifier documents, or raw AWS error text.

## Tests (`tests/test_worker_dispatcher.py`, now 86)

Run under a Lambda-like setup (a root handler at level WARNING): the dispatcher
logger's effective level is INFO; `no_work` is emitted with its reason and
counts; `worker_started` is emitted at INFO with the task ARN; `worker_already_active`
and `lock_not_acquired` are emitted; failures still log at ERROR; every event's
fields are within the allowed set and hostile input (a fake receipt handle, body,
bearer token, and provider error text) never appears; and only the dispatcher
logger was changed (no `basicConfig`, no DEBUG, no root-logger access). Removing
the `setLevel` line fails six of them.

## Package and Terraform

| | |
| --- | --- |
| Zip | `build/dispatcher/chordsync-dispatcher.zip`, 8,059 bytes, 6 files |
| SHA-256 | `f382488f0c15743843b0baf91328b93273c0386eaa5822b88e2d86cf8d58d48a` |
| Terraform `source_code_hash` | `84JIjwwVdDhDsLr5Eyi5MnPAOG6qWCK4ji2Gz41Y1Io=` (matches the deployed `CodeSha256`) |
| Reproducible | two builds, identical bytes |
| Previous zip | `e477a4be…ec06`, 7,906 bytes |

The first plan showed two changes: the dispatcher function **and**
`aws_iam_role_policy.api_lambda`. The policy would have been identical after the
apply, but Terraform marked it "known after apply" because the policy read the
dispatcher function's ARN from the function resource, so any change to the function
deferred it. To keep this deployment dispatcher-only, `api.tf` now builds that ARN
from the function name (`local.dispatcher_arn`, the same string as before). The
IAM scope is unchanged, and a test now pins the construction and that the policy
never references the function resource.

Saved plan: **0 to add, 1 to change, 0 to destroy**, changing only
`aws_lambda_function.dispatcher[0]` (`source_code_hash`, `last_modified`). No
API Gateway, API Lambda image, S3 lifecycle, worker task definition, networking,
SQS, or DynamoDB changes. `terraform fmt` and `validate` pass. The plan file is
session scratch (`dispatcher-logging.tfplan`); it was applied as saved.

## Deployed smoke (no compute)

Invoked once with `{"reason":"scheduled_reconcile"}` on an empty queue.

- Result: status 200, no function error, response
  `{"outcome": "no_work", "task_arn": null, "detail": null}`.
- CloudWatch (log level `[INFO]`):
  `{"event": "no_work", "reason": "scheduled_reconcile", "visible": 0, "in_flight": 0, "delayed": 0}`.
  The run before the deployment shows only START/END/REPORT, confirming the change.
- ECS tasks started: none. Queue 0/0 before and after; DLQ 0.

`worker_started` was not forced (no paid Fargate run); it is covered by the tests
and will appear on the next real analysis.

## State afterwards

Running ECS tasks 0 (one stopped task in history, the S7-T08 job's); queue and
DLQ empty; a fresh `terraform plan` shows 0 to add, 0 to change, 0 to destroy; the
API is healthy (`/health` 200, `/` 200) and still answers 401 without a token on
create and status; the API Lambda still runs the `api-2ed4afa-s7` image.

## Notes

- The change is not committed. HEAD is still `2ed4afa`, so the deployed
  dispatcher zip now differs from that commit until a follow-up commit (the zip is
  git-ignored; the source diff is the one `setLevel` line, its tests, and the
  `dispatcher_arn` change in `api.tf` and its test).
- The scheduled run every 5 minutes now emits one short INFO line per invocation
  (about 8,600 lines a month, well within the free log tier at 7-day retention).

## Next

AWS account hardening (MFA, an admin role, budget and alarms, CloudTrail), which
was deferred until this deployment check.
