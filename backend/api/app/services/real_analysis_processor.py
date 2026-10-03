import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from analysis.chords.estimator import ChordEstimator
from analysis.fusion.models import SharedTimeline
from analysis.lyrics.forced_alignment import WhisperXReferenceAligner
from analysis.lyrics.lrclib_transport import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    LrclibTransport,
)
from analysis.lyrics.lyrics_api_reference import LyricsReferenceResult
from analysis.lyrics.production_verification import (
    ReferenceAligner,
    verify_and_correct_whisperx,
)
from analysis.lyrics.production_reference import obtain_lrclib_reference


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
    vamp_simple_host_executable: Path | None = None
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
    lrclib_reference_enabled: bool = False
    lrclib_timeout: float = DEFAULT_TIMEOUT_SECONDS
    lrclib_user_agent: str = DEFAULT_USER_AGENT

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
            vamp_simple_host_executable=_optional_executable(
                "CHORDSYNC_VAMP_SIMPLE_HOST",
                "vamp-simple-host",
            ),
            chord_estimator=estimator,
            btc_python=btc_python,
            btc_checkpoint=btc_checkpoint,
            btc_source=btc_source,
            lrclib_reference_enabled=(
                os.getenv("CHORDSYNC_LRCLIB_REFERENCE_ENABLED", "").casefold()
                in {"1", "true", "yes"}
            ),
            lrclib_timeout=_positive_float_environment(
                "CHORDSYNC_LRCLIB_TIMEOUT",
                DEFAULT_TIMEOUT_SECONDS,
            ),
            lrclib_user_agent=os.getenv(
                "CHORDSYNC_LRCLIB_USER_AGENT",
                DEFAULT_USER_AGENT,
            ),
        )


