# S8-T03 Reference lyrics in the worker, and job cancel

## Reference lyrics (LRCLIB)

Hosted mode returned raw WhisperX lyrics because `CHORDSYNC_LRCLIB_REFERENCE_ENABLED`
was unset in the worker task definition. The `CHORDSYNC_STAGE_NETWORK=disabled` guard
only covers analysis subprocesses (it hands them a copy of the environment with a dead
proxy); the lookup runs in the worker's own process, and the worker security group
already allows HTTPS egress. So the fix was two settings in `main.tf`
(`CHORDSYNC_LRCLIB_REFERENCE_ENABLED=true`, `CHORDSYNC_LRCLIB_USER_AGENT` naming the
repo). No image rebuild, and the reference lyrics stay in worker memory only
(`full_lyrics_storage_permitted` is false). The song is identified from its embedded
tags (28 of 31 test files have them; untagged files skip the lookup).

Real-device run (job `642a95c0…`, Homewrecker): `reference matched`, 3 min 4 s worker
stages, 100 BPM, 87 bars. The same file through the local pipeline:

| | Local | Cloud |
| --- | --- | --- |
| raw WER vs reference | 0.3135 | 0.6698 |
| corrected WER | 0.3064 | 0.6675 |
| inserted words | 17 | 151 |
| candidates accepted | 3 | 1 |

Cause: one WhisperX repetition loop in the cloud transcript (lyric line 7, 123-151 s:
192 words, 12 distinct, one 4-gram repeated 30 times; local had 59 words). The other
nine lines match in text and timing. Same model files (checksums), same command (CPU,
int8). This is a transcription hallucination, not a cloud configuration difference.
Possible fixes, not done: collapse repeated n-grams before verification, or stop
conditioning on previous text. Follow-up.

## Incident: model assets lost in the rename

The S8-T02 rename replaced the artifacts bucket, which held `models/` (15 files,
960 MB) next to the job data. The first run after it failed at model bootstrap
(`AccessDenied` on the manifest, exit 3, queue not polled). Recovery: all 15 files were
found locally, matched the committed manifest by SHA-256, and were re-uploaded with
SHA-256 checksums and SSE-S3; the manifest (`ecb88b94…fa894`) went up last. Lesson: the
artifacts bucket is not disposable. Model assets should be backed up or the bucket
protected before any replacement.

## Cancel

`POST /analysis/jobs/{job_id}/cancel` (hosted only, same bearer auth, same write
throttle). Owner only; another owner's or an unknown job is the same 404. Allowed from
created, awaiting_upload, validating, queued and processing; repeating it returns 200;
a completed, failed or expired job answers 409 `invalid_job_state`. The status API now
reports `cancelled` and the result route answers 409 `job_cancelled`.

The worker already skips cancelled jobs it has not claimed and discards the result of
one cancelled while processing, so there is no worker change. A processing job still
runs to the end (up to about 4 minutes of worker time); stopping it early would need a
cancel check between stages in the worker and a new image. A cancelled queued job still
causes one short worker start that acknowledges the message and exits.

Mobile: `AnalysisApiClient.cancelJob` (no-op for the local API). The hosted client
cancels the job if the user cancels after it was created (during upload or confirm), and
the coordinator cancels it when polling is cancelled. Both are best effort (5 s cap) and
never hide the cancellation. A job cancelled elsewhere stops polling as cancelled.

## Repetition guard

`analysis/lyrics/repetition_guard.py` cuts WhisperX loops right after the lyrics stage,
before verification or fusion. Only uninterrupted runs count (10+ repeats of one word,
6+ of a phrase of up to 8 words); the first three repeats are kept. On the real
transcripts it cut the looping line from 192 to 36 words and left the good local result
untouched.

## Deployment and device results (2026-10-18)

Images built from `69b5021`, pushed to `chordsync-demo/*`. API `api-69b5021`
(`sha256:96fbeffb…a355a`, clean `git archive` build, linux/arm64). Worker
`worker-69b5021` (`sha256:4e65d4e9…41f85`) is the reviewed worker image
`worker-d9ef4a3-runtime2` with only `/opt/chordsync/app/analysis` and `.../backend`
replaced by the committed source, because a full rebuild would have re-downloaded every
dependency (the Docker build cache had been cleared). Plan applied: 2 added, 2 changed,
1 destroyed (cancel route, API stage, API Lambda image, worker task definition).

| Check | Result |
| --- | --- |
| Cancel route | 401 without a token, 404 for an unknown job, 200 for the owner |
| Cancel from the app, mid-analysis | job `cancelled` on AWS; the started worker acknowledged and skipped it (41 s, exit 0, no analysis) |
| Homewrecker again | worker exit 0 in 4m29s; "removed 65 words from 1 repeated lyric loops" |
| Raw WER vs reference | 0.3373 (was 0.6698; local 0.3135); inserted words 7 (was 151) |
| Lyrics follow playback | works on the iPhone with and without a capo |

