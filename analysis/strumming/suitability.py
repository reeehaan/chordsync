from analysis.beats.models import BeatGrid
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
from analysis.evaluation.harmonic_consensus import (
    build_harmonic_windows,
    compare_harmonic_windows,
)
from analysis.evaluation.strumming_state_classifier import (
    StrummingEvidenceWindow,
    classify_strumming_windows,
    estimator_disagreement_strength,
    export_confirmed_music_only_regions,
    model_uncertainty_strength,
    section_consistency_strength,
    structural_instability_strength,
)
from analysis.fusion.models import PracticeRegion
from analysis.strumming.boundary_refinement import refine_music_only_boundaries


def detect_music_only_regions(
    btc_chords: list[ChordSegment],
    chordino_chords: list[ChordSegment],
    beat_grid: BeatGrid,
    frame_diagnostics: list[BtcFrameUncertainty],
) -> list[PracticeRegion]:
    """Apply the frozen S5-T16 evidence, classifier, and consolidation."""
    beats = beat_grid.beats
    uncertainty = aggregate_uncertainty_windows(frame_diagnostics, beats)
    structural = build_reliability_windows(btc_chords, beats)
    harmonic = build_harmonic_windows(
        btc_chords,
        beats,
        bars_per_window=2,
        align_to_downbeat=False,
    )
    estimator_samples = sample_estimators_on_beats(
        btc_chords,
        chordino_chords,
        beats,
    )
    window_count = min(len(uncertainty), len(structural), len(harmonic))
    evidence = []
    for index in range(window_count):
        uncertainty_window = uncertainty[index]
        structural_window = structural[index]
        harmonic_window = harmonic[index]
        if not _same_window(
            uncertainty_window.start,
            uncertainty_window.end,
            structural_window.start,
            structural_window.end,
            harmonic_window.start,
            harmonic_window.end,
        ):
            raise ValueError("strumming diagnostic windows are not aligned")
        estimator = summarize_estimator_region(
            estimator_samples,
            start=uncertainty_window.start,
            end=uncertainty_window.end,
        )
        similarities = [
            compare_harmonic_windows(harmonic_window, other)
            .repeated_progression_similarity
            for other_index, other in enumerate(harmonic)
            if other_index != index
        ]
        nearest_similarity = max(similarities, default=0.0)
        supporting_windows = sum(value >= 0.75 for value in similarities)
        evidence.append(
            StrummingEvidenceWindow(
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
                section_consistency=section_consistency_strength(
                    nearest_similarity=nearest_similarity,
                    supporting_windows=supporting_windows,
                ),
                estimator_disagreement=estimator_disagreement_strength(
                    disagreement_ratio=1.0 - estimator.exact_agreement,
                    longest_disagreement_run_beats=(
                        estimator.longest_disagreement_run_beats
                    ),
                ),
            )
        )
    classified = classify_strumming_windows(evidence)
    regions = export_confirmed_music_only_regions(classified, evidence)
    if not regions:
        return regions
    return refine_music_only_boundaries(
        regions,
        beats,
        btc_chords,
        chordino_chords,
        frame_diagnostics,
    )


def _same_window(*values: float) -> bool:
    starts = values[0::2]
    ends = values[1::2]
    return max(starts) - min(starts) < 1e-6 and max(ends) - min(ends) < 1e-6
