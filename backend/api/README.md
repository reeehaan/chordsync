# ChordSync API

The FastAPI application exposes the initial public contract for asynchronous
analysis jobs. S5-T01 deliberately separates job creation and status retrieval
from the eventual analysis worker.

## Analysis jobs

`POST /analysis/jobs` accepts `multipart/form-data` with two required fields:

- `title`: a trimmed title between 1 and 200 characters
- `audio`: a `.wav`, `.mp3`, or `.m4a` upload

Uploads are limited to 25 MB and empty files are rejected. A successful request
stores one input copy under the application-controlled local development path
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
