# S7-T08 Hosted deployment and controlled smoke test

Applied exactly the saved plan `final-hosted-2ed4afa.tfplan` (22 added, 1
changed, 0 destroyed) at about 10:51 UTC on 2026-10-16, then ran one controlled
smoke test with one analysis job. Source: Git `2ed4afa`; API image
`api-2ed4afa-s7`, digest `sha256:bc9b30b6d5d87006bdac420e5614c747ac91e24598f11addb53f6efe073e82ca`.

Endpoint: `https://1vdojhtkg8.execute-api.ap-southeast-1.amazonaws.com`
(API id `1vdojhtkg8`). It is public but token-gated.

## Smoke results (in the requested order)

| Step | Result |
| --- | --- |
| `GET /`, `GET /health` | 200, 200 |
| `/analysis/*` without a token, with an unknown token, wrong scheme | 401, same body, `WWW-Authenticate: Bearer` |
| `/docs`, `/openapi.json`, `/redoc`, legacy upload | 404 from the gateway |
| Create job as `demo-owner` | 201, `awaiting_upload`, presigned PUT, 600 s, owner `demo:demo-owner` |
| **Confirm before uploading** (twice) | **409 `upload_not_received`**, job stays `awaiting_upload` |
| `demo-reviewer` confirm / status / result on that job | 404 / 404 / 404 (same body as a nonexistent job) |
| Upload with the returned headers | S3 200, SSE AES256, tag `chordsync-upload=presigned` |
| Confirm | 202 `queued`; repeat confirm 200 (idempotent); `demo-reviewer` confirm 404 |
| Dispatcher | API nudge invoked it 4 s after confirm; it started one Fargate task (`startedBy chordsync-dispatcher`) |
| Worker | one task, task definition `chordsync-student-demo-worker:3`, 4 vCPU / 16 GB; model bootstrap, then chords 18.4 s, beats 5.2 s, separate 22.2 s, lyrics 15.4 s, fuse 0.4 s; exit code 0; stopped about 97 s after start |
| Job | `completed` in about 3.2 min from creation; attempts 1; `published`; result available |
| Result (owner) | 200, bpm 89.55, 4/4, beat source madmom, lyric source whisperx-small, 13 bars, 4 lyric lines, first bars C then G (matches the synthetic input) |
| Result (reviewer / no token) | 404 / 401 |

The audio was a synthetic 33 s WAV (C-G-Am-F pad at 90 bpm plus macOS `say`
speech), generated for this test; no real song was uploaded. Exactly one job and
one worker task ran.

## What the real S3 test showed

**The narrow `ListBucket` statement works.** A HEAD for the not-yet-uploaded
source key returned a true 404, so the API answered `409 upload_not_received`
(not a 403/503). The S7-T06 caveat is resolved: `s3:prefix = jobs/*/source/*`
on the bucket ARN is sufficient for the API's HEAD.

## State afterwards

Queue 0/0/0 and DLQ 0; no ECS tasks or services; no EC2, NAT, load balancer,
or VPC endpoint. Terraform reports no resource changes (`0 add, 0 change,
0 destroy`; the exit code is 2 only because the quota check's scoped data
source is always re-read at apply). The two Lambdas exist, neither with reserved
concurrency; the stage and the two write routes carry the planned throttles; no
CORS, no custom domain; the schedule is `rate(5 minutes)`, ENABLED, targeting
only the dispatcher; all four log groups have 7-day retention; the lifecycle
configuration has four rules, including `expire-abandoned-source-uploads`. The
DynamoDB table holds the job, the dispatcher lock item, and one pre-existing
ownerless job from 2026-10-12 (invisible to every caller in hosted mode). No
plaintext token appears in the API, dispatcher, worker, or access logs.

Left in S3 from the smoke job: `source/input.wav` (tagged for removal after 2
days), `playback/audio.wav`, and `results/timeline.json`.

## Findings

1. **The dispatcher's structured INFO events are not written.** Lambda's default
   log level is WARNING, so `worker_started` (with the task ARN) and the other
   events never reach CloudWatch; only START/REPORT lines appear. Behavior is
   correct (the task started), but the evidence trail is thin. Fix: set the
   `chordsync.dispatcher` logger to INFO, rebuild the zip, and apply.
2. **Cold start:** the first API request spent 4.9 s in init (`REPORT` showed
   4,922 ms), inside the 30 s function limit; the first dispatcher run took 6.7 s.
3. The worker's job-level logs go to `/chordsync/student-demo/worker`; they show
   stage timings but no job-level success line after `fuse`.

## Rollback

`terraform apply -var hosted_api_enabled=false -var dispatcher_enabled=false`
(removes the stack; the SSM parameter and ECR images are not Terraform-managed).
