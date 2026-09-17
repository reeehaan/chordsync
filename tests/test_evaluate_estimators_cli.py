import json
import subprocess
from pathlib import Path

from analysis.evaluation import evaluate_estimators
from analysis.evaluation.models import TrackComparisonResult


def test_isolated_btc_estimator_uses_argv_without_shell(monkeypatch, tmp_path):
    normalized = tmp_path / "normalized.wav"
    normalized.write_bytes(b"RIFF")
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed.update(kwargs)
        output = Path(argv[argv.index("--output") + 1])
        output.write_text(
            json.dumps(
                [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "raw_label": "C:maj",
                        "normalized_label": "C",
                        "source": "btc",
                    }
                ]
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(evaluate_estimators.subprocess, "run", fake_run)
    estimator = evaluate_estimators.IsolatedBtcEstimator(
        python=Path("/portable/btc/python"),
        source=Path("/external/BTC-ISMIR19"),
        checkpoint=Path("/local/btc_model.pt"),
    )

    segments = estimator(normalized)

    assert len(segments) == 1
    assert segments[0].normalized_label == "C"
    assert observed["argv"][0] == "/portable/btc/python"
    assert observed["shell"] is False
    assert observed["check"] is False
    assert type(observed["argv"]) is list


def test_cli_writes_machine_json_and_prints_human_summary(
    monkeypatch, tmp_path, capsys
):
    result = TrackComparisonResult.model_validate(
        {
            "track_id": "safe-track",
            "duration": 2.0,
            "preprocessing_seconds": 0.1,
            "normalization": "ChordSync major/minor/no-chord v1",
            "chordino": _estimator_payload("chordino", 1.0),
            "btc": _estimator_payload("btc", 0.5),
        }
    )
    monkeypatch.setattr(evaluate_estimators, "run_evaluation", lambda _: result)
    output = tmp_path / "comparison.json"

    evaluate_estimators.main(
        [
            "--track-id",
            "safe-track",
            "--audio",
            str(tmp_path / "audio.wav"),
            "--reference",
            str(tmp_path / "reference.lab"),
            "--output",
            str(output),
            "--btc-python",
            "/portable/btc/python",
            "--btc-source",
            "/external/BTC-ISMIR19",
            "--btc-checkpoint",
            "/local/btc_model.pt",
            "--btc-version",
            "test-version",
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    console = capsys.readouterr().out
    assert payload["track_id"] == "safe-track"
    assert payload["chordino"]["root_score"] == 1.0
    assert payload["btc"]["root_score"] == 0.5
    assert "Track | Estimator | Root | MajMin | Triads | Runtime" in console
    assert "safe-track | chordino" in console
    assert "safe-track | btc" in console


def _estimator_payload(estimator: str, score: float) -> dict:
    return {
        "estimator": estimator,
        "version": "test",
        "duration": 2.0,
        "root_score": score,
        "majmin_score": score,
        "triad_score": score,
        "no_chord": {
            "reference_duration": 0.0,
            "estimated_duration": 0.0,
            "correct_duration": 0.0,
            "precision": 1.0,
            "recall": 1.0,
        },
        "runtime_seconds": 0.2,
        "runtime_scope": "cold complete estimator call",
        "segment_count": 2,
        "checkpoint_sha256": "hash" if estimator == "btc" else None,
    }
