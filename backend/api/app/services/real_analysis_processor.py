import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping, Protocol

from pydantic import ValidationError

from analysis.chords.estimator import ChordEstimator
from analysis.fusion.models import SharedTimeline
from analysis.lyrics.forced_alignment import WhisperXReferenceAligner
from analysis.lyrics.lrclib_transport import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    LrclibTransport,
)
from analysis.lyrics.lyrics_api_reference import (
    IdentityConfidence,
    LyricsReferenceResult,
)
from analysis.lyrics.production_verification import (
    CorrectionTimingProvenance,
    LyricsVerificationDiagnostics,
    ProductionLyricsVerificationResult,
    ReferenceAligner,
    verify_and_correct_whisperx,
)
from analysis.lyrics.production_reference import obtain_lrclib_reference
from analysis.lyrics.language_hint import looks_english
from analysis.lyrics.repetition_guard import remove_repetition_loops
from analysis.lyrics.romanization import (
    add_approximate_word_timings,
    romanize_whisperx_result,
    whisperx_needs_romanization,
)


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


# Loopback "discard" port: nothing listens, so proxied requests fail at once.
BLACKHOLE_PROXY = "http://127.0.0.1:9"
_PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


def offline_stage_environment(base: Mapping[str, str]) -> dict[str, str]:
    """Environment for analysis subprocesses that must never reach the network.

    Model libraries fetch over HTTP(S) when a cached file is missing (NLTK,
    torch hub, Hugging Face). Routing every proxy-aware client to a closed
    loopback port makes such fallbacks fail immediately instead of reaching
    the internet; NLTK additionally refuses unverifiable proxied fetches.
    """
    environment = dict(base)
    for name in _PROXY_VARIABLES:
        environment[name] = BLACKHOLE_PROXY
        environment[name.lower()] = BLACKHOLE_PROXY
    for name in ("NO_PROXY", "no_proxy", "NLTK_ALLOW_PROXIED_URLOPEN"):
        environment.pop(name, None)
    environment["HF_HUB_OFFLINE"] = "1"
    environment["TRANSFORMERS_OFFLINE"] = "1"
    return environment


class LocalSubprocessRunner:
    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        # None inherits the worker's environment unchanged.
        self._environment = dict(environment) if environment is not None else None

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
                env=self._environment,
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
    music_only_enabled: bool = False
    multilingual_lyrics_enabled: bool = False
    # Show non-English lyrics converted to Latin letters instead of their own
    # script. Off by default: songs are shown in the script they are sung in.
    romanize_lyrics: bool = False
    lrclib_reference_enabled: bool = False
    lrclib_timeout: float = DEFAULT_TIMEOUT_SECONDS
    lrclib_user_agent: str = DEFAULT_USER_AGENT
    stage_network_disabled: bool = False

    @classmethod
    def local(cls) -> "AnalysisPipelineConfig":
        btc_python = _optional_path("CHORDSYNC_BTC_PYTHON")
        btc_checkpoint = _optional_path("CHORDSYNC_BTC_CHECKPOINT")
        btc_source = _optional_path("CHORDSYNC_BTC_SOURCE")
        estimator_text = os.getenv("CHORDSYNC_CHORD_ESTIMATOR", "btc")
        try:
            estimator = ChordEstimator(estimator_text)
        except ValueError as error:
            raise AnalysisPipelineError("chord estimator configuration is invalid") from error
        return cls(
            repo_root=_PROJECT_ROOT,
            workspace_root=_environment_path(
                "CHORDSYNC_WORKSPACE_ROOT",
                _PROJECT_ROOT / "storage/analysis_jobs",
            ),
            api_python=_environment_path(
                "CHORDSYNC_API_PYTHON",
                _PROJECT_ROOT / "backend/api/.venv-api/bin/python",
            ),
            beat_python=_environment_path(
                "CHORDSYNC_BEAT_PYTHON",
                _PROJECT_ROOT / "analysis/beats/.venv-beats/bin/python",
            ),
            whisperx_executable=_environment_path(
                "CHORDSYNC_WHISPERX_EXECUTABLE",
                _PROJECT_ROOT / "analysis/lyrics/.venv-whisperx/bin/whisperx",
            ),
            demucs_executable=_environment_path(
                "CHORDSYNC_DEMUCS_EXECUTABLE",
                _PROJECT_ROOT / "analysis/separation/.venv-separation/bin/demucs",
            ),
            vamp_simple_host_executable=_optional_executable(
                "CHORDSYNC_VAMP_SIMPLE_HOST",
                "vamp-simple-host",
            ),
            chord_estimator=estimator,
            btc_python=btc_python,
            btc_checkpoint=btc_checkpoint,
            btc_source=btc_source,
            music_only_enabled=(
                os.getenv("CHORDSYNC_MUSIC_ONLY_ENABLED", "").casefold()
                in {"1", "true", "yes"}
            ),
            multilingual_lyrics_enabled=(
                _enabled_by_default("CHORDSYNC_MULTILINGUAL_LYRICS_ENABLED")
            ),
            romanize_lyrics=(
                os.getenv("CHORDSYNC_ROMANIZE_LYRICS", "").casefold()
                in {"1", "true", "yes"}
            ),
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
            stage_network_disabled=(
                os.getenv("CHORDSYNC_STAGE_NETWORK", "").casefold() == "disabled"
            ),
        )


