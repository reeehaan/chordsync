# S6-T05 cloud API integration and dispatch reconciliation

No AWS resource is created by this ticket. Cloud behavior is exercised through
in-memory/SQLite adapters and fake queue clients without network requests.

## Implemented runtime paths

Local behavior remains:

```text
Flutter → FastAPI → local upload → in-process executor → in-memory timeline
        → existing status/result routes → PracticeScreen
```

The cloud-ready path is:

```text
Flutter → multipart FastAPI upload → validated temporary staging
        → durable CloudJobRecord → private ArtifactStorage source
        → AnalysisJobQueue → worker → retained playback + timeline
        → durable COMPLETED state → FastAPI validated result retrieval
```

The router depends on one `AnalysisApplication` interface. The local adapter
wraps the existing `AnalysisJobService` and executor. The cloud adapter owns
durable creation, source publication, dispatch, compatible status mapping, and
timeline retrieval. It does not execute analysis in the API process.

Multipart upload is temporary compatibility behavior. The future flow remains:

```text
Flutter → create job → authorized presigned S3 upload → confirm upload
        → SQS → worker → S3 result/playback → authorized access
```

No object key, bucket name, queue URL, database key, provider response, or local
path is returned by the public job contract. Playback keys remain durable
internal references; Flutter continues playing its imported app-owned file.

## Durable create and reconciliation

Cloud creation validates the same WAV/MP3/M4A, 25 MB, and 360-second limits in
temporary server-owned staging. It then creates a durable `CREATED` record,
publishes the exact source bytes, records duration/type/source key, and moves to
`AWAITING_UPLOAD`. Dispatch verifies the object, conditionally moves to
`QUEUED` with `dispatch_pending=true`, sends the versioned queue message, then
clears the marker.

The marker closes the DynamoDB/SQS transaction gap:

- crash or provider failure before enqueue leaves a discoverable pending job;
- crash after enqueue but before marker clearing may enqueue a duplicate;
- reconciliation scans pending queued jobs, re-enqueues, and conditionally
  clears the marker;
- the worker's conditional claim and completed-artifact checks make duplicates
  safe;
- source artifacts remain retained, so reconciliation needs no re-upload.

`python -m backend.api.app.reconcile_dispatch --once` performs one bounded
reconciliation pass. Scheduling it with EventBridge/Lambda or another runtime
is future infrastructure work.

## Status and result compatibility

Internal `CREATED`, `AWAITING_UPLOAD`, and `QUEUED` map to public `queued`.
`PROCESSING` and `COMPLETED` map directly. Failed, cancelled, or expired records
map to the existing safe public `failed` status.

Completed timeline bytes are loaded through `ArtifactStorage`, decoded as
UTF-8, parsed as JSON, and validated with the existing `SharedTimeline` model.
Missing, corrupt, and temporarily unavailable artifacts produce stable safe
errors; arbitrary stored bytes are never returned.

## Cleanup and retained data

- rejected staging uploads are removed by the established validator;
- staging copies are removed after source publication attempts;
- failed dispatch never deletes the durable source;
- worker intermediates remain worker-owned and are deleted after processing;
- playback and timeline artifacts remain retained after successful publication;
- source remains eligible for the separately designed approximately 24-hour
  post-success cleanup policy.

## Legacy classification

- `InMemoryAnalysisJobRepository`: **ACTIVE_LOCAL**;
- `LocalAnalysisInputStorage`: **STILL_REQUIRED** for local uploads and cloud
  multipart validation/staging during this compatibility phase;
- `InProcessAnalysisJobExecutor`: **ACTIVE_LOCAL**.

They must not be deleted until Flutter moves to presigned upload and the local
development experience has an intentional replacement.
