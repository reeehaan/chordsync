"""Frozen conservative classifier for chord-guidance display states.

MUSIC_ONLY never changes or removes an estimator's chord labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from analysis.fusion.models import PracticeMode, PracticeRegion


class EvidenceStrength(str, Enum):
    NORMAL = "NORMAL"
    WEAK = "WEAK"
    STRONGLY_WEAK = "STRONGLY_WEAK"


class StrummingState(str, Enum):
    PLAY_CHORD = "PLAY_CHORD"
    UNCERTAIN = "UNCERTAIN"
    MUSIC_ONLY = "MUSIC_ONLY"


@dataclass(frozen=True)
class StrummingEvidenceWindow:
    start: float
    end: float
    model_uncertainty: EvidenceStrength
    structural_instability: EvidenceStrength
    section_consistency: EvidenceStrength
    estimator_disagreement: EvidenceStrength


@dataclass(frozen=True)
class ClassifiedStrummingWindow:
    start: float
    end: float
    state: StrummingState
    weak_group_count: int
    strongly_weak_group_count: int
    music_only_candidate: bool


@dataclass(frozen=True)
class StrummingStateRegion:
    start: float
    end: float
    state: StrummingState


def model_uncertainty_strength(
    *,
    mean_margin: float,
    mean_normalized_entropy: float,
    low_margin_ratio: float,
) -> EvidenceStrength:
    severe = sum(
        (
            mean_margin < 0.50,
            mean_normalized_entropy > 0.30,
            low_margin_ratio > 0.12,
        )
    )
    warnings = sum(
        (
            mean_margin < 0.70,
            mean_normalized_entropy > 0.18,
            low_margin_ratio > 0.05,
        )
    )
    if severe >= 2:
        return EvidenceStrength.STRONGLY_WEAK
    if warnings >= 2:
        return EvidenceStrength.WEAK
    return EvidenceStrength.NORMAL


def structural_instability_strength(
    *,
    churn_per_beat: float,
    average_run_duration: float,
    rapid_transition_count: int,
    beat_alignment_ratio: float,
) -> EvidenceStrength:
    severe = sum(
        (
            churn_per_beat >= 0.75,
            average_run_duration < 0.75,
            rapid_transition_count >= 2,
            beat_alignment_ratio < 0.40,
        )
    )
    warnings = sum(
        (
            churn_per_beat >= 0.50,
            average_run_duration < 1.25,
            rapid_transition_count >= 1,
            beat_alignment_ratio < 0.60,
        )
    )
    if severe >= 2:
        return EvidenceStrength.STRONGLY_WEAK
    if warnings >= 1:
        return EvidenceStrength.WEAK
    return EvidenceStrength.NORMAL


def section_consistency_strength(
    *,
    nearest_similarity: float,
    supporting_windows: int,
) -> EvidenceStrength:
    if supporting_windows == 0 and nearest_similarity < 0.40:
        return EvidenceStrength.STRONGLY_WEAK
    if supporting_windows == 0 and nearest_similarity < 0.65:
        return EvidenceStrength.WEAK
    return EvidenceStrength.NORMAL


def estimator_disagreement_strength(
    *,
    disagreement_ratio: float,
    longest_disagreement_run_beats: int,
) -> EvidenceStrength:
    if disagreement_ratio >= 0.70 and longest_disagreement_run_beats >= 4:
        return EvidenceStrength.STRONGLY_WEAK
    if disagreement_ratio >= 0.45 or longest_disagreement_run_beats >= 3:
        return EvidenceStrength.WEAK
    return EvidenceStrength.NORMAL


def classify_strumming_windows(
    windows: Sequence[StrummingEvidenceWindow],
) -> list[ClassifiedStrummingWindow]:
    """Classify ordered windows with two-window entry and recovery hysteresis."""
    ordered = sorted(windows, key=lambda window: (window.start, window.end))
    classified = []
    previous_state = StrummingState.PLAY_CHORD
    candidate_streak = 0
    stable_streak = 2

    for window in ordered:
        groups = (
            window.model_uncertainty,
            window.structural_instability,
            window.section_consistency,
            window.estimator_disagreement,
        )
        weak_count = sum(group != EvidenceStrength.NORMAL for group in groups)
        strong_count = sum(
            group == EvidenceStrength.STRONGLY_WEAK for group in groups
        )
        structure_is_weak = (
            window.structural_instability != EvidenceStrength.NORMAL
        )
        decisive_cross_check = (
            window.estimator_disagreement == EvidenceStrength.STRONGLY_WEAK
            or (
                window.model_uncertainty == EvidenceStrength.STRONGLY_WEAK
                and window.section_consistency == EvidenceStrength.STRONGLY_WEAK
            )
        )
        candidate = weak_count >= 3 and structure_is_weak and decisive_cross_check

        if candidate:
            candidate_streak += 1
            stable_streak = 0
            state = (
                StrummingState.MUSIC_ONLY
                if previous_state == StrummingState.MUSIC_ONLY
                or candidate_streak >= 2
                else StrummingState.UNCERTAIN
            )
        else:
            candidate_streak = 0
            warning = weak_count >= 2 or any(
                group == EvidenceStrength.STRONGLY_WEAK
                for index, group in enumerate(groups)
                if index != 2
            )
            if warning:
                stable_streak = 0
                state = StrummingState.UNCERTAIN
            else:
                stable_streak += 1
                recovering = previous_state in {
                    StrummingState.MUSIC_ONLY,
                    StrummingState.UNCERTAIN,
                }
                state = (
                    StrummingState.UNCERTAIN
                    if recovering and stable_streak < 2
                    else StrummingState.PLAY_CHORD
                )

        classified.append(
            ClassifiedStrummingWindow(
                start=window.start,
                end=window.end,
                state=state,
                weak_group_count=weak_count,
                strongly_weak_group_count=strong_count,
                music_only_candidate=candidate,
            )
        )
        previous_state = state
    return classified


def merge_strumming_regions(
    windows: Sequence[ClassifiedStrummingWindow],
) -> list[StrummingStateRegion]:
    regions = []
    for window in windows:
        if regions and regions[-1].state == window.state:
            previous = regions[-1]
            regions[-1] = StrummingStateRegion(
                start=previous.start,
                end=window.end,
                state=previous.state,
            )
        else:
            regions.append(
                StrummingStateRegion(window.start, window.end, window.state)
            )
    return regions


def export_confirmed_music_only_regions(
    classified: Sequence[ClassifiedStrummingWindow],
    evidence: Sequence[StrummingEvidenceWindow],
    *,
    beats_per_window: int = 8,
    minimum_music_only_beats: int = 16,
) -> list[PracticeRegion]:
    """Consolidate first, then export MUSIC_ONLY runs for SharedTimeline.

    PLAY_CHORD and UNCERTAIN intentionally remain implicit normal-practice
    behavior. Keeping consolidation inside this API prevents raw one-window
    candidates from being exported accidentally.
    """
    windows = consolidate_strumming_windows(
        classified,
        evidence,
        beats_per_window=beats_per_window,
        minimum_music_only_beats=minimum_music_only_beats,
    )
    music_windows = [
        window for window in windows if window.state == StrummingState.MUSIC_ONLY
    ]
    if not music_windows:
        return []

    regions = []
    start = music_windows[0].start
    end = music_windows[0].end
    for window in music_windows[1:]:
        if window.start == end:
            end = window.end
            continue
        regions.append(
            PracticeRegion(start=start, end=end, mode=PracticeMode.MUSIC_ONLY)
        )
        start, end = window.start, window.end
    regions.append(
        PracticeRegion(start=start, end=end, mode=PracticeMode.MUSIC_ONLY)
    )
    return regions


def consolidate_strumming_windows(
    classified: Sequence[ClassifiedStrummingWindow],
    evidence: Sequence[StrummingEvidenceWindow],
    *,
    beats_per_window: int = 8,
    minimum_music_only_beats: int = 16,
) -> list[ClassifiedStrummingWindow]:
    """Consolidate existing states without manufacturing new weak evidence."""
    if len(classified) != len(evidence):
        raise ValueError("classified windows and evidence must have equal lengths")
    if beats_per_window <= 0 or minimum_music_only_beats <= 0:
        raise ValueError("beat counts must be positive")
    minimum_windows = (
        minimum_music_only_beats + beats_per_window - 1
    ) // beats_per_window
    states = [window.state for window in classified]

    music_indexes = {
        index
        for index, state in enumerate(states)
        if state == StrummingState.MUSIC_ONLY
    }
    changed = True
    while changed:
        changed = False
        for index, state in enumerate(states):
            if state != StrummingState.UNCERTAIN or index in music_indexes:
                continue
            next_to_music = index - 1 in music_indexes or index + 1 in music_indexes
            if next_to_music and _supports_music_only_expansion(
                classified[index], evidence[index]
            ):
                music_indexes.add(index)
                changed = True

    for start, end in _contiguous_runs(sorted(music_indexes)):
        if end - start < minimum_windows:
            music_indexes.difference_update(range(start, end))

    for index, state in enumerate(states):
        if index in music_indexes:
            states[index] = StrummingState.MUSIC_ONLY
        elif state == StrummingState.MUSIC_ONLY:
            states[index] = StrummingState.UNCERTAIN

    for index in range(len(states) - 1):
        if states[index] != StrummingState.MUSIC_ONLY:
            continue
        if states[index + 1] == StrummingState.PLAY_CHORD:
            states[index + 1] = StrummingState.UNCERTAIN

    return [
        ClassifiedStrummingWindow(
            start=window.start,
            end=window.end,
            state=states[index],
            weak_group_count=window.weak_group_count,
            strongly_weak_group_count=window.strongly_weak_group_count,
            music_only_candidate=window.music_only_candidate,
        )
        for index, window in enumerate(classified)
    ]


def _supports_music_only_expansion(classified, evidence):
    return (
        classified.weak_group_count >= 3
        and evidence.structural_instability != EvidenceStrength.NORMAL
    )


def _contiguous_runs(indexes):
    if not indexes:
        return []
    runs = []
    start = previous = indexes[0]
    for index in indexes[1:]:
        if index != previous + 1:
            runs.append((start, previous + 1))
            start = index
        previous = index
    runs.append((start, previous + 1))
    return runs
