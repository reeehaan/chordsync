# Development setup

This is the full local setup for ChordSync on macOS (Apple Silicon), the
verified development platform. For a short overview, see the main
[README](../README.md).

## Requirements

- Python 3.11
- Flutter (SDK constraint in `mobile/pubspec.yaml`)
- FFmpeg and ffprobe on `PATH`
- Optional: Vamp/Chordino tooling with a command-line host, for the Chordino
  estimator
- Optional: a local checkout of [BTC-ISMIR19](https://github.com/jayg996/BTC-ISMIR19)
  and its checkpoint, for the BTC estimator (see
  `analysis/chords/btc/README.md`)

ML model downloads are external runtime inputs and are not stored in Git.

## Flutter client

From `mobile/`:

```sh
flutter pub get
```

## Python environments

The backend, beat tracking, evaluation, Whisper, WhisperX, and separation
dependencies use separate virtual environments because their native and ML
requirements differ.

Shared/test environment, from the repository root:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Subsystem environments:

```sh
python3.11 -m venv backend/api/.venv-api
backend/api/.venv-api/bin/python -m pip install -r backend/api/requirements.txt

python3.11 -m venv analysis/beats/.venv-beats
analysis/beats/.venv-beats/bin/python -m pip install -r analysis/beats/requirements.txt

python3.11 -m venv analysis/evaluation/.venv-eval
analysis/evaluation/.venv-eval/bin/python -m pip install -r analysis/evaluation/requirements.txt

python3.11 -m venv analysis/chords/btc/.venv-btc
analysis/chords/btc/.venv-btc/bin/python -m pip install \
  -r analysis/chords/btc/requirements.txt

python3.11 -m venv analysis/lyrics/.venv-lyrics
analysis/lyrics/.venv-lyrics/bin/python -m pip install -r analysis/lyrics/requirements-whisper.txt

python3.11 -m venv analysis/lyrics/.venv-whisperx
analysis/lyrics/.venv-whisperx/bin/python -m pip install -r analysis/lyrics/requirements-whisperx.txt

python3.11 -m venv analysis/separation/.venv-separation
analysis/separation/.venv-separation/bin/python -m pip install \
  -r analysis/separation/requirements.txt
```

Notes:

- Do not combine the Whisper and WhisperX environments; their PyTorch and
  native dependencies can differ.
- The madmom environment uses the tested NumPy 1.26.4 and setuptools 80.10.2
  combination. madmom 0.16.1 is legacy software, so ChordSync applies a small
  compatibility shim before importing it on Python 3.11. Use madmom through the
  ChordSync beat modules; no manual package editing is needed.
- BTC needs `CHORDSYNC_BTC_PYTHON`, `CHORDSYNC_BTC_SOURCE`, and
  `CHORDSYNC_BTC_CHECKPOINT`. See `analysis/chords/btc/README.md` for
  configuration, provenance, and Apple Silicon notes, and
  `docs/licensing/btc-checkpoint.md` for the checkpoint's usage terms.

## Running locally

Start the API (with the BTC variables set in the same shell):

```sh
backend/api/.venv-api/bin/python -m uvicorn backend.api.app.main:app \
  --host 127.0.0.1 --port 8000
```

Then run the app from `mobile/`:

```sh
flutter run
```

The app expects the API at `http://127.0.0.1:8000`. Uploads must be WAV, MP3,
or M4A, at most 25 MB and 10 minutes long.

### Pointing the app at the hosted API

A build can talk to the deployed cloud API instead. Pass these at build time
(`mobile/lib/features/analysis/data/analysis_api_config.dart`):

```sh
flutter run \
  --dart-define=CHORDSYNC_API_MODE=hosted \
  --dart-define=CHORDSYNC_API_BASE_URL=https://<api-id>.execute-api.<region>.amazonaws.com
```

A build-time `CHORDSYNC_API_TOKEN` is compiled into the app, so use it for
private demo builds only. How the hosted stack is built and deployed is in
`docs/cloud/`.

## Testing

Python tests, from the repository root, using the shared environment (pytest is
pinned in `requirements.txt`):

```sh
.venv/bin/python -m pytest
```

Static analysis (tools listed in `requirements-dev.txt`, configured in
`pyproject.toml`):

```sh
python3.11 -m venv .venv-dev
.venv-dev/bin/python -m pip install -r requirements-dev.txt
.venv-dev/bin/ruff check .
.venv-dev/bin/mypy
```

Flutter, from `mobile/`:

```sh
flutter test
flutter analyze
```

## Research data

Commercial or otherwise restricted audio is not distributed with the
repository. Supply your own permitted local evaluation audio. See
`datasets/README.md` and `analysis/evaluation/README.md`.
