# S7-T02 / S7-T02A / S7-T02B API Lambda packaging

The existing FastAPI API is packaged as an ARM64 container image that runs in
AWS Lambda through AWS Lambda Web Adapter, or as a plain container. Nothing is
deployed; the image exists only locally. S7-T02A then removed ffmpeg from the
image, replaced ffprobe validation with a small Python validator, and made AWS
outages return a clean 503. S7-T02B then replaced the validator's GPL-licensed
Mutagen dependency with in-house, standard-library parsers.

## Image

- Tag: `chordsync-api:lambda-s7t02b` (local only, not pushed)
- Image ID: `sha256:1eda7428fea7036606e31611851cac49c7acf3646e0310c76d216544004574c0`
- Platform: linux/arm64, user `10001` (non-root)
- Size: **196.0 MB uncompressed (196,021,068 bytes), 70.4 MB compressed
  (70,384,362 bytes, `docker save | gzip`).** S7-T02A was 197.6 MB / 70.9 MB,
  and the S7-T02 image with ffmpeg was 607 MB / 234 MB. The worker image is
  5.1 GB.
- Base: `python:3.11-slim-trixie@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce`
  (Debian 13 Trixie, Python 3.11.17), the same supported, digest-pinned base
  as the worker.
- Lambda Web Adapter **1.1.0**:
  `public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0@sha256:17cfd08eff1dfea3f6a9a1e9c65fdac80aa4919b6085e746615530f43f57d2f1`
  (multi-arch index; the newest stable tag in the public registry on
  2026-10-13), copied to `/opt/extensions/lambda-adapter`.

## Startup flow

`python -m uvicorn backend.api.app.main:app --host 0.0.0.0 --port 8000`.

In Lambda, the adapter extension starts first, waits for `GET /health`
(`AWS_LWA_READINESS_CHECK_PATH`), and forwards API Gateway HTTP events to
`127.0.0.1:8000` (`AWS_LWA_PORT`). Outside Lambda the extension is inert and
uvicorn serves directly. Port 8000 is used instead of 8080 because Lambda's
local emulator binds 8080 inside the container.

## Hosted vs local mode

`backend/api/app/hosting.py`, with explicit configuration rather than
detection from AWS environment variables:

| | Local (`CHORDSYNC_API_HOSTING_MODE` unset/`local`) | Lambda (`lambda`, image default) |
| --- | --- | --- |
| Legacy `POST /api/v1/audio/upload` | registered (unchanged) | **not registered**: absent from OpenAPI, 404 |
| Analysis routes | `get_analysis_application_service` (local or cloud by `CHORDSYNC_RUNTIME_MODE`) | `get_hosted_analysis_application`: cloud only; no local service, executor, or `RealAnalysisProcessor` |
| Runtime | local or aws | **must be `aws`**, or startup fails |
| Upload staging | `STORAGE_PATH/cloud_api_staging` (unchanged) | `CHORDSYNC_API_STAGING_ROOT/cloud_api_staging`, default `/tmp/chordsync-api` |
| AWS outage on status/result | unchanged | JSON 503 (below) |

`create_app(hosting)` builds the app; the module-level `app` keeps working for
uvicorn and tests. In hosted mode, importing the API loads only
`analysis.fusion.models`, `analysis.lyrics.models`, and
`analysis.temporal.models`: the router now imports `RealAnalysisProcessor`
inside the local-only function, so the analysis pipeline (and its ffmpeg
wrapper) is never imported by a hosted API.

## Writable paths

- Only `/tmp` is written in hosted mode. The staging root must be absolute,
  strictly under `/tmp`, and free of `..`, validated at startup.
- `/app` is root-owned and read-only. Verified by running the image with
  `--read-only --tmpfs /tmp`.
