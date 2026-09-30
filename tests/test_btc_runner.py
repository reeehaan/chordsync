import math
from pathlib import Path

import pytest

from analysis.chords.btc.btc_runner import (
    BtcInferenceError,
    BtcModelLoadError,
    BtcOutputError,
    MissingBtcCheckpointError,
    run_btc,
    run_btc_with_diagnostics,
)


class FakeInference:
    def __init__(self, predictions):
        self.predictions = predictions
        self.calls = []

    def predict(self, audio_path, checkpoint_path, source_path):
        self.calls.append((audio_path, checkpoint_path, source_path))
        return self.predictions


class FakeDiagnosticInference:
    def __init__(self, predictions, diagnostics):
        self.predictions = predictions
        self.diagnostics = diagnostics
        self.calls = []

    def predict_with_diagnostics(self, audio_path, checkpoint_path, source_path):
        self.calls.append((audio_path, checkpoint_path, source_path))
        return self.predictions, self.diagnostics


@pytest.fixture
def btc_paths(tmp_path):
    audio = tmp_path / "normalized.wav"
    checkpoint = tmp_path / "btc_model.pt"
    source = tmp_path / "BTC-ISMIR19"
    audio.write_bytes(b"RIFF normalized")
    checkpoint.write_bytes(b"local weights")
    source.mkdir()
    return audio, checkpoint, source


def test_runner_passes_normalized_input_and_maps_canonical_chords(btc_paths):
    audio, checkpoint, source = btc_paths
    inference = FakeInference(
        [
            {"start": 2.0, "end": 3.0, "label": "N"},
            {"start": 1.0, "end": 2.0, "label": "A:min"},
            {"start": 0.0, "end": 1.0, "label": "C:maj"},
        ]
    )

    segments = run_btc(audio, checkpoint, source, inference=inference)

    assert inference.calls == [(audio, checkpoint, source)]
    assert [segment.raw_label for segment in segments] == ["C:maj", "A:min", "N"]
    assert [segment.normalized_label for segment in segments] == ["C", "Am", "N"]
    assert [(segment.start, segment.end) for segment in segments] == [
        (0.0, 1.0),
        (1.0, 2.0),
        (2.0, 3.0),
    ]
    assert all(segment.source == "btc" for segment in segments)
    assert segments[0].model_dump() == {
        "start": 0.0,
        "end": 1.0,
        "raw_label": "C:maj",
        "normalized_label": "C",
        "source": "btc",
    }


def test_diagnostic_runner_preserves_chords_and_uses_one_inference_call(btc_paths):
    audio, checkpoint, source = btc_paths
    predictions = [
        {"start": 0.0, "end": 1.0, "label": "C:maj"},
        {"start": 1.0, "end": 2.0, "label": "A:min"},
    ]
    diagnostics = [
        {
            "time": 0.0,
            "predicted_index": 0,
            "predicted_label": "C:maj",
            "top1_score": 0.8,
            "top2_score": 0.1,
            "margin": 0.7,
            "normalized_entropy": 0.2,
        }
    ]
    inference = FakeDiagnosticInference(predictions, diagnostics)

    result = run_btc_with_diagnostics(
        audio,
        checkpoint,
        source,
        inference=inference,
    )

    assert inference.calls == [(audio, checkpoint, source)]
    assert [chord.model_dump() for chord in result.chords] == [
        chord.model_dump()
        for chord in run_btc(
            audio,
            checkpoint,
            source,
            inference=FakeInference(predictions),
        )
    ]
    assert result.frame_diagnostics == diagnostics


@pytest.mark.parametrize(
    "prediction",
    [
        {"start": -0.1, "end": 1.0, "label": "C"},
        {"start": 1.0, "end": 1.0, "label": "C"},
        {"start": 2.0, "end": 1.0, "label": "C"},
        {"start": math.nan, "end": 1.0, "label": "C"},
        {"start": 0.0, "end": math.inf, "label": "C"},
    ],
)
def test_runner_rejects_invalid_timestamps(btc_paths, prediction):
    audio, checkpoint, source = btc_paths

    with pytest.raises(BtcOutputError, match="timestamp"):
        run_btc(audio, checkpoint, source, inference=FakeInference([prediction]))


@pytest.mark.parametrize(
    "prediction",
    [
        {},
        {"start": "zero", "end": 1.0, "label": "C"},
        {"start": 0.0, "end": 1.0, "label": ""},
        {"start": 0.0, "end": 1.0, "label": 4},
    ],
)
def test_runner_rejects_malformed_model_output(btc_paths, prediction):
    audio, checkpoint, source = btc_paths

    with pytest.raises(BtcOutputError, match="malformed"):
        run_btc(audio, checkpoint, source, inference=FakeInference([prediction]))


def test_runner_rejects_overlapping_segments(btc_paths):
    audio, checkpoint, source = btc_paths
    predictions = [
        {"start": 0.0, "end": 2.0, "label": "C"},
        {"start": 1.0, "end": 3.0, "label": "G"},
    ]

    with pytest.raises(BtcOutputError, match="overlap"):
        run_btc(audio, checkpoint, source, inference=FakeInference(predictions))


def test_runner_reports_missing_checkpoint_before_inference(btc_paths):
    audio, checkpoint, source = btc_paths
    checkpoint.unlink()
    inference = FakeInference([])

    with pytest.raises(MissingBtcCheckpointError, match="checkpoint"):
        run_btc(audio, checkpoint, source, inference=inference)

    assert inference.calls == []


@pytest.mark.parametrize("error_type", [BtcModelLoadError, BtcInferenceError])
def test_runner_preserves_safe_model_and_inference_failures(btc_paths, error_type):
    audio, checkpoint, source = btc_paths

    class FailingInference:
        def predict(self, audio_path, checkpoint_path, source_path):
            raise error_type("safe BTC failure")

    with pytest.raises(error_type, match="safe BTC failure"):
        run_btc(audio, checkpoint, source, inference=FailingInference())


def test_runner_hides_unexpected_inference_failure_details(btc_paths):
    audio, checkpoint, source = btc_paths

    class FailingInference:
        def predict(self, audio_path, checkpoint_path, source_path):
            raise RuntimeError(f"private checkpoint path: {checkpoint_path}")

    with pytest.raises(BtcInferenceError, match="BTC inference failed") as error:
        run_btc(audio, checkpoint, source, inference=FailingInference())

    assert "checkpoint path" not in str(error.value)
