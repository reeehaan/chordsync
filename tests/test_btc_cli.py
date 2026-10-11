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
