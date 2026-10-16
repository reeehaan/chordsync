# S7 API hosting design

Design for hosting the ChordSync API in AWS for the private student demo. The
worker pipeline is proven (job `1633d423-…` completed on Fargate,
2026-10-13). This document covers the API the Flutter app calls. Nothing here
is deployed yet.

## 1. Current API inventory

FastAPI app `backend.api.app.main:app`, Python 3.11, served by uvicorn.

| Method | Path | Request | Response | AWS (cloud mode) | Local disk | Heavy ML |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/`, `/health` | – | JSON | none | no | no |
| POST | `/analysis/jobs` (local mode) | multipart `title` + `audio` (≤ 25 MB) | `AnalysisJobResponse` (202) | DynamoDB PutItem/conditional Put; S3 PutObject (source); SQS SendMessage | **yes**: stages the file, validates its real format and duration (≤ 360 s) in Python with in-house parsers, then reads it into memory | no |
| POST | `/analysis/jobs` (hosted) | JSON `title`, `filename`, `declared_size_bytes`, `content_type?` | `UploadInitiationResponse` (201) | DynamoDB conditional Put; presigned S3 PUT (local signing, no call) | no | no |
| POST | `/analysis/jobs/{id}/confirm-upload` (hosted) | – | `AnalysisJobResponse` (202, or 200 on repeat) | DynamoDB conditional writes; S3 HeadObject/GetObject/DeleteObject; SQS SendMessage | **yes**, `/tmp` staging only | no |
| GET | `/analysis/jobs/{id}` | – | `AnalysisJobResponse` | DynamoDB GetItem | no | no |
| GET | `/analysis/jobs/{id}/result` | – | `SharedTimeline` (~35 KB) | DynamoDB GetItem; S3 HeadObject/GetObject | no | no |
| POST | `/api/v1/audio/upload` | multipart | `AudioUploadResponse` | none | **yes**: writes to `storage/uploads` | no |

- There is no playback endpoint. The app plays its own local copy of the
  imported file, so the published playback artifact is not needed for
  single-device use.
- The API is lightweight. In hosted mode, importing the app loads only the
  three pure data-model modules behind `SharedTimeline` (`analysis.fusion`,
  `analysis.lyrics.models`, `analysis.temporal`). The analysis pipeline and its
  ffmpeg wrapper are not imported until used, and no ML runs in
  the API.
- The legacy `/api/v1/audio/upload` route is unauthenticated and writes to
  local disk. It must not be exposed by a hosted API.
- `backend/api/Dockerfile` is separate from the worker image. It is now a
  digest-pinned Debian Trixie slim image with FastAPI and boto3, and
  no ffmpeg (S7-T02, S7-T02A, S7-T02B: `docs/cloud/s7-t02-api-lambda-packaging.md`).

The runtime split holds: **API = lightweight HTTP + validation; worker =
ML.**

## 2. Hosting options

Prices are ap-southeast-1, from the AWS Pricing API on 2026-10-13.

| | A. API Gateway HTTP API + Lambda | B. ECS Fargate API service | C. App Runner |
| --- | --- | --- | --- |
| Idle monthly cost | **$0** | ≈ $9 (0.25 vCPU / 0.5 GB ARM always on) + $3.65 public IPv4, plus an ALB (≈ $16–20) or VPC-link plumbing | ≈ $3.2 provisioned memory minimum |
| Request cost | HTTP API $1.25/M; Lambda ARM $0.20/M + $0.0000133/GB-s | none beyond the fixed cost | vCPU $0.0809/h while active |
| Cold start | 1–3 s first request (container image + FastAPI import) | none | none while provisioned |
| Containers / FastAPI | Container image (≤ 10 GB) with AWS Lambda Web Adapter runs the existing uvicorn app unchanged | native | native |
| Upload limit | **HTTP API payload 10 MB; Lambda synchronous request 6 MB.** A 25 MB upload cannot pass through. | ALB has no practical limit | proxied through the service |
| Networking | no VPC, no NAT | VPC, public subnet or NAT, load balancer | managed |
| Operations | low (no servers) | medium–high | low |
| Demo suitability | **good** (scales to zero) | over budget at idle | **closed to new customers** (announced 2026-03-31, effective 2026-04-30) |

App Runner is excluded because the service no longer accepts new customers. AWS
announced the change on 2026-03-31, and the AWS App Runner release notes state
it is closed to new customers starting **April 30, 2026**
(<https://docs.aws.amazon.com/apprunner/latest/relnotes/relnotes.html>). AWS
recommends ECS Express Mode instead. That mode provisions an ECS service on
Fargate with an Application Load Balancer, so it has the same always-on cost
profile as option B.
An always-on ECS service would use most of the US$20 budget while idle.

## 3. Selected architecture

```text
Flutter (HTTPS, demo access token)
  → API Gateway HTTP API (default execute-api URL, route throttling)
  → Lambda (ARM64 container image: existing FastAPI app + AWS Lambda Web Adapter, no VPC)
      ├─ DynamoDB  (job state, conditional writes, existing adapter)
      ├─ S3        (presigned POST for source upload; read results)
      ├─ SQS       (SendMessage: one analysis message per job)
      └─ Lambda    (async invoke: worker dispatcher)
  → Flutter uploads audio directly to private S3 with the presigned POST

