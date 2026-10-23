# Chord extensions

An optional pipeline stage that upgrades plain major and minor chords to 7, maj7,
m7, sus2 or sus4 where two independent checks agree. Deployed to AWS on
2026-10-23 from commit `e974aff`, worker image `worker-e974aff`
(`sha256:9977fda803e3eec3ca8bc470d600b8e67ae54b8456ec7b8ebf3800ab699efc34`),
ECS task definition revision 20, model release 2026.10.3
(`docs/cloud/model-release-2026.10.3.md`).

## Problem

BTC's standard model has 25 classes: 12 major, 12 minor and none.
`analysis/chords/normalizer.py` also flattens every label to major or minor. A song
whose chart says Em7 or Asus4 therefore shows Em or A.

## Findings

1. BTC's large 170-chord model, tested on 31 songs, has mean confidence 0.57 on
   its 7, maj7, sus2, sus4 and dim7 labels (0.60 on m7) against 0.79 on plain
   triads. Its segments are about 1.3 s long. It is too noisy to show directly.
2. A note check (`analysis/chords/extensions.py`) measures which notes sound in the
   audio relative to the chord root. On synthetic guitar chords it is 94-97% right,
   with 0-2% false alarms on plain chords.
3. On real full-mix songs the note check invents extensions, because vocal melody
   notes count as chord notes. It therefore runs on the Demucs `no_vocals` stem.

## The rule

A plain BTC triad becomes 7, maj7, m7, sus2 or sus4 only where both agree:

- the large model gives the same root and the same extension at the segment
  midpoint, and
- the note check finds the extension in the instrumental audio.

Otherwise the chord stays a plain triad. A missing extension costs a beginner
nothing; a wrong one is a harder chord that is not in the song. dim7 is not
included: the large model almost never reports it and there is no reliable note
test for it.

## Validation

| Song | Result |
| --- | --- |
| Let It Be, Riptide, Perfect, Take Me Home, Knockin' (plain chords) | 0 false extensions |
| Wonderwall (against chord charts) | F#m7 47 beats (Em7 with capo 2), Esus4 4, Bsus4 5 |
| Wish You Were Here | Em7 55 beats, A7 12 |
| Hey Jude | C7 24, F7 8 |

Recall is partial by design.

Limits: the thresholds were tuned while looking at about 10 songs. More songs with
known charts should be checked, for example Folsom Prison Blues for dominant 7ths.

## Pipeline

- New optional stage `chord-extensions` (`analysis/pipeline_cli.py`), run after
  vocal separation.
- Switch: `CHORDSYNC_CHORD_EXTENSIONS_ENABLED`, set by the Terraform variable
  `chord_extensions_enabled` (default `false`).
- The step is optional in every way. If it is off, the large model is missing or
  fails to install, or the step times out or errors, the song keeps its plain
  chords. A song never fails because of it. The processor timeout default is 300 s
  (`chord_extensions_timeout`).
- The worker fetches the large model on demand, not at startup.

## App

The app draws 60 new chord shapes: the easiest shape per root for 7, maj7, m7, sus2
and sus4, within frets 0-9. A test verifies that each shape sounds only chord notes.
A built-in sample song, "All chord shapes" (84 chords), is listed only in builds
made with `--dart-define=CHORDSYNC_SHOW_CHORD_SAMPLE=true`.

## Deployment (2026-10-23)

| Item | Value |
| --- | --- |
| Worker image | `worker-e974aff`, `sha256:9977fda803e3eec3ca8bc470d600b8e67ae54b8456ec7b8ebf3800ab699efc34` |
| Task definition | revision 20 |
| Previous | revision 19: `worker-6d3b1b3`, `sha256:c79e7b5fa4b0c2b017fe508cffcfba10a9f8e1063419de9f00dd28c49d938361`, release 2026.10.2 |
| Settings | `CHORDSYNC_CHORD_EXTENSIONS_ENABLED=true`, model release 2026.10.3 |
| In-image check | the step on CPU with no network reproduced the local result: 175/175 labels identical |

ECR scan of the new image: 2 CRITICAL (tiff CVE-2026-52490, brotli
CVE-2026-111497) and 14 HIGH. The live image before had 8 CRITICAL and 91 HIGH.
Exceptions are recorded in `docs/security/container-exceptions.md`; the Brotli
exception was approved 2026-10-23 and expires 2026-11-22.

## Real AWS test

Wonderwall through the hosted API, job `633ccd39-32df-4764-b8d7-0d1bbb82489e`:

| Measure | Result |
| --- | --- |
| Total time | 384 s |
| Chord extensions step | 20.8 s |
| Chords | identical to the local run (F#m7 47, Bsus4 5, Esus4 4) |
| Lyrics | 274 words |

## Rollback

Run `terraform apply` with `worker_image_digest=sha256:c79e7b5f...` (the full digest
is in the table above), `model_release_id=2026.10.2` and
`chord_extensions_enabled=false`. To switch the feature off without changing the
image, set only `chord_extensions_enabled=false`.

The live Terraform inputs are not in the repository. A plain `terraform plan` with
only the saved `local.tfvars` would try to destroy the hosted API. Pass the live
values too: `project_name` chordsync, `environment` demo, `hosted_api_enabled` true,
`api_image_digest`, `demo_token_parameter_name`, `dispatcher_enabled`,
`worker_initial_wait_seconds` 120, `worker_linger_seconds` 300 and
`api_reserved_concurrency` -1. Read the plan before applying.

## Open questions

- Accuracy beyond the songs above is not measured.
- Behaviour on songs whose key or capo differs from the validation set is not
  measured.
