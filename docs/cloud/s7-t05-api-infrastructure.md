# S7-T05 Hosted API and dispatcher infrastructure (Terraform, plan only)

Terraform for the hosted API (API Gateway HTTP API, Lambda container, role,
logs, throttling) and the worker dispatcher (Lambda, role, optional schedule),
plus an S3 cleanup rule for abandoned uploads. **Nothing was applied.** The
files are `infrastructure/aws/api.tf` (new), `dispatcher.tf` (S7-T04, regated),
and a gated rule in `main.tf`. No NAT, no load balancer, no always-on ECS
service, no function URL, no custom domain.

## Switches

| Variable | Default | Meaning |
| --- | --- | --- |
| `hosted_api_enabled` | **false** | Creates the whole hosted stack (API, API Lambda, role, logs, lifecycle rule) **and** the dispatcher. |
| `demo_token_parameter_name` | `""` | **S7-T06 replaced the old `hosted_api_acknowledge_no_auth` escape hatch.** With `hosted_api_enabled` and this empty, the plan fails. See `docs/cloud/s7-t06-demo-auth.md`. |
| `api_image_digest` | `""` | Immutable `sha256:<64 hex>` of the pushed API image. A tag, an empty value, or a malformed digest fails the plan (precondition). |
| `dispatcher_enabled` | false | Dispatcher alone (S7-T04); also on whenever `hosted_api_enabled` is. |
| `dispatcher_schedule_enabled` | true | The 5-minute reconcile follows the dispatcher. |
| `api_reserved_concurrency` | -1 | S7-T06: no reservation (the account limit is 10); 0 is rejected. See the quota note below. |
| `api_throttle_*`, `api_write_throttle_*` | 2/5, 1/2 | See "Throttling". |
| `abandoned_upload_expiry_days` | 2 (min 2) | Cleanup age. |
| `log_retention_days` | 7 | All log groups. |

With defaults, a plan changes nothing.

## Resources when enabled (22 added, 1 changed)

API: `aws_lambda_function.api`, `aws_iam_role.api_lambda`,
`aws_iam_role_policy.api_lambda`, `aws_cloudwatch_log_group.api`,
`aws_apigatewayv2_api.hosted`, `…_integration.hosted`, six `…_route.hosted`,
`…_stage.hosted`, `aws_cloudwatch_log_group.api_access`,
`aws_lambda_permission.hosted_api`. Dispatcher: `aws_lambda_function.dispatcher`,
`aws_iam_role.dispatcher`, `aws_iam_role_policy.dispatcher`,
`aws_cloudwatch_log_group.dispatcher`, `aws_cloudwatch_event_rule`,
`…_event_target`, `aws_lambda_permission.dispatcher_schedule`. Changed in place:
`aws_s3_bucket_lifecycle_configuration.artifacts`, which only gains one rule (the
plan shows a pure addition; existing rules are untouched). Two data sources are
read at apply time: the Lambda concurrency quota (a warning-only check) and the
policy document. Outputs add `hosted_api_endpoint`, `api_function_name/arn`,
`api_log_group_name`, `api_access_log_group_name`, `dispatcher_function_arn`,
`dispatcher_log_group_name`, all empty while disabled.

## API Lambda

Container image from the **existing** `aws_ecr_repository.api` (immutable tags;
no second repository) referenced as `<repository_url>@<digest>`. arm64, 512 MB,
30 s, default 512 MB ephemeral storage, no reserved concurrency (see S7-T06). Environment is
non-secret only: `CHORDSYNC_API_HOSTING_MODE=lambda`, `CHORDSYNC_RUNTIME_MODE=aws`,
`CHORDSYNC_DISPATCH_MODE=queue`, `CHORDSYNC_UPLOAD_URL_TTL_SECONDS=600`,
`CHORDSYNC_API_STAGING_ROOT=/tmp/chordsync-api`, bucket, jobs table, queue URL,
and `CHORDSYNC_WORKER_DISPATCHER_FUNCTION`. `AWS_REGION` is supplied by Lambda
(it is a reserved name). The API image already sets the web-adapter port and
readiness path. The image is **not pushed**.

The dispatcher function name is now read by the API: `CloudRuntimeConfig` takes
`CHORDSYNC_WORKER_DISPATCHER_FUNCTION`, and when present the queue dispatcher is
built with the asynchronous Lambda trigger from S7-T04. Unset, there is no
trigger (local mode and tests are unchanged).

## IAM boundaries

