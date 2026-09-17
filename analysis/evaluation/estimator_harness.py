import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from analysis.chords.models import ChordSegment
from analysis.evaluation.chord_evaluator import (
    evaluate_chords,
    load_reference_lab,
    segments_to_intervals,
)
from analysis.evaluation.models import (
    EstimatorEvaluationResult,
    EvaluationTrack,
    NoChordEvaluation,
    TrackComparisonResult,
)


AudioPreprocessor = Callable[[Path, Path], None]
ChordEstimatorRunner = Callable[[Path], list[ChordSegment]]


def evaluate_track(
    track: EvaluationTrack,
    *,
    chordino_estimator: ChordEstimatorRunner,
    btc_estimator: ChordEstimatorRunner,
    preprocessor: AudioPreprocessor,
    chordino_version: str,
    btc_version: str,
    btc_checkpoint_sha256: str,
) -> TrackComparisonResult:
    reference_intervals, reference_labels = load_reference_lab(
        track.reference_lab_path
    )
    duration = float(reference_intervals[-1][1] - reference_intervals[0][0])

    with tempfile.TemporaryDirectory(prefix="chordsync-evaluation-") as directory:
        normalized_path = Path(directory) / "normalized.wav"
        preprocessing_started = time.perf_counter()
        preprocessor(track.audio_path, normalized_path)
        preprocessing_seconds = time.perf_counter() - preprocessing_started
        if not normalized_path.is_file() or normalized_path.stat().st_size == 0:
            raise RuntimeError("Evaluation preprocessing produced no audio.")

        chordino = _evaluate_estimator(
            estimator="chordino",
            version=chordino_version,
            runner=chordino_estimator,
            normalized_path=normalized_path,
            reference_intervals=reference_intervals,
            reference_labels=reference_labels,
            duration=duration,
        )
        btc = _evaluate_estimator(
            estimator="btc",
            version=btc_version,
            runner=btc_estimator,
            normalized_path=normalized_path,
            reference_intervals=reference_intervals,
            reference_labels=reference_labels,
            duration=duration,
            checkpoint_sha256=btc_checkpoint_sha256,
        )

    return TrackComparisonResult(
        track_id=track.track_id,
        duration=duration,
        preprocessing_seconds=preprocessing_seconds,
        normalization="ChordSync major/minor/no-chord v1",
        chordino=chordino,
        btc=btc,
    )


def _evaluate_estimator(
    *,
    estimator: str,
    version: str,
    runner: ChordEstimatorRunner,
    normalized_path: Path,
    reference_intervals,
    reference_labels,
    duration: float,
    checkpoint_sha256: str | None = None,
) -> EstimatorEvaluationResult:
    started = time.perf_counter()
    segments = runner(normalized_path)
    runtime_seconds = time.perf_counter() - started
    estimated_intervals, estimated_labels = segments_to_intervals(segments)
    metrics = evaluate_chords(
        reference_intervals,
        reference_labels,
        estimated_intervals,
        estimated_labels,
    )
    return EstimatorEvaluationResult(
        estimator=estimator,
        version=version,
        duration=duration,
        root_score=metrics["root_wcsr"],
        majmin_score=metrics["majmin_wcsr"],
        triad_score=metrics["triad_wcsr"],
        no_chord=NoChordEvaluation.model_validate(metrics["no_chord"]),
        runtime_seconds=runtime_seconds,
        runtime_scope="cold complete estimator call",
        segment_count=len(segments),
        checkpoint_sha256=checkpoint_sha256,
    )