class RealAnalysisProcessor:
    def __init__(
        self,
        config: AnalysisPipelineConfig | None = None,
        runner: SubprocessRunner | None = None,
        reference_aligner: ReferenceAligner | None = None,
    ) -> None:
        self._config = config or AnalysisPipelineConfig.local()
        self._runner = runner or LocalSubprocessRunner()
        self._reference_aligner = reference_aligner
        self.last_reference_identity_confidence = None
        self.last_lyrics_verification_diagnostics = None
        self.last_lyrics_timing_provenance = ()

    def process(self, input_path: Path) -> SharedTimeline:
        self.last_reference_identity_confidence = None
        self.last_lyrics_verification_diagnostics = None
        self.last_lyrics_timing_provenance = ()
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
        reference = self._obtain_optional_lyrics_reference(input_path, job_id)
        workspace = self._config.workspace_root / job_id
        try:
            workspace.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise AnalysisPipelineError("workspace stage failed") from error

        normalized_path = workspace / "normalized.wav"
        chord_path = workspace / "chords.json"
        btc_uncertainty_path = workspace / "btc_uncertainty.json"
        chordino_diagnostic_path = workspace / "chordino_diagnostic.json"
        practice_regions_path = workspace / "practice_regions.json"
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
        practice_regions_available = False
        if self._config.chord_estimator is ChordEstimator.BTC:
            chordino_available = False
            if self._config.vamp_simple_host_executable is None:
                logger.warning(
                    "[job %s] chordino diagnostic unavailable; "
                    "vamp-simple-host was not found; continuing without "
                    "practice_regions",
                    job_id,
                )
            else:
                chordino_available = self._run_optional_stage(
                    "chordino diagnostic",
                    [
                        str(self._config.api_python),
                        "-m",
                        self._config.stage_module,
                        "chordino-diagnostic",
                        "--input",
                        str(normalized_path),
                        "--output",
                        str(chordino_diagnostic_path),
                        "--executable",
                        str(self._config.vamp_simple_host_executable),
                    ],
                    self._config.chord_timeout,
                    chordino_diagnostic_path,
                )
            if _has_nonempty_json_list(btc_uncertainty_path) and chordino_available:
                practice_regions_available = self._run_optional_stage(
                    "strumming suitability",
                    [
                        str(self._config.api_python),
                        "-m",
                        self._config.stage_module,
                        "strumming-suitability",
                        "--chords",
                        str(chord_path),
                        "--chordino",
                        str(chordino_diagnostic_path),
                        "--beats",
                        str(beat_path),
                        "--uncertainty",
                        str(btc_uncertainty_path),
                        "--output",
                        str(practice_regions_path),
                    ],
                    self._config.fusion_timeout,
                    practice_regions_path,
                )
            else:
                logger.warning(
                    "[job %s] strumming suitability diagnostics unavailable; "
                    "continuing without practice_regions",
                    job_id,
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
        with tempfile.TemporaryDirectory(
            prefix="chordsync-verified-lyrics-"
        ) as temporary_directory:
            fusion_whisperx_path = self._verify_optional_lyrics(
                reference,
                whisperx_path,
                Path(temporary_directory) / "vocals.verified.json",
                vocals_path,
                job_id,
            )
            self._run_fusion_stage(
                chord_path,
                beat_path,
                fusion_whisperx_path,
                timeline_path,
                practice_regions_path if practice_regions_available else None,
            )

        try:
            payload = json.loads(timeline_path.read_text(encoding="utf-8"))
            return SharedTimeline.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise AnalysisPipelineError("fuse stage produced an invalid timeline") from error

    def _obtain_optional_lyrics_reference(
        self,
        input_path: Path,
        job_id: str,
    ) -> LyricsReferenceResult | None:
        if not self._config.lrclib_reference_enabled:
            return None
        try:
            reference = obtain_lrclib_reference(
                input_path,
                transport=LrclibTransport(
                    user_agent=self._config.lrclib_user_agent,
                    timeout_seconds=self._config.lrclib_timeout,
                ),
            )
        except Exception as error:
            logger.warning(
                "[job %s] optional lyrics reference unavailable (%s); continuing",
                job_id,
                type(error).__name__,
            )
            return None
        logger.info(
            "[job %s] optional lyrics reference %s; continuing with WhisperX",
            job_id,
            "matched" if reference is not None else "unavailable",
        )
        if reference is not None:
            self.last_reference_identity_confidence = getattr(
                reference,
                "identity_confidence",
                None,
            )
        return reference

    def _verify_optional_lyrics(
        self,
        reference: LyricsReferenceResult | None,
        whisperx_path: Path,
        verified_whisperx_path: Path,
        audio_path: Path,
        job_id: str,
    ) -> Path:
        if reference is None:
            return whisperx_path
        try:
            whisperx_result = json.loads(whisperx_path.read_text(encoding="utf-8"))
            aligner = self._reference_aligner or WhisperXReferenceAligner(
                python_executable=(
                    self._config.whisperx_executable.parent / "python"
                ),
                repo_root=self._config.repo_root,
                timeout_seconds=self._config.lyric_timeout,
            )
            result = verify_and_correct_whisperx(
                whisperx_result,
                reference.plain_lyrics,
                audio_path,
                aligner,
            )
            diagnostics = result.diagnostics
            self.last_lyrics_verification_diagnostics = diagnostics
            self.last_lyrics_timing_provenance = result.timing_provenance
            logger.info(
                "[job %s] lyrics verification: matches=%d substitutions=%d "
                "insertions=%d deletions=%d candidates=%d forced_candidates=%d "
                "aligned=%d reconciliation_candidates=%d accepted=%d rejected=%d "
                "alignment_failures=%d safety_rejections=%d raw_wer=%.4f "
                "corrected_wer=%.4f",
                job_id,
                diagnostics.matches,
                diagnostics.substitutions,
                diagnostics.insertions,
                diagnostics.deletions,
                diagnostics.verified_candidates,
                diagnostics.forced_alignment_candidates,
                diagnostics.forced_alignment_successes,
                diagnostics.reconciliation_candidates,
                diagnostics.accepted_corrections,
                diagnostics.rejected_corrections,
                diagnostics.forced_alignment_failures,
                diagnostics.safety_rejections,
                diagnostics.raw_wer,
                diagnostics.corrected_wer,
            )
            if not result.changed:
                return whisperx_path
            verified_whisperx_path.write_text(
                json.dumps(result.whisperx_result, indent=2),
                encoding="utf-8",
            )
            return verified_whisperx_path
        except Exception as error:
            logger.warning(
                "[job %s] optional lyrics verification unavailable (%s); "
                "continuing with WhisperX",
                job_id,
                type(error).__name__,
            )
            return whisperx_path

    def _run_fusion_stage(
        self,
        chord_path: Path,
        beat_path: Path,
        whisperx_path: Path,
        timeline_path: Path,
        practice_regions_path: Path | None,
    ) -> None:
        command = [
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
        ]
        if practice_regions_path is not None:
            command.extend(["--practice-regions", str(practice_regions_path)])
        self._run_stage(
            "fuse",
            command,
            self._config.fusion_timeout,
            timeline_path,
        )

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
            "--uncertainty-output",
            str(output_path.with_name("btc_uncertainty.json")),
        ]

    def _run_optional_stage(
        self,
        stage: str,
        argv: list[str],
        timeout: float,
        expected_output: Path,
    ) -> bool:
        try:
            self._run_stage(stage, argv, timeout, expected_output)
        except AnalysisPipelineError:
            logger.warning(
                "[job %s] strumming suitability diagnostics unavailable; "
                "continuing without practice_regions",
                self._job_id_for(expected_output),
            )
            return False
        return True

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


def _optional_executable(environment_name: str, command: str) -> Path | None:
    configured = os.getenv(environment_name)
    if configured:
        return Path(configured).expanduser()
    discovered = shutil.which(command)
    return Path(discovered) if discovered else None


def _positive_float_environment(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _has_nonempty_json_list(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, list) and bool(payload)