**API role** (`api_lambda`): S3 `PutObject`, `PutObjectTagging`, `GetObject`,
`DeleteObject` on `jobs/*/source/*`; `GetObject` on `jobs/*/results/*`; `ssm:GetParameter` on the one demo-token parameter and `s3:ListBucket` on the bucket with an `s3:prefix` condition (both added in S7-T06); DynamoDB
`GetItem`, `PutItem` on the jobs table; SQS `SendMessage` on the analysis queue;
`lambda:InvokeFunction` on the dispatcher ARN only; log-stream writes to its own
group. `PutObject` is exercised by the client through the presigned URL, which
carries this role's authority. `PutObjectTagging` is the one action beyond the
requested list: AWS requires it for a `PutObject` that carries an `x-amz-tagging`
header, and the signed upload carries one for lifecycle cleanup (below).
`ListBucket` was ungranted in this ticket and is now a narrow, unverified design in S7-T06. `UpdateItem` is not needed (the repository uses `GetItem` and conditional
`PutItem`), and the API never scans. Not granted: `ListBucket`, `models/*`, ECS,
IAM, `s3:*`, `lambda:*`. A test enforces this exact action set.

**Dispatcher role**: as in S7-T04 (SQS `GetQueueAttributes`; ECS `ListTasks`,
`DescribeTasks`, `RunTask` on the one cluster/family; `PassRole` only for the
worker and ECS execution roles to `ecs-tasks.amazonaws.com`; DynamoDB
`PutItem`/`DeleteItem` on the lock key only; its own logs). No S3,
`ReceiveMessage`, `DeleteMessage`, or `ChangeMessageVisibility`.

The pre-existing `aws_iam_role.api` (ECS-task trust, broader) is untouched and
unused by the Lambda; remove it in a cleanup ticket.

## API Gateway

HTTP API, default HTTPS `execute-api` endpoint, no custom domain, **no CORS**
(the Flutter mobile client is not a browser; add CORS only if a web client
appears). Lambda proxy integration (payload 2.0, 29 s timeout). **Explicit
routes only**: `GET /`, `GET /health`, `POST /analysis/jobs`,
`POST /analysis/jobs/{job_id}/confirm-upload`, `GET /analysis/jobs/{job_id}`,
`GET /analysis/jobs/{job_id}/result`. There is no `$default` catch-all, so the
legacy multipart upload, `/docs`, and `/openapi.json` are answered 404 by the
gateway without invoking Lambda. The stage `$default` auto-deploys and writes
access logs (request id, method, route, status, size, latency, source IP; no
headers or bodies, so a future bearer token never reaches a log).

## Throttling

Stage-wide **2 requests/s, burst 5**; `POST /analysis/jobs` and
`POST …/confirm-upload` **1 request/s, burst 2**. Reasoning: one phone session is
about one create, one confirm, a status poll every ~5 s (0.2/s), and one result
read, so 2/s covers roughly eight simultaneous pollers, far beyond a private
demo. Create writes DynamoDB and signs a URL, and confirm downloads and parses
up to 25 MB, so those are held lower. Worst case at the cap is 2/s, about 5 M
requests a month: roughly $5 of gateway fees plus Lambda, which the $20 budget
alarm would flag first; the throttle bounds it, auth removes the exposure.

## S3 403 decision

`ListBucket` stays ungranted. The adapter now treats only a definite 404 as
"not uploaded" (`409 upload_not_received`, or `409 upload_expired` after the URL
expiry). A 403/`AccessDenied` is never read as absence: it is logged as an error,
the job returns to `awaiting_upload`, and the client gets `503 service_unavailable`.
Tests cover a missing object, an explicit access-denied error, and a permission
misconfiguration through the API.

