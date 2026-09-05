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

## Sprint 1 Objective

Produce an end-to-end pipeline:

Audio → Chord Labels → Raw Timestamps → Evaluation

The first comparison will be:

- Chordino / NNLS-Chroma baseline
- BTC Bi-directional Transformer

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

## Status

Sprint 1 — Harmonic Spine