@dataclass(frozen=True)
class JobWorkspace:
    """Layout of one job's disposable working files."""

    root: Path
    demucs_model: str

    @property
    def normalized_audio(self) -> Path:
        return self.root / "normalized.wav"

    @property
    def chords(self) -> Path:
        return self.root / "chords.json"

    @property
    def btc_uncertainty(self) -> Path:
        return self.root / "btc_uncertainty.json"

    @property
    def chordino_diagnostic(self) -> Path:
        return self.root / "chordino_diagnostic.json"

    @property
    def practice_regions(self) -> Path:
        return self.root / "practice_regions.json"

    @property
    def beats(self) -> Path:
        return self.root / "beats.json"

    @property
    def separation_directory(self) -> Path:
        return self.root / "separated"

    @property
    def vocals(self) -> Path:
        return (
            self.separation_directory
            / self.demucs_model
            / self.normalized_audio.stem
            / "vocals.wav"
        )

    @property
    def whisperx_directory(self) -> Path:
        return self.root / "whisperx"

    @property
    def whisperx(self) -> Path:
        return self.whisperx_directory / f"{self.vocals.stem}.json"

    @property
    def timeline(self) -> Path:
        return self.root / "timeline.json"


@dataclass(frozen=True)
class AnalysisOutcome:
    """A finished analysis: the timeline plus optional lyrics diagnostics."""

    timeline: SharedTimeline
    reference_identity_confidence: IdentityConfidence | None = None
    lyrics_verification_diagnostics: LyricsVerificationDiagnostics | None = None
    lyrics_timing_provenance: tuple[CorrectionTimingProvenance, ...] = ()


@dataclass(frozen=True)
class _FusionLyrics:
    whisperx_path: Path
    verification: ProductionLyricsVerificationResult | None = None


