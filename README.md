# ChordSync

**Upload a song, get its guitar chords and synchronised lyrics, and practise
along on your phone.**

ChordSync is a final-year software engineering project for beginner
guitarists. It analyses an audio file you own: it finds the chords, beats,
bars, and word-timed lyrics, then turns them into an interactive practice
sheet that scrolls in time with the music.

## Features

- **Upload a song**: WAV, MP3, or M4A, up to 6 minutes (25 MB).
- **Automatic chord recognition** with a neural model (BTC), with Chordino as
  a fallback.
- **Beat and bar tracking**, so chords line up with the rhythm.
- **Synchronised lyrics** with word-level timing, including other languages
  and romanised display for non-Latin scripts.
- **Practice screen** with chord diagrams, a scrolling song sheet, A–B
  looping, playback speed control, and bar-by-bar skipping.
- **Capo and simplify** tools that transpose the song into easier chord
  shapes.
- **Song library** of everything you've analysed.

## How it works

1. **Prepare the audio**: convert the upload to a standard format (FFmpeg).
2. **Find the chords**: a transformer model (BTC) labels the chords over time.
3. **Find the beat**: madmom detects beats and downbeats and groups them into
   bars.
4. **Isolate the vocals**: Demucs separates the singing from the
   instruments.
5. **Transcribe the lyrics**: WhisperX transcribes the vocals and times every
   word.
6. **Combine everything** into one shared timeline (JSON) that the app plays
   back in sync with the original audio.

## Tech stack

| Area | Technologies |
| --- | --- |
| Mobile app | Flutter, Dart |
| Backend API | Python 3.11, FastAPI |
| Audio and ML | FFmpeg, PyTorch, BTC-ISMIR19, Chordino, madmom, Demucs, WhisperX |
| Cloud (in progress) | AWS ECS Fargate (ARM64), S3, DynamoDB, SQS, ECR, Terraform |
| Quality | pytest, ruff, mypy, flutter test, Docker image scanning |

## Architecture

```text
Flutter app  →  FastAPI API  →  job queue  →  analysis worker  →  practice timeline
```

The app uploads a song to the API, which queues an analysis job. A worker runs
the pipeline and publishes the result, and the app downloads it when the job
is done. Locally, everything runs on one machine. The cloud version stores
files in S3, tracks jobs in DynamoDB, queues work in SQS, and runs the worker
as a container on AWS Fargate. All of it is defined in Terraform.

## Project status

- ✅ Full pipeline and mobile app working end to end on a local machine
- ✅ Cloud infrastructure defined in Terraform, with a security-scanned worker
  container
- 🔄 First controlled cloud run of the analysis worker
- 🔜 Formal accuracy evaluation of chord recognition on real songs

## Getting started

You need Python 3.11, Flutter, and FFmpeg. The analysis models use separate
Python environments, so see the
[full development setup](https://github.com/reeehaan/chordsync/blob/main/docs/development-setup.md)
for details. Once set up:

```sh
# Start the API
backend/api/.venv-api/bin/python -m uvicorn backend.api.app.main:app --port 8000

# Run the app (from mobile/)
flutter pub get
flutter run
```

Run the tests with `pytest` (Python) and `flutter test` (app).

## Project structure

```text
mobile/          Flutter practice app
backend/         FastAPI API and analysis worker
analysis/        Chord, beat, lyric, and timeline-fusion pipeline
infrastructure/  AWS infrastructure (Terraform)
tests/           Python tests
docs/            Architecture, cloud, and research notes
```

## Data and model notes

- No commercial audio is included; bring your own audio files.
- Model weights are not stored in this repository.
- The BTC source code is MIT licensed. Its pretrained checkpoint is used for
  non-commercial research only
  ([details](https://github.com/reeehaan/chordsync/blob/main/docs/licensing/btc-checkpoint.md)).

## About

ChordSync is my final-year academic project, exploring how Music Information
Retrieval techniques can support a practical practice tool for beginner
guitarists. It was built in Agile sprints covering chords, timing, lyrics, the
mobile client, and cloud deployment.