**Consequence to decide on before deployment.** AWS returns 403 (not 404) for a
missing key when the caller lacks `ListBucket`. So in production, a confirm that
arrives before the upload finishes, or after an expired URL with nothing
uploaded, will come back as `503`, not `409 upload_not_received`/`upload_expired`;
and a job whose upload never happened stays `awaiting_upload` (the expiry
transition never fires). The happy path, rejection, duplicate, and concurrent
cases are unaffected. Choices: (a) accept it, and have the client treat a 503
on confirm as "retry shortly, then create a new job"; (b) grant `s3:ListBucket`
(it cannot be limited to a prefix for HEAD, so the API role could list all keys,
including other jobs' IDs, though not read them); (c) add an S3-event step that
records uploads. This ticket takes (a) and **does not claim real-S3 behavior was
observed**.

## Abandoned-upload cleanup

Every presigned upload carries the signed header
`x-amz-tagging: chordsync-upload=presigned`. The new lifecycle rule
`expire-abandoned-source-uploads` expires objects with **prefix `jobs/` and that
tag after 2 days** (the minimum safe value; queue retention is 24 h, so queued
work cannot outlive it; lifecycle runs in whole days, so actual removal can take
up to about a day longer). Only uploaded sources carry the tag, so playback,
timeline/results, debug, and `models/` objects are never matched. The tag is
not cleared when a job validates: a valid source is only needed until its worker
run, which finishes (or exhausts its retries) well inside two days, and the
worker publishes its own playback copy. The existing 1-day rule for sources
tagged `chordsync-expire-source` is unchanged. Invalid uploads are deleted at
confirm; the rule is the backstop. Versioning is suspended, so expiry removes the
object outright. The rule exists only when `hosted_api_enabled` is set.

## Logging

Explicit log groups, 7-day retention: `/aws/lambda/chordsync-student-demo-api`,
`/aws/lambda/chordsync-student-demo-worker-dispatcher`, and
`/aws/apigateway/chordsync-student-demo-api-access`.

## Dispatcher schedule

`rate(5 minutes)` to the dispatcher with `{"reason":"scheduled_reconcile"}`,
created with the dispatcher by default. Per run with no work: one
`GetQueueAttributes` call and one short log line. With work and no worker: it
starts one task (cost is the Fargate task, unchanged). Retries and missed
notifications are restarted by it. Set `dispatcher_schedule_enabled=false` to rely
on the API nudge alone.

## Estimated idle cost (ap-southeast-1, order of magnitude)

| Item | Idle | Basis |
| --- | --- | --- |
| API Gateway HTTP API | $0 | priced per request; none when idle |
| API Lambda | $0 | no provisioned concurrency; reserved concurrency is free |
| Dispatcher Lambda | ~$0.00 | 8,640 runs a month, about 216 GB-s, inside the free tier |
| EventBridge schedule | $0 | scheduled rules to Lambda are not charged |
| SQS `GetQueueAttributes` | $0 | 8,640 requests, inside the free tier |
| Logs | ~$0.01–0.05 | ~10 MB a month ingested, 7-day retention |
| ECR (API image) | ~$0.01 | ~70 MB at $0.10/GB-month |

About **$0.05 a month idle**, no NAT and no load balancer. Active use adds
fractions of a dollar for gateway and Lambda requests; Fargate time remains the
real cost. This fits the ~$20 monthly budget with no change to it.

## Deployment sequence (after this ticket)

1. Demo-token authentication and job ownership (replaces the acknowledge variable
   with a real check).
2. Decide the S3 403 consequence above.
3. Lambda concurrency: the account limit is **10** and AWS requires 10 unreserved,
   so the default is now `-1` (no reservation); raise the quota (to at least 15)
   before setting a positive value. Never 0 (rejected).
4. Push the API image to ECR; record its digest as `api_image_digest`.
5. `python scripts/build_dispatcher_package.py`.
6. Plan, review, then apply with `hosted_api_enabled=true`.
7. Smoke: health, create, upload with the returned headers (including tagging),
   confirm, status; confirm a worker starts via the dispatcher. Verify real S3
   behavior for an early confirm.

## Validation

`terraform fmt -recursive` and `terraform validate`: valid. Plans were read-only
(`-lock=false`, nothing applied):

| Scenario | Result |
| --- | --- |
| Defaults | 0 to add, 0 to change, 0 to destroy |
| `hosted_api_enabled=true` + acknowledge + placeholder digest | 22 to add, **1 to change** (lifecycle, additive), 0 to destroy; quota warning |
| Enabled without acknowledge | fails (auth precondition) |
| Enabled with a tag as digest | fails (digest precondition) |
| `dispatcher_enabled=true` alone | 7 to add, 0 to change, 0 to destroy |

No ECS service, instance, NAT, load balancer, endpoint, or replacement appears;
the bucket, table, and queue are untouched. The placeholder digest was used for
plan review only and is not a real image.

`tests/test_api_terraform.py` (19) guards these properties statically (flag
default, gating, digest rule, exact IAM actions, routes, throttles, retention,
cleanup rule scope, nothing always-on); mutations of each failed a test.

## Remaining blocker

**Authentication (now implemented in S7-T06).** The API requires a demo bearer
token; the plan fails without `demo_token_parameter_name`. The SSM parameter must
still be created out of band before deployment.
