"""Fine-grained boundary refinement for already-confirmed MUSIC_ONLY regions.

The frozen strumming-state classifier (`analysis.evaluation
.strumming_state_classifier`) is solely responsible for deciding WHETHER a
MUSIC_ONLY region exists, using coarse beat-aligned windows. That decision is
never revisited here.

This module only adjusts WHERE an already-confirmed region starts and ends,
by re-examining the same underlying evidence (BTC frame uncertainty, BTC
chord-change behavior, BTC/Chordino disagreement) at a finer beat resolution
immediately around each boundary. It cannot create a MUSIC_ONLY region: with
no confirmed regions as input, it returns nothing, regardless of how much
fine-grained instability evidence exists elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment
from analysis.evaluation.btc_uncertainty import (
    BtcFrameUncertainty,
    aggregate_uncertainty_windows,
)
from analysis.evaluation.chord_reliability import build_reliability_windows
from analysis.evaluation.estimator_consensus import (
    sample_estimators_on_beats,
    summarize_estimator_region,
)
from analysis.evaluation.strumming_state_classifier import (
    EvidenceStrength,
    estimator_disagreement_strength,
    model_uncertainty_strength,
    structural_instability_strength,
)
from analysis.fusion.models import PracticeMode, PracticeRegion

_DEFAULT_COARSE_BEATS_PER_WINDOW = 8
_DEFAULT_FINE_BEATS_PER_WINDOW = 2
_TOLERANCE = 1e-6


@dataclass(frozen=True)
class _FineWindow:
    start: float
    end: float
    model_uncertainty: EvidenceStrength
    structural_instability: EvidenceStrength
    estimator_disagreement: EvidenceStrength


def refine_music_only_boundaries(
    regions: Sequence[PracticeRegion],
    beats: Sequence[BeatEvent],
    btc_chords: Sequence[ChordSegment],
    chordino_chords: Sequence[ChordSegment],
    frame_diagnostics: Sequence[BtcFrameUncertainty],
    *,
    coarse_beats_per_window: int = _DEFAULT_COARSE_BEATS_PER_WINDOW,
    fine_beats_per_window: int = _DEFAULT_FINE_BEATS_PER_WINDOW,
) -> list[PracticeRegion]:
    """Adjust only the start/end of already-confirmed MUSIC_ONLY regions.

    Non-MUSIC_ONLY regions pass through unchanged. When `regions` contains no
    MUSIC_ONLY entries, nothing is created here: the classifier's confirmation
    is a strict precondition, not something this function can supply.
    """
    if coarse_beats_per_window <= 0 or fine_beats_per_window <= 0:
        raise ValueError("beat counts must be positive")
    if coarse_beats_per_window % fine_beats_per_window != 0:
        raise ValueError(
            "fine_beats_per_window must evenly divide coarse_beats_per_window"
        )

    ordered_regions = sorted(regions, key=lambda region: region.start)
    music_only_positions = [
        index
        for index, region in enumerate(ordered_regions)
        if region.mode == PracticeMode.MUSIC_ONLY
    ]
    if not music_only_positions:
        return list(ordered_regions)

    ordered_beats = sorted(beats, key=lambda beat: beat.time)
    beat_times = [float(beat.time) for beat in ordered_beats]
    fine_windows = _build_fine_windows(
        btc_chords,
        chordino_chords,
        frame_diagnostics,
        ordered_beats,
        beats_per_window=fine_beats_per_window,
    )
    windows_by_end = {round(window.end, 6): window for window in fine_windows}
    windows_by_start = {round(window.start, 6): window for window in fine_windows}

    refined = list(ordered_regions)
    for position in music_only_positions:
        region = refined[position]
        lower_neighbor_bound = _bound_before(
            beat_times, region.start, coarse_beats_per_window
        )
        if position > 0:
            lower_neighbor_bound = max(
                lower_neighbor_bound, refined[position - 1].end
            )
        upper_neighbor_bound = _bound_after(
            beat_times, region.end, coarse_beats_per_window
        )
        if position + 1 < len(refined):
            upper_neighbor_bound = min(
                upper_neighbor_bound, refined[position + 1].start
            )

        new_start = _extend_start_backward(
            region.start, lower_neighbor_bound, windows_by_end
        )
        new_end = _extend_end_forward(
            region.end, upper_neighbor_bound, windows_by_start
        )
        if new_end <= region.end + _TOLERANCE:
            new_end = _contract_end_backward(
                region.end, new_start, windows_by_end
            )

        refined[position] = PracticeRegion(
            start=new_start, end=new_end, mode=region.mode
        )

    return refined


def _bound_before(beat_times, time, coarse_beats_per_window):
    index = _beat_index(beat_times, time)
    lower_index = max(0, index - coarse_beats_per_window)
    return beat_times[lower_index]


def _bound_after(beat_times, time, coarse_beats_per_window):
    index = _beat_index(beat_times, time)
    upper_index = min(len(beat_times) - 1, index + coarse_beats_per_window)
    return beat_times[upper_index]


def _beat_index(beat_times, time):
    for index, candidate in enumerate(beat_times):
        if abs(candidate - time) <= _TOLERANCE:
            return index
    raise ValueError(f"time {time} does not align to a beat")


def _extend_start_backward(start, lower_bound, windows_by_end):
    new_start = start
    while new_start > lower_bound + _TOLERANCE:
        window = windows_by_end.get(round(new_start, 6))
        if window is None or window.start < lower_bound - _TOLERANCE:
            break
        if not _supports_instability(window):
            break
        new_start = window.start
    return new_start


def _extend_end_forward(end, upper_bound, windows_by_start):
    new_end = end
    while new_end < upper_bound - _TOLERANCE:
        window = windows_by_start.get(round(new_end, 6))
        if window is None or window.end > upper_bound + _TOLERANCE:
            break
        if not _supports_instability(window):
            break
        new_end = window.end
    return new_end


def _contract_end_backward(end, region_start, windows_by_end):
    new_end = end
    while new_end > region_start + _TOLERANCE:
        window = windows_by_end.get(round(new_end, 6))
        if window is None or window.start <= region_start + _TOLERANCE:
            break
        if not _is_stable(window):
            break
        new_end = window.start
    return new_end


def _supports_instability(window: _FineWindow) -> bool:
    if window.structural_instability == EvidenceStrength.NORMAL:
        return False
    strengths = (
        window.model_uncertainty,
        window.structural_instability,
        window.estimator_disagreement,
    )
    non_normal = sum(strength != EvidenceStrength.NORMAL for strength in strengths)
    return non_normal >= 2


def _is_stable(window: _FineWindow) -> bool:
    return (
        window.model_uncertainty == EvidenceStrength.NORMAL
        and window.structural_instability == EvidenceStrength.NORMAL
    )


def _build_fine_windows(
    btc_chords,
    chordino_chords,
    frame_diagnostics,
    beats,
    *,
    beats_per_window,
) -> list[_FineWindow]:
    uncertainty_windows = aggregate_uncertainty_windows(
        frame_diagnostics, beats, beats_per_window=beats_per_window
    )
    structural_windows = build_reliability_windows(
        btc_chords, beats, beats_per_window=beats_per_window
    )
    structural_by_key = {
        (round(window.start, 6), round(window.end, 6)): window
        for window in structural_windows
    }
    estimator_samples = sample_estimators_on_beats(
        btc_chords, chordino_chords, beats
    )

    fine_windows = []
    for uncertainty_window in uncertainty_windows:
        key = (
            round(uncertainty_window.start, 6),
            round(uncertainty_window.end, 6),
        )
        structural_window = structural_by_key.get(key)
        if structural_window is None:
            continue
        estimator = summarize_estimator_region(
            estimator_samples,
            start=uncertainty_window.start,
            end=uncertainty_window.end,
        )
        fine_windows.append(
            _FineWindow(
                start=uncertainty_window.start,
                end=uncertainty_window.end,
                model_uncertainty=model_uncertainty_strength(
                    mean_margin=uncertainty_window.mean_margin,
                    mean_normalized_entropy=(
                        uncertainty_window.mean_normalized_entropy
                    ),
                    low_margin_ratio=uncertainty_window.low_margin_ratio,
                ),
                structural_instability=structural_instability_strength(
                    churn_per_beat=structural_window.churn_per_beat,
                    average_run_duration=structural_window.average_run_duration,
                    rapid_transition_count=(
                        structural_window.rapid_transition_count
                    ),
                    beat_alignment_ratio=structural_window.beat_alignment_ratio,
                ),
                estimator_disagreement=estimator_disagreement_strength(
                    disagreement_ratio=1.0 - estimator.exact_agreement,
                    longest_disagreement_run_beats=(
                        estimator.longest_disagreement_run_beats
                    ),
                ),
            )
        )
    return fine_windows
