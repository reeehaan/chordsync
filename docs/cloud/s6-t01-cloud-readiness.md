# S6-T01 cloud readiness baseline

This document records the current local runtime and the minimum seams for a
future private AWS demo. It does not provision cloud resources or change the
analysis algorithms.

## Frozen product constraints

- Maximum accepted duration: 360 seconds.
- No authentication for the first private/student demo. Authentication is a
  release blocker for public or multi-user access.
- Budget target: approximately USD 20/month in `ap-southeast-1`.
- MUSIC_ONLY remains implemented and disabled by default.
- Multilingual lyrics remain disabled by default.
- LRCLIB remains an opt-in development/academic verification source. Its data
  must not be treated as commercially redistributable.
- The recording analyzed by the worker is the recording used for synchronized
  practice. Spotify is not a playback source.

## Current runtime architecture

The current path is:

```text
Flutter
  -> POST /analysis/jobs
  -> LocalAnalysisInputStorage
  -> InMemoryAnalysisJobRepository
  -> InProcessAnalysisJobExecutor (one worker thread)
  -> RealAnalysisProcessor
  -> isolated subprocess environments
  -> local job workspace
  -> SharedTimeline held in memory and returned by GET /result
  -> Flutter persists timeline + its app-owned imported audio file
```

Concern | Current implementation
--- | ---
Request handling | `backend/api/app/routers/analysis_jobs.py:create_analysis_job`
Job creation/state | `AnalysisJobService`, `AnalysisJobRecord`, and `InMemoryAnalysisJobRepository` in `backend/api/app/services/analysis_jobs.py`
Upload storage | `LocalAnalysisInputStorage` in `backend/api/app/services/analysis_input_storage.py`; one directory per job under `storage/uploads/analysis_jobs`
Execution | `InProcessAnalysisJobExecutor` in `backend/api/app/services/analysis_job_executor.py`
Subprocess orchestration | `RealAnalysisProcessor` in `backend/api/app/services/real_analysis_processor.py`
Result persistence | The public result is only in the in-memory job record. `timeline.json` also remains in the local analysis workspace, but it is not a durable result repository.
Playback persistence | `NativeAudioFileSelector` copies the selected file into the Flutter application documents directory. `LocalAnalyzedSessionLibrary` retains its path and timeline in `sessions.json`. `PracticeSessionFactory` plays that local file.
Temporary workspace | `RealAnalysisProcessor` creates `storage/analysis_jobs/<job-id>` and currently does not delete it. Only the temporary verified/romanized lyric directory and forced-alignment temporary directories self-delete.

## Future API/worker seam

The seam should be one durable job descriptor, not a set of stage-level remote
calls. The interface contains:

- job ID and display title;
- immutable source-audio object reference;
- isolated workspace identity;
- retained playback-audio destination;
- SharedTimeline result destination;
- feature/configuration version needed to reproduce the run.

API responsibilities:

- validate request metadata, format, decoded duration, and size;
- create and expose durable job state;
- issue upload authorization in a later ticket;
- enqueue one descriptor in a later ticket;
- expose status and result locations;
- never import or execute the heavy ML environments in the cloud deployment.

Worker responsibilities:

- claim one descriptor idempotently;
- obtain the exact source recording;
- create an isolated job workspace;
- run the unchanged analysis pipeline;
- atomically publish SharedTimeline and the retained playback artifact;
- delete normalized analysis WAVs, stems, model outputs, and other temporary
  artifacts after publication;
- update terminal job state.

No SQS, S3, or durable database adapter is introduced in S6-T01. The existing
in-process adapter remains the local implementation until a second executor
adapter makes this a real seam.

## Independent worker entry point

`python -m backend.api.app.analysis_worker` executes one job through the same
`RealAnalysisProcessor` used by FastAPI. Its contract is documented in
`backend/api/README.md`. The job ID must equal the input file's parent directory
name. This preserves the processor's existing deterministic job-local naming.
The API title is accepted in the descriptor but does not replace embedded audio
metadata for LRCLIB lookup.

## Workspace design

Current local layout:

```text
storage/analysis_jobs/<job-id>/
  normalized.wav
  chords.json
  btc_uncertainty.json       # BTC only
  beats.json
  separated/...              # temporary stems
  whisperx/...               # temporary transcript
  practice_regions.json      # only when MUSIC_ONLY is enabled
  timeline.json              # final result candidate
```

The worker command makes the workspace root configurable with
`CHORDSYNC_WORKSPACE_ROOT`, allowing `/tmp/chordsync/<job-id>` in a container.
All paths remain job-local and the processor refuses to reuse an existing job
directory. The worker owns cleanup. A future object-storage adapter owns only
published playback audio and SharedTimeline; neither the API nor object storage
should retain the ephemeral workspace.

Current cleanup is incomplete: local workspaces and uploads are retained. A
future worker must clean intermediates after successful publication and on
failure. The original upload should expire approximately 24 hours after a
successful job.

## Playback artifact

Today Flutter plays its app-owned copy of the original imported WAV, MP3, or
M4A file. That is already the exact recording supplied to analysis, so no
transcode is required for the supported clients. In cloud storage, publish the
same bytes under a retained playback-artifact key and treat the short-lived
upload object as a separate lifecycle role, even if the initial implementation
performs a server-side copy.

