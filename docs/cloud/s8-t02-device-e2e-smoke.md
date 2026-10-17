# S8-T02 Flutter to hosted AWS, real-device end-to-end test

Run on 2026-10-17 with a physical iPhone 17 Pro (release build, hosted mode, owner demo
token as a build-time define). Source: Git `33ea780`. API image `api-2ed4afa-s7`
(`sha256:bc9b30b6…e82ca`); worker image `worker-d9ef4a3-runtime2`; dispatcher zip rebuilt
from the current commit.

## Deploy

Saved plan applied unchanged: 28 added, 1 changed, 0 destroyed (the six extra resources
versus S7-T08 are the S7-T10 alarms and metric filters). New endpoint
`https://etisfjkajd.execute-api.ap-southeast-1.amazonaws.com` (the API id changes on every
re-enable, so the app must be rebuilt each time).

## Results (two real songs, one job each)

| Check | Result |
| --- | --- |
| App flow | upload, "Finishing upload", queued, analyzing, practice sheet |
| Jobs | both `completed`, attempts 1 |
| Worker | one task per job, exit 0, 4m18s and 4m29s |
| Stage times | preprocess <1 s, chords 15-20 s, beats 23-31 s, separate 115-120 s, lyrics 63-65 s, fuse <1 s |
| Queue / DLQ / ECS | 0 / 0 / no leftover tasks |
| Logs | no ERROR or WARNING in API, dispatcher or worker groups |
| Dispatcher INFO logs | `worker_started`, `worker_already_active` now written (S7-T08 finding 1 fixed) |
| Ownership | owner 200/200; other demo token 404/404; no token 401 |
| Leaks | no demo token or `X-Amz-Signature` in the four log groups |

## Findings

1. **Lyrics are raw WhisperX.** The local pipeline corrects them against LRCLIB reference
   lyrics; hosted mode does not, because `CHORDSYNC_LRCLIB_REFERENCE_ENABLED` is unset and
   the worker runs with `CHORDSYNC_STAGE_NETWORK=disabled`. Planned fix (S8-T03): the API
   Lambda fetches the reference from LRCLIB (song identified from file tags and duration)
   before queueing and passes it to the worker, which stays offline; fall back to raw
   WhisperX on no or low-confidence match.
2. **About 5 minutes per song** end to end on 4 vCPU CPU-only; separation is about 2 of
   the 4.5 minutes.
3. Installing on iOS needs a signing team and trusting the developer profile on the phone.

## State afterwards

Hosted runtime torn down (`hosted_api_enabled=false`, `dispatcher_enabled=false`: 28
destroyed, 1 changed, then no drift). ECR trimmed to the two images in use. Thirteen
unrelated IAM roles from earlier experiments were deleted; only the project roles and
`ChordSyncTerraformRole` remain. Test jobs and their S3 objects were left in place.
