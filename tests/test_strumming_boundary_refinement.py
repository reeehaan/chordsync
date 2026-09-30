"""Synthetic tests for S5-T16C3 MUSIC_ONLY boundary refinement.

These tests exercise ``refine_music_only_boundaries`` directly against
hand-built evidence blocks, independent of the frozen classifier. Each block
is two beats (two seconds) wide, matching the refiner's fine resolution:

- "stable": no chord change, high BTC margin/low entropy, matching estimators.
- "weak": one off-beat chord change, moderate margin/entropy degradation.
- "strongly_weak": two off-beat chord changes, severe margin/entropy collapse.

Blocks never disagree between BTC and Chordino; instability is carried
entirely by BTC chord-change behavior and BTC frame uncertainty, which keeps
the fixtures simple while still routing through the real evidence functions
(no internal function is monkeypatched).
"""

from __future__ import annotations

from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment
from analysis.evaluation.btc_uncertainty import BtcFrameUncertainty
from analysis.fusion.models import PracticeMode, PracticeRegion
from analysis.strumming.boundary_refinement import refine_music_only_boundaries

_BLOCK_SECONDS = 2.0


def _beats(max_time: int) -> list[BeatEvent]:
    return [
        BeatEvent(time=float(t), beat_number=t % 4 + 1, is_downbeat=t % 4 == 0, source="fixture")
        for t in range(max_time + 1)
    ]


def _build_song(blocks: str, *, label_cycle=("G", "C", "D")):
    """``blocks`` is a string of 's' (stable), 'w' (weak), 'x' (strongly weak).

    Each character covers one 2-second block starting at index * 2 seconds.
    """
    btc_chords: list[ChordSegment] = []
    frames: list[BtcFrameUncertainty] = []
    label_index = 0

    for index, kind in enumerate(blocks):
        start = index * _BLOCK_SECONDS
        if kind == "s":
            label = label_cycle[label_index % len(label_cycle)]
            label_index += 1
            btc_chords.append(
                ChordSegment(
                    start=start,
                    end=start + 2.0,
                    raw_label=label,
                    normalized_label=label,
                    source="fixture",
                )
            )
            margin, entropy = 0.95, 0.05
        elif kind == "w":
            first, second = (
                label_cycle[label_index % len(label_cycle)],
                label_cycle[(label_index + 1) % len(label_cycle)],
            )
            label_index += 2
            btc_chords.append(
                ChordSegment(
                    start=start,
                    end=start + 1.0,
                    raw_label=first,
                    normalized_label=first,
                    source="fixture",
                )
            )
            btc_chords.append(
                ChordSegment(
                    start=start + 1.0,
                    end=start + 2.0,
                    raw_label=second,
                    normalized_label=second,
                    source="fixture",
                )
            )
            margin, entropy = 0.60, 0.20
        elif kind == "x":
            labels = [
                label_cycle[(label_index + offset) % len(label_cycle)]
                for offset in range(3)
            ]
            label_index += 3
            third = _BLOCK_SECONDS / 3.0
            for run_index, label in enumerate(labels):
                btc_chords.append(
                    ChordSegment(
                        start=start + run_index * third,
                        end=start + (run_index + 1) * third,
                        raw_label=label,
                        normalized_label=label,
                        source="fixture",
                    )
                )
            margin, entropy = 0.30, 0.35
        else:
            raise ValueError(f"unknown block kind: {kind!r}")

        for offset in (0.0, 1.0):
            frames.append(
                BtcFrameUncertainty(
                    time=start + offset,
                    predicted_index=0,
                    predicted_label="G",
                    top1_score=0.5 + margin / 2,
                    top2_score=0.5 - margin / 2,
                    margin=margin,
                    normalized_entropy=entropy,
                )
            )

    chordino_chords = [
        ChordSegment(
            start=chord.start,
            end=chord.end,
            raw_label=chord.raw_label,
            normalized_label=chord.normalized_label,
            source="fixture",
        )
        for chord in btc_chords
    ]
    max_time = int(len(blocks) * _BLOCK_SECONDS)
    return _beats(max_time), btc_chords, chordino_chords, frames


def test_a_preceding_weak_evidence_extends_start_backward():
    blocks = "sssssssw" + "xxxxxxxx" + "ssssssss"
    beats, btc_chords, chordino_chords, frames = _build_song(blocks)
    region = PracticeRegion(start=16.0, end=32.0, mode=PracticeMode.MUSIC_ONLY)

    refined = refine_music_only_boundaries(
        [region], beats, btc_chords, chordino_chords, frames
    )

    assert len(refined) == 1
    assert refined[0].start == 14.0
    assert refined[0].end == 32.0


def test_b_preceding_stable_evidence_leaves_start_unchanged():
    blocks = "ssssssss" + "xxxxxxxx" + "ssssssss"
    beats, btc_chords, chordino_chords, frames = _build_song(blocks)
    region = PracticeRegion(start=16.0, end=32.0, mode=PracticeMode.MUSIC_ONLY)

    refined = refine_music_only_boundaries(
        [region], beats, btc_chords, chordino_chords, frames
    )

    assert len(refined) == 1
    assert refined[0].start == 16.0
    assert refined[0].end == 32.0


def test_c_stable_recovery_before_coarse_end_contracts_end():
    blocks = "ssssssss" + "xxxxxxss" + "ssssssss"
    beats, btc_chords, chordino_chords, frames = _build_song(blocks)
    region = PracticeRegion(start=16.0, end=32.0, mode=PracticeMode.MUSIC_ONLY)

    refined = refine_music_only_boundaries(
        [region], beats, btc_chords, chordino_chords, frames
    )

    assert len(refined) == 1
    assert refined[0].start == 16.0
    assert refined[0].end == 28.0


def test_d_uncertain_only_region_cannot_manufacture_music_only():
    blocks = "xxxxxxxxxxxxxxxxxxxxxxxx"
    beats, btc_chords, chordino_chords, frames = _build_song(blocks)

    refined = refine_music_only_boundaries(
        [], beats, btc_chords, chordino_chords, frames
    )

    assert refined == []


def test_e_no_practice_regions_is_unchanged():
    blocks = "ssssssss"
    beats, btc_chords, chordino_chords, frames = _build_song(blocks)

    refined = refine_music_only_boundaries(
        [], beats, btc_chords, chordino_chords, frames
    )

    assert refined == []


def test_f_refined_boundaries_stay_monotonic_non_overlapping_and_in_range():
    blocks = "ssss" + "xxxx" + "ssss" + "xxxx"
    beats, btc_chords, chordino_chords, frames = _build_song(blocks)
    region_one = PracticeRegion(start=0.0, end=8.0, mode=PracticeMode.MUSIC_ONLY)
    region_two = PracticeRegion(start=16.0, end=24.0, mode=PracticeMode.MUSIC_ONLY)

    refined = refine_music_only_boundaries(
        [region_two, region_one], beats, btc_chords, chordino_chords, frames
    )

    assert [region.start for region in refined] == sorted(
        region.start for region in refined
    )
    for earlier, later in zip(refined, refined[1:]):
        assert earlier.end <= later.start
    for region in refined:
        assert region.start >= 0.0
        assert region.end <= float(len(beats) - 1)
