import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from analysis.chords.btc.btc_runner import BtcInferenceError
from analysis.chords.chordino.chordino_runner import (
    DEFAULT_PLUGIN,
    get_sonic_annotator_path,
    run_chordino,
)
from analysis.chords.models import ChordSegment
from analysis.evaluation.estimator_harness import evaluate_track
from analysis.evaluation.models import EvaluationTrack, TrackComparisonResult
from analysis.preprocessing.audio_preprocessor import preprocess_audio


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class IsolatedBtcEstimator:
    def __init__(
        self,
        *,
        python: Path,
        source: Path,
        checkpoint: Path,
    ) -> None:
        self._python = python
        self._source = source
        self._checkpoint = checkpoint

    def __call__(self, normalized_path: Path) -> list[ChordSegment]:
        output_path = normalized_path.with_name("btc-chords.json")
        command = [
            str(self._python),
            "-m",
            "analysis.pipeline_cli",
            "btc-chords",
            "--input",
            str(normalized_path),
            "--output",
            str(output_path),
            "--source",
            str(self._source),
            "--checkpoint",
            str(self._checkpoint),
        ]
        completed = subprocess.run(
            command,
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
        )
        if completed.returncode != 0:
            raise BtcInferenceError("BTC evaluation subprocess failed.")
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            return [ChordSegment.model_validate(item) for item in payload]
        except Exception as error:
            raise BtcInferenceError("BTC evaluation output was invalid.") from error


def run_evaluation(arguments: argparse.Namespace) -> TrackComparisonResult:
    checkpoint_hash = _sha256(arguments.btc_checkpoint)
    return evaluate_track(
        EvaluationTrack(
            track_id=arguments.track_id,
            audio_path=arguments.audio,
            reference_lab_path=arguments.reference,
        ),
        chordino_estimator=run_chordino,
        btc_estimator=IsolatedBtcEstimator(
            python=arguments.btc_python,
            source=arguments.btc_source,
            checkpoint=arguments.btc_checkpoint,
        ),
        preprocessor=preprocess_audio,
        chordino_version=(
            f"sonic-annotator {_sonic_annotator_version()} {DEFAULT_PLUGIN}"
        ),
        btc_version=arguments.btc_version,
        btc_checkpoint_sha256=checkpoint_hash,
    )


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Chordino and BTC against one trusted chord reference."
    )
    parser.add_argument("--track-id", required=True)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--btc-python",
        type=Path,
        default=_environment_path("CHORDSYNC_BTC_PYTHON"),
        required="CHORDSYNC_BTC_PYTHON" not in os.environ,
    )
    parser.add_argument(
        "--btc-source",
        type=Path,
        default=_environment_path("CHORDSYNC_BTC_SOURCE"),
        required="CHORDSYNC_BTC_SOURCE" not in os.environ,
    )
    parser.add_argument(
        "--btc-checkpoint",
        type=Path,
        default=_environment_path("CHORDSYNC_BTC_CHECKPOINT"),
        required="CHORDSYNC_BTC_CHECKPOINT" not in os.environ,
    )
    parser.add_argument(
        "--btc-version",
        required=True,
        help="Upstream BTC source commit or release identifier.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    arguments = parse_arguments(argv)
    result = run_evaluation(arguments)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        result.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    _print_summary(result)


def _print_summary(result: TrackComparisonResult) -> None:
    print("Track | Estimator | Root | MajMin | Triads | Runtime")
    for estimator in (result.chordino, result.btc):
        print(
            f"{result.track_id} | {estimator.estimator} | "
            f"{estimator.root_score:.4f} | {estimator.majmin_score:.4f} | "
            f"{estimator.triad_score:.4f} | {estimator.runtime_seconds:.3f}s"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as checkpoint:
        for chunk in iter(lambda: checkpoint.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _environment_path(name: str) -> Path | None:
    value = os.getenv(name)
    return Path(value).expanduser() if value else None


def _sonic_annotator_version() -> str:
    completed = subprocess.run(
        [str(get_sonic_annotator_path()), "-v"],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    version = completed.stdout.strip() or completed.stderr.strip()
    return version if completed.returncode == 0 and version else "unknown"


if __name__ == "__main__":
    main()
