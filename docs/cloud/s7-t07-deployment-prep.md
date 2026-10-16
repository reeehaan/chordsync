# S7-T07 Deployment preparation and final hosted-API plan

Deployment artifacts and secrets are prepared; the hosted stack is **not
applied**. Authorized mutations were exactly two: one SSM SecureString parameter
and one ECR image. Account `396765697713`, region `ap-southeast-1`, profile
`chordsync-terraform` (`assumed-role/ChordSyncTerraformRole`).

## Demo authentication

| | |
| --- | --- |
| Parameter | `/chordsync/demo/auth/token-verifiers` |
| Type / version | SecureString, version 1, tier Standard |
| Key | AWS-managed `alias/aws/ssm` (no customer-managed key created) |
| Tags | `Project=ChordSync`, `Environment=Demo`, `Purpose=APIAuthentication` |
| Created | create-only (no overwrite); the name did not exist beforehand |
| Principals | `demo-owner`, `demo-reviewer` (owner IDs `demo:demo-owner`, `demo:demo-reviewer`) |
| Entries | 2, each `{id, sha256}`; SHA-256 hex (64 chars) |
| Token length | 43 characters each (256 bits, URL-safe) |

The stored value was read back and compared with the local verifier file: equal,
no plaintext token in it, and each generated token matches one stored hash. The
plaintext tokens are in `~/.chordsync-demo-tokens/tokens.txt` (directory 700,
files 600, outside the repository). They are not in Git, Terraform, the plan, the
image, the dispatcher zip, the SSM value, or any log; a scan of the image's
`/app`, site-packages and `/opt`, and of its environment, found none. Give a token
to a tester through a private channel; delete the file when done. To rotate, build
a new document with `scripts/generate_demo_token.py` and update the parameter
(the API picks it up within 5 minutes).

## API image

| | |
| --- | --- |
| Repository | `396765697713.dkr.ecr.ap-southeast-1.amazonaws.com/chordsync-student-demo/api` (existing, tags immutable, scan on push) |
| Tag | `api-s7t07-runtime1` (the only image) |
| Digest | `sha256:cdfaf6c6795893ae98fd8a0684dc3cb070b6b9001dbbe41b6007667d8c8f982e` |
| Manifest | Docker v2 image manifest (Lambda-compatible, not an index) |
| Platform | linux/arm64, user 10001 |
| Size | 72,043,692 bytes in ECR (about 70.4 MB compressed locally), 196.2 MB uncompressed |
| Local ID | `sha256:bc3382e14a4c6da043c0ec87d0277d0f4493ab51c2a8a2de76448bc2ff1d38ba` (`chordsync-api:s7t07`) |

**The tag does not imply Git reproducibility.** The S7 source is uncommitted
(HEAD is `9161d70`), so this image cannot be rebuilt from a commit. Commit the
work, then rebuild and re-tag from the commit before treating the image as
reproducible; the Terraform input is the digest either way.

ECR scan (complete 2026-10-15): **CRITICAL 0**, HIGH 3, MEDIUM 9, LOW 3, no
undefined. All twelve HIGH/MEDIUM findings are Debian base packages: glibc
`2.41-12+deb13u4` (2 HIGH: CVE-2026-19499, CVE-2026-5435; 9 MEDIUM) and zlib
`1.3.dfsg+really1.3.1-1` (HIGH CVE-2026-85091, no fix, unchanged since S7-T02A).
Docker Scout reports 0C/1H/1M/26L on the same image (zlib HIGH, tar MEDIUM); ECR
uses a different database and additionally lists glibc. No exception was created
and none is needed under the CRITICAL = 0 gate. glibc should be re-checked when
the base image digest is next refreshed.

Local validation before the push (test-only root tag, closed AWS endpoint, fake
credentials): `/` 200, `/health` 200, create and status without a token 401 with
`WWW-Authenticate: Bearer`, create with a token and unreachable SSM 503, `/docs`
and `/openapi.json` 404, legacy upload 404; the image runs as uid 10001 with a
read-only root, no ffmpeg, no Mutagen; startup without the auth parameter refuses.