- The staged upload is deleted after each job creation.
- S7-T02 fixed `LocalAnalysisInputStorage._job_directory`, which accepted the
  job IDs `.` and `..`. Tests now cover `..`, `.`, nested traversal
  (`a/../../b`, `../../etc/passwd`), absolute paths, backslashes, and the
  empty string, for both lookup and delete, and prove a sibling file survives.

## Media validation (S7-T02A, parsers replaced in S7-T02B)

`backend/api/app/services/media_inspection.py` replaces the one ffprobe call
the API made (`_probe_duration_seconds`). It returns the detected format,
duration, and file size, and **detects the format from the file's contents,
never from its extension or the client's Content-Type.** The upload storage
then requires the detected format to equal the extension's format.

| Format | Detection | Duration | Module |
| --- | --- | --- | --- |
| WAV | `RIFF`…`WAVE` signature | `data` size ÷ (sample rate × block align) | `media_inspection.py` (`struct` chunk reader) |
| M4A | `ftyp` box | audio track `mdhd` duration ÷ timescale | `mp4_audio.py` |
| MP3 | anything else is tried as MPEG audio | Xing/Info/VBRI frame count, else audio bytes ÷ bitrate | `mpeg_audio.py` |

All three are standard-library-only and read headers only. `media_errors.py`
holds the shared `MediaInspectionError`, which `media_inspection` re-exports.

### S7-T02B: why Mutagen was removed

S7-T02A used Mutagen 1.48.1 for MP3 and M4A. It is GPL-2.0-or-later, which is
the only copyleft dependency the API image had. Following the preference order
(in-house standard-library parser, then a permissive pure-Python package, then
anything else after licensing review), the validator now uses small in-house
parsers, so **no third-party media parser is installed at all**.

The parsers are written from the public format layouts (the MPEG audio frame
header and the Xing/Info and VBRI fields; ISO/IEC 14496-12 boxes; ID3v2/v1).
No Mutagen code was copied. Mutagen and ffprobe were used
only as black-box oracles from a scratch virtual environment outside the
repository, and Mutagen was uninstalled from the API environment to prove the
validator does not need it.

**MP3 (`mpeg_audio.py`).** ID3v2 tags (v2.3 and v2.4, with footers, stacked up
to 16) are skipped by their declared synchsafe size, so cover art is never read
or parsed, and a tag larger than the file is rejected. A file is MP3 only if
the first MiB after the tags contains **four consecutive, mutually consistent,
complete frames** (same version, layer, and sample rate; reserved and
free-format values rejected). At most 1,500 frame-sync candidates are tried, so
junk cannot cause unbounded work. Duration is the Xing/Info or VBRI frame count
when present, else audio bytes (excluding an ID3v1 tag) ÷ bitrate.

**M4A (`mp4_audio.py`).** Every box must fit inside its parent, including
64-bit sizes and a final size-0 box, so a file cut anywhere, even by one byte,
is rejected. The first `soun` track must have a positive `mdhd` timescale and
duration (versions 0 and 1) and a first sample entry of `mp4a` (AAC) or `alac`
(Apple Lossless). Fragmented MP4 (zero `mdhd` duration), video-only files, and
other audio entries are rejected. Tags and cover art are not parsed.

**WAV.** Unchanged: a small RIFF chunk reader. The standard library `wave`
module is not used because on Python 3.11 it rejects 24-bit
`WAVE_FORMAT_EXTENSIBLE` and 32-bit float WAVs that ffprobe accepts. PCM,
float, and extensible files with those subformats are accepted, including
streamed files with an unknown data size; compressed WAV is rejected.

- Limits are unchanged: 25 MB (enforced while streaming) and 360 s (inclusive).
  Rejected: zero bytes, malformed or unsupported media, extension/content
  mismatch, non-positive duration, and over-long audio. Validation errors are
  the existing controlled codes (`invalid_audio`, `unsupported_audio_format`,
  `empty_audio`, `audio_too_large`, `audio_too_long`) with fixed messages; no
  parser text reaches a client.
- The S3 object's content type is derived from the validated format, not from
  the client's header.
