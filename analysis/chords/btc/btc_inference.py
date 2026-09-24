import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

from analysis.chords.btc.btc_runner import BtcInferenceError, BtcModelLoadError

# BTC's frame-label decoding has no built-in smoothing: a single frame
# (~93ms, from run_config.yaml's inst_len/timestep) that the model flips on
# becomes its own chord segment. Real chord changes are almost never that
# short, so this window majority-votes each frame against its neighbors
# before segmenting, suppressing single- and double-frame flicker while
# still tracking genuine changes a few frames long.
_SMOOTHING_WINDOW_FRAMES = 7
_MAX_ISOLATED_INTERRUPTION_SECONDS = 0.4


def predict(
    audio_path: Path,
    checkpoint_path: Path,
    source_path: Path,
) -> Sequence[Mapping[str, object]]:
    source_text = str(source_path.resolve())
    if source_text not in sys.path:
        sys.path.insert(0, source_text)
    os.environ.setdefault(
        "NUMBA_CACHE_DIR", str(Path(tempfile.gettempdir()) / "chordsync-numba-cache")
    )

    try:
        import numpy as np
        import torch
        from btc_model import BTC_model
        from utils.hparams import HParams
        from utils.mir_eval_modules import audio_file_to_features, idx2chord
    except Exception as error:
        raise BtcModelLoadError("BTC model dependencies could not be imported.") from error

    try:
        config = HParams.load(str(source_path / "run_config.yaml"))
        config.feature["large_voca"] = False
        config.model["num_chords"] = 25
        device = _select_device(torch)
        load_started = time.perf_counter()
        model = BTC_model(config=config.model).to(device)
        checkpoint = torch.load(
            checkpoint_path,
            map_location=device,
            weights_only=False,
        )
        mean = checkpoint["mean"]
        std = checkpoint["std"]
        model.load_state_dict(checkpoint["model"])
        model.eval()
        load_seconds = time.perf_counter() - load_started
    except Exception as error:
        raise BtcModelLoadError("BTC checkpoint could not be loaded.") from error

    try:
        inference_started = time.perf_counter()
        feature, time_unit, song_length = audio_file_to_features(
            str(audio_path), config
        )
        feature = feature.T
        feature = (feature - mean) / std
        timestep = config.model["timestep"]
        padding = timestep - (feature.shape[0] % timestep)
        feature = np.pad(feature, ((0, padding), (0, 0)), mode="constant")
        instance_count = feature.shape[0] // timestep
        tensor = torch.tensor(feature, dtype=torch.float32).unsqueeze(0).to(device)
        frame_labels: list[int] = []
        with torch.no_grad():
            for index in range(instance_count):
                window = tensor[:, timestep * index : timestep * (index + 1), :]
                attention, _ = model.self_attn_layers(window)
                prediction, _ = model.output_layer(attention)
                frame_labels.extend(prediction.squeeze().tolist())
        useful_frames = max(1, len(frame_labels) - padding)
        smoothed_labels = _smooth_frame_labels(
            frame_labels[:useful_frames], _SMOOTHING_WINDOW_FRAMES
        )
        segmented = _frames_to_segments(
            smoothed_labels, time_unit, song_length, idx2chord
        )
        predictions = _stabilize_segments(
            segmented,
            max_interruption_seconds=_MAX_ISOLATED_INTERRUPTION_SECONDS,
        )
        inference_seconds = time.perf_counter() - inference_started
    except Exception as error:
        raise BtcInferenceError("BTC inference failed.") from error

    print(
        f"BTC_METRICS device={device.type} model_load={load_seconds:.3f}s "
        f"inference={inference_seconds:.3f}s",
        file=sys.stderr,
    )
    return predictions


def _select_device(torch):
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _smooth_frame_labels(frame_labels, window):
    if window <= 1 or len(frame_labels) <= window:
        return list(frame_labels)
    half = window // 2
    total = len(frame_labels)
    smoothed = []
    for index in range(total):
        start = max(0, index - half)
        end = min(total, index + half + 1)
        neighborhood = frame_labels[start:end]
        smoothed.append(Counter(neighborhood).most_common(1)[0][0])
    return smoothed


def _frames_to_segments(frame_labels, time_unit, song_length, vocabulary):
    if not frame_labels or song_length <= 0:
        return []
    segments = []
    start = 0.0
    previous = int(frame_labels[0])
    for index, label_value in enumerate(frame_labels[1:], start=1):
        label = int(label_value)
        boundary = min(float(song_length), float(time_unit) * index)
        if label != previous and boundary > start:
            segments.append(
                {"start": start, "end": boundary, "label": vocabulary[previous]}
            )
            start = boundary
            previous = label
    if float(song_length) > start:
        segments.append(
            {
                "start": start,
                "end": float(song_length),
                "label": vocabulary[previous],
            }
        )
    return segments


def _stabilize_segments(
    segments: Sequence[Mapping[str, object]],
    *,
    max_interruption_seconds: float,
) -> list[dict[str, object]]:
    """Merge only short, contiguous A-B-A interruptions after segmentation."""
    cleaned = [dict(segment) for segment in segments]
    index = 1
    while index < len(cleaned) - 1:
        previous = cleaned[index - 1]
        middle = cleaned[index]
        following = cleaned[index + 1]
        duration = float(middle["end"]) - float(middle["start"])
        is_contiguous = (
            previous["end"] == middle["start"]
            and middle["end"] == following["start"]
        )
        same_harmonic_neighbor = (
            previous["label"] == following["label"]
            and previous["label"] != "N"
        )
        if (
            is_contiguous
            and same_harmonic_neighbor
            and duration <= max_interruption_seconds
        ):
            merged = dict(previous)
            merged["end"] = following["end"]
            cleaned[index - 1 : index + 2] = [merged]
            index = max(1, index - 1)
            continue
        index += 1
    return cleaned
