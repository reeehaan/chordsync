import math
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from analysis.chords.models import ChordSegment
from analysis.chords.normalizer import normalize_chord_label


class BtcRunnerError(RuntimeError):
    pass


class MissingBtcCheckpointError(BtcRunnerError):
    pass


class BtcModelLoadError(BtcRunnerError):
    pass


class BtcInferenceError(BtcRunnerError):
    pass


class BtcOutputError(BtcRunnerError):
    pass


class BtcInference(Protocol):
    def predict(
        self,
        audio_path: Path,
        checkpoint_path: Path,
        source_path: Path,
    ) -> Sequence[Mapping[str, object]]: ...


class NativeBtcInference:
    def predict(
        self,
        audio_path: Path,
        checkpoint_path: Path,
        source_path: Path,
    ) -> Sequence[Mapping[str, object]]:
        from analysis.chords.btc.btc_inference import predict

        return predict(audio_path, checkpoint_path, source_path)


def run_btc(
    audio_path: Path,
    checkpoint_path: Path,
    source_path: Path,
    *,
    inference: BtcInference | None = None,
) -> list[ChordSegment]:
    if not audio_path.is_file():
        raise FileNotFoundError(f"Normalized audio file not found: {audio_path}")
    if not checkpoint_path.is_file():
        raise MissingBtcCheckpointError("BTC checkpoint is not configured or missing.")
    if not source_path.is_dir():
        raise BtcModelLoadError("BTC source directory is not configured or missing.")

    backend = inference or NativeBtcInference()
    try:
        predictions = backend.predict(audio_path, checkpoint_path, source_path)
    except BtcRunnerError:
        raise
    except Exception as error:
        raise BtcInferenceError("BTC inference failed.") from error
    segments = [_to_segment(prediction) for prediction in predictions]
    segments.sort(key=lambda segment: (segment.start, segment.end))

    for previous, current in zip(segments, segments[1:]):
        if current.start < previous.end:
            raise BtcOutputError("BTC output contains overlapping segments.")
    return segments


def _to_segment(prediction: Mapping[str, object]) -> ChordSegment:
    try:
        raw_start = prediction["start"]
        raw_end = prediction["end"]
        raw_label = prediction["label"]
    except (KeyError, TypeError) as error:
        raise BtcOutputError("BTC model output is malformed.") from error

    if (
        isinstance(raw_start, bool)
        or not isinstance(raw_start, (int, float))
        or isinstance(raw_end, bool)
        or not isinstance(raw_end, (int, float))
        or not isinstance(raw_label, str)
        or not raw_label.strip()
    ):
        raise BtcOutputError("BTC model output is malformed.")

    start = float(raw_start)
    end = float(raw_end)
    if not math.isfinite(start) or not math.isfinite(end):
        raise BtcOutputError("BTC output contains an invalid timestamp.")
    if start < 0 or end <= start:
        raise BtcOutputError("BTC output contains an invalid timestamp boundary.")

    label = raw_label.strip()
    return ChordSegment(
        start=round(start, 6),
        end=round(end, 6),
        raw_label=label,
        normalized_label=normalize_chord_label(label),
        source="btc",
    )
