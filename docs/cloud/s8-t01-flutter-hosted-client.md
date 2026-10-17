# S8-T01 Flutter hosted analysis client

The Flutter app can now talk to the hosted analysis API (create job, direct upload to
storage, confirm, poll, fetch the result). The hosted backend is off, and nothing here
needs it: all tests run against faked HTTP. Local development keeps working unchanged.

## Where it fits

The app has no state-management library: plain Dart, constructor injection, a
`ChangeNotifier` (`AudioImportController`), and interfaces with fakes in tests. The hosted
flow plugs in behind the existing seam instead of replacing it.

```
AudioImportController ─► AnalysisPracticeCoordinator ─► AnalysisJobPoller
                                  │                           │
                                  └──── AnalysisApiClient ◄───┘
                                         ├─ DioAnalysisApiClient      (local multipart, unchanged)
                                         └─ HostedAnalysisClient      (new)
                                              ├─ DioHostedAnalysisApi (create / confirm / status / result, bearer token)
                                              └─ DioPresignedUploader (direct PUT to storage, no token)
```

`main.dart` picks the client from build settings, so the controller, practice screens and
`SharedTimeline` mapping are untouched.

## Build settings

| `--dart-define` | Default | Meaning |
| --- | --- | --- |
| `CHORDSYNC_API_MODE` | `local` | `hosted` selects the presigned-upload flow |
| `CHORDSYNC_API_BASE_URL` | `http://127.0.0.1:8000` | The API base URL (the hosted `execute-api` endpoint) |
| `CHORDSYNC_API_TOKEN` | empty | Demo bearer token (hosted only) |

Example: `flutter run --dart-define=CHORDSYNC_API_MODE=hosted
--dart-define=CHORDSYNC_API_BASE_URL=https://<id>.execute-api.ap-southeast-1.amazonaws.com
--dart-define=CHORDSYNC_API_TOKEN=<token>`.

A build-time token is compiled into the app, so it is for private demo builds only. The
`AnalysisAuthTokenProvider` callback is the seam for a sign-in flow later. With no token the
app fails fast with a clear message and sends nothing.

## Models (exact backend values)

- `AnalysisJobStatus`: `awaiting_upload`, `validating`, `queued`, `processing`, `completed`,
  `failed`. The first two are new (hosted only); an unknown value is a data error.
- `CreateUploadRequest` (title, filename, declared size, content type) and `UploadTarget`
  (job id, status, upload URL, required headers, expiry, object key). The target is rejected
  unless the method is `PUT` and the URL is `https`. Its `toString` never prints the URL.
- `ConfirmOutcome`: the job plus whether this call queued it (202) or it was a repeat (200).
- Errors, all domain types so widgets never see Dio: `AnalysisApiException` (with
  `isUnauthorized`/`isNotFound`; carries the backend `code`), `AnalysisUploadException`
  (`urlExpired`, `connection`, `timeout`, `rejected`), `AnalysisTransportException`,
  `AnalysisDataException`, and the existing cancelled/timeout exceptions.

## Flow (`HostedAnalysisClient.createJob`, then the existing coordinator)

1. Check the file locally: extension WAV/MP3/M4A, not empty, at most 25 MB (no network
   call otherwise; the codes match the backend's).
2. `POST /analysis/jobs` with metadata only, expecting 201.
3. `PUT` the bytes to the presigned URL, streamed from disk, with exactly the returned
   headers. The signed `Content-Length` must equal the file size, or the upload is refused
   locally (the file changed). An expired link is detected before and after sending.
4. `POST …/confirm-upload`: 202 or 200 is success. `409 upload_not_received` is retried up
   to 3 times, one second apart; every other error (401, hidden 404, 503, other 409) is not.
5. The coordinator then polls every 3 seconds (1 second locally) until `completed`
   (`awaiting_upload` and `validating` count as still waiting), fetches the result,
   validates the timeline, and builds the practice session as before.

## Safety properties (each has a test that fails if broken)

- The bearer token goes only to the ChordSync API. The uploader uses a separate plain
  client, so storage never receives an `Authorization` header (a combined auth would make
  S3 reject the request).
- The presigned URL is used unchanged (query intact) and never logged or put in an error.
- Hidden 404s and 401s are not retried and not distinguished beyond their status.
- Cancelling stops the upload (the token is watched while it runs) and skips the confirm;
  a job left unconfirmed is cleaned up by the backend.
- Error messages shown to the user are fixed strings: no URL, path, or server detail.

## Tests

`flutter test`: **214 passed** in total (the analysis area went from 60 to 126 tests; the
rest are unchanged), `flutter analyze` clean. New: hosted API client (23), uploader (13),
submission and end-to-end flow (22), config (3), controller states and messages (5).
Mutating each safeguard (token leaked to storage, size check, skipped upload,
retrying every error, plain-HTTP targets, missing bearer on a route) fails a test. Two
existing test fakes gained the new optional `cancellation` argument.

## Not done

- The hosted backend is off, so nothing was run against real AWS or S3.
- Token entry/storage UI and a real sign-in.
- Added afterwards (S8-T01b): the poller retries 429/503 (capped exponential backoff, 5
  consecutive tries) and `result_not_ready`, all within the overall timeout; a "Finishing
  upload…" stage shows between the last byte sent and the job being queued. Retries only
  touch status/result requests, so no second job or upload is made.
- A Dio-level progress callback measures bytes sent to the OS, not bytes accepted by storage.
