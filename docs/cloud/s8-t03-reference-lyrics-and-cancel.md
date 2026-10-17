# S8-T03 Reference lyrics in the worker, and job cancel

## Reference lyrics (LRCLIB)

Hosted mode returned raw WhisperX lyrics because `CHORDSYNC_LRCLIB_REFERENCE_ENABLED`
was unset in the worker task definition. The `CHORDSYNC_STAGE_NETWORK=disabled` guard
only covers analysis subprocesses (it hands them a copy of the environment with a dead
proxy); the lookup runs in the worker's own process, and the worker security group
already allows HTTPS egress. So the fix was two settings in `main.tf`
(`CHORDSYNC_LRCLIB_REFERENCE_ENABLED=true`, `CHORDSYNC_LRCLIB_USER_AGENT` naming the
repo). No image rebuild, and the reference lyrics stay in worker memory only
(`full_lyrics_storage_permitted` is false). The song is identified from its embedded
tags (28 of 31 test files have them; untagged files skip the lookup).

Real-device run (job `642a95c0…`, Homewrecker): `reference matched`, 3 min 4 s worker
stages, 100 BPM, 87 bars. The same file through the local pipeline:

| | Local | Cloud |
| --- | --- | --- |
| raw WER vs reference | 0.3135 | 0.6698 |
| corrected WER | 0.3064 | 0.6675 |
| inserted words | 17 | 151 |
| candidates accepted | 3 | 1 |

Cause: one WhisperX repetition loop in the cloud transcript (lyric line 7, 123-151 s:
192 words, 12 distinct, one 4-gram repeated 30 times; local had 59 words). The other
nine lines match in text and timing. Same model files (checksums), same command (CPU,
int8). This is a transcription hallucination, not a cloud configuration difference.
Possible fixes, not done: collapse repeated n-grams before verification, or stop
conditioning on previous text. Follow-up.

## Incident: model assets lost in the rename

The S8-T02 rename replaced the artifacts bucket, which held `models/` (15 files,
960 MB) next to the job data. The first run after it failed at model bootstrap
(`AccessDenied` on the manifest, exit 3, queue not polled). Recovery: all 15 files were
found locally, matched the committed manifest by SHA-256, and were re-uploaded with
SHA-256 checksums and SSE-S3; the manifest (`ecb88b94…fa894`) went up last. Lesson: the
artifacts bucket is not disposable. Model assets should be backed up or the bucket
protected before any replacement.

## Cancel

`POST /analysis/jobs/{job_id}/cancel` (hosted only, same bearer auth, same write
throttle). Owner only; another owner's or an unknown job is the same 404. Allowed from
created, awaiting_upload, validating, queued and processing; repeating it returns 200;
a completed, failed or expired job answers 409 `invalid_job_state`. The status API now
reports `cancelled` and the result route answers 409 `job_cancelled`.

The worker already skips cancelled jobs it has not claimed and discards the result of
one cancelled while processing, so there is no worker change. A processing job still
runs to the end (up to about 4 minutes of worker time); stopping it early would need a
cancel check between stages in the worker and a new image. A cancelled queued job still
causes one short worker start that acknowledges the message and exits.

Mobile: `AnalysisApiClient.cancelJob` (no-op for the local API). The hosted client
cancels the job if the user cancels after it was created (during upload or confirm), and
the coordinator cancels it when polling is cancelled. Both are best effort (5 s cap) and
never hide the cancellation. A job cancelled elsewhere stops polling as cancelled.
