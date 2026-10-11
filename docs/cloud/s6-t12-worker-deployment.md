# S6-T12 worker deployment for the controlled runtime test

This ticket changes the worker task definition only. It creates no ECS
service, task, EC2 instance, GPU, NAT Gateway, load balancer, network, or model
object, and it does not apply Terraform.

## Approved image

```text
396765697713.dkr.ecr.ap-southeast-1.amazonaws.com/chordsync-student-demo/worker@sha256:9c027714e07bad4bb1916f364c04c5ea2ce8545d5be41babfecdcbcbd65f11c5
```

- Tag: `worker-24025ef0-guard2` (repository is tag-immutable and private).
- Platform: `linux/arm64`.
- Scan: complete; CRITICAL findings are exactly CVE-2026-52490,
  CVE-2026-95210, and CVE-2026-88647, covered by the exceptions in
  `docs/security/container-exceptions.md` until 2026-11-09.

Terraform references the image by digest through `worker_image_digest`, whose
validation rejects anything except `sha256:<64 hex>`. A tag cannot be supplied.
Changing the digest requires a new scan review and, if CRITICAL findings
remain, a new exception bound to that digest.

## Task definition

Setting | Value | Reason
--- | --- | ---
Compatibility | `FARGATE` (`EC2` only if `worker_gpu_count > 0`) | A one-shot RunTask needs no EC2 instance and bills only while it runs.
Runtime platform | `LINUX` / `ARM64` | Matches the image config.
CPU / memory | 4096 (4 vCPU) / 16384 MiB | See sizing below.
Network mode | `awsvpc` | Required by Fargate.
Ephemeral storage | Fargate default, 20 GiB | Holds the image and the staged models, see below.
Command | `python -m backend.api.app.analysis_worker_consumer --once` | The consumer requires `--once`.
Logs | `awslogs` to `/chordsync/student-demo/worker`, prefix `worker` | Existing 7-day log group.

### Sizing

Pipeline stages run sequentially, each in its own subprocess, all forced to
CPU. The memory peak is Demucs `htdemucs` separating up to six minutes of
44.1 kHz stereo audio on CPU, which needs several GiB. WhisperX `small` with
`int8` and BTC need much less. 8 GiB risks an OOM kill during separation, and
16 GiB leaves headroom without an evidence-free jump to 30 GiB. Four vCPU
parallelise PyTorch and CTranslate2 inference. The ~4m47s Mac runtime is not a
Linux/ARM64 measurement: record wall-clock and peak memory per stage in the
first controlled run, then right-size it (for example to 4 vCPU / 12 GiB).

Ephemeral storage: the image is about 5.1 GB uncompressed. The staged models
are under 3 GB (Whisper small about 0.5 GB, English wav2vec2 about 0.4 GB,
htdemucs about 0.1 GB, BTC small, plus about 1.2 GB for each extra alignment
language). The per-job workspace is under 0.5 GB. This fits within 20 GiB.

### Execution mode: one-shot

Each task receives at most one delivery, processes it, and exits. With an
empty queue it exits after one 20 s long poll. This is cheaper and safer for
the first test than a long-running consumer: the cost of a test is bounded and
explicit, and no idle task needs to be found and stopped. The consumer CLI
supports only `--once`.

### Environment

All values are non-secret. Credentials come from the task role through the
ECS container credentials endpoint, not from environment variables or STS
calls.

```text
CHORDSYNC_RUNTIME_MODE=aws
CHORDSYNC_DISPATCH_MODE=queue
AWS_REGION=ap-southeast-1
CHORDSYNC_S3_BUCKET=<aws_s3_bucket.artifacts.id>
CHORDSYNC_DYNAMODB_JOB_TABLE=<aws_dynamodb_table.jobs.name>
CHORDSYNC_SQS_ANALYSIS_QUEUE_URL=<aws_sqs_queue.analysis.url>
CHORDSYNC_WORKSPACE_ROOT=/tmp/chordsync
CHORDSYNC_BTC_PYTHON=/opt/chordsync/venvs/btc/bin/python
CHORDSYNC_BTC_SOURCE=/opt/chordsync/models/btc/source
CHORDSYNC_BTC_CHECKPOINT=/opt/chordsync/models/btc/btc_model.pt
CHORDSYNC_BEAT_PYTHON=/opt/chordsync/venvs/beats/bin/python
CHORDSYNC_WHISPERX_EXECUTABLE=/opt/chordsync/venvs/whisperx/bin/whisperx
CHORDSYNC_DEMUCS_EXECUTABLE=/opt/chordsync/venvs/demucs/bin/demucs
XDG_CACHE_HOME=/opt/chordsync/cache
HF_HOME=/opt/chordsync/cache/huggingface
TORCH_HOME=/opt/chordsync/cache/torch
HF_HUB_OFFLINE=1
```

These paths match the image's own `ENV` and directory layout. The cache and
model directories are owned by the non-root `chordsync` user. They are set
explicitly so the deployment does not depend on image defaults without anyone
noticing.

## Worker IAM review

The worker task role is unchanged by this ticket:

- DynamoDB `GetItem`, `PutItem`, `UpdateItem` on the job table only. Versioned
  state transitions are conditional `PutItem` calls, so no extra action is
  needed.
- S3 `GetObject` on `jobs/*/source/*`, and `GetObject`/`PutObject` on
  `jobs/*/playback/*` and `jobs/*/results/*`. There is no `ListBucket` and no
  `DeleteObject`. Production code never calls `delete_transient_source`, and
  source expiry is lifecycle-tag driven.