class RealAnalysisProcessor:
    def __init__(
        self,
        config: AnalysisPipelineConfig | None = None,
        runner: SubprocessRunner | None = None,
        reference_aligner: ReferenceAligner | None = None,
    ) -> None:
        self._config = config or AnalysisPipelineConfig.local()
        self._runner = runner or LocalSubprocessRunner(
            offline_stage_environment(os.environ)
            if self._config.stage_network_disabled
            else None
        )
        self._reference_aligner = reference_aligner

    def process(self, input_path: Path) -> SharedTimeline:
        return self.analyze(input_path).timeline

    def analyze(self, input_path: Path) -> AnalysisOutcome:
        if not input_path.is_file():
            raise AnalysisPipelineError("input stage output is missing")
        self._require_configured_chord_estimator()

        job_id = input_path.parent.name
        reference = self._obtain_optional_lyrics_reference(input_path, job_id)
        workspace = self._create_workspace(job_id)

        self._run_preprocess(input_path, workspace)
        self._run_stage(
            "chords",
            self._chord_command(workspace.normalized_audio, workspace.chords),
            self._config.chord_timeout,
            workspace.chords,
        )
        self._run_beats(workspace)
        practice_regions = self._run_practice_regions(workspace, job_id)
        self._run_separation(workspace)
        self._run_lyrics(workspace, job_id, reference)
        self._remove_lyric_repetition_loops(workspace.whisperx, job_id)
        with tempfile.TemporaryDirectory(
            prefix="chordsync-verified-lyrics-"
        ) as temporary_directory:
            lyrics = self._prepare_fusion_lyrics(
                reference,
                workspace,
                Path(temporary_directory),
                job_id,
            )
            self._run_fusion_stage(
                workspace.chords,
                workspace.beats,
                lyrics.whisperx_path,
                workspace.timeline,
                practice_regions,
            )

        verification = lyrics.verification
        return AnalysisOutcome(
            timeline=self._read_timeline(workspace.timeline),
            reference_identity_confidence=getattr(
                reference, "identity_confidence", None
            ),
            lyrics_verification_diagnostics=(
                verification.diagnostics if verification else None
            ),
            lyrics_timing_provenance=(
                verification.timing_provenance if verification else ()
            ),
        )

    def _require_configured_chord_estimator(self) -> None:
        if self._config.chord_estimator is not ChordEstimator.BTC:
            return
        if not all(
            (
                self._config.btc_python,
                self._config.btc_checkpoint,
                self._config.btc_source,
            )
        ):
            raise AnalysisPipelineError("BTC is not configured")

    def _create_workspace(self, job_id: str) -> JobWorkspace:
        workspace = JobWorkspace(
            self._config.workspace_root / job_id,
            self._config.demucs_model,
        )
        try:
            workspace.root.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise AnalysisPipelineError("workspace stage failed") from error
        return workspace

    def _run_preprocess(self, input_path: Path, workspace: JobWorkspace) -> None:
        self._run_stage(
            "preprocess",
            self._module_command(
                self._config.api_python,
                "preprocess",
                input_path,
                workspace.normalized_audio,
            ),
            self._config.preprocessing_timeout,
            workspace.normalized_audio,
            json_output=False,
        )

    def _run_beats(self, workspace: JobWorkspace) -> None:
        self._run_stage(
            "beats",
            self._module_command(
                self._config.beat_python,
                "beats",
                workspace.normalized_audio,
                workspace.beats,
            ),
            self._config.beat_timeout,
            workspace.beats,
        )

    def _run_practice_regions(
        self,
        workspace: JobWorkspace,
        job_id: str,
    ) -> Path | None:
        """Optional MUSIC_ONLY diagnostics; returns the regions file if made."""
        if not self._config.music_only_enabled:
            logger.info("[job %s] music_only_enabled=false", job_id)
            return None
        if self._config.chord_estimator is not ChordEstimator.BTC:
            return None
        chordino_available = self._run_chordino_diagnostic(workspace, job_id)
        if not (
            _has_nonempty_json_list(workspace.btc_uncertainty)
            and chordino_available
        ):
            logger.warning(
                "[job %s] strumming suitability diagnostics unavailable; "
                "continuing without practice_regions",
                job_id,
            )
            return None
        produced = self._run_optional_stage(
            "strumming suitability",
            [
                str(self._config.api_python),
                "-m",
                self._config.stage_module,
                "strumming-suitability",
                "--chords",
                str(workspace.chords),
                "--chordino",
                str(workspace.chordino_diagnostic),
                "--beats",
                str(workspace.beats),
                "--uncertainty",
                str(workspace.btc_uncertainty),
                "--output",
                str(workspace.practice_regions),
            ],
            self._config.fusion_timeout,
            workspace.practice_regions,
        )
        return workspace.practice_regions if produced else None

    def _run_chordino_diagnostic(
        self,
        workspace: JobWorkspace,
        job_id: str,
    ) -> bool:
        if self._config.vamp_simple_host_executable is None:
            logger.warning(
                "[job %s] chordino diagnostic unavailable; "
                "vamp-simple-host was not found; continuing without "
                "practice_regions",
                job_id,
            )
            return False
        return self._run_optional_stage(
            "chordino diagnostic",
            [
                str(self._config.api_python),
                "-m",
                self._config.stage_module,
                "chordino-diagnostic",
                "--input",
                str(workspace.normalized_audio),
                "--output",
                str(workspace.chordino_diagnostic),
                "--executable",
                str(self._config.vamp_simple_host_executable),
            ],
            self._config.chord_timeout,
            workspace.chordino_diagnostic,
        )

    def _run_separation(self, workspace: JobWorkspace) -> None:
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
                str(workspace.separation_directory),
                str(workspace.normalized_audio),
            ],
            self._config.separation_timeout,
            workspace.vocals,
            json_output=False,
        )

    def _run_lyrics(
        self,
        workspace: JobWorkspace,
        job_id: str,
        reference: LyricsReferenceResult | None = None,
    ) -> None:
        lyrics_command = [
            str(self._config.whisperx_executable),
            str(workspace.vocals),
            "--model",
            self._config.whisperx_model,
        ]
        if not self._config.multilingual_lyrics_enabled:
            lyrics_command.extend(["--language", "en"])
        elif reference is not None and looks_english(reference.plain_lyrics):
            # Language detection can misjudge a quiet intro; the reference
            # lyrics are a better guide than the first 30 seconds of audio.
            logger.info("[job %s] reference lyrics are English; using language=en", job_id)
            lyrics_command.extend(["--language", "en"])
        lyrics_command.extend(
            [
                "--device",
                "cpu",
                "--compute_type",
                "int8",
                "--output_dir",
                str(workspace.whisperx_directory),
                "--output_format",
                "json",
                "--verbose",
                "False",
            ]
        )
        self._run_stage(
            "lyrics",
            lyrics_command,
            self._config.lyric_timeout,
            workspace.whisperx,
            retry_without_alignment=self._config.multilingual_lyrics_enabled,
        )
        if self._config.multilingual_lyrics_enabled:
            self._retry_misdetected_sinhala(
                lyrics_command,
                workspace.whisperx,
                job_id,
            )

    def _remove_lyric_repetition_loops(self, whisperx_path: Path, job_id: str) -> None:
        """Drop Whisper repetition loops before anything reads the transcript."""
        try:
            transcript = json.loads(whisperx_path.read_text(encoding="utf-8"))
            report = remove_repetition_loops(transcript)
            if report.removed_words:
                whisperx_path.write_text(
                    json.dumps(transcript, ensure_ascii=False), encoding="utf-8"
                )
        except (OSError, ValueError, TypeError, AttributeError):
            logger.warning("[job %s] lyric repetition check skipped", job_id)
            return
        if report.removed_words:
            logger.info(
                "[job %s] removed %d words from %d repeated lyric loops",
                job_id,
                report.removed_words,
                report.loops,
            )

    def _prepare_fusion_lyrics(
        self,
        reference: LyricsReferenceResult | None,
        workspace: JobWorkspace,
        temporary_directory: Path,
        job_id: str,
    ) -> _FusionLyrics:
        lyrics = self._verify_optional_lyrics(
            reference,
            workspace.whisperx,
            temporary_directory / "vocals.verified.json",
            workspace.vocals,
            job_id,
        )
        if not self._config.multilingual_lyrics_enabled:
            return lyrics
        return replace(
            lyrics,
            whisperx_path=self._romanize_optional_lyrics(
                lyrics.whisperx_path,
                temporary_directory / "vocals.romanized.json",
                job_id,
            ),
        )

    @staticmethod
    def _read_timeline(timeline_path: Path) -> SharedTimeline:
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
        return reference

    def _verify_optional_lyrics(
        self,
        reference: LyricsReferenceResult | None,
        whisperx_path: Path,
        verified_whisperx_path: Path,
        audio_path: Path,
        job_id: str,
    ) -> _FusionLyrics:
        if reference is None:
            return _FusionLyrics(whisperx_path)
        verification: ProductionLyricsVerificationResult | None = None
        try:
            whisperx_result = json.loads(whisperx_path.read_text(encoding="utf-8"))
            language = str(whisperx_result.get("language", "")).casefold()
            if (
                self._config.multilingual_lyrics_enabled
                and whisperx_needs_romanization(whisperx_result)
            ):
                logger.info(
                    "[job %s] lyrics reference verification skipped for "
                    "language=%s",
                    job_id,
                    language or "unknown",
                )
                return _FusionLyrics(whisperx_path)
            aligner = self._reference_aligner or WhisperXReferenceAligner(
                python_executable=(
                    self._config.whisperx_executable.parent / "python"
                ),
                repo_root=self._config.repo_root,
                timeout_seconds=self._config.lyric_timeout,
            )
            verification = verify_and_correct_whisperx(
                whisperx_result,
                reference.plain_lyrics,
                audio_path,
                aligner,
            )
            diagnostics = verification.diagnostics
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
            if not verification.changed:
                return _FusionLyrics(whisperx_path, verification)
            verified_whisperx_path.write_text(
                json.dumps(verification.whisperx_result, indent=2),
                encoding="utf-8",
            )
            return _FusionLyrics(verified_whisperx_path, verification)
        except Exception as error:
            logger.warning(
                "[job %s] optional lyrics verification unavailable (%s); "
                "continuing with WhisperX",
                job_id,
                type(error).__name__,
            )
            return _FusionLyrics(whisperx_path, verification)

    def _romanize_optional_lyrics(
        self,
        whisperx_path: Path,
        romanized_whisperx_path: Path,
        job_id: str,
    ) -> Path:
        try:
            whisperx_result = json.loads(whisperx_path.read_text(encoding="utf-8"))
            if not whisperx_needs_romanization(whisperx_result):
                return whisperx_path
            if self._config.romanize_lyrics:
                prepared = romanize_whisperx_result(whisperx_result)
                outcome = "romanized"
            else:
                prepared = add_approximate_word_timings(whisperx_result)
                outcome = "kept in native script"
            romanized_whisperx_path.write_text(
                json.dumps(prepared, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("[job %s] multilingual lyrics %s", job_id, outcome)
            return romanized_whisperx_path
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            logger.warning(
                "[job %s] multilingual lyrics romanization unavailable; "
                "continuing with native lyrics",
                job_id,
            )
            return whisperx_path

    def _retry_misdetected_sinhala(
        self,
        lyrics_command: list[str],
        whisperx_path: Path,
        job_id: str,
    ) -> None:
        try:
            result = json.loads(whisperx_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if str(result.get("language", "")).casefold() != "sa":
            return
        text = " ".join(
            str(segment.get("text", ""))
            for segment in result.get("segments", [])
            if isinstance(segment, dict)
        )
        if not any("\u0d80" <= character <= "\u0dff" for character in text):
            return
        logger.info(
            "[job %s] Sinhala script detected after Sanskrit classification; "
            "retrying with language=si",
            job_id,
        )
        self._run_stage(
            "lyrics",
            [*lyrics_command, "--language", "si", "--no_align"],
            self._config.lyric_timeout,
            whisperx_path,
        )

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
        command = [
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
        if self._config.music_only_enabled:
            command.extend(
                [
                    "--uncertainty-output",
                    str(output_path.with_name("btc_uncertainty.json")),
                ]
            )
        return command

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
        retry_without_alignment: bool = False,
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
        if (
            result.returncode != 0
            and retry_without_alignment
            and _is_missing_alignment_model(result.stderr)
            and "--no_align" not in argv
        ):
            logger.info(
                "%s: alignment model unavailable; retrying with segment timing",
                prefix,
            )
            try:
                result = self._runner.run(
                    [*argv, "--no_align"],
                    cwd=self._config.repo_root,
                    timeout=timeout,
                )
            except SubprocessRunnerTimeout as error:
                logger.warning("%s: fallback timed out", prefix)
                raise AnalysisStageTimeout(f"{stage} stage timed out") from error
            except OSError as error:
                logger.warning("%s: fallback could not start", prefix)
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


def _environment_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser() if value else default


_MISSING_ALIGNMENT_MESSAGES = (
    # WhisperX has no default aligner for the language.
    "No default align-model for language:",
    # It has one, but it is not in the offline model release (the worker cannot
    # download it), e.g. a wrong language guess such as Nynorsk.
    "The chosen align_model",
    "could not be found in huggingface",
)


def _is_missing_alignment_model(stderr: str) -> bool:
    return any(message in stderr for message in _MISSING_ALIGNMENT_MESSAGES)


def _enabled_by_default(name: str) -> bool:
    value = os.getenv(name)
    return value is None or value.casefold() in {"1", "true", "yes"}


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
