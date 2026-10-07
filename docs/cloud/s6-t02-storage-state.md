# S6-T02 durable state and artifact storage

S6-T02 adds local adapters that prove the cloud storage/state interfaces without
provisioning AWS resources or changing the Flutter-facing contract.

## Current coupling audit

- `AnalysisJobService` creates a UUID, writes the upload through the
  `AnalysisInputStorage` interface, and stores an `AnalysisJobRecord` through
  the `AnalysisJobRepository` interface.
- `InMemoryAnalysisJobRepository` is process-local and stores the complete
  `SharedTimeline` in memory after completion.
- `LocalAnalysisInputStorage` is path-backed. Its interface still returns a
  local path because the current in-process worker requires one.
- `InProcessAnalysisJobExecutor` coordinates state and calls an
  `AnalysisProcessor` with that local path.
- `RealAnalysisProcessor` owns subprocess order and writes job-local analysis
  artifacts under its configured workspace root.
- `backend.api.app.analysis_worker` is an independent command over the same
  processor, but it still consumes a local input path.
- The current workspace layout is deterministic and isolated by job ID. Cleanup
  is not coupled to execution yet.

The existing modules remain unchanged for local application compatibility. The
new cloud modules establish real seams with two adapters each: in-memory and
SQLite job repositories, plus protocol and local filesystem artifact storage.

## Durable job domain

`CloudJobRecord` supports:

- states: `CREATED`, `AWAITING_UPLOAD`, `QUEUED`, `PROCESSING`, `COMPLETED`,
  `FAILED`, `CANCELLED`, and `EXPIRED`;
- job ID, title, timestamps, state, and current stage;
- logical source, playback, and timeline object keys;
- safe error code/message;
- attempt count, maximum attempts, and last-attempt timestamp;
- decoded duration and file type;
- nullable future owner ID;
- optimistic-lock version.

Audio bytes and timeline JSON are deliberately absent. The Flutter API can keep
its current four public states until a later version explicitly exposes more.

`CloudJobRepository.save` requires an expected state and record version. The
local adapters reject stale/invalid writes. A future DynamoDB adapter should use
the same conditional-write semantics.

## Artifact storage interface

`ArtifactStorage` exposes only `put_bytes`, `read_bytes`, `exists`, and `delete`.
It returns size, content type, and SHA-256 metadata. Filesystem paths are an
implementation detail of `LocalArtifactStorage`; job records store logical keys.

Artifact roles:

- `SOURCE_UPLOAD`: transient upload staging, approximately 24 hours after
  successful publication;
- `PLAYBACK_AUDIO`: exact analyzed recording, retained while the saved result
  exists;
- `TIMELINE_RESULT`: SharedTimeline JSON, retained with playback;
- `OPTIONAL_DEBUG_ARTIFACT`: private, short-lived, and disabled unless needed;
- analysis intermediates: worker-local only, never object-storage artifacts.

Local emulation uses `storage/cloud_local/`, already excluded by the repository
Git ignore and Docker build context.

## Private object-key design

Demo keys do not pretend a user identity exists:

```text
jobs/{job_id}/source/input.{ext}
jobs/{job_id}/playback/audio.{ext}
jobs/{job_id}/results/timeline.json
jobs/{job_id}/debug/{safe-name}
```

Raw filenames never form identifiers. A future owner-scoped key factory produces:

```text
users/{user_id}/jobs/{job_id}/...
```

Artifact roles and leaf names stay unchanged.

## Publication and idempotency

Required order:

1. analysis finishes into worker-local output;
2. publish exact source bytes as `PLAYBACK_AUDIO`;
3. publish SharedTimeline as `TIMELINE_RESULT`;
4. verify both objects exist;
5. conditionally transition `PROCESSING` to `COMPLETED` with both logical keys.

If publication fails, the durable state remains `PROCESSING`; deterministic
keys make retry safe. A playback object left by a timeline failure is overwritten
with the same analyzed bytes on retry. A duplicate delivery of an already
completed job only succeeds when both required retained artifacts exist and does
not rerun publication.

## Cleanup

`ArtifactCleanup` has two explicit operations:

- delete the validated job-local workspace after success or failure;
- delete only the transient source artifact after the retention decision.

It never deletes playback or timeline artifacts. No scheduler is introduced.
Future S3 lifecycle configuration should expire source-prefix objects about 24
hours after successful publication. Because S3 lifecycle rules cannot inspect
job state directly, production should either tag successful source objects with
an expiry intent or delete them through a scheduled cleanup module. Playback and
timeline prefixes must not receive that expiration rule.

## Future S3 adapter mapping

- Bucket name is environment/deployment configuration, never stored in the
  Flutter response or hard-coded in domain records.
- `ArtifactKey.value` maps directly to the private object key.
- `ArtifactMetadata.content_type`, size, and SHA-256 become object metadata;
  S3 ETag is recorded only as transport metadata because multipart ETags are not
  content hashes.
- Block Public Access remains enabled; no public ACLs or URLs.
- Use default server-side encryption (SSE-S3 initially, or SSE-KMS if the later
  security design requires customer-managed keys).
- API-layer authorization owns future presigned upload/download creation. The
  storage adapter never returns public URLs.
- Upload size, decoded-duration validation, and checksum verification remain
  application responsibilities.

## Future DynamoDB mapping

Private-demo table:

```text
PK = JOB#{job_id}
```

One item stores the scalar `CloudJobRecord` fields and optimistic version. No
audio or timeline JSON is stored. Required first-version queries are only:

- get one job by ID;
- conditionally create one job;
- conditionally update one job by current state/version.

No GSI is needed for those queries. A future authenticated design can introduce
owner-scoped access such as `PK = USER#{user_id}`, `SK = JOB#{job_id}` or a
separate owner index after its actual query pattern is known.

## Security and remaining integration work

- Object references reject absolute paths and traversal segments.
- Keys are deterministic from validated job IDs and supported extensions.
- All objects are private by design.
- No AWS SDK, credentials, bucket, table, public URL, or cloud resource exists.
- SQLite proves restart survival but is not wired as the default local API
  repository yet; doing so also requires result retrieval through artifact
  storage instead of the existing in-memory `SharedTimeline` field.
- The current executor must later stage source bytes into `SOURCE_UPLOAD`, call
  the publisher after analysis, and invoke cleanup only after durable publication.