## Dispatcher package

`build/dispatcher/chordsync-dispatcher.zip` (git-ignored): 7,906 bytes, 6 files
(`backend/__init__.py` and `backend/dispatcher/{__init__,aws,config,dispatcher,handler}.py`),
SHA-256 `e477a4bee54870a161e0c3af7d1c4036f28fdafe47b8276b5529daccbbd6ec06`
(Terraform `source_code_hash` `5HekvuVIcKFh4MOvfRxANvKP2v5HuCdrVSnazLvW7AY=`).
Built twice: identical. It holds no API package, tests, credentials, caches, or
docs, and no token.

## Final Terraform plan

Saved plan (outside the repo, not applied):
`/private/tmp/claude-501/-Users-rehan-Documents-ChordSync/de742a01-ff90-4b4e-a5e4-d8bd3a744be7/scratchpad/final-hosted.tfplan`
(session scratch; regenerate with the inputs below if it is gone).

Inputs: `hosted_api_enabled=true`, `api_image_digest=<digest above>`,
`demo_token_parameter_name=/chordsync/demo/auth/token-verifiers`,
`api_reserved_concurrency=-1`, `dispatcher_enabled=true`,
`dispatcher_schedule_enabled=true`. `terraform fmt` and `validate` pass.

**22 to add, 1 to change, 0 to destroy; no warnings.** Added: the API Lambda,
role, role policy and log group; the HTTP API, integration, six routes, stage
and access-log group; the gateway-to-Lambda permission; the dispatcher Lambda,
role, policy and log group; the schedule rule, target and permission. Changed:
only `aws_s3_bucket_lifecycle_configuration.artifacts` (one rule added; the other
three are unchanged). No ECS service, running task, EC2, NAT, load balancer, VPC
endpoint, SSM resource, or any replacement. The bucket, table, queue, repositories,
and worker task definition are untouched (25 resources no-op).

### API role (exact)

- S3: `PutObject`, `PutObjectTagging`, `GetObject`, `DeleteObject` on
  `…/jobs/*/source/*`; `GetObject` on `…/jobs/*/results/*`.
- S3 `ListBucket` on the **bucket ARN only**
  (`arn:aws:s3:::chordsync-student-demo-artifacts-ccc29fca15314138549f9c799d`), with
  condition `StringLike` `s3:prefix` = `jobs/*/source/*`. No object ARN, not
  `IfExists`, not unrestricted. Not broadened: whether it makes a HEAD return 404
  is still unverified against real S3 (a 403 is reported as 503, which is safe).
- DynamoDB: `GetItem`, `PutItem` on the jobs table.
- SQS: `SendMessage` on the analysis queue.
- Lambda: `InvokeFunction` on the dispatcher ARN (known at apply; a test pins it).
- SSM: `GetParameter` on
  `arn:aws:ssm:ap-southeast-1:396765697713:parameter/chordsync/demo/auth/token-verifiers`.
- Logs: `CreateLogStream`, `PutLogEvents` on its own log group.
- Absent: ECS, `models/*`, `s3:*`, `ssm:*`, Secrets Manager, KMS (the default key
  needs none).

### Dispatcher role (exact)

SQS `GetQueueAttributes`; ECS `ListTasks` (limited to the cluster ARN),
`DescribeTasks`, `RunTask` (the worker family, cluster-limited); `iam:PassRole`
only on `chordsync-student-demo-worker-task` and `chordsync-student-demo-ecs-execution`
to `ecs-tasks.amazonaws.com`; DynamoDB `PutItem`/`DeleteItem` on the jobs table
restricted to `LOCK#worker-dispatch`; its own logs. No S3, `ReceiveMessage`,
`DeleteMessage`, or `ChangeMessageVisibility`.

### Other planned settings

- **Lifecycle rule** `expire-abandoned-source-uploads`: prefix `jobs/`, tag
  `chordsync-upload=presigned`, expire after 2 days. It cannot match `models/`
  (outside the prefix) and playback, results, and debug objects (never tagged).
