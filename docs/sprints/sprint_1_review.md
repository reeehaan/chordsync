# Sprint 1 Review and Retrospective

## Sprint

Sprint 1 — Harmonic Spine

## Sprint Dates

7 September 2026 – 20 September 2026

## Sprint Objective

Build the initial harmonic-analysis pipeline for ChordSync, including audio preprocessing, baseline chord estimation, neural chord estimation, normalization, and evaluation.

## Completed Work

- Repository structure created
- Local development environment configured
- Audio ingestion implemented
- FFmpeg preprocessing implemented
- Chordino baseline integrated
- Common chord output model implemented
- BTC chord estimator integrated
- mir_eval-based evaluation implemented
- Chordino and BTC compared against a reference annotation

## Evaluation Track

**Song:** Let It Be — The Beatles

**Reference annotation:** Isophonics chord annotation

### Results

| Model    | Root WCSR | Maj/Min WCSR |
| -------- | --------: | -----------: |
| Chordino |    0.8255 |       0.8254 |
| BTC      |    0.8529 |       0.8529 |

BTC achieved the highest result on the evaluated track.

The Maj/Min WCSR improvement over Chordino was approximately:

**0.8529 - 0.8254 = 0.0275**

or approximately **2.75 percentage points**.

## Sprint Outcome

The sprint objective was achieved.

ChordSync now has a working chord-analysis pipeline capable of:

1. accepting an audio file,
2. preprocessing it into a consistent audio representation,
3. estimating chords with Chordino,
4. estimating chords with BTC,
5. converting estimator outputs into a shared chord model,
6. normalizing chord labels,
7. evaluating predictions against reference annotations.

BTC currently appears to be the stronger candidate for the primary chord estimator, while Chordino remains useful as a classical baseline.

## What Went Well

- Chordino successfully ran natively on Apple Silicon.
- Sonic Annotator was successfully built and integrated.
- BTC inference successfully ran locally on CPU.
- Both estimators were converted into a common output representation.
- mir_eval provided reproducible quantitative evaluation.
- The first end-to-end chord benchmark was successfully completed.

## Challenges

### Chordino / Sonic Annotator

Sonic Annotator and the NNLS-Chroma Vamp plugin required manual compilation for Apple Silicon.

### BTC Compatibility

The original BTC implementation required compatibility changes for modern Python and PyTorch, including:

- YAML loading changes
- NumPy deprecated type replacement
- PyTorch checkpoint loading compatibility

### Chord Representation

Chordino and BTC use different naming conventions.

Examples:

- `Bbm` vs `A#:min`
- `Ab` vs `G#`
- extended chords such as `Fmaj7` and `F6`

A normalization layer was therefore required.

### Evaluation Dataset

A trusted reference annotation was required for meaningful evaluation.

The project initially used real-world test songs without verified chord ground truth. A reference-annotated Beatles track was later added for formal evaluation.

## Limitations

The current quantitative comparison uses only one reference song.

Therefore, the current results are preliminary and should not be interpreted as proof that BTC will outperform Chordino across all music.

Future evaluation should use multiple annotated tracks and report aggregate metrics.

The current normalization and evaluation primarily focus on major/minor chord recognition. Extended chord-quality evaluation will require additional work.

## Technical Debt

- Add support for evaluating multiple songs automatically.
- Export evaluation results to CSV or JSON.
- Add aggregate mean WCSR calculation.
- Improve support for seventh and extended chord qualities.
- Add stronger validation for malformed `.lab` files.
- Store estimator configuration and model information with evaluation results.

## Decision

For the next development stages:

**BTC will be treated as the primary neural chord estimator.**

**Chordino will remain as the baseline estimator for comparison.**

This decision may be revisited after evaluation on a larger dataset.

## Retrospective

### Keep

- Building small testable pipeline components
- Writing tests after each integration
- Using common data models between different estimators
- Validating models quantitatively instead of relying only on visual inspection

### Improve

- Select evaluation datasets earlier in the sprint
- Separate model environments before dependency conflicts occur
- Record model configurations and dataset provenance as experiments are created
- Benchmark multiple tracks rather than a single song

### Next Sprint

Sprint 2 will focus on the temporal grid.

Main areas:

- beat tracking
- downbeat detection
- timing representation
- chord-to-beat alignment
- preparation for timeline fusion
