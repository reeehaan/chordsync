# ChordSync

ChordSync is a final-year software engineering and Music Information
Retrieval project designed to help novice guitarists practise songs
using automatically recognised guitar chords and synchronised lyrics.

## Core Research Problem

The project investigates whether automatic chord estimation,
chord-boundary localisation, beat/downbeat information and word-level
lyric alignment can be integrated into a sufficiently accurate and
usable practice interface for novice guitarists.

## Core Pipeline

Audio
→ Pre-processing
→ Source Separation
→ Beat/Downbeat Tracking
→ Chord Estimation
→ Temporal Decoding
→ Lyric Processing
→ Timeline Fusion
→ Flutter Practice Interface

## Architecture

ChordSync uses a four-tier architecture:

1. Flutter mobile client
2. FastAPI application/API tier
3. Python asynchronous analysis workers
4. PostgreSQL/object-storage/Redis persistence tier

## Development Methodology

The project follows an adapted Agile/Scrum methodology consisting of
four risk-driven sprints:

- Sprint 1 — Harmonic Spine
- Sprint 2 — Temporal Grid
- Sprint 3 — Lyric Layer
- Sprint 4 — Interactive Client

## Current Status

ChordSync is currently in Sprint 5 — backend and client integration. The Python
pipeline supports chord analysis, beat/downbeat tracking, WhisperX word
alignment, and fusion into a shared practice timeline. Chordino remains the
default classical chord-estimation baseline, while BTC-ISMIR19 is now an
independently executable neural candidate using an isolated environment and
external local checkpoint. Formal multi-track comparison is still pending.

A duration-aware evaluation harness can run both estimators on one normalized
input and score them against a trusted `.lab` reference using root,
major/minor, triad, and no-chord metrics. Its synthetic result validates the
workflow only; real-song evaluation requires authorized audio, trusted
annotations, and recorded provenance. See `analysis/evaluation/README.md`.

The Flutter client can upload audio, poll analysis jobs, deserialize completed
timelines, and provide synchronized practice playback with chord, lyric,
rhythm, seeking, looping, speed, and bar-navigation controls.

## Repository Structure

- `mobile/` — Flutter practice client
- `backend/` — FastAPI application and analysis-worker foundations
- `analysis/` — chord, beat/downbeat, lyric, evaluation, and timeline fusion code
- `tests/` — Python pipeline tests
- `schemas/` — shared data schemas
- `datasets/` — reviewed evaluation metadata and permitted fixtures
- `storage/` — ignored local uploads and generated analysis output
- `docs/` — architecture, sprint, experiment, and research notes

## Hardware Strategy

Development:

- MacBook M2
- 8 GB unified memory

Local:

- Flutter
- FastAPI
- PostgreSQL
- Redis
- FFmpeg
- Chordino
- BTC inference on CPU through its isolated environment
- evaluation tooling

Remote CUDA worker (future/heavier runs):

- Demucs
- BTC full evaluation
- WhisperX
- heavier MIR workloads

## Mobile Target

Primary development target:

- iOS / physical iPhone

Secondary compatibility target:

- Android

## Development Setup

The Flutter client uses the SDK constraints and dependencies declared in
`mobile/pubspec.yaml`. From `mobile/`, resolve them with:

```sh
flutter pub get
```

Python 3.11 is the currently verified baseline. The backend, beat tracking,
evaluation, Whisper, and WhisperX dependencies intentionally use separate
virtual environments because their native and ML requirements differ.

Create and install the lightweight shared/test environment from the repository
root:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Create the subsystem environments in the same way:

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

Do not casually combine the Whisper and WhisperX environments: their PyTorch
and native dependency requirements can differ. The madmom environment uses the
tested NumPy 1.26.4 and setuptools 80.10.2 combination. Because madmom 0.16.1
is legacy software, ChordSync applies a small compatibility shim before
importing it on Python 3.11. Use madmom through the ChordSync beat modules and
scripts; no manual editing of packages inside a virtual environment is needed.

FFmpeg and ffprobe are external system requirements for audio preprocessing.
Chordino requires separately installed Vamp/Chordino tooling, including a
compatible command-line host. ML model downloads are external runtime inputs
and are not stored in Git. These instructions document the verified macOS
development arrangement and do not claim support for untested platforms.

BTC additionally requires a local checkout of the upstream BTC-ISMIR19 source
and a locally supplied checkpoint. Neither is vendored into this repository;
see `analysis/chords/btc/README.md` for configuration, provenance, vocabulary,
and Apple Silicon notes.

## Testing

Run the Python tests from the repository root:

```sh
pytest
```

Run static analysis from the repository root (tools are listed in
`requirements-dev.txt` and configured in `pyproject.toml`):

```sh
python3.11 -m venv .venv-dev
.venv-dev/bin/python -m pip install -r requirements-dev.txt
.venv-dev/bin/ruff check .
.venv-dev/bin/mypy
```

Run Flutter verification from `mobile/`:

```sh
flutter test
flutter analyze
```

## Research Data

Commercial or otherwise restricted audio is not distributed with the intended
public repository. Researchers must supply their own permitted local evaluation
audio. See `datasets/README.md` for repository data-handling guidance.

## Academic Context

ChordSync is a final-year academic project investigating the integration of
Music Information Retrieval techniques into a practice experience for novice
guitarists. Results and evaluation artifacts should be interpreted in that
research context.
