import json
import subprocess
import sys

import pytest

from analysis.chords.models import ChordSegment
from analysis import pipeline_cli


def test_btc_chords_cli_accepts_explicit_paths_and_writes_canonical_json(
    monkeypatch, tmp_path
):
    audio = tmp_path / "normalized.wav"
    checkpoint = tmp_path / "model.pt"
    source = tmp_path / "upstream"
    output = tmp_path / "btc.json"
    observed = {}

    def fake_run(input_path, checkpoint_path, source_path):
        observed["paths"] = (input_path, checkpoint_path, source_path)
        return [
            ChordSegment(
                start=0.0,
                end=1.0,
                raw_label="C:maj",
                normalized_label="C",
                source="btc",
            )
        ]

    monkeypatch.setattr(pipeline_cli, "run_btc_chord_analysis", fake_run)

    pipeline_cli.main(
        [
            "btc-chords",
            "--input",
            str(audio),
            "--output",
            str(output),
            "--checkpoint",
            str(checkpoint),
            "--source",
            str(source),
        ]
    )

    assert observed["paths"] == (audio, checkpoint, source)
    assert json.loads(output.read_text(encoding="utf-8")) == [
        {
            "start": 0.0,
            "end": 1.0,
            "raw_label": "C:maj",
            "normalized_label": "C",
            "source": "btc",
        }
    ]


def test_btc_chords_cli_propagates_failure_without_writing_output(
    monkeypatch, tmp_path
):
    output = tmp_path / "btc.json"

    def fail(*args):
        raise RuntimeError("safe failure")

    monkeypatch.setattr(pipeline_cli, "run_btc_chord_analysis", fail)

    with pytest.raises(RuntimeError, match="safe failure"):
        pipeline_cli.main(
            [
                "btc-chords",
                "--input",
                str(tmp_path / "input.wav"),
                "--output",
                str(output),
                "--checkpoint",
                str(tmp_path / "model.pt"),
                "--source",
                str(tmp_path / "source"),
            ]
        )

    assert not output.exists()


def test_btc_chords_process_exits_nonzero_when_checkpoint_is_missing(tmp_path):
    audio = tmp_path / "normalized.wav"
    source = tmp_path / "source"
    output = tmp_path / "btc.json"
    audio.write_bytes(b"RIFF synthetic")
    source.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "analysis.pipeline_cli",
            "btc-chords",
            "--input",
            str(audio),
            "--output",
            str(output),
            "--checkpoint",
            str(tmp_path / "missing.pt"),
            "--source",
            str(source),
        ],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )

    assert result.returncode != 0
    assert not output.exists()


def test_chord_extensions_cli_upgrades_chords_and_uses_the_large_model(
    monkeypatch, tmp_path
):
    import numpy as np

    import types

    from analysis.chords import extensions

    audio = tmp_path / "normalized.wav"
    stem = tmp_path / "no_vocals.wav"
    chords = tmp_path / "chords.json"
    large = tmp_path / "btc_model_large_voca.pt"
    source = tmp_path / "upstream"
    output = tmp_path / "extended.json"
    chords.write_text(
        json.dumps(
            [
                {"start": 0.0, "end": 4.0, "raw_label": "E:min",
                 "normalized_label": "Em", "source": "btc"},
                {"start": 4.0, "end": 8.0, "raw_label": "C:maj",
                 "normalized_label": "C", "source": "btc"},
            ]
        ),
        encoding="utf-8",
    )
    observed = {}

    def fake_predict(audio_path, checkpoint_path, source_path, *, large_vocabulary):
        observed["call"] = (audio_path, checkpoint_path, source_path, large_vocabulary)
        return [
            {"start": 0.0, "end": 4.0, "label": "E:min7"},
            {"start": 4.0, "end": 8.0, "label": "C"},
        ]

    def fake_chroma(path):
        observed["stem"] = path
        times = np.arange(0.0, 8.0, 0.1)
        notes = np.full(12, 0.05)
        notes[[0, 7]] = [1.0, 0.7]
        notes[3], notes[10] = 0.55, 0.3  # minor third and minor seventh above E
        return extensions.Chroma(
            values=np.tile(np.roll(notes, 4)[:, None], (1, len(times))), times=times
        )

    # A stand-in module: the real BTC code is never imported here (other tests
    # check that the API process does not load it).
    fake_inference = types.ModuleType("analysis.chords.btc.btc_inference")
    fake_inference.predict = fake_predict
    monkeypatch.setitem(sys.modules, "analysis.chords.btc.btc_inference", fake_inference)
    monkeypatch.setattr(extensions, "chroma_from_audio", fake_chroma)

    pipeline_cli.main(
        [
            "chord-extensions",
            "--input", str(audio),
            "--stem", str(stem),
            "--chords", str(chords),
            "--large-checkpoint", str(large),
            "--source", str(source),
            "--output", str(output),
        ]
    )

    # The large model runs on the full song, the notes are read from the stem.
    assert observed["call"] == (audio, large, source, True)
    assert observed["stem"] == stem
    written = json.loads(output.read_text(encoding="utf-8"))
    assert [chord["normalized_label"] for chord in written] == ["Em7", "C"]
    assert [chord["raw_label"] for chord in written] == ["E:min", "C:maj"]
    # The plain chords file is not modified in place.
    assert json.loads(chords.read_text(encoding="utf-8"))[0]["normalized_label"] == "Em"
