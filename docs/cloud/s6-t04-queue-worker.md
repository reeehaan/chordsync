# S6-T04 queue and external worker execution seam

No AWS queue, DLQ, container module, or other resource is created by this
ticket. All SQS behavior is tested with an injected fake client.

## Current and target flow

Cloud-ready module flow:

```text
Flutter
  ↓
API
  ↓
durable job state
  ↓
ArtifactStorage
  ↓
AnalysisJobQueue
  ↓
worker
  ↓
RealAnalysisProcessor
  ↓
result publication
  ↓
playback + timeline artifacts
```

Future AWS mapping:

```text
Flutter → FastAPI → DynamoDB → S3 → SQS → ECS worker → S3 → DynamoDB
```

The current local Flutter workflow deliberately remains on
`InMemoryAnalysisJobRepository`, `LocalAnalysisInputStorage`, and
`InProcessAnalysisJobExecutor`. The router constructs those modules inside the
API process, and completed `SharedTimeline` objects are still returned from API
memory. Cloud API wiring therefore remains incomplete: upload must later create
a `CloudJobRecord`, publish the source artifact, dispatch through the queue, and
retrieve results from artifact storage. Doing only one of those steps would
break polling or result retrieval.

## Message and queue semantics

Schema version 1 contains only `job_id`, `source_artifact_key`, and `title`, plus
the schema version. Deterministic compact JSON contains no audio, timeline,
credentials, model paths, secrets, or absolute filesystem paths.

`AnalysisJobQueue` owns receipt handles through `QueueDelivery`. Its interface
supports enqueue, receive, acknowledge, release, and visibility extension.
`InMemoryAnalysisJobQueue` supplies explicit ack/retry and duplicate delivery
for deterministic tests. `SqsAnalysisJobQueue` uses one-message long polling,
an initial configurable visibility timeout, delete acknowledgement, and
`ChangeMessageVisibility` for release or heartbeat extension.

Dispatch validates that the private source artifact exists before conditionally
changing `AWAITING_UPLOAD` to `QUEUED`. The API never changes it to `PROCESSING`;
only a worker claim does. DynamoDB/SQS cannot provide one atomic transaction, so
an enqueue failure can leave a durable `QUEUED` record without a message. A
future reconciliation module must redispatch such records idempotently.

## Worker idempotency and retry policy

The one-delivery consumer applies these rules:

- `QUEUED`: conditionally claim as `PROCESSING`, incrementing attempt metadata;
- `PROCESSING`: release without duplicate execution;
- `COMPLETED` with retained artifacts: acknowledge without analysis;
- `CANCELLED` or stale state: acknowledge and discard;
- partial deterministic publication: retry overwrites the same artifact keys;
- successful publication alone changes `PROCESSING` to `COMPLETED`.

Temporary storage/queue failures and transient processing infrastructure errors
are retryable. Malformed/unsupported messages, corrupt inputs, and deterministic
validation failures are non-retryable. The existing `max_attempts` default is
three. Exhaustion leaves the job `FAILED` with a safe error and acknowledges the
delivery; provider exception details are never copied to user-visible state.

## Visibility, DLQ, and cancellation

Analysis can take several minutes. Production must not use a short fixed SQS
visibility timeout. The adapter supports visibility extension so an ECS worker
can heartbeat while heavy processing runs. The initial 15-minute adapter
default is only a conservative development value, not a production decision;
set the final value and heartbeat cadence after Linux/AWS benchmarking.

Provision the future main queue with a DLQ and `maxReceiveCount = 3`, consistent
with the application attempt limit. Poison messages that cannot be decoded are
left unacknowledged for SQS redrive. Operational DLQ handling should safely mark
a known, non-terminal job `FAILED` without exposing raw payload or exception
details.

Cancellation before claim is acknowledged without work. Cancellation observed
after analysis but before publication skips publication. Interrupting an
already-running ML subprocess is intentionally not implemented; that requires
cooperative processor cancellation and safe process-group termination in a
later ticket.
