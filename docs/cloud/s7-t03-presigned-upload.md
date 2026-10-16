# S7-T03 Presigned upload lifecycle

The hosted API (Lambda) no longer accepts audio. A client creates a job,
uploads straight to S3 with a short-lived signed URL, then asks the API to
confirm. The API reads the stored object back, validates it with
`inspect_audio`, and queues the analysis exactly once. Local development keeps
the multipart upload. Nothing here is deployed.

## Where the old flow did each step

`CloudAnalysisApplication.create` (multipart, `POST /analysis/jobs`, unchanged
and still used by the local/non-hosted runtime) did everything in one request:
received the multipart file (`routers/analysis_jobs.py`), generated the job ID
(`uuid4`), staged it with `LocalAnalysisInputStorage.store` (size cap, then
`inspect_audio`, format/extension match, 360 s), uploaded it to S3
(`put_bytes`), wrote DynamoDB (`add`, then `save` to `AWAITING_UPLOAD`), and
sent SQS (`QueueBackedDispatcher.dispatch`). The hosted router now mounts
`create_upload` and `confirm_upload` instead; the multipart route is not
registered there.

## Endpoint contract (hosted)

### `POST /analysis/jobs`: create

Request (JSON, never audio):

| Field | Rule |
| --- | --- |
| `title` | 1–200 characters, not blank |
| `filename` | only its extension is used (`.mp3`, `.m4a`, `.wav`); path parts ignored |
| `declared_size_bytes` | integer, 1 to 26,214,400 |
| `content_type` | optional hint; must fit the extension or be `application/octet-stream` |

Response `201`: `job_id`, `status` (`awaiting_upload`), `upload_url`,
`upload_method` (`PUT`), `required_headers`, `expires_at`, `source_object_key`.
`required_headers` are `Content-Type` (canonical for the extension),
`Content-Length` (the declared size), and `x-amz-server-side-encryption:
AES256`. The client must send them unchanged. No other body field is read, so a
client cannot supply a key, job ID, or bucket. Nothing is queued.

### `POST /analysis/jobs/{job_id}/confirm-upload`: confirm

No body. Returns `202` with the job when this request queued it, or `200` with
the current job when it had already been confirmed. The response is the normal
`AnalysisJobResponse`, with `status` `queued` (or later).

`GET /analysis/jobs/{id}` and `/result` are shared with local mode. Status now
also reports `awaiting_upload` and `validating`.

## State machine

```
create ─► awaiting_upload ──confirm──► validating ──ok──► queued ─► processing ─► completed / failed
               ▲     │                      │
               │     └─ URL expired,        ├─ invalid upload ─► failed   (terminal)
               │        nothing stored ──► expired (terminal)
               └──── transient error / object not yet there ◄┘
```

Chosen states: `awaiting_upload` (pre-upload; the existing state, stage
`upload_pending`), `validating` (new), `queued`, `processing`, `completed`,
`failed`, `expired`. `created` is not used by the hosted flow: the job is
written once, already `awaiting_upload`. The job reaches `queued` only after
validation succeeds, inside the dispatcher's conditional write.

New durable fields: `declared_size_bytes`, `upload_expires_at`.

## S3 key and signed upload

