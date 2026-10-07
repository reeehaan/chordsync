# ChordSync API

The FastAPI application exposes the initial public contract for asynchronous
analysis jobs. S5-T01 deliberately separates job creation and status retrieval
from the eventual analysis worker.

## Analysis jobs

`POST /analysis/jobs` accepts `multipart/form-data` with two required fields:

- `title`: a trimmed title between 1 and 200 characters
- `audio`: a `.wav`, `.mp3`, or `.m4a` upload

Uploads are limited to 25 MB and empty files are rejected. Audio duration is
decoded server-side with ffprobe; files longer than 360 seconds or files that
cannot be decoded are removed before a job record is created. A successful
request stores one input copy under the application-controlled local development path
`storage/uploads/analysis_jobs/`, then creates a job in the `queued` state and
returns `202 Accepted`. Client filenames never determine the stored path, and
absolute server paths are not exposed by the public API.

`GET /analysis/jobs/{job_id}` returns the current public job status. Lifecycle
values are `queued`, `processing`, `completed`, and `failed`. Failed jobs expose
only a stable error code and safe message.

`GET /analysis/jobs/{job_id}/result` returns the existing ChordSync
`SharedTimeline` representation after completion. A queued, processing, or
failed job returns `409 Conflict`; an unknown job returns `404 Not Found`.

Job records remain in memory, while uploaded inputs use replaceable local
filesystem storage. Accepted jobs are submitted to an in-process asynchronous
executor, which owns the `queued` → `processing` → `completed`/`failed`
lifecycle. The executor calls an `AnalysisProcessor` abstraction so a later
adapter can invoke the project's isolated analysis environments without placing
their dependencies in the API environment.

The runtime processor is a subprocess adapter over the existing Chordino,
madmom, WhisperX, preprocessing, and timeline-fusion stages. Each job uses an
isolated workspace under `storage/analysis_jobs/`. The uploaded source remains
unchanged; normalization and generated JSON artifacts stay in that workspace.
The API environment imports only the lightweight adapter and shared result
models. madmom and WhisperX run through their existing isolated environments.
Chordino resolves `sonic-annotator` from normal `PATH`. When a local build is
kept elsewhere, set `CHORDSYNC_SONIC_ANNOTATOR` to its executable path. The
path is server-owned configuration and is never accepted from API clients.

Automated tests replace subprocess execution with deterministic publication-safe
artifacts. They do not run heavy models or present synthetic output as genuine
analysis.

The executor and repository are development-grade, in-process/in-memory
implementations. Subprocess orchestration is local and development-grade;
persistent jobs, a durable remote worker/queue, authentication, input retention
policies, and malware scanning remain deferred. Uploaded audio is retained after
execution so it remains available for future playback support.

## Independent worker command

The same `RealAnalysisProcessor` used by the in-process executor can run as one
independent job:

```sh
python -m backend.api.app.analysis_worker \
  --job-id JOB_ID \
  --title "Song title" \
  --input /inputs/JOB_ID/input.mp3 \
  --workspace-root /tmp/chordsync \
  --result /results/JOB_ID/timeline.json
```

The input must be inside a directory named exactly as the job ID. The workspace
must be empty for that job because the processor deliberately refuses to reuse
an existing job workspace. The result is written atomically. The title is part
of the worker descriptor for future durable job transport; current LRCLIB song
identity continues to use embedded audio metadata, preserving existing behavior.

The cloud-ready queue consumer can process one delivery and exit:

```sh
CHORDSYNC_RUNTIME_MODE=aws \
CHORDSYNC_DISPATCH_MODE=queue \
python -m backend.api.app.analysis_worker_consumer --once
```

AWS mode additionally requires `AWS_REGION`, `CHORDSYNC_S3_BUCKET`,
`CHORDSYNC_DYNAMODB_JOB_TABLE`, and `CHORDSYNC_SQS_ANALYSIS_QUEUE_URL`. It uses
the normal AWS credential provider chain. The command never creates AWS
resources. Local API development remains on the existing in-process executor;
see `docs/cloud/s6-t04-queue-worker.md` for the migration seam and limitations.

Cloud-mode multipart API integration now persists job state and source/result
artifacts behind the cloud interfaces. Dispatch failures remain recoverable via:

```sh
python -m backend.api.app.reconcile_dispatch --once
```

This compatibility path does not expose object keys or presigned URLs. The
existing local Flutter workflow remains the default. Architecture and recovery
semantics are documented in `docs/cloud/s6-t05-cloud-api-integration.md`.

## Optional development lyrics verification

Set `CHORDSYNC_LRCLIB_REFERENCE_ENABLED=1` to enable the development/academic
LRCLIB reference lookup. It uses embedded title and artist metadata, validates
the provider identity, and only applies conservatively verified corrections
with fresh WhisperX alignment timing. The feature is off by default. Provider
failure, weak identity, unsafe context, or invalid timing always preserves the
original WhisperX transcript and does not fail analysis.

Optional transport settings are `CHORDSYNC_LRCLIB_TIMEOUT` and
`CHORDSYNC_LRCLIB_USER_AGENT`. Full provider responses and reference lyrics are
not persisted or logged. Only corrected timed words that pass verification may
flow through the existing `SharedTimeline` output.

## Optional multilingual lyrics

Set `CHORDSYNC_MULTILINGUAL_LYRICS_ENABLED=1` to let WhisperX detect the sung
language and convert detected non-English lyrics to Latin-script display text
after word alignment. Alignment is performed against the native transcript;
romanization does not change word timestamps. English results are passed
through unchanged. The established forced-English production path remains the
default when the variable is unset.

Romanization is best-effort and character based. It supports practically all
Unicode scripts, but context-sensitive writing systems may not match a native
speaker's preferred spelling. Non-English transcripts skip the existing
English-only LRCLIB correction pass and continue safely with WhisperX output.
