# ChordSync

**Upload a song, get its guitar chords and synchronised lyrics, and practise
along on your phone.**

ChordSync is a final-year software engineering project for beginner
guitarists. It analyses an audio file you own: it finds the chords, beats,
bars, and word-timed lyrics, then turns them into an interactive practice
sheet that scrolls in time with the music.

## The problem

Online chord sheets are plain text. They list the chords and the lyrics, but
they don't show *when* each chord should be played or *which word* is being
sung at that moment, and for many songs no chord sheet exists at all. A
beginner is left to work out the timing alone. ChordSync puts the detected
chords and the aligned lyrics on one shared timeline, so both can be shown
together, in time with the music, with the sung word highlighted.

## Features

- **Upload a song**: WAV, MP3, or M4A, up to 10 minutes (25 MB).
- **Automatic chord recognition** with a neural model (BTC), including 7th
  and sus chords where two checks agree.
- **Beat and bar tracking**, so chords line up with the rhythm.
- **Synchronised lyrics** with word-level highlighting, including other
  languages (such as Sinhala and Hindi) and romanised display for non-Latin
  scripts. Reference lyrics are used to check and correct what is heard.
- **Practice screen** with chord diagrams, a scrolling song sheet, A–B
  looping, playback speed control, and bar-by-bar skipping.
- **Capo and simplify** tools that transpose the song into easier chord
  shapes.
- **Song library** of everything you've analysed, with accounts and sign-in
  by emailed code.

## How it works

1. **Prepare the audio**: convert the upload to a standard format (FFmpeg).
2. **Find the chords**: a transformer model (BTC) labels the chords over time.
3. **Find the beat**: madmom detects beats and downbeats and groups them into
   bars.
4. **Isolate the vocals**: Demucs separates the singing from the
   instruments.
5. **Get the lyrics**: WhisperX transcribes the vocals and times every word.
   Where reference lyrics exist (LRCLIB), they are compared with the
   transcript and used when the transcript is poor. For non-English songs,
   the reference text is aligned straight to the vocals instead.
6. **Combine everything** into one shared timeline (JSON) that the app plays
   back in sync with the original audio.

## Tech stack

| Area | Technologies |
| --- | --- |
| Mobile app | Flutter, Dart |
| Backend API | Python 3.11, FastAPI |
| Audio and ML | FFmpeg, PyTorch, BTC-ISMIR19, madmom, Demucs, WhisperX, MMS forced alignment |
| Cloud (live) | API Gateway, Lambda, ECS Fargate (ARM64), S3, DynamoDB, SQS, Cognito, SES, ECR, CloudWatch, Terraform |
| Quality | pytest, ruff, mypy, flutter test, Docker image scanning |

## Architecture

```text
Flutter app  →  API  →  job queue  →  analysis worker  →  practice timeline
```

The app uploads a song, and the API queues an analysis job. A worker runs the
pipeline and publishes the result, and the app downloads it when the job is
done. Locally, everything runs on one machine. In the cloud, the API runs on
Lambda behind API Gateway, files live in S3, jobs are tracked in DynamoDB,
work is queued in SQS, and the worker runs as a container on AWS Fargate.
Users sign in with Cognito. All of it is defined in Terraform.

## Project status

- ✅ Full pipeline and mobile app working end to end
- ✅ Deployed on AWS with accounts, a song library, and security-scanned
  containers
- ✅ Word-level lyric highlighting, including non-English songs

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
backend/         API and analysis worker
analysis/        Chord, beat, lyric, and timeline-fusion pipeline
infrastructure/  AWS infrastructure (Terraform)
tests/           Python tests
docs/            Architecture, cloud, and research notes
```

## Data and model notes

- No commercial audio is included; bring your own audio files.
- Model weights are not stored in this repository.
- The BTC source code is MIT licensed. Its pretrained checkpoint, and the MMS
  alignment model, are used for non-commercial research only
  ([BTC details](https://github.com/reeehaan/chordsync/blob/main/docs/licensing/btc-checkpoint.md)).

## About

ChordSync is my final-year academic project, exploring how Music Information
Retrieval techniques can support a practical practice tool for beginner
guitarists: how automatically detected chords and aligned lyrics can be
brought onto one timeline and shown in a way that is genuinely useful when
learning a song on guitar. It was built in Agile sprints covering chords,
timing, lyrics, the mobile client, and cloud deployment.
