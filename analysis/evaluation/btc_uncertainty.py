"""BTC frame-level uncertainty measurements used by evaluation and production.

BTC's softmax scores compare the model's relative uncertainty; they are not
calibrated probabilities of chord correctness.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, pstdev
from typing import Sequence

from analysis.beats.models import BeatEvent


@dataclass(frozen=True)
class BtcFrameUncertainty:
    time: float
    predicted_index: int
    predicted_label: str
    top1_score: float
    top2_score: float
    margin: float
    normalized_entropy: float


@dataclass(frozen=True)
class BtcUncertaintyWindow:
    start: float
    end: float
    frame_count: int
    mean_top1_score: float
    mean_top2_score: float
    mean_margin: float
    minimum_margin: float
    low_margin_ratio: float
    mean_normalized_entropy: float
    high_entropy_ratio: float
    label_change_frequency: float
    margin_standard_deviation: float


def measure_frame_uncertainty(
    probabilities: Sequence[float],
    *,
    time: float = 0.0,
    labels: Sequence[str] | None = None,
) -> BtcFrameUncertainty:
    """Measure one softmax vector without treating it as calibrated confidence."""
    if not probabilities:
        raise ValueError("probabilities must contain at least one class")
    values = tuple(float(value) for value in probabilities)
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("probabilities must be finite and non-negative")
    total = sum(values)
    if total <= 0.0:
        raise ValueError("probabilities must have a positive sum")
    normalized = tuple(value / total for value in values)
    ranked = sorted(enumerate(normalized), key=lambda item: (-item[1], item[0]))
    predicted_index, top1 = ranked[0]
    top2 = ranked[1][1] if len(ranked) > 1 else 0.0
    if len(normalized) == 1:
        entropy = 0.0
    else:
        entropy = -sum(
            probability * math.log(probability)
            for probability in normalized
            if probability > 0.0
        ) / math.log(len(normalized))
    if labels is not None and len(labels) != len(normalized):
        raise ValueError("labels must match the probability class count")
    label = labels[predicted_index] if labels is not None else str(predicted_index)
    return BtcFrameUncertainty(
        time=float(time),
        predicted_index=predicted_index,
        predicted_label=label,
        top1_score=top1,
        top2_score=top2,
        margin=top1 - top2,
        normalized_entropy=entropy,
    )


def aggregate_uncertainty_windows(
    frames: Sequence[BtcFrameUncertainty],
    beats: Sequence[BeatEvent],
    *,
    beats_per_window: int = 8,
    low_margin_threshold: float = 0.10,
    high_entropy_threshold: float = 0.75,
) -> list[BtcUncertaintyWindow]:
    """Aggregate frame diagnostics over non-overlapping beat-defined windows."""
    if beats_per_window <= 0:
        raise ValueError("beats_per_window must be positive")
    if not 0.0 <= low_margin_threshold <= 1.0:
        raise ValueError("low_margin_threshold must be between zero and one")
    if not 0.0 <= high_entropy_threshold <= 1.0:
        raise ValueError("high_entropy_threshold must be between zero and one")

    ordered_frames = sorted(frames, key=lambda frame: frame.time)
    ordered_beats = sorted(beats, key=lambda beat: beat.time)
    windows = []
    for index in range(0, len(ordered_beats) - beats_per_window, beats_per_window):
        start = float(ordered_beats[index].time)
        end = float(ordered_beats[index + beats_per_window].time)
        selected = [frame for frame in ordered_frames if start <= frame.time < end]
        if selected:
            windows.append(
                _summarize_frames(
                    selected,
                    start=start,
                    end=end,
                    low_margin_threshold=low_margin_threshold,
                    high_entropy_threshold=high_entropy_threshold,
                )
            )
    return windows


def summarize_region(
    frames: Sequence[BtcFrameUncertainty],
    *,
    start: float,
    end: float,
    low_margin_threshold: float = 0.10,
    high_entropy_threshold: float = 0.75,
) -> BtcUncertaintyWindow:
    """Summarize a fixed diagnostic region using unchanged frame timestamps."""
    if end <= start:
        raise ValueError("end must be greater than start")
    selected = sorted(
        (frame for frame in frames if start <= frame.time < end),
        key=lambda frame: frame.time,
    )
    if not selected:
        raise ValueError("region contains no BTC frames")
    return _summarize_frames(
        selected,
        start=start,
        end=end,
        low_margin_threshold=low_margin_threshold,
        high_entropy_threshold=high_entropy_threshold,
    )


def extract_btc_uncertainty(
    audio_path: Path,
    checkpoint_path: Path,
    source_path: Path,
) -> tuple[list[BtcFrameUncertainty], tuple[int, int, int]]:
    """Run BTC offline and retain the 25-class softmax vector for each frame.

    Returns useful (unpadded) frames and the per-window raw tensor shape. Imports
    stay local so pure metric tests do not require the BTC environment.
    """
    source_text = str(source_path.resolve())
    if source_text not in sys.path:
        sys.path.insert(0, source_text)
    os.environ.setdefault(
        "NUMBA_CACHE_DIR", str(Path(tempfile.gettempdir()) / "chordsync-numba-cache")
    )

    import numpy as np
    import torch
    from btc_model import BTC_model
    from utils.hparams import HParams
    from utils.mir_eval_modules import audio_file_to_features, idx2chord

    config = HParams.load(str(source_path / "run_config.yaml"))
    config.feature["large_voca"] = False
    config.model["num_chords"] = 25
    device = _select_device(torch)
    model = BTC_model(config=config.model).to(device)
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model"])
    model.eval()

    feature, time_unit, _ = audio_file_to_features(str(audio_path), config)
    feature = (feature.T - checkpoint["mean"]) / checkpoint["std"]
    timestep = int(config.model["timestep"])
    padding = timestep - (feature.shape[0] % timestep)
    feature = np.pad(feature, ((0, padding), (0, 0)), mode="constant")
    tensor = torch.tensor(feature, dtype=torch.float32).unsqueeze(0).to(device)
    probabilities = []
    raw_shape = (1, timestep, int(config.model["num_chords"]))
    with torch.no_grad():
        for index in range(feature.shape[0] // timestep):
            window = tensor[:, timestep * index : timestep * (index + 1), :]
            attention, _ = model.self_attn_layers(window)
            logits = model.output_layer.output_projection(attention)
            raw_shape = tuple(int(value) for value in logits.shape)
            probabilities.extend(
                torch.softmax(logits, dim=-1).squeeze(0).cpu().tolist()
            )

    useful_probabilities = probabilities[: len(probabilities) - padding]
    labels = tuple(idx2chord[index] for index in range(len(useful_probabilities[0])))
    frames = [
        measure_frame_uncertainty(
            scores,
            time=index * float(time_unit),
            labels=labels,
        )
        for index, scores in enumerate(useful_probabilities)
    ]
    return frames, raw_shape


def _summarize_frames(
    frames,
    *,
    start,
    end,
    low_margin_threshold,
    high_entropy_threshold,
):
    margins = [frame.margin for frame in frames]
    changes = sum(
        left.predicted_index != right.predicted_index
        for left, right in zip(frames, frames[1:])
    )
    return BtcUncertaintyWindow(
        start=start,
        end=end,
        frame_count=len(frames),
        mean_top1_score=fmean(frame.top1_score for frame in frames),
        mean_top2_score=fmean(frame.top2_score for frame in frames),
        mean_margin=fmean(margins),
        minimum_margin=min(margins),
        low_margin_ratio=(
            sum(margin < low_margin_threshold for margin in margins) / len(margins)
        ),
        mean_normalized_entropy=fmean(
            frame.normalized_entropy for frame in frames
        ),
        high_entropy_ratio=(
            sum(
                frame.normalized_entropy > high_entropy_threshold
                for frame in frames
            )
            / len(frames)
        ),
        label_change_frequency=changes / max(1, len(frames) - 1),
        margin_standard_deviation=pstdev(margins),
    )


def _select_device(torch):
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")