- **API Gateway:** HTTP API, default HTTPS endpoint, six explicit routes
  (`GET /`, `GET /health`, `POST /analysis/jobs`,
  `POST /analysis/jobs/{job_id}/confirm-upload`, `GET /analysis/jobs/{job_id}`,
  `GET /analysis/jobs/{job_id}/result`), no catch-all, no docs or schema route, no
  custom domain, no CORS. Stage throttle 2 req/s, burst 5; create and confirm
  1 req/s, burst 2. Access logs: request id, method, route, status, size,
  latency, source IP; no headers or bodies; 7-day retention (as are the API and
  dispatcher log groups).
- **API Lambda:** image by digest, arm64, 512 MB, 30 s, 512 MB ephemeral storage,
  reserved concurrency -1 (none). **Dispatcher:** Python 3.13, arm64, 128 MB, 30 s,
  also unreserved. No quota increase was requested (the account limit is 10).
- **Schedule:** `rate(5 minutes)`, target the dispatcher Lambda only, input
  `{"reason":"scheduled_reconcile"}`; no direct ECS target.
- **API environment** is non-secret only: hosting and runtime modes, dispatch mode,
  upload TTL 600, staging `/tmp/chordsync-api`, bucket, table, queue, dispatcher
  name, and the SSM parameter *name*.

## Cost

Actual artifact sizes change nothing material. The 72 MB image costs about
$0.007 a month in ECR. SSM Standard parameters and the AWS-managed key are free.
API Gateway, the API Lambda, and EventBridge cost nothing idle; the dispatcher
runs 8,640 times a month inside the free tier; logs add about $0.01–0.05. Idle
total is about **$0.06 a month**. At roughly 100 analyses a month the hosted stack
adds about $0.1 (a few thousand gateway requests and Lambda seconds); the
estimate stays dominated by Fargate time at about **US$3–4 a month**, unchanged.
No NAT or load balancer.

## AWS state after preparation

Mutated: SSM 1 parameter (`/chordsync/demo/auth/token-verifiers`); ECR 1 image
(`api-s7t07-runtime1`). Verified read-only: Lambda functions 0, API Gateway APIs
0, EventBridge rules 0, ECS tasks 0 and services 0, EC2 instances 0, NAT gateways
0, load balancers 0, VPC endpoints 0, the new IAM roles absent, the queue empty,
no dispatcher lock item, and the S3 lifecycle still 3 rules. Terraform was not
applied and no worker or analysis ran.

## Smoke checklist after apply

1. `GET /health` is 200 and `GET /` is 200 on the output `hosted_api_endpoint`.
2. `POST /analysis/jobs` without a token is 401; with `demo-owner` it is 201.
3. Upload with exactly the returned headers (Content-Type, Content-Length,
   `x-amz-server-side-encryption`, `x-amz-tagging`); a request missing one fails
   at S3.
4. Confirm early (before uploading) and record the result: 409 means the
   `ListBucket` condition works; 503 means it does not (see S7-T06). Then upload and
   confirm: 202, then 200 on repeat, one SQS message.
5. `demo-reviewer` gets 404 for the owner's job (confirm, status, result).
6. The dispatcher starts one worker (check the queue, the task, and the dispatcher
   log line), the job completes, and the worker exits; confirm no task remains.
7. `/docs`, `/openapi.json`, and `/api/v1/audio/upload` are 404 at the gateway.
8. Check throttling (bursts above 5 get 429) and that logs hold no tokens.
9. Roll back with `terraform apply -var hosted_api_enabled=false -var dispatcher_enabled=false`.

## Open items

- The S7 source is uncommitted, so the image is not reproducible from Git yet.
- The `ListBucket` prefix condition is unverified on real S3 (step 4).
- glibc and zlib findings come from the pinned Debian base; refresh the digest and
  re-scan when a fix lands.
- The pre-existing ECS-style `aws_iam_role.api` is unused and can be removed.
