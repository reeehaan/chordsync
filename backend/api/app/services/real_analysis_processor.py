import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from analysis.chords.estimator import ChordEstimator
from analysis.fusion.models import SharedTimeline


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
logger = logging.getLogger(__name__)


class AnalysisPipelineError(RuntimeError):
    pass


class AnalysisStageTimeout(AnalysisPipelineError):
    pass


class SubprocessRunnerTimeout(RuntimeError):
    pass


@dataclass(frozen=True)
class SubprocessResult:
    returncode: int
    stdout: str
    stderr: str


class SubprocessRunner(Protocol):
    def run(
        self,
        argv: list[str],
        cwd: Path,
        timeout: float,
    ) -> SubprocessResult: ...


class LocalSubprocessRunner:
    def run(
        self,
        argv: list[str],
        cwd: Path,
        timeout: float,
    ) -> SubprocessResult:
        try:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                timeout=timeout,
                capture_output=True,
                text=True,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise SubprocessRunnerTimeout from error
        return SubprocessResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True)
class AnalysisPipelineConfig:
    repo_root: Path
    workspace_root: Path
    api_python: Path
    beat_python: Path
    whisperx_executable: Path
    demucs_executable: Path
    chord_estimator: ChordEstimator = ChordEstimator.CHORDINO
    btc_python: Path | None = None
    btc_checkpoint: Path | None = None
    btc_source: Path | None = None
    stage_module: str = "analysis.pipeline_cli"
    whisperx_model: str = "small"
    demucs_model: str = "htdemucs"
    preprocessing_timeout: float = 120.0
    chord_timeout: float = 300.0
    beat_timeout: float = 300.0
    separation_timeout: float = 600.0
    lyric_timeout: float = 1800.0
    fusion_timeout: float = 120.0

    @classmethod
    def local(cls) -> "AnalysisPipelineConfig":
        btc_python = _optional_path("CHORDSYNC_BTC_PYTHON")
        btc_checkpoint = _optional_path("CHORDSYNC_BTC_CHECKPOINT")
        btc_source = _optional_path("CHORDSYNC_BTC_SOURCE")
        btc_configured = bool(btc_python and btc_checkpoint and btc_source)
        default_estimator = "btc" if btc_configured else "chordino"
        estimator_text = os.getenv("CHORDSYNC_CHORD_ESTIMATOR", default_estimator)
        try:
            estimator = ChordEstimator(estimator_text)
        except ValueError as error:
            raise AnalysisPipelineError("chord estimator configuration is invalid") from error
        return cls(
            repo_root=_PROJECT_ROOT,
            workspace_root=_PROJECT_ROOT / "storage/analysis_jobs",
            api_python=_PROJECT_ROOT / "backend/api/.venv-api/bin/python",
            beat_python=_PROJECT_ROOT / "analysis/beats/.venv-beats/bin/python",
            whisperx_executable=(
                _PROJECT_ROOT / "analysis/lyrics/.venv-whisperx/bin/whisperx"
            ),
            demucs_executable=(
                _PROJECT_ROOT / "analysis/separation/.venv-separation/bin/demucs"
            ),
            chord_estimator=estimator,
            btc_python=btc_python,
            btc_checkpoint=btc_checkpoint,
            btc_source=btc_source,
        )


