# Sprint 1 — Harmonic Spine

## Sprint Goal

Determine whether automatic chord estimation is sufficiently accurate
to form the harmonic foundation of ChordSync.

## Research Question

How effectively can an automatic chord-recognition approach identify
relevant guitar chords and their approximate temporal boundaries from
song audio?

## Planned Output

Audio
→ preprocessing
→ chord estimation
→ timestamped chord segments
→ evaluation

## Sprint Tasks

- [x] S1-T01 Create repository structure
- [ ] S1-T02 Configure local development environment
- [ ] S1-T03 Implement audio ingestion
- [ ] S1-T04 Implement FFmpeg preprocessing
- [ ] S1-T05 Implement Chordino baseline
- [ ] S1-T06 Define common chord output model
- [ ] S1-T07 Integrate BTC estimator
- [ ] S1-T08 Implement mir_eval evaluation
- [ ] S1-T09 Compare Chordino vs BTC
- [ ] S1-T10 Sprint review and retrospective

## Definition of Done

Sprint 1 is complete when:

- a real recording can be accepted by the analysis pipeline
- audio can be normalised into the required analysis format
- Chordino produces timestamped chord labels
- BTC produces timestamped chord labels
- both outputs conform to the same schema
- evaluation metrics can be generated reproducibly
- experiment results are recorded