- Key: `jobs/<job_id>/source/input.<ext>`, built only from the server's UUID
  and the validated extension (`ArtifactKeyFactory`; `..`, `.`, `/`-leading,
  and backslashes are rejected). The key is stored on the job, and confirm
  recomputes it and refuses a job whose stored key differs (so one job can
  never confirm, read, or delete another job's object).
- Method: **presigned PUT** (SigV4, regional endpoint). Chosen over presigned
  POST because a PUT with signed headers fixes the exact size, not just a
  range, and is simpler for a mobile client.
- Signed and therefore enforced by S3: the exact `Content-Length` (the
  declared size), `Content-Type` (canonical for the extension), and
  `x-amz-server-side-encryption: AES256`. No ACL is signed and the bucket
  blocks public ACLs. A client that sends different bytes-length, type, or
  encryption gets `SignatureDoesNotMatch`.
- Expiry: `CHORDSYNC_UPLOAD_URL_TTL_SECONDS`, default **600**, allowed 60–3600.
  A URL signed with Lambda's temporary credentials also stops working when
  those credentials expire, whichever comes first.
- The signing call is local; it makes no AWS request.

## Confirm validation sequence

1. Load the job (`404` if unknown). Already `queued`/`processing`/`completed`:
   answer `200`, send nothing.
2. Claim it: a versioned conditional write `awaiting_upload` → `validating`.
   Exactly one concurrent request wins.
3. Recompute the expected key; refuse a mismatched record.
4. `HEAD` the exact object. Missing: see "Expiry". Present: require
   `0 < ContentLength ≤ 25 MB`, equal to the declared size, `ContentType` (if
   present) equal to the canonical type, and `ServerSideEncryption` of
   `AES256` or `aws:kms`. The ETag is not used.
5. Clear stale staging, stream the object into `/tmp/chordsync-api/cloud_api_staging/<job>/`
   with a hard 25 MB cap, then run `inspect_audio`: real format must match the
   extension, duration `> 0` and `≤ 360 s`.
6. Delete the staged file (`finally`, on every path).
7. Save the duration, then dispatch: conditional `validating` → `queued`
   (`dispatch_pending`), one SQS message, then clear `dispatch_pending`.

## Idempotency

| Case | Result |
| --- | --- |
| A. first confirm succeeds | `202`, one SQS message |
| B. confirm again after dispatch | `200`, current state, no message |
| C. concurrent confirms | one wins the claim and sends; the others get `409 validation_in_progress` or `200` |
| D. confirm while another is validating | `409 validation_in_progress` |
| E. retry after a transient AWS error | job handed back to `awaiting_upload`; `503`; the retry validates and sends once |
| F. API died mid-validation | the job stays `validating`; after 120 s (longer than the Lambda timeout) the next confirm takes it over with a versioned write |
| G. queue outage at send | job is durably `queued` + `dispatch_pending`; confirm returns `202`; the reconciler sends it later; repeat confirms never send |

Two independent guards: the claim, and the dispatcher's own conditional
`validating` → `queued` write. A test removes each and both are caught.
Confirm never re-sends a message itself; resending is the reconciler's job.
SQS delivery is at-least-once and the worker already claims jobs
conditionally.

## Invalid uploads

The job becomes `failed` (stage `upload_rejected`, with the error code), then
the source object is deleted, and no SQS message is sent. Marking first means no
later confirm can succeed even if the delete fails; a failed delete is logged
and the bucket is the backstop (versioning is suspended, so `DeleteObject`
removes the object outright). The job is terminal; the client creates a new job.
Local staging is removed on every path.

## Expiry

No URL regeneration: the demo client creates a new job. If confirm finds no
object and `upload_expires_at` has passed, the job becomes `expired` and the
reply is `409 upload_expired`. If it is not yet expired, the job stays
`awaiting_upload` and the reply is `409 upload_not_received`, so the client can
finish the upload and confirm again. An object that was stored in time is still
accepted if confirm arrives late. Abandoned `awaiting_upload` jobs and their
objects need a lifecycle rule (future infrastructure ticket).

## Errors

| Status | Codes |
| --- | --- |
| 400 | `invalid_request` (malformed body, size ≤ 0, multipart sent to hosted), `unsupported_audio_format`, `unsupported_content_type` |
| 404 | `job_not_found` |
| 409 | `upload_not_received`, `upload_expired`, `validation_in_progress`, `invalid_job_state` (failed/expired/cancelled/key mismatch) |
| 413 | `audio_too_large` (declared or actual) |
| 422 | `invalid_audio` (malformed, or content differs from the extension), `audio_too_long`, `empty_audio`, `invalid_upload` (size, type, or encryption differs from the request) |
| 500 | `source_storage_failed` (could not read the object or write `/tmp`), `upload_unavailable` (uploads not configured) |
| 503 | `service_unavailable` (any transient AWS failure; existing handler) |

Bodies carry only a fixed code and message: no boto text, bucket, key, ARN, or
trace. `invalid_upload` also covers a missing encryption header.

## Future API role permissions

For the Lambda's own role (not created here). The presigned PUT is authorized
by the signer, so the role needs `s3:PutObject` even though it never calls it.

| Service | Allow | Resource |
| --- | --- | --- |
| S3 | `PutObject`, `GetObject` (covers `HeadObject`), `DeleteObject` | `…/jobs/*/source/*` |
| S3 | `GetObject` | `…/jobs/*/results/*` (result route) |
| DynamoDB | `GetItem`, `PutItem` (conditional writes use `PutItem`) | the jobs table |
| SQS | `SendMessage` | the analysis queue |

Not needed: `s3:ListBucket`, `models/*`, ECS `RunTask`, and `dynamodb:Scan` or
`UpdateItem` for the API (the reconciler needs `Scan`; the ECS-era API
statement in `infrastructure/aws/iam.tf` grants more than this and should not be
copied). `s3:DeleteObject` is the one addition over that statement.

**Missing keys without `ListBucket` (revised in S7-T05).** S3 answers a HEAD for
a key that does not exist with 403, not 404, when the caller lacks
`s3:ListBucket`. `ListBucket` stays ungranted, and `S3SourceUploadStore.head`
now treats **only** a definite 404 as "not uploaded". A 403/`AccessDenied` is a
configuration fault: it is logged at error level, the job goes back to
`awaiting_upload`, and the client gets `503 service_unavailable`. See
`docs/cloud/s7-t05-api-infrastructure.md` for the consequence for early and
expired confirms.

## Local vs hosted

| | Local | Hosted (Lambda) |
| --- | --- | --- |
| `POST /analysis/jobs` | multipart `title` + `audio` | JSON metadata; multipart gets `400 invalid_request` |
| `/confirm-upload` | not registered | registered |
| Legacy `/api/v1/audio/upload` | registered | not registered |
| Media rules | `LocalAnalysisInputStorage` + `inspect_audio` | the same code, from the S3 object |

## Tests

`tests/test_hosted_upload.py` (72): create contract and validation, key
scoping, signed-request scope (a real SigV4 URL and a recording client), the
full hosted flow, duplicate/concurrent/stale/takeover confirms, every rejection
class with cleanup and no SQS, transient failures and retry, queue outage and
reconciliation, key tampering, no secret in responses, TTL configuration, and
the local route set. `test_api_hosting.py` and `test_api_error_mapping.py` were
updated for the new hosted flow. Mutating each guard (claim, confirmed-state
short-circuit, key check, encryption check, delete, stale staging clear, release
on error) makes at least one test fail.

## Known limitations

- **A missing object may arrive as 403** when `ListBucket` is not granted, so an early or expired confirm can surface as `503` (see the S7-T05 document); this was checked against a fake client only.
- No authentication or ownership yet (`owner_id` is unset). The confirm path has
  one place to add the check.
- A client can upload and never confirm: the object and job linger until a
  lifecycle rule exists.
- `Content-Length` pins the size exactly, but S3 does not re-verify the bytes
  against anything; validation is the media check at confirm.
- Durations come from container headers (see the S7-T02 document).
- A confirm that passes validation then loses its response is safe to repeat.
- Not run against real AWS; S3 signing behavior was checked offline only.

## Next

Worker dispatcher Lambda (the reconciler for `queued` + `dispatch_pending` jobs
and the ECS worker trigger), then the Terraform API stack.