class RealAnalysisProcessor:
    def __init__(
        self,
        config: AnalysisPipelineConfig | None = None,
        runner: SubprocessRunner | None = None,
    ) -> None:
        self._config = config or AnalysisPipelineConfig.local()
        self._runner = runner or LocalSubprocessRunner()

    def process(self, input_path: Path) -> SharedTimeline:
        if not input_path.is_file():
            raise AnalysisPipelineError("input stage output is missing")
        if self._config.chord_estimator is ChordEstimator.BTC:
            if not all(
                (
                    self._config.btc_python,
                    self._config.btc_checkpoint,
                    self._config.btc_source,
                )
            ):
                raise AnalysisPipelineError("BTC is not configured")

        job_id = input_path.parent.name
        workspace = self._config.workspace_root / job_id
        try:
            workspace.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise AnalysisPipelineError("workspace stage failed") from error

        normalized_path = workspace / "normalized.wav"
        chord_path = workspace / "chords.json"
        beat_path = workspace / "beats.json"
        separation_directory = workspace / "separated"
        vocals_path = (
            separation_directory
            / self._config.demucs_model
            / normalized_path.stem
            / "vocals.wav"
        )
        whisperx_directory = workspace / "whisperx"
        whisperx_path = whisperx_directory / f"{vocals_path.stem}.json"
        timeline_path = workspace / "timeline.json"

        self._run_stage(
            "preprocess",
            [
                str(self._config.api_python),
                "-m",
                self._config.stage_module,
                "preprocess",
                "--input",
                str(input_path),
                "--output",
                str(normalized_path),
            ],
            self._config.preprocessing_timeout,
            normalized_path,
            json_output=False,
        )
        self._run_stage(
            "chords",
            self._chord_command(normalized_path, chord_path),
            self._config.chord_timeout,
            chord_path,
        )
        self._run_stage(
            "beats",
            self._module_command(
                self._config.beat_python,
                "beats",
                normalized_path,
                beat_path,
            ),
            self._config.beat_timeout,
            beat_path,
        )
        self._run_stage(
            "separate",
            [
                str(self._config.demucs_executable),
                "-n",
                self._config.demucs_model,
                "--two-stems",
                "vocals",
                "-d",
                "cpu",
                "-o",
                str(separation_directory),
                str(normalized_path),
            ],
            self._config.separation_timeout,
            vocals_path,
            json_output=False,
        )
        self._run_stage(
            "lyrics",
            [
                str(self._config.whisperx_executable),
                str(vocals_path),
                "--model",
                self._config.whisperx_model,
                "--language",
                "en",
                "--device",
                "cpu",
                "--compute_type",
                "int8",
                "--output_dir",
                str(whisperx_directory),
                "--output_format",
                "json",
                "--verbose",
                "False",
            ],
            self._config.lyric_timeout,
            whisperx_path,
        )
        self._run_stage(
            "fuse",
            [
                str(self._config.api_python),
                "-m",
                self._config.stage_module,
                "fuse",
                "--chords",
                str(chord_path),
                "--beats",
                str(beat_path),
                "--whisperx",
                str(whisperx_path),
                "--lyric-source",
                f"whisperx-{self._config.whisperx_model}",
                "--output",
                str(timeline_path),
            ],
            self._config.fusion_timeout,
            timeline_path,
        )

        try:
            payload = json.loads(timeline_path.read_text(encoding="utf-8"))
            return SharedTimeline.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise AnalysisPipelineError("fuse stage produced an invalid timeline") from error

    def _module_command(
        self,
        interpreter: Path,
        stage: str,
        input_path: Path,
        output_path: Path,
    ) -> list[str]:
        return [
            str(interpreter),
            "-m",
            self._config.stage_module,
            stage,
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]

    def _chord_command(self, input_path: Path, output_path: Path) -> list[str]:
        if self._config.chord_estimator is ChordEstimator.CHORDINO:
            return self._module_command(
                self._config.api_python, "chords", input_path, output_path
            )
        return [
            str(self._config.btc_python),
            "-m",
            self._config.stage_module,
            "btc-chords",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--checkpoint",
            str(self._config.btc_checkpoint),
            "--source",
            str(self._config.btc_source),
        ]

    def _run_stage(
        self,
        stage: str,
        argv: list[str],
        timeout: float,
        expected_output: Path,
        json_output: bool = True,
    ) -> None:
        job_id = self._job_id_for(expected_output)
        prefix = f"[job {job_id}] {stage}"
        logger.info("%s: started", prefix)
        started_at = time.monotonic()
        try:
            result = self._runner.run(
                argv,
                cwd=self._config.repo_root,
                timeout=timeout,
            )
        except SubprocessRunnerTimeout as error:
            logger.warning("%s: timed out", prefix)
            raise AnalysisStageTimeout(f"{stage} stage timed out") from error
        except OSError as error:
            logger.warning("%s: could not start", prefix)
            raise AnalysisPipelineError(f"{stage} stage could not start") from error
        elapsed = time.monotonic() - started_at
        if result.returncode != 0:
            logger.warning("%s: failed\n%s", prefix, result.stderr)
            raise AnalysisPipelineError(f"{stage} stage failed")
        if not expected_output.is_file() or expected_output.stat().st_size == 0:
            logger.warning("%s: output is missing", prefix)
            raise AnalysisPipelineError(f"{stage} stage output is missing")
        if json_output:
            try:
                json.loads(expected_output.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                logger.warning("%s: output is malformed", prefix)
                raise AnalysisPipelineError(
                    f"{stage} stage output is malformed"
                ) from error
        logger.info("%s: finished in %.1fs", prefix, elapsed)

    def _job_id_for(self, expected_output: Path) -> str:
        try:
            return expected_output.relative_to(self._config.workspace_root).parts[0]
        except ValueError:
            return "unknown"


def _optional_path(name: str) -> Path | None:
    value = os.getenv(name)
    return Path(value).expanduser() if value else None
