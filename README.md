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

ChordSync is currently in Sprint 4 — Interactive Client. The Python pipeline
supports chord analysis, beat/downbeat tracking, WhisperX word alignment, and
fusion into a shared practice timeline. The Flutter client can deserialize that
timeline, resolve playback state, and control test playback positions. Real
audio playback and the full practice interface are not implemented yet.

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
- evaluation tooling

Remote CUDA worker:

- Demucs
- BTC full inference/evaluation
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

Python components use intentionally isolated environments because the backend,
evaluation tools, beat tracking, and lyric alignment have different native and
ML dependencies. Existing pinned manifests include:

- `backend/api/requirements.txt`
- `analysis/evaluation/requirements.txt`

Some pipeline stages also require system tools such as FFmpeg and
Sonic Annotator/Chordino. Environment-specific setup is still being documented;
consult the sprint and experiment notes before attempting full pipeline setup.

## Testing

Run the Python tests from the repository root:

```sh
pytest
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