- Local mode uses the same validator, so the API no longer needs ffprobe in
  any mode. The ML worker still uses ffmpeg for its own preprocessing.

### S7-T02B verification

- All 63 existing media tests passed unchanged against the new parsers before
  any test was edited, and 74 parser-specific tests were added
  (`test_mpeg_audio.py`, `test_mp4_audio.py`). Seven parser safeguards were
  mutation-tested: three were caught at once, two survived and now have tests,
  and two (an ID3v2 tag past end-of-file, a zero `mdhd` duration) are also
  enforced by later checks, so removing them changes no outcome.
- **Real files**, new parser vs the previous Mutagen validator vs ffprobe: the
  14 files tested (approved MP3 with cover art, Apple AAC and ALAC, `afconvert`
  and ffmpeg WAV at 16/24/32-bit float, ffmpeg MP3 CBR and VBR, ffmpeg AAC with
  and without faststart, three dataset WAVs read locally and never committed)
  gave identical formats, identical durations to the previous validator, and
  durations within 0.05 s of ffprobe. The same 11 non-dataset files give the
  same result inside the image, run read-only as uid 10001 with no network.
- **MPEG grid:** all 756 version/layer/bitrate/sample-rate/channel combinations
  were accepted with the exact expected duration. The previous validator
  rejected 12 of them (Layer I combinations), so the new parser is more
  complete there.
- **Mutation corpus:** 1,687 truncations and byte flips of valid files. The new
  parser accepted 1,196 and the previous validator 1,199; the differences are
  8 files only the new parser accepted, 11 only the previous one accepted, and
  8 accepted files that ffprobe rejects. The differences are all byte flips in
  M4A metadata or sample tables, or MP3s cut inside a Xing frame
  (see the limitations).