Worker dispatcher Lambda (reserved concurrency 1)
  triggered by: API async invoke after dispatch, plus EventBridge rate(5 minutes) safety net
  → if queue has visible messages AND no running worker task → ecs:RunTask (1 task)
  → existing one-shot ARM64 Fargate worker (task definition revision 3)
  → S3 timeline/playback + DynamoDB COMPLETED
```

Why Lambda: idle cost is zero, the existing FastAPI app runs mostly
unchanged, there is no VPC or NAT, and HTTPS comes with the API. The payload
limit is the one real constraint, and the presigned upload removes it while
also keeping 25 MB bodies out of the API.

## 4. Upload flow (presigned S3 POST)

The current single multipart request cannot pass the 10 MB / 6 MB limits, so
uploads move to a three-step flow:

1. `POST /analysis/jobs`: JSON `{title, filename, content_type, size_bytes}`.
   The API validates the extension (`.wav`/`.mp3`/`.m4a`), the content type,
   and `size_bytes ≤ 25 MB`. It creates the job in `AWAITING_UPLOAD` (a state
   that already exists) and returns `{job_id, upload: {url, fields}, expires_in}`.
2. Flutter POSTs the file directly to S3 using the returned form fields.
3. `POST /analysis/jobs/{id}/uploaded`. The API checks the object
   (HeadObject: size, type), downloads it to Lambda `/tmp`, validates it with
   `inspect_audio` (real format must match the extension, duration ≤ 360 s,
   decodable), records size and ETag, then dispatches
   exactly one SQS message through the existing `QueueBackedDispatcher`
   (idempotent: `dispatch_pending` plus conditional state writes). Invalid
   uploads become FAILED with the existing error codes, and the object is
   deleted.
4. Flutter polls `GET /analysis/jobs/{id}`, then `GET …/result`.

Validation moved from ffprobe to a Python validator in S7-T02A: the API image
has no ffmpeg or ffprobe. The checks are the same (supported format, size,
duration) with an added requirement that the file's real format matches its
extension. Its limits are listed in the S7-T02 document.

### S3 presigned POST restrictions

- **Exact key:** `jobs/{server-generated uuid}/source/input.{ext}`. The key is
  chosen by the API, never by the client.
- **Policy conditions:** `content-length-range` 1–26,214,400 bytes;
  `Content-Type` equal to the validated type;
  `x-amz-server-side-encryption = AES256`.
- **Expiry:** 10 minutes. The bucket stays private: Block Public Access,
  BucketOwnerEnforced (ACLs disabled, so no public ACL is possible), and the
  HTTPS-only policy.
- **Signing:** with the API role, which holds `s3:PutObject` only on
  `jobs/*/source/*`. No ListBucket.
- **Isolation:** one job maps to one source key. A URL cannot write any other
  key. Re-uploading to the same key within the expiry affects only that
  caller's own job. The ETag recorded at confirmation lets the worker detect a
  later swap; adding that check is a follow-up.

## 5. Authentication

| Option | Verdict |
| --- | --- |
| No authentication | Rejected: public upload endpoint, cost and abuse risk |
| **A. Demo access token** | **Now.** The tester enters it in app settings; it is not compiled into the app and is not an AWS credential. FastAPI middleware checks `Authorization: Bearer` against a hash in SSM Parameter Store (SecureString, free tier). It can be rotated or revoked per tester. Combined with HTTP API route throttling and Lambda reserved concurrency. |
| B. Cognito User Pool + HTTP API JWT authorizer | **Before any public or multi-user release.** It uses the existing `owner_id` field and `users/{owner}/jobs/…` key layout already in `ArtifactKeyFactory`. |

Job IDs are random UUIDs, and every route also requires the token.

## 6. IAM boundaries

**API Lambda role** (replaces the existing `api` role's `ecs-tasks` trust with
`lambda.amazonaws.com`):

- DynamoDB: `GetItem`, `PutItem`, `UpdateItem` on the jobs table. Drop the
  current `Scan`; dispatch reconciliation stays out of the API.
- S3: `PutObject` (presigned POST signing), `GetObject`, `DeleteObject` on
  `jobs/*/source/*`; `GetObject` on `jobs/*/results/*`. No `models/*`, no
  ListBucket, no `s3:*`.
- SQS: `SendMessage` on the analysis queue only.
- Lambda: `InvokeFunction` on the dispatcher only.
- SSM: `GetParameter` on the demo-token parameter only.
- Logs: its own log group only.
- No ECS permissions.

**Dispatcher Lambda role:**

- `sqs:GetQueueAttributes` on the analysis queue.
- `ecs:ListTasks`, `ecs:DescribeTasks`, and `ecs:RunTask` on the worker
  task-definition family, conditioned to the analysis cluster.
- `iam:PassRole` on the worker task role and the execution role, conditioned
  on `iam:PassedToService = ecs-tasks.amazonaws.com`.

**Worker:** unchanged.

## 7. Worker trigger

| Option | Assessment |
| --- | --- |
| A. API calls RunTask | Simple, but gives the API ECS and PassRole rights, and does not cover retries: a released message has no task to consume it. |
| B. SQS event source on the queue | A Lambda event source mapping would itself consume the messages the worker must receive, which breaks the existing claim, visibility, and retry semantics. |
| **C. Dispatcher Lambda** | **Selected.** It is invoked asynchronously by the API after dispatch and every 5 minutes by EventBridge. If messages are visible and no worker started by the dispatcher is running, it starts exactly one task. Reserved concurrency 1 prevents racing duplicates. It covers retries and missed dispatches, scales to zero, and keeps the API IAM minimal. |

Concurrency is initially 1. Each `--once` task handles one job, and the next
dispatch picks up the next message. Worst-case extra latency for a queued
retry is about 5 minutes.

## 8. Networking and HTTPS

- The API Lambda and the dispatcher run outside a VPC. S3, DynamoDB, SQS, ECS,
  and SSM are reached through public AWS endpoints over TLS. No NAT and no VPC
  endpoints are needed.
- The worker is unchanged: public subnet, public IP, egress-only security
  group.
- HTTPS uses the default `https://{id}.execute-api.ap-southeast-1.amazonaws.com`
  endpoint. No custom domain or certificate is needed.

## 9. Flutter integration

| Area | Today | Change |
| --- | --- | --- |
| Base URL | `CHORDSYNC_API_BASE_URL` dart-define, default `http://127.0.0.1:8000` (`analysis_api_config.dart`, used in `main.dart`) | Keep the dart-define. Release builds must pass the HTTPS URL and refuse a localhost default (flavor or assert). |
| Auth | none | Settings field for the demo token (secure storage). Dio interceptor adds `Authorization: Bearer`. |
| Upload | one multipart POST (`analysis_api_client.dart`) | Three calls: create (JSON), direct presigned POST to S3 with progress, confirm. |
| Polling | every 1 s, 15-minute timeout (`analysis_job_poller.dart`) | Every 3–5 s; keep the timeout. |
| Result | `GET …/result` | unchanged |
| Playback | local copy (`analyzed_session_library.dart`) | unchanged |
| Timeouts | Dio defaults (none) | connect/receive timeouts; retry idempotent GETs |
| Android | `INTERNET` permission only in the debug manifest | Add it to `android/app/src/main/AndroidManifest.xml`. Release builds cannot reach the network today. |
| iOS/macOS | ATS exception only for 127.0.0.1; macOS network-client entitlement present | none needed for HTTPS |

User-facing states map onto the existing `AnalysisJobStatus` (queued /
processing / completed / failed), which the API already derives from
internal states:

- **Uploading:** the client, during the S3 POST.
- **Queued:** created, awaiting_upload, queued, and also `retry_queued`. A
  retry stays "Queued" or "Analyzing" and is never shown as a failure.
- **Analyzing:** processing.
- **Completed**, and **Failed** (terminal failure only, with an existing
  error code).

## 10. Security review

- Private S3 only. Presigned POST is limited to one key, size, type, SSE, and
  a 10-minute expiry. No public ACLs, no public models.
- HTTPS only. API Gateway is TLS, and the bucket denies insecure transport.
- No AWS credentials or secrets in the Flutter bundle. The demo token is
  entered at runtime, revocable, and not an AWS credential.
- No direct DynamoDB or SQS access from Flutter.
- Least-privilege, separate roles for the API, dispatcher, and worker.
- Abuse controls: token, HTTP API throttling, Lambda reserved concurrency,
  25 MB / 360 s validation, one Fargate task at a time, and the existing US$20
  budget alert.
- **Blockers before hosting:**
  1. Disable `/api/v1/audio/upload` in hosted mode.
  2. Implement token auth.
  3. Move the API image to a digest-pinned base and scan it.
  4. Change the API role's trust and scope.
- **Before public release:** Cognito and per-user ownership.

## 11. Cost estimate (100 analyses per month)

| Item | Basis | ≈ US$/month |
| --- | --- | --- |
| API Gateway HTTP API | ~10k requests (polling every 5 s) × $1.25/M | 0.01 |
| API Lambda | ~1.2k GB-s at 512 MB (polls + 100 upload confirms) + requests | 0.02 |
| Dispatcher Lambda | 8,640 scheduled runs + 100 async | < 0.01 |
| Fargate worker | 100 × ~315 s billed × (4 vCPU + 16 GiB ARM) ≈ $0.020 each | 2.0 |
| Public IPv4 (worker only) | 100 × ~5.4 min × $0.005/h | 0.05 |
| S3 | models 0.96 GB + ~1.6 GB new source/playback per month, plus requests | 0.1 (growing about 0.04/month) |
| DynamoDB on-demand | ~10k reads, ~1k writes | < 0.01 |
| SQS | a few hundred requests | < 0.01 |
| CloudWatch Logs | small, 7-day retention | < 0.1 |
| ECR | ~6 worker images × ~1.6 GB × $0.10/GB-month | ~0.95 (≈ 0.16 if old tags are pruned) |
| **Total** | | **≈ $3–4/month**, idle ≈ $1.1 |

This is well within US$20. There is no NAT, ALB, always-on service, or GPU.
Retries add about $0.02 each.

## 12. Risks

- Lambda cold starts add about 1–3 s to the first request after idle.
- The extra confirm round trip adds complexity, and the validation step
  downloads up to 25 MB inside the Lambda (in-region, typically under 2 s).
- Source swap after confirmation: the recorded ETag allows a worker-side
  check in a later ticket.
- A shared demo token can leak. Mitigate with per-tester tokens, rotation, and
  throttling. It is not suitable for public release.
- Up to about 5 minutes of extra latency on retries (dispatcher schedule).
- The CVE exceptions expire 2026-11-09 and apply to the worker image only.
  The API image no longer contains libtiff or GnuTLS (S7-T02A), so it needs no
  such exception. Its remaining findings are in the S7-T02 document.

## 13. Implementation tickets

1. **S7-T02 / S7-T02A / S7-T02B API Lambda packaging (done):** ARM64 Lambda container
   (digest-pinned base + AWS Lambda Web Adapter, no ffmpeg); Python media
   validation; clean 503 for AWS outages; legacy upload route disabled in
   hosted mode; `/tmp` staging; scanned and tested in a local Lambda emulator.
   No deploy.
2. **S7-T03 Presigned upload flow (done):** create / confirm endpoints using
   `inspect_audio` for confirmation, tests; local mode unchanged. See
   `docs/cloud/s7-t03-presigned-upload.md`. (S7-T03's brief numbers the worker
   dispatcher Lambda as the next ticket, S7-T04; this list's order differs.)
3. **S7-T04 Worker dispatcher Lambda (done):** starts one Fargate worker when
   the queue has work; `docs/cloud/s7-t04-worker-dispatcher.md`. Terraform is
   written but disabled. (This list's old step 5 "Worker dispatcher" is
   superseded.)
3b. **Demo-token auth (done, S7-T06):** `docs/cloud/s7-t06-demo-auth.md`.
   Original scope: middleware, SSM parameter, tests.
4. **S7-T05 Terraform API stack (plan-only, done):** `docs/cloud/s7-t05-api-infrastructure.md`; gated off by default; not applied. Original scope: HTTP API, Lambda, API IAM role, throttling,
   SSM parameter; plan, review, apply.
5. **S7-T06 Worker dispatcher:** Lambda, EventBridge schedule, IAM; dry-run
   with an empty queue.
6. **S7-T07 Flutter cloud client:** three-step upload, token setting, polling
   interval, timeouts, Android INTERNET permission, release base URL.
7. **S7-T08 Physical-phone end-to-end test** with an approved track.