For a typical 256 kbps track, six minutes is about 11.5 MB. At the current
25 MB upload ceiling, a retained six-minute artifact is at most 25 MB. The
analysis-only mono 44.1 kHz 16-bit PCM WAV would be about 31.8 MB and should not
be retained as playback unless a later client compatibility requirement makes
transcoding necessary. If that becomes necessary, AAC-LC in M4A at 192 kbps is
about 8.6 MB for six minutes, but it adds a lossy generation and is not the
current recommendation.

## Analysis-worker dependency inventory

Classification: **A** image install, **B** runtime download/cache, **C**
external mount/configuration, **D** development-only, **E** unresolved.

Dependency | Class | Notes
--- | --- | ---
Python 3.11 | A | All current isolated environments target Python 3.11.
FFmpeg and ffprobe | A | Upload duration validation, normalization, and audio decoding.
Vamp SDK host (`sonic-annotator` or `vamp-simple-host`) | A/E | Install one supported Linux host. Exact distribution/package source must be proven in the worker image.
NNLS Chroma/Chordino Vamp plugin | A/E | Required by the Chordino path and optional MUSIC_ONLY diagnostics. Linux plugin discovery must be proven.
libsndfile | A | Used through SoundFile/librosa audio I/O.
Rubber Band CLI/library | A/E | `pyrubberband` is pinned in the BTC environment; verify whether production BTC inference actually invokes the native executable.
Build toolchain (`gcc`, `g++`, Python headers) | A | Build-stage requirement for madmom/native wheels; omit from final runtime where possible.
FastAPI, Uvicorn, python-multipart, Pydantic, AnyAscii | A | API/core contracts; versions are pinned in `requirements-runtime.txt`.
Core test environment (`pytest`) | D | Not needed in production images.
BTC environment: Torch, NumPy, librosa, PyYAML, mir_eval, pretty_midi, pandas, pyrubberband, SoundFile, Pydantic | A | Keep isolated because its NumPy/Torch constraints differ from madmom and other stages.
madmom environment: NumPy 1.26.4, madmom 0.16.1, setuptools | A | Keep isolated; compatibility shim is already present.
WhisperX environment (`whisperx==3.8.6` and its Torch/CTranslate2 dependencies) | A | Keep isolated from BTC and Demucs.
Demucs environment (`demucs==4.0.1`, TorchCodec) | A | Keep isolated.
Lyrics verification | A | Repository Python plus standard library; forced alignment executes through the WhisperX environment.
Romanization (`anyascii==0.3.3`) | A | Feature remains available but multilingual mode is disabled by default.
BTC upstream source and checkpoint | C | Paths supplied by `CHORDSYNC_BTC_SOURCE` and `CHORDSYNC_BTC_CHECKPOINT`; do not bake local checkpoints into the API image.
BTC Python executable | C | Supplied by `CHORDSYNC_BTC_PYTHON` in the multi-environment worker image.
Whisper ASR model | B | Download/cache on first use unless pre-populated in a separately governed model cache/image layer.
WhisperX language alignment models | B | Language-dependent runtime cache; availability differs by language.
Demucs `htdemucs` weights | B | Download/cache on first use unless pre-populated.
madmom model data | A | Distributed with madmom.
Reference/evaluation datasets and local lyrics | D | Explicitly excluded from production build context.
CUDA toolkit/runtime and matching GPU Torch wheels | E | Not needed for the CPU baseline. Pin and validate together when the GPU worker ticket selects an AWS instance family.

The worker-container recommendation is one Linux image with several isolated
virtual environments under `/opt/chordsync/venvs`, built in separate stages and
copied into the runtime stage. This preserves the tested dependency isolation
while still producing one schedulable worker artifact. BTC source/checkpoint
and model caches remain external or separately versioned. Do not collapse the
environments merely to reduce image count.

## Runtime portability findings

- No runtime `/Users`, `/opt/homebrew`, `/private/tmp`, simulator, or shell
  path is hard-coded in backend/analysis source.
- `AnalysisPipelineConfig.local()` previously assumed repository-local virtual
  environments. Environment overrides now cover workspace root, API Python,
  beat Python, WhisperX, and Demucs executables while retaining local defaults.
- BTC source, checkpoint, and interpreter were already environment-configured.
- Chordino host lookup uses `PATH` or environment configuration and is portable,
  but Linux host/plugin packaging remains unresolved.
- Subprocesses use argument arrays with `shell=False`; no shell dialect is
  required at runtime.
- Apple MPS selection remains in BTC as an optional local acceleration path;
  CUDA and CPU fallbacks remain portable.

## Container baseline

`backend/api/Dockerfile` is a non-root, lightweight API baseline. It includes
FFmpeg/ffprobe for request validation but deliberately excludes ML environments,
models, audio, datasets, storage, and Flutter. This ticket does not move job
execution out of process, so the image proves API import/startup/health only;
analysis submission requires the future external executor adapter and worker.

The repository `.dockerignore` excludes environment files, credentials by
omission from the build inputs, model extensions, commercial audio extensions,
local storage, local lyrics, datasets, virtual environments, caches, Git data,
Flutter, tests, documentation, and build output.

## Retention and security gaps for later tickets

- Durable job/result state and idempotency do not exist.
- Upload and workspace cleanup policies are not scheduled.
- Authentication, authorization, quotas, rate limiting, malware scanning, and
  encryption/key policy are required before public release.
- LRCLIB licensing/redistribution is not established; keep it opt-in and do not
  persist provider payloads.
- Logs need centralized retention and path/content review before production.
- Model/source provenance and reproducible Linux hashes need recording in the
  worker image manifest.

## Benchmark

Benchmark measurements and CPU feasibility are recorded in the S6-T01 delivery
report so commercial song identity and media are not added to the repository.