- SQS `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`,
  `GetQueueAttributes` on the analysis queue only.
- The execution role pulls only from the worker repository and writes only to
  the worker log group.

No wildcard service actions are granted.

Known gaps for S6-T13:

1. Model bootstrap needs `s3:GetObject` on `models/*`. Add it scoped to that
   prefix together with the bootstrap code, not before.
2. Without `s3:ListBucket`, `HeadObject` on a missing key returns 403, not 404.
   The worker's existence checks run after it has written the object, or for a
   redelivered job whose artifacts should exist. A missing artifact therefore
   surfaces as a provider error instead of `False`. This is acceptable for the
   first test, so the role was not broadened.
3. The SQS adapter receives with a 900 s visibility timeout, overriding the
   queue's 1200 s, and the consumer does not heartbeat. A run longer than
   15 minutes would make the message visible again. With exactly one one-shot
   task this causes a later duplicate receive, not concurrent processing.
   Measure the run and add the visibility heartbeat before any concurrency.

## Model assets

The image ships no model weights, and there is no NAT, so nothing may be
fetched from the public internet at runtime. With `HF_HUB_OFFLINE=1`, a missing
Hugging Face model fails fast instead of hanging.

Asset | Needed by | Must be staged before analysis?
--- | --- | ---
BTC source tree | `CHORDSYNC_BTC_SOURCE` (default estimator `btc`) | Yes. The chords stage fails without it.
BTC checkpoint `btc_model.pt` | `CHORDSYNC_BTC_CHECKPOINT` | Yes.
Whisper `small` CTranslate2 model (Hugging Face cache) | WhisperX ASR and language detection | Yes. The lyrics stage fails without it.
WhisperX VAD model | WhisperX segmentation | Yes, unless the pinned `whisperx==3.8.6` ships it in-package. Verify while staging.
English wav2vec2 alignment model (torchaudio bundle in `TORCH_HOME`) | Alignment for `en` | Yes for English test tracks. A download failure is a stage failure; the no-align retry only covers languages with no default model.
Other-language alignment models (Hugging Face wav2vec2) | Multilingual mode (production default) | Only for languages to be tested. Stage them in batches.
Demucs `htdemucs` weights (torch hub checkpoint) | Vocal separation | Yes. Separation runs before lyrics.
madmom models | Beats | No. Shipped inside the madmom package in the image.

Nothing can be fetched lazily from the public internet. "Lazy" here can only
mean "fetched from the private S3 prefix on first use". For the first test,
stage everything up front.

## Model delivery design

```text
private S3 models/ prefix (SSE-S3, HTTPS-only, no public access)
  → bootstrap step at task start (task role, s3:GetObject on models/*)
  → copy into /opt/chordsync/models and /opt/chordsync/cache on ephemeral storage
  → verify every file against the release manifest's SHA-256
  → exec the --once consumer; on any mismatch exit non-zero before receiving
```

Bootstrap must finish before `ReceiveMessage`, so a bad asset never consumes
a delivery attempt. Implement it as a small entry step in the repository, then
build and scan a new image digest. That digest needs its own approval.

Suggested key layout, versioned and immutable per release:

```text
models/manifests/<release>.json             # path → sha256, size, licence note
models/btc/source/<btc-commit>/...           # upstream source tree
models/btc/checkpoints/<sha256>/btc_model.pt
models/whisperx/asr/small-ct2/<revision>/... # Hugging Face snapshot layout
models/whisperx/vad/<revision>/...
models/alignment/torchaudio/wav2vec2_asr_base_960h/<sha256>/...
models/alignment/hf/<language>/<revision>/...
models/demucs/htdemucs/<sha256>/...
```

Release identifiers are pinned digests or revisions, never `latest`. EFS is
not justified: about 3 GB copied from same-region S3 per one-shot task is
cheap, and EFS adds a mount target, security group, and storage cost.

## Networking

The worker needs outbound HTTPS only, to:

- ECR API and ECR DKR, plus S3 for image layers (execution role)
- CloudWatch Logs (execution role)
- S3, SQS, and DynamoDB (task role)

STS is not required: task-role credentials come from the ECS agent endpoint.
No inbound port is needed.

Option | Cost | Assessment
--- | --- | ---
Public subnet, public IP, no inbound SG rules, egress TCP 443 only | Public IPv4 hourly charge only while the task runs | **Recommended.** The default VPC already has public subnets in all three AZs. No NAT and no fixed cost.
Private subnet + VPC endpoints | S3/DynamoDB gateway endpoints are free. ECR API, ECR DKR, Logs, and SQS interface endpoints are billed per hour per AZ even when idle | Exceeds the USD 20/month target on its own for a scale-to-zero demo.
Private subnet + NAT | NAT hourly plus per-GB charges | Rejected for budget.

Recommendation: `PUBLIC_TASK`. When S6-T13 adds networking, create a dedicated
security group (for example `chordsync-analysis-worker`) with no ingress and
egress TCP 443 to `0.0.0.0/0`. Optionally add the free S3 and DynamoDB gateway
endpoints so that data traffic stays on the AWS network. S3 stays private
through Block Public Access, the HTTPS-only policy, and IAM scoping.

## Naming

This ticket creates no new resources. The existing task-definition family
`chordsync-student-demo-worker`, roles, repository, and log group keep their
names, because renaming them would replace live resources. New resources in
S6-T13 should use names such as `chordsync-analysis-worker` (security group),
`/chordsync/worker` (new log groups), and `models/` within the existing
artifact bucket. Names must not contain `student-demo`, `smoke`, or `test`.