- **Random corpus:** 6,000 random, sync-prefixed, ID3-prefixed, and
  `ftyp`-prefixed blobs (up to 200 KB, assigned random extensions): **0
  accepted** by the new parser (S7-T02A's sample was 5,000), and 0 by the
  previous one.
- Memory: validating a 20 MB MP3 (a 20 MB cover image) inside the image adds
  no measurable memory over building the file (peak 91 MB, almost all from
  building it) and takes about 0.1 ms.

### Validation limitations

- **Durations come from container headers, as they do with ffprobe.** A
  hostile file can understate its length. The 25 MB cap and the worker's
  per-stage timeouts bound the consequence. A worker-side check of the decoded
  duration would close it and is out of scope here.
- **An MP3 cut mid-stream is a valid shorter MP3** and is accepted (ffprobe
  does the same). Four consecutive valid frames are required even when a Xing
  header is present, so a tiny stream cut inside its first frames is rejected
  where the previous validator accepted it.
- MP3 files without a Xing/VBRI header get an estimated duration (size ÷
  first-frame bitrate), exact for constant bitrate.
- M4A is header-only: bytes flipped in metadata or sample tables that the
  parser does not read can still be accepted when ffprobe would reject them.
  The worker re-validates when it decodes. M4A files cut anywhere, even by one
  byte, are rejected, and a video MP4 with an AAC audio track is accepted as
  M4A.
- M4A is limited to AAC (`mp4a`) and Apple Lossless (`alac`) audio. Other
  audio in an MP4 (AC-3, AMR, PCM) is rejected.
- **Compressed WAV (ADPCM, A-law, μ-law, MP3-in-WAV) and RF64 are rejected.**
  ffprobe accepted compressed WAV, so this is a deliberate narrowing for the
  demo's music uploads.

## Native dependencies

- **ffmpeg and ffprobe are removed from the API image**, along with 202 Debian
  packages (289 → 87, none added): ffmpeg, `libavcodec`, `libavformat`,
  `libavutil`, `libavfilter`, `libavdevice`, `libswresample`, `libswscale`,
  `libpostproc`, **`libtiff6`**, **`libgnutls30t64`**, `libxml2`, `libexpat1`,
  `libcjson1`, the gdk-pixbuf/librsvg/cairo/pango stack, Mesa/GL, and the
  codec libraries (x264, x265, vpx, aom, dav1d, opus, webp).
- The remaining 87 packages are the slim base system. The only TLS library is
  OpenSSL, which Python uses.
- 23 Python distributions remain (FastAPI, uvicorn, boto3, pydantic, and their
  dependencies); Mutagen was the 24th in S7-T02A. pip, setuptools, and wheel are uninstalled after
  installation.
- Absent: torch, WhisperX, Demucs, BTC, madmom, numpy, librosa, scipy, nltk,
  soundfile, model weights, CUDA.

## Clean 503 for AWS outages (S7-T02A)

Root cause: `translate_provider_error` classified only AWS error *codes*, so a
network failure such as `EndpointConnectionError` (no code) became the generic
`UNEXPECTED` kind and surfaced as a bare 500.

- `backend/api/app/services/aws_errors.py` now classifies botocore
  `EndpointConnectionError`, `ConnectTimeoutError`, `ReadTimeoutError`, and
  `ConnectionClosedError` as `TEMPORARY_UNAVAILABLE`, with a message that omits
  the endpoint. The worker retries both kinds, so its behaviour is unchanged.
- In hosted mode only, `main.py` maps `TEMPORARY_UNAVAILABLE` to:

  ```json
  {"error": {"code": "service_unavailable", "message": "Analysis service is temporarily unavailable."}}
  ```

  with HTTP 503. The response never contains the provider message, endpoint,
  ARNs, or a traceback. Only the error kind is logged.
- Narrow by design: configuration, access-denied, and unexpected provider
  errors are re-raised and behave as before. Genuine 404 (`job_not_found`),
  409 (`result_not_ready`), and 400 (`invalid_audio`) responses are unchanged,
  and the result route keeps its own `result_temporarily_unavailable` 503 for
  S3 read outages.

## Local smoke procedure

1. Lambda path: AWS SAM CLI 1.160.1 `sam local invoke` with HTTP API v2
   events, fake credentials, and `AWS_ENDPOINT_URL=http://127.0.0.1:9`, so no
   real AWS call is possible. SAM's emulator injection needs a root build step,
   so a local-only tag (`FROM` the image, `USER root`) is used, then deleted.

   | Request | Result |
   | --- | --- |
   | `GET /` | 200 |
   | `GET /health` | 200 |
   | `GET /openapi.json` | `/`, `/health`, `/analysis/jobs`, `/analysis/jobs/{job_id}`, `/analysis/jobs/{job_id}/result` |
   | `POST /api/v1/audio/upload` | 404 |
   | `GET /analysis/jobs/{id}` (AWS unreachable) | **503**, JSON above |
   | `GET /analysis/jobs/{id}/result` (AWS unreachable) | **503**, JSON above |

2. Real image, `--read-only --tmpfs /tmp`, uid 10001: health 200, legacy upload
   404, status/result 503 with AWS unreachable, `/app` not writable, `/tmp`
   writable, no ffmpeg, no AWS credential files.
3. The deployed worker image (`worker-d9ef4a3-runtime2`, no Mutagen) imports
   the S7-T02A code from a read-only mount without errors, so the API change
   does not require a worker rebuild. S7-T02B adds only standard-library
   modules to the API package, and a test imports the worker-side modules with
   every third-party media package blocked.

## Vulnerability review (Docker Scout, local)

| Image | CRITICAL | HIGH | MEDIUM | LOW | Unspecified |
| --- | --- | --- | --- | --- | --- |
| S7-T02, as recorded | 0 | 8 | 15 | 100 | 1 |
| S7-T02, re-scanned 2026-10-14 (scanner data moved) | 0 | 8 | 14 | 100 | 2 |
| S7-T02A, before removing pip | 0 | 1 | 6 | 27 | 0 |
| S7-T02A, final | 0 | 1 | 1 | 26 | 0 |
| **S7-T02B** | **0** | **1** | **1** | **26** | **0** |

- TIFF and GnuTLS are gone from the image, and with them the findings
  tied to the ffmpeg stack (`cjson`, `expat`, `libxml2`). The worker's CRITICAL
  exceptions do not apply to the API image.
- S7-T02B removes a pure-Python package, so the OS package set and the finding
  counts are identical to S7-T02A (146 packages indexed, 13 vulnerable). No new
  CRITICAL.
- The one HIGH is **zlib 1:1.3.dfsg+really1.3.1-1, CVE-2026-85091**, a heap
  overflow in zlib's `gzwrite()`/`gzprintf()` file API. Debian lists Trixie and
  unstable as vulnerable; no fixed package exists. ChordSync does not call that
  API, and CPython's `zlib`/`gzip` modules use the deflate/inflate stream
  interface, but this has not been verified in depth. No exception was created.
- The remaining MEDIUM is `tar`; the LOW findings are base-system packages.
- ECR's scanner uses a different database, so its counts will differ. Scan the
  image there before any deployment.

## Dependency and licensing status (S7-T02B)

Licences below are as declared in each package's metadata inside the image.
This is an inventory, not legal advice.

| Component | Declared licence | Role |
| --- | --- | --- |
| Mutagen | **absent** (was GPL-2.0-or-later) | removed |
| `mpeg_audio.py`, `mp4_audio.py`, `media_inspection.py` | project code | in-house, standard library only |
| FastAPI, starlette, pydantic, pydantic_core, annotated-types, annotated-doc, anyio, jmespath, six, typing-inspection, urllib3, idna (BSD-3), h11 | MIT / BSD-3-Clause | web framework |
| uvicorn, click | BSD-3-Clause | server |
| boto3, botocore, s3transfer, python-multipart | Apache-2.0 | AWS client, form parsing |
| python-dateutil | Apache-2.0 / BSD dual | botocore |
| typing_extensions | PSF-2.0 | typing |
| packaging | Apache-2.0 OR BSD-2-Clause | transitive |
| anyascii | no licence field in metadata (project page: ISC) | filename transliteration |

- No GPL, LGPL, or other copyleft Python package is installed, and no package
  was added for media inspection. The 23 distributions are the ones in
  `requirements-runtime.txt` plus `packaging`.
- The Debian base system keeps its own licences (some components are GPL or
  LGPL, such as `bash` and `libc`); they come from the digest-pinned base
  image and are unchanged by this work.
- A test fails if any requirements file lists Mutagen or another third-party
  media parser, or if the media modules import anything outside the standard
  library.

## Proposed Lambda settings (not deployed)

| Setting | Value | Reason |
| --- | --- | --- |
| Architecture | arm64 | matches the image, and is cheaper |
| Memory | **512 MB** (was 1024 MB while ffprobe was needed) | measured: 35 MiB idle, 66 MiB after 100 requests, and a 124 MB peak for the worst case I could build (a 24 MB MP3 with a 20 MB cover image, including constructing it); more than 4× headroom |
| Timeout | 30 s | status and result take well under 1 s; S3 download plus validation of 25 MB takes a few seconds; the HTTP API integration limit is 30 s |
| Ephemeral `/tmp` | 512 MB (default) | one staged source ≤ 25 MB, deleted after use |
| Concurrency | reserved 5 | caps cost and abuse for a private demo, with HTTP API throttling |

## Remaining work for S7-T03 (presigned upload)

1. Replace the multipart create with JSON create + presigned S3 POST +
   confirm, using the `AWAITING_UPLOAD` state and `/tmp` staging. The confirm
   step downloads the object and calls `inspect_audio`.
2. Keep local mode's multipart flow working for development.
3. Optional follow-ups: a worker-side check of the decoded duration, and a JSON
   500 for non-transient provider errors.
