import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Mapping, Sequence

from analysis.chords.btc.btc_runner import BtcInferenceError, BtcModelLoadError


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
        predictions = _frames_to_segments(
            frame_labels[:useful_frames], time_unit, song_length, idx2chord
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