Mobile fix: with a capo set the practice screen passed a new timeline object on every
build, and `SongSheetLyrics` refreshed its remembered focus while regrouping, so it never
saw a line change and never scrolled. It now compares against the previous focus first
(test: "keeps following when the timeline is rebuilt on every frame").

## Still open

- A processing job cancelled by the user still runs to the end (up to about 4 minutes);
  stopping it early needs a stage-boundary check in the worker.
- LRCLIB correction changes little (one candidate accepted, WER 0.3373 to 0.3349); the
  verifier does not insert words ASR missed (79 deletions here).
- Untagged files skip the lookup; the app could ask for title and artist.

## Language misdetection: "Her" (2026-10-18)

An English song ("Her") crashed the lyrics stage: WhisperX guessed Nynorsk from the
vocals' opening and tried to download `NbAiLab/nb-wav2vec2-1b-nynorsk`, which the
offline worker cannot do. The existing fallback only matched "No default align-model for
language:", so the job failed and was re-queued (the app showed "Waiting to analyze").
Only the English alignment model is staged, so any non-English detection would have done
the same.

Fixes (commit `df1ef53`, worker image `worker-df1ef53`, `sha256:23d273a7…8888b0d`, task
definition revision 4, plan 1 added / 1 destroyed):

- `analysis/lyrics/language_hint.py`: reference lyrics with at least 30 Latin words and a
  25% share of common English words pin the run to `--language en`. Checked on real
  LRCLIB lyrics: English songs detected as English; Hindi, Japanese and Sinhala lyrics are
  in their own scripts, so they keep automatic detection.
- The `--no_align` fallback now also matches "The chosen align_model" and "could not be
  found in huggingface", so an unavailable alignment model degrades to sentence timing
  instead of failing the job.

Device result for "Her": `reference lyrics are English; using language=en`, lyrics stage
38 s, worker exit 0 in 4m07s, raw and corrected WER 0.2733, 0 inserted words.

Remaining: non-English songs without reference lyrics still use automatic detection (a
wrong guess now completes but may be mistranscribed); Hindi and Sinhala get sentence-level
timing until their alignment models are staged in the model release.

## Synced lyrics, word alignment and on-demand models (2026-10-19)

**Sinhala via WhisperX failed.** The small Whisper model wrote "Mandaaram Handaawe"
as noisy Latin text (723 Latin letters, no Sinhala) with a 75-character stuck word,
and "Naadagam Geeya" (no lyrics at LRCLIB) as a mix of Latin and Devanagari with one
word repeated 47 times. Only an English aligner is staged, so other languages get
sentence-level timing at best.

**Synced lyrics replace transcription** for non-English songs when LRCLIB has them
(`analysis/lyrics/synced_reference.py`): the lines are parsed from LRC, shifted to
the singing found in the vocals stem (`audioop` RMS), and turned into a WhisperX-shaped
transcript, so fusion is unchanged (lyric source `lrclib-synced`). Matching was widened:
the exact LRCLIB lookup rejects a recording more than ~2 s off, so a search fallback
picks the closest candidate within 10 s, accepted only when title, artist and album all
match exactly. A rate-limited (429) answer never triggers a second request.

**Word times by forced alignment** (`analysis/lyrics/mms_alignment.py`): the even split
of words inside a line was off by 0.6 s on average and up to 1.8 s (median late, so
highlights looked delayed and chords landed on the wrong words, because chords attach to
whichever word has not ended when the chord changes). Each line is now aligned to the
vocals with `torchaudio.pipelines.MMS_FA` inside a window around its synced time, with
words romanised by `uroman` 1.3.1.1. A line that fails keeps the even split. Locally: all
41 lines aligned, 30 s; on the 4-vCPU Fargate worker 75 s.

**On-demand model.** The 1.18 GB MMS weights (CC-BY-NC 4.0, approved for non-commercial
research in `docs/licensing/mms-fa.md`) live in model release `2026.10.2` as the optional
role `alignment_mms`. Startup installs everything except on-demand roles; the processor
fetches and verifies the aligner just before alignment (`install_role`), so songs that do
not need it never download it. Containers are one-shot, so a song that does need it
downloads it each time (13.0 s measured).

| Device run (job `cd459c4d…`, worker revision 7) | |
| --- | --- |
| total | 4m45s, exit 0 |
| lyrics from synced reference | 0.2 s, 41 lines |
| alignment model ready | 13.0 s |
| align | 75.0 s |

Also: lyric auto-scroll no longer stalls with a capo (the timeline object changed every
build), a stuck-letter guard drops words of 15+ identical characters, and the app now uses
the Golden Hour theme with Newsreader and DM Sans (`docs/licensing/fonts.md`).

Open: songs LRCLIB lacks (for example Naadagam Geeya) still go through Whisper small;
ideas are a language picker (force `si` instead of guessing), user-supplied lyrics to align,
or a larger model. The second transcription pass when the alignment model is missing costs
60-90 s and could be skipped by detecting the language first.
