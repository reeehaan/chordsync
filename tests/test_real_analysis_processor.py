import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from analysis.chords.estimator import ChordEstimator
from analysis.fusion.models import SharedTimeline
from backend.api.app.models.analysis_job import AnalysisJobCreateRequest
from backend.api.app.services.analysis_input_storage import LocalAnalysisInputStorage
from backend.api.app.services.analysis_job_executor import InProcessAnalysisJobExecutor
from backend.api.app.services.analysis_jobs import (
    AnalysisJobService,
    InMemoryAnalysisJobRepository,
)
from backend.api.app.services.real_analysis_processor import (
    AnalysisPipelineConfig,
    AnalysisPipelineError,
    AnalysisStageTimeout,
    LocalSubprocessRunner,
    RealAnalysisProcessor,
    SubprocessResult,
)


SYNTHETIC_TIMELINE = {
    "schema_version": 1,
    "bpm": 120.0,
    "beats_per_bar": 4,
    "beat_source": "synthetic-madmom",
    "lyric_source": "synthetic-whisperx",
    "bars": [
        {
            "bar_number": 1,
            "start_time": 0.0,
            "end_time": 1.0,
            "beats": [
                {
                    "time": 0.0,
                    "beat_number": 1,
                    "is_downbeat": True,
                    "chord": "C",
                }
            ],
        }
    ],
    "lyrics": [
        {
            "start": 0.1,
            "end": 0.5,
            "text": "steady",
            "words": [{"start": 0.1, "end": 0.5, "text": "steady"}],
        }
    ],
    "practice_regions": [],
}


@dataclass(frozen=True)
class RecordedCall:
    argv: list[str]
    cwd: Path
    timeout: float


class FakePipelineRunner:
    def __init__(
        self,
        *,
        failing_stage: str | None = None,
        missing_stage: str | None = None,
        malformed_stage: str | None = None,
        malformed_final: bool = False,
        timeout_stage: str | None = None,
        whisperx_words: list[str] | None = None,
        whisperx_language: str = "en",
    ) -> None:
        self.failing_stage = failing_stage
        self.missing_stage = missing_stage
        self.malformed_stage = malformed_stage
        self.malformed_final = malformed_final
        self.timeout_stage = timeout_stage
        self.whisperx_words = whisperx_words
        self.whisperx_language = whisperx_language
        self.calls: list[RecordedCall] = []
        self.fusion_whisperx_payload = None

    def run(self, argv: list[str], cwd: Path, timeout: float) -> SubprocessResult:
        assert type(argv) is list
        stage = self._stage(argv)
        self.calls.append(RecordedCall(argv=list(argv), cwd=cwd, timeout=timeout))
        if stage == self.timeout_stage:
            raise AnalysisStageTimeout(stage)
        if stage == self.failing_stage:
            return SubprocessResult(returncode=7, stdout="", stderr="private failure")
        if stage != self.missing_stage:
            if stage == self.malformed_stage:
                output = Path(argv[argv.index("--output") + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("not json", encoding="utf-8")
            else:
                self._write_output(stage, argv)
        return SubprocessResult(returncode=0, stdout="ok", stderr="")

    @staticmethod
    def _stage(argv: list[str]) -> str:
        if "analysis.lyrics.mms_alignment" in argv:
            return "align"
        executable_name = Path(argv[0]).name
        if executable_name == "whisperx":
            return "lyrics"
        if executable_name == "demucs":
            return "separate"
        return argv[3]

    def _write_output(self, stage: str, argv: list[str]) -> None:
        if stage == "preprocess":
            output = Path(argv[argv.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"RIFF normalized synthetic audio")
        elif stage in {"chords", "btc-chords"}:
            self._write_json(
                Path(argv[argv.index("--output") + 1]),
                [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "raw_label": "C",
                        "normalized_label": "C",
                        "source": "btc" if stage == "btc-chords" else "chordino",
                    }
                ],
            )
            if stage == "btc-chords" and "--uncertainty-output" in argv:
                self._write_json(
                    Path(argv[argv.index("--uncertainty-output") + 1]),
                    [
                        {
                            "time": 0.0,
                            "predicted_index": 0,
                            "predicted_label": "C:maj",
                            "top1_score": 0.8,
                            "top2_score": 0.1,
                            "margin": 0.7,
                            "normalized_entropy": 0.2,
                        }
                    ],
                )
        elif stage == "beats":
            self._write_json(
                Path(argv[argv.index("--output") + 1]),
                {
                    "bpm": 120.0,
                    "beats_per_bar": 4,
                    "source": "madmom",
                    "beats": [
                        {
                            "time": 0.0,
                            "beat_number": 1,
                            "is_downbeat": True,
                            "source": "madmom",
                        }
                    ],
                },
            )
        elif stage == "separate":
            output_dir = Path(argv[argv.index("-o") + 1])
            model_name = argv[argv.index("-n") + 1]
            input_path = Path(argv[-1])
            vocals_path = output_dir / model_name / input_path.stem / "vocals.wav"
            vocals_path.parent.mkdir(parents=True, exist_ok=True)
            vocals_path.write_bytes(b"RIFF synthetic vocals audio")
        elif stage == "lyrics":
            output_directory = Path(argv[argv.index("--output_dir") + 1])
            input_path = Path(argv[1])
            words = self.whisperx_words or ["steady"]
            self._write_json(
                output_directory / f"{input_path.stem}.json",
                {
                    "language": self.whisperx_language,
                    "segments": [
                        {
                            "start": 0.1,
                            "end": len(words) * 0.5,
                            "text": " ".join(words),
                            "words": [
                                {
                                    "start": index * 0.5,
                                    "end": index * 0.5 + 0.4,
                                    "word": word,
                                }
                                for index, word in enumerate(words)
                            ],
                        }
                    ],
                },
            )
        elif stage == "align":
            source = json.loads(
                Path(argv[argv.index("--transcript") + 1]).read_text(encoding="utf-8")
            )
            for segment in source["segments"]:
                for word in segment["words"]:
                    word["start"] += 0.25  # a recognisable change
                    word["end"] += 0.25
            source["alignment"] = "mms_fa"
            self._write_json(Path(argv[argv.index("--output") + 1]), source)
        elif stage == "chordino-diagnostic":
            self._write_json(
                Path(argv[argv.index("--output") + 1]),
                [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "raw_label": "C",
                        "normalized_label": "C",
                        "source": "chordino-diagnostic",
                    }
                ],
            )
        elif stage == "strumming-suitability":
            self._write_json(
                Path(argv[argv.index("--output") + 1]),
                [
                    {"start": 0.0, "end": 1.0, "mode": "music_only"},
                ],
            )
        elif stage == "fuse":
            output = Path(argv[argv.index("--output") + 1])
            self.fusion_whisperx_payload = json.loads(
                Path(argv[argv.index("--whisperx") + 1]).read_text(
                    encoding="utf-8"
                )
            )
            if self.malformed_final:
                self._write_json(output, {"schema_version": "invalid"})
            else:
                timeline = dict(SYNTHETIC_TIMELINE)
                if self.whisperx_words is not None:
                    whisperx = self.fusion_whisperx_payload
                    timeline["lyrics"] = [
                        {
                            "start": segment["start"],
                            "end": segment["end"],
                            "text": segment["text"],
                            "words": [
                                {
                                    "start": word["start"],
                                    "end": word["end"],
                                    "text": word["word"],
                                }
                                for word in segment["words"]
                            ],
                        }
                        for segment in whisperx["segments"]
                    ]
                if "--practice-regions" in argv:
                    timeline["practice_regions"] = json.loads(
                        Path(
                            argv[argv.index("--practice-regions") + 1]
                        ).read_text(encoding="utf-8")
                    )
                self._write_json(output, timeline)

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


class MissingAlignmentModelRunner(FakePipelineRunner):
    message = "ValueError: No default align-model for language: sa"

    def run(self, argv: list[str], cwd: Path, timeout: float) -> SubprocessResult:
        if self._stage(argv) == "lyrics" and "--no_align" not in argv:
            self.calls.append(RecordedCall(argv=list(argv), cwd=cwd, timeout=timeout))
            return SubprocessResult(
                returncode=1,
                stdout="",
                stderr=self.message,
            )
        result = super().run(argv, cwd, timeout)
        if self._stage(argv) == "lyrics" and "--no_align" in argv:
            output_directory = Path(argv[argv.index("--output_dir") + 1])
            output_path = output_directory / f"{Path(argv[1]).stem}.json"
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            payload["segments"][0].pop("words")
            if "--language" in argv:
                payload["language"] = argv[argv.index("--language") + 1]
            self._write_json(output_path, payload)
        return result


@pytest.fixture
def processor_context(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    input_path = tmp_path / "uploads" / "job-one" / "input.mp3"
    input_path.parent.mkdir(parents=True)
    input_path.write_bytes(b"original synthetic upload")
    config = AnalysisPipelineConfig(
        repo_root=repo_root,
        workspace_root=tmp_path / "workspaces",
        api_python=Path("/env/api/python"),
        beat_python=Path("/env/beats/python"),
        whisperx_executable=Path("/env/whisperx/whisperx"),
        demucs_executable=Path("/env/demucs/demucs"),
        preprocessing_timeout=11,
        chord_timeout=22,
        beat_timeout=33,
        separation_timeout=66,
        lyric_timeout=44,
        fusion_timeout=55,
    )
    return config, input_path


def test_real_adapter_runs_isolated_stages_in_order_and_parses_timeline(
    processor_context,
):
    config, input_path = processor_context
    runner = FakePipelineRunner()
    processor = RealAnalysisProcessor(config, runner)

    timeline = processor.process(input_path)

    assert timeline.model_dump(mode="json") == SYNTHETIC_TIMELINE
    assert [runner._stage(call.argv) for call in runner.calls] == [
        "preprocess",
        "chords",
        "beats",
        "separate",
        "lyrics",
        "fuse",
    ]
    assert runner.calls[0].argv[0] == str(config.api_python)
    assert runner.calls[1].argv[0] == str(config.api_python)
    assert runner.calls[2].argv[0] == str(config.beat_python)
    assert runner.calls[3].argv[0] == str(config.demucs_executable)
    assert runner.calls[4].argv[0] == str(config.whisperx_executable)
    assert runner.calls[4].argv[
        runner.calls[4].argv.index("--language") + 1
    ] == "en"
    assert runner.calls[5].argv[0] == str(config.api_python)
    assert runner.calls[5].argv[
        runner.calls[5].argv.index("--lyric-source") + 1
    ] == "whisperx-small"
    assert [call.timeout for call in runner.calls] == [11, 22, 33, 66, 44, 55]
    assert all(call.cwd == config.repo_root for call in runner.calls)
    assert str(input_path) in runner.calls[0].argv
    assert input_path.read_bytes() == b"original synthetic upload"


def test_optional_reference_failure_does_not_change_pipeline_output(
    processor_context,
    monkeypatch,
):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{**config.__dict__, "lrclib_reference_enabled": True}
    )
    monkeypatch.setattr(
        "backend.api.app.services.real_analysis_processor.obtain_lrclib_reference",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()),
    )
    runner = FakePipelineRunner()

    timeline = RealAnalysisProcessor(config, runner).process(input_path)

    assert timeline.model_dump(mode="json") == SYNTHETIC_TIMELINE
    assert [runner._stage(call.argv) for call in runner.calls] == [
        "preprocess", "chords", "beats", "separate", "lyrics", "fuse"
    ]


def test_optional_reference_payload_is_not_logged_or_persisted(
    processor_context,
    monkeypatch,
    caplog,
):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{**config.__dict__, "lrclib_reference_enabled": True}
    )
    lyric_marker = "provider payload must remain ephemeral"
    monkeypatch.setattr(
        "backend.api.app.services.real_analysis_processor.obtain_lrclib_reference",
        lambda *args, **kwargs: SimpleNamespace(plain_lyrics=lyric_marker),
    )

    processor = RealAnalysisProcessor(config, FakePipelineRunner())
    outcome = processor.analyze(input_path)

    persisted_text = "".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in config.workspace_root.rglob("*")
        if path.is_file()
    )
    assert lyric_marker not in persisted_text
    assert lyric_marker not in caplog.text
    assert outcome.lyrics_verification_diagnostics is not None


def test_trusted_reference_uses_safely_corrected_transcript_for_fusion(
    processor_context,
    monkeypatch,
):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{**config.__dict__, "lrclib_reference_enabled": True}
    )
    monkeypatch.setattr(
        "backend.api.app.services.real_analysis_processor.obtain_lrclib_reference",
        lambda *args, **kwargs: SimpleNamespace(
            plain_lyrics="silver birds cross quiet skies"
        ),
    )
    forced_result = {
        "segments": [
            {
                "words": [
                    {"word": "silver", "start": 0.02, "end": 0.36},
                    {"word": "birds", "start": 0.51, "end": 0.86},
                    {"word": "cross", "start": 0.92, "end": 1.18},
                    {"word": "quiet", "start": 1.51, "end": 1.86},
                    {"word": "skies", "start": 2.01, "end": 2.36},
                ]
            }
        ]
    }

    class Aligner:
        def align(self, audio_path, segments):
            assert audio_path.name == "vocals.wav"
            return forced_result

    runner = FakePipelineRunner(
        whisperx_words=["silver", "birds", "crest", "quiet", "skies"]
    )
    processor = RealAnalysisProcessor(
        config,
        runner,
        reference_aligner=Aligner(),
    )
    outcome = processor.analyze(input_path)
    timeline = outcome.timeline

    fuse_call = next(
        call for call in runner.calls if runner._stage(call.argv) == "fuse"
    )
    verified_path = Path(fuse_call.argv[fuse_call.argv.index("--whisperx") + 1])
    corrected = runner.fusion_whisperx_payload["segments"][0]["words"][2]
    assert not verified_path.exists()
    assert not (config.workspace_root / "job-one/whisperx/vocals.verified.json").exists()
    assert corrected == {"word": "cross", "start": 0.92, "end": 1.18}
    assert timeline.lyrics[0].words[2].text == "cross"
    assert len(outcome.lyrics_timing_provenance) == 1


def test_btc_estimator_uses_isolated_python_and_explicit_model_paths(
    processor_context,
):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{
            **config.__dict__,
            "chord_estimator": ChordEstimator.BTC,
            "btc_python": Path("/env/btc/python"),
            "btc_checkpoint": Path("/local/models/btc_model.pt"),
            "btc_source": Path("/external/BTC-ISMIR19"),
            "vamp_simple_host_executable": Path("/portable/bin/vamp-simple-host"),
            "music_only_enabled": True,
        }
    )
    runner = FakePipelineRunner()

    timeline = RealAnalysisProcessor(config, runner).process(input_path)

    chord_call = runner.calls[1]
    assert runner._stage(chord_call.argv) == "btc-chords"
    assert chord_call.argv[0] == "/env/btc/python"
    assert chord_call.argv[chord_call.argv.index("--checkpoint") + 1] == (
        "/local/models/btc_model.pt"
    )
    assert chord_call.argv[chord_call.argv.index("--source") + 1] == (
        "/external/BTC-ISMIR19"
    )
    assert all(runner._stage(call.argv) != "chords" for call in runner.calls)
    assert "--uncertainty-output" in chord_call.argv
    assert [runner._stage(call.argv) for call in runner.calls][1:5] == [
        "btc-chords",
        "beats",
        "chordino-diagnostic",
        "strumming-suitability",
    ]
    assert timeline.practice_regions[0].model_dump(mode="json") == {
        "start": 0.0,
        "end": 1.0,
        "mode": "music_only",
    }


@pytest.mark.parametrize(
    "failing_stage",
    ["chordino-diagnostic", "strumming-suitability"],
)
def test_btc_optional_diagnostic_failure_keeps_normal_analysis(
    processor_context,
    failing_stage,
):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{
            **config.__dict__,
            "chord_estimator": ChordEstimator.BTC,
            "btc_python": Path("/env/btc/python"),
            "btc_checkpoint": Path("/local/models/btc_model.pt"),
            "btc_source": Path("/external/BTC-ISMIR19"),
            "vamp_simple_host_executable": Path("/portable/bin/vamp-simple-host"),
            "music_only_enabled": True,
        }
    )
    runner = FakePipelineRunner(failing_stage=failing_stage)

    timeline = RealAnalysisProcessor(config, runner).process(input_path)

    assert timeline.practice_regions == []
    fuse_call = next(
        call for call in runner.calls if runner._stage(call.argv) == "fuse"
    )
    assert "--practice-regions" not in fuse_call.argv


def test_chordino_remains_default_estimator(processor_context):
    config, input_path = processor_context
    runner = FakePipelineRunner()

    RealAnalysisProcessor(config, runner).process(input_path)

    chord_call = runner.calls[1]
    assert runner._stage(chord_call.argv) == "chords"
    assert chord_call.argv[0] == str(config.api_python)


def test_btc_selection_requires_all_local_configuration(processor_context):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{**config.__dict__, "chord_estimator": ChordEstimator.BTC}
    )
    runner = FakePipelineRunner()

    with pytest.raises(AnalysisPipelineError, match="BTC is not configured"):
        RealAnalysisProcessor(config, runner).process(input_path)

    assert runner.calls == []


def test_local_config_defaults_to_btc_without_silently_falling_back(monkeypatch):
    monkeypatch.delenv("CHORDSYNC_CHORD_ESTIMATOR", raising=False)
    monkeypatch.delenv("CHORDSYNC_BTC_PYTHON", raising=False)
    monkeypatch.delenv("CHORDSYNC_BTC_CHECKPOINT", raising=False)
    monkeypatch.delenv("CHORDSYNC_BTC_SOURCE", raising=False)
    monkeypatch.delenv("CHORDSYNC_VAMP_SIMPLE_HOST", raising=False)
    monkeypatch.setattr(
        "backend.api.app.services.real_analysis_processor.shutil.which",
        lambda command: None,
    )

    config = AnalysisPipelineConfig.local()

    assert config.chord_estimator is ChordEstimator.BTC
    assert config.btc_python is None
    assert config.btc_checkpoint is None
    assert config.btc_source is None
    assert config.vamp_simple_host_executable is None


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "YES"])
def test_local_config_enables_lrclib_only_for_explicit_true_values(
    monkeypatch,
    value,
):
    monkeypatch.setenv("CHORDSYNC_LRCLIB_REFERENCE_ENABLED", value)

    assert AnalysisPipelineConfig.local().lrclib_reference_enabled is True


def test_local_config_disables_lrclib_when_environment_is_unset(monkeypatch):
    monkeypatch.delenv("CHORDSYNC_LRCLIB_REFERENCE_ENABLED", raising=False)

    assert AnalysisPipelineConfig.local().lrclib_reference_enabled is False


@pytest.mark.parametrize("value", ["", "0", "false", "no", "unexpected"])
def test_local_config_keeps_lrclib_disabled_for_other_values(
    monkeypatch,
    value,
):
    monkeypatch.setenv("CHORDSYNC_LRCLIB_REFERENCE_ENABLED", value)

    assert AnalysisPipelineConfig.local().lrclib_reference_enabled is False


def test_local_config_disables_music_only_when_environment_is_unset(monkeypatch):
    monkeypatch.delenv("CHORDSYNC_MUSIC_ONLY_ENABLED", raising=False)

    assert AnalysisPipelineConfig.local().music_only_enabled is False


@pytest.mark.parametrize(
    "value",
    ["", "0", "false", "FALSE", "no", "unexpected"],
)
def test_local_config_keeps_music_only_disabled_for_false_values(
    monkeypatch,
    value,
):
    monkeypatch.setenv("CHORDSYNC_MUSIC_ONLY_ENABLED", value)

    assert AnalysisPipelineConfig.local().music_only_enabled is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "YES"])
def test_local_config_enables_music_only_for_explicit_true_values(
    monkeypatch,
    value,
):
    monkeypatch.setenv("CHORDSYNC_MUSIC_ONLY_ENABLED", value)

    assert AnalysisPipelineConfig.local().music_only_enabled is True


def test_local_config_enables_multilingual_lyrics_when_environment_is_unset(
    monkeypatch,
):
    monkeypatch.delenv("CHORDSYNC_MULTILINGUAL_LYRICS_ENABLED", raising=False)

    assert AnalysisPipelineConfig.local().multilingual_lyrics_enabled is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "unexpected"])
def test_local_config_can_disable_multilingual_lyrics(monkeypatch, value):
    monkeypatch.setenv("CHORDSYNC_MULTILINGUAL_LYRICS_ENABLED", value)

    assert AnalysisPipelineConfig.local().multilingual_lyrics_enabled is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "YES"])
def test_local_config_enables_multilingual_lyrics_for_explicit_true_values(
    monkeypatch,
    value,
):
    monkeypatch.setenv("CHORDSYNC_MULTILINGUAL_LYRICS_ENABLED", value)

    assert AnalysisPipelineConfig.local().multilingual_lyrics_enabled is True


def test_multilingual_lyrics_uses_detection_while_english_output_stays_unchanged(
    processor_context,
):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{**config.__dict__, "multilingual_lyrics_enabled": True}
    )
    runner = FakePipelineRunner()

    timeline = RealAnalysisProcessor(config, runner).process(input_path)

    lyrics_call = next(
        call for call in runner.calls if runner._stage(call.argv) == "lyrics"
    )
    assert "--language" not in lyrics_call.argv
    assert timeline.model_dump(mode="json") == SYNTHETIC_TIMELINE


def test_multilingual_lyrics_romanizes_words_after_alignment(processor_context):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{
            **config.__dict__,
            "multilingual_lyrics_enabled": True,
            "romanize_lyrics": True,
        }
    )
    runner = FakePipelineRunner(
        whisperx_words=["महासमुंद"],
        whisperx_language="en",
    )

    timeline = RealAnalysisProcessor(config, runner).process(input_path)

    word = timeline.lyrics[0].words[0]
    assert word.text == "mhasmumd"
    assert word.start == 0.0
    assert word.end == 0.4


def test_multilingual_lyrics_falls_back_when_language_has_no_alignment_model(
    processor_context,
):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{**config.__dict__, "multilingual_lyrics_enabled": True}
    )
    runner = MissingAlignmentModelRunner(
        whisperx_words=["මන්දාරම්", "හැන්දෑවේ"],
        whisperx_language="sa",
    )

    timeline = RealAnalysisProcessor(config, runner).process(input_path)

    lyrics_calls = [
        call for call in runner.calls if runner._stage(call.argv) == "lyrics"
    ]
    assert len(lyrics_calls) == 3
    assert "--no_align" not in lyrics_calls[0].argv
    assert "--no_align" in lyrics_calls[1].argv
    assert "--language" not in lyrics_calls[1].argv
    assert "--no_align" in lyrics_calls[2].argv
    assert lyrics_calls[2].argv[
        lyrics_calls[2].argv.index("--language") + 1
    ] == "si"
    assert [word.text for word in timeline.lyrics[0].words] == [
        "මන්දාරම්",
        "හැන්දෑවේ",
    ]
    assert timeline.lyrics[0].words[0].start == pytest.approx(0.1)
    assert timeline.lyrics[0].words[-1].end == pytest.approx(1.0)


def test_romanizing_lyrics_can_be_turned_on(processor_context):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{
            **config.__dict__,
            "multilingual_lyrics_enabled": True,
            "romanize_lyrics": True,
        }
    )
    runner = MissingAlignmentModelRunner(
        whisperx_words=["මන්දාරම්", "හැන්දෑවේ"],
        whisperx_language="sa",
    )

    timeline = RealAnalysisProcessor(config, runner).process(input_path)

    assert [word.text for word in timeline.lyrics[0].words] == [
        "mndarm",
        "haendaeve",
    ]


def test_romanize_lyrics_is_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv("CHORDSYNC_ROMANIZE_LYRICS", raising=False)
    assert AnalysisPipelineConfig.local().romanize_lyrics is False
    monkeypatch.setenv("CHORDSYNC_ROMANIZE_LYRICS", "true")
    assert AnalysisPipelineConfig.local().romanize_lyrics is True


def test_non_english_multilingual_lyrics_skips_english_reference_alignment(
    processor_context,
    monkeypatch,
):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{
            **config.__dict__,
            "multilingual_lyrics_enabled": True,
            "lrclib_reference_enabled": True,
        }
    )
    monkeypatch.setattr(
        "backend.api.app.services.real_analysis_processor.obtain_lrclib_reference",
        lambda *args, **kwargs: SimpleNamespace(
            plain_lyrics="reference must not enter the English aligner"
        ),
    )

    alignment_calls = []

    class EnglishOnlyAligner:
        def align(self, audio_path, segments):
            alignment_calls.append((audio_path, segments))
            raise AssertionError("English aligner called for non-English lyrics")

    runner = FakePipelineRunner(
        whisperx_words=["महासमुंद"],
        whisperx_language="en",
    )
    processor = RealAnalysisProcessor(
        config,
        runner,
        reference_aligner=EnglishOnlyAligner(),
    )
    outcome = processor.analyze(input_path)
    timeline = outcome.timeline

    assert timeline.lyrics[0].words[0].text == "महासमुंद"
    assert alignment_calls == []
    assert outcome.lyrics_verification_diagnostics is None


def test_disabled_music_only_preserves_timeline_and_skips_diagnostics(
    processor_context,
    caplog,
):
    caplog.set_level(logging.INFO)
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{
            **config.__dict__,
            "chord_estimator": ChordEstimator.BTC,
            "btc_python": Path("/env/btc/python"),
            "btc_checkpoint": Path("/local/models/btc_model.pt"),
            "btc_source": Path("/external/BTC-ISMIR19"),
            "vamp_simple_host_executable": Path("/portable/bin/vamp-simple-host"),
        }
    )
    runner = FakePipelineRunner()

    timeline = RealAnalysisProcessor(config, runner).process(input_path)

    stages = [runner._stage(call.argv) for call in runner.calls]
    chord_call = runner.calls[1]
    assert stages == [
        "preprocess",
        "btc-chords",
        "beats",
        "separate",
        "lyrics",
        "fuse",
    ]
    assert "--uncertainty-output" not in chord_call.argv
    assert timeline.model_dump(mode="json") == SYNTHETIC_TIMELINE
    assert timeline.practice_regions == []
    assert timeline.bars == SharedTimeline.model_validate(SYNTHETIC_TIMELINE).bars
    assert timeline.lyrics == SharedTimeline.model_validate(SYNTHETIC_TIMELINE).lyrics
    assert "music_only_enabled=false" in caplog.text


def test_stored_timeline_with_music_only_region_still_parses():
    payload = {
        **SYNTHETIC_TIMELINE,
        "practice_regions": [
            {"start": 10.0, "end": 20.0, "mode": "music_only"}
        ],
    }

    timeline = SharedTimeline.model_validate(payload)

    assert timeline.practice_regions[0].model_dump(mode="json") == {
        "start": 10.0,
        "end": 20.0,
        "mode": "music_only",
    }


@pytest.mark.parametrize("value", ["invalid", "0", "-4"])
def test_invalid_lrclib_timeout_falls_back_to_default(monkeypatch, value):
    monkeypatch.setenv("CHORDSYNC_LRCLIB_TIMEOUT", value)

    assert AnalysisPipelineConfig.local().lrclib_timeout == 10.0


def test_local_config_resolves_vamp_simple_host_from_environment(monkeypatch):
    monkeypatch.setenv(
        "CHORDSYNC_VAMP_SIMPLE_HOST",
        "/portable/bin/configured-vamp-simple-host",
    )

    config = AnalysisPipelineConfig.local()

    assert config.vamp_simple_host_executable == Path(
        "/portable/bin/configured-vamp-simple-host"
    )


def test_local_config_resolves_vamp_simple_host_from_path(monkeypatch):
    monkeypatch.delenv("CHORDSYNC_VAMP_SIMPLE_HOST", raising=False)
    monkeypatch.setattr(
        "backend.api.app.services.real_analysis_processor.shutil.which",
        lambda command: "/portable/bin/vamp-simple-host",
    )

    config = AnalysisPipelineConfig.local()

    assert config.vamp_simple_host_executable == Path(
        "/portable/bin/vamp-simple-host"
    )


def test_btc_without_vamp_simple_host_skips_optional_diagnostics(
    processor_context,
):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{
            **config.__dict__,
            "chord_estimator": ChordEstimator.BTC,
            "btc_python": Path("/env/btc/python"),
            "btc_checkpoint": Path("/local/models/btc_model.pt"),
            "btc_source": Path("/external/BTC-ISMIR19"),
            "vamp_simple_host_executable": None,
            "music_only_enabled": True,
        }
    )
    runner = FakePipelineRunner()

    timeline = RealAnalysisProcessor(config, runner).process(input_path)

    stages = [runner._stage(call.argv) for call in runner.calls]
    assert "chordino-diagnostic" not in stages
    assert "strumming-suitability" not in stages
    assert timeline.practice_regions == []


def test_local_config_prefers_btc_once_configured_without_explicit_opt_in(
    monkeypatch,
):
    monkeypatch.delenv("CHORDSYNC_CHORD_ESTIMATOR", raising=False)
    monkeypatch.setenv("CHORDSYNC_BTC_PYTHON", "/portable/btc/python")
    monkeypatch.setenv("CHORDSYNC_BTC_CHECKPOINT", "/local/model.pt")
    monkeypatch.setenv("CHORDSYNC_BTC_SOURCE", "/external/BTC-ISMIR19")

    config = AnalysisPipelineConfig.local()

    assert config.chord_estimator is ChordEstimator.BTC


def test_local_config_reads_btc_environment_without_importing_model(monkeypatch):
    monkeypatch.setenv("CHORDSYNC_CHORD_ESTIMATOR", "btc")
    monkeypatch.setenv("CHORDSYNC_BTC_PYTHON", "/portable/btc/python")
    monkeypatch.setenv("CHORDSYNC_BTC_CHECKPOINT", "/local/model.pt")
    monkeypatch.setenv("CHORDSYNC_BTC_SOURCE", "/external/BTC-ISMIR19")

    config = AnalysisPipelineConfig.local()

    assert config.chord_estimator is ChordEstimator.BTC
    assert config.btc_python == Path("/portable/btc/python")
    assert config.btc_checkpoint == Path("/local/model.pt")
    assert config.btc_source == Path("/external/BTC-ISMIR19")
    assert "analysis.chords.btc.btc_inference" not in sys.modules


def test_local_config_supports_container_runtime_paths(monkeypatch):
    monkeypatch.setenv("CHORDSYNC_WORKSPACE_ROOT", "/tmp/chordsync")
    monkeypatch.setenv("CHORDSYNC_API_PYTHON", "/opt/chordsync/api/bin/python")
    monkeypatch.setenv("CHORDSYNC_BEAT_PYTHON", "/opt/chordsync/beats/bin/python")
    monkeypatch.setenv(
        "CHORDSYNC_WHISPERX_EXECUTABLE",
        "/opt/chordsync/whisperx/bin/whisperx",
    )
    monkeypatch.setenv(
        "CHORDSYNC_DEMUCS_EXECUTABLE",
        "/opt/chordsync/demucs/bin/demucs",
    )

    config = AnalysisPipelineConfig.local()

    assert config.workspace_root == Path("/tmp/chordsync")
    assert config.api_python == Path("/opt/chordsync/api/bin/python")
    assert config.beat_python == Path("/opt/chordsync/beats/bin/python")
    assert config.whisperx_executable == Path(
        "/opt/chordsync/whisperx/bin/whisperx"
    )
    assert config.demucs_executable == Path(
        "/opt/chordsync/demucs/bin/demucs"
    )


def test_separate_jobs_use_separate_workspaces(processor_context):
    config, first_input = processor_context
    second_input = first_input.parents[1] / "job-two" / "input.wav"
    second_input.parent.mkdir()
    second_input.write_bytes(b"second synthetic upload")
    runner = FakePipelineRunner()
    processor = RealAnalysisProcessor(config, runner)

    processor.process(first_input)
    processor.process(second_input)

    assert (config.workspace_root / "job-one" / "timeline.json").exists()
    assert (config.workspace_root / "job-two" / "timeline.json").exists()


@pytest.mark.parametrize("stage", ["chords", "beats", "separate", "lyrics", "fuse"])
def test_nonzero_stage_exit_fails_processing(processor_context, stage):
    config, input_path = processor_context
    processor = RealAnalysisProcessor(
        config,
        FakePipelineRunner(failing_stage=stage),
    )

    with pytest.raises(AnalysisPipelineError, match=stage):
        processor.process(input_path)


@pytest.mark.parametrize(
    "stage", ["preprocess", "chords", "beats", "separate", "lyrics", "fuse"]
)
def test_missing_stage_output_fails_processing(processor_context, stage):
    config, input_path = processor_context
    processor = RealAnalysisProcessor(config, FakePipelineRunner(missing_stage=stage))

    with pytest.raises(AnalysisPipelineError, match=stage):
        processor.process(input_path)


def test_malformed_final_timeline_fails_processing(processor_context):
    config, input_path = processor_context
    processor = RealAnalysisProcessor(config, FakePipelineRunner(malformed_final=True))

    with pytest.raises(AnalysisPipelineError, match="fuse"):
        processor.process(input_path)


@pytest.mark.parametrize("stage", ["chords", "beats"])
def test_malformed_intermediate_json_fails_processing(processor_context, stage):
    config, input_path = processor_context
    processor = RealAnalysisProcessor(
        config,
        FakePipelineRunner(malformed_stage=stage),
    )

    with pytest.raises(AnalysisPipelineError, match=stage):
        processor.process(input_path)


def test_stage_timeout_fails_processing(processor_context):
    config, input_path = processor_context
    processor = RealAnalysisProcessor(
        config,
        FakePipelineRunner(timeout_stage="lyrics"),
    )

    with pytest.raises(AnalysisStageTimeout, match="lyrics"):
        processor.process(input_path)


def test_local_runner_uses_argv_without_shell(monkeypatch, tmp_path):
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "out", "err")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = LocalSubprocessRunner().run(
        ["python", "-m", "safe.module"],
        cwd=tmp_path,
        timeout=9,
    )

    assert observed["argv"] == ["python", "-m", "safe.module"]
    assert observed["shell"] is False
    assert observed["cwd"] == tmp_path
    assert observed["timeout"] == 9
    assert result.returncode == 0


def test_api_import_does_not_load_heavy_analysis_packages():
    assert not any(name == "madmom" or name.startswith("madmom.") for name in sys.modules)
    assert not any(
        name == "whisperx" or name.startswith("whisperx.") for name in sys.modules
    )
    assert not any(
        name == "demucs" or name.startswith("demucs.") for name in sys.modules
    )
    assert not any(name == "torch" or name.startswith("torch.") for name in sys.modules)
    assert not any(
        name == "analysis.chords.btc.btc_inference"
        for name in sys.modules
    )


def test_real_adapter_integrates_with_executor_success(processor_context, tmp_path):
    config, _ = processor_context
    storage = LocalAnalysisInputStorage(
        tmp_path / "job-inputs",
        duration_probe=lambda _: 1.0,
    )
    service = AnalysisJobService(InMemoryAnalysisJobRepository(), storage)
    job = service.create(
        request=AnalysisJobCreateRequest(title="Synthetic integration"),
        original_filename="synthetic.wav",
        content_type="audio/wav",
        source=BytesIO(b"RIFF synthetic"),
    )
    processor = RealAnalysisProcessor(config, FakePipelineRunner())
    executor = InProcessAnalysisJobExecutor(service, storage, processor)

    assert executor.run(job.job_id) is True
    record = service.get(job.job_id)
    assert record.status.value == "completed"
    assert record.result.model_dump(mode="json") == SYNTHETIC_TIMELINE


def test_real_adapter_failure_is_sanitized_by_executor(processor_context, tmp_path):
    config, _ = processor_context
    storage = LocalAnalysisInputStorage(
        tmp_path / "job-inputs",
        duration_probe=lambda _: 1.0,
    )
    service = AnalysisJobService(InMemoryAnalysisJobRepository(), storage)
    job = service.create(
        request=AnalysisJobCreateRequest(title="Synthetic failure"),
        original_filename="synthetic.wav",
        content_type="audio/wav",
        source=BytesIO(b"RIFF synthetic"),
    )
    processor = RealAnalysisProcessor(
        config,
        FakePipelineRunner(failing_stage="beats"),
    )
    executor = InProcessAnalysisJobExecutor(service, storage, processor)

    assert executor.run(job.job_id) is True
    record = service.get(job.job_id)
    assert record.status.value == "failed"
    assert record.error.model_dump() == {
        "code": "analysis_failed",
        "message": "Analysis could not be completed.",
    }
    public_response = str(service.response(record).model_dump())
    assert "private failure" not in public_response
    assert str(config.api_python) not in public_response
    assert str(config.beat_python) not in public_response
    assert str(config.whisperx_executable) not in public_response


NYNORSK_ERROR = (
    'ValueError: The chosen align_model "NbAiLab/nb-wav2vec2-1b-nynorsk" could '
    "not be found in huggingface (https://huggingface.co/models) or torchaudio"
)
ENGLISH_LYRICS = (
    "I know that you are all that I need and I love the way you hold me in the "
    "night when the world is quiet and we are alone with the stars and the sky "
    "oh you are the one that I want and I will never let you go"
)


def _multilingual(config):
    return AnalysisPipelineConfig(
        **{**config.__dict__, "multilingual_lyrics_enabled": True}
    )


def test_an_alignment_model_missing_offline_falls_back_instead_of_failing(
    processor_context,
):
    config, input_path = processor_context

    class NynorskRunner(MissingAlignmentModelRunner):
        message = NYNORSK_ERROR

    runner = NynorskRunner(whisperx_words=["hello", "there"], whisperx_language="nn")

    timeline = RealAnalysisProcessor(_multilingual(config), runner).process(input_path)

    lyrics_calls = [c for c in runner.calls if runner._stage(c.argv) == "lyrics"]
    assert len(lyrics_calls) == 2
    assert "--no_align" not in lyrics_calls[0].argv
    assert "--no_align" in lyrics_calls[1].argv
    assert timeline.lyrics


def test_english_reference_lyrics_pin_the_language_to_english(
    processor_context, monkeypatch
):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{**_multilingual(config).__dict__, "lrclib_reference_enabled": True}
    )
    monkeypatch.setattr(
        "backend.api.app.services.real_analysis_processor.obtain_lrclib_reference",
        lambda *args, **kwargs: SimpleNamespace(plain_lyrics=ENGLISH_LYRICS),
    )
    runner = FakePipelineRunner()

    RealAnalysisProcessor(config, runner).process(input_path)

    lyrics_call = next(c for c in runner.calls if runner._stage(c.argv) == "lyrics")
    assert lyrics_call.argv[lyrics_call.argv.index("--language") + 1] == "en"


@pytest.mark.parametrize(
    "plain_lyrics",
    [
        "tum mere ho tum mere ho kya kahun main tujhse dil mein basa hai tu hi "
        "mera sab kuch hai tu hi meri duniya hai bas tu hi tu hi hai mere liye "
        "tera naam hai mere dil par likha hua hai tu hi mera khuda hai",
        "මන්දාරම් හැන්දෑවේ " * 20,
        "too short",
    ],
)
def test_other_or_unknown_languages_keep_automatic_detection(
    processor_context, monkeypatch, plain_lyrics
):
    config, input_path = processor_context
    config = AnalysisPipelineConfig(
        **{**_multilingual(config).__dict__, "lrclib_reference_enabled": True}
    )
    monkeypatch.setattr(
        "backend.api.app.services.real_analysis_processor.obtain_lrclib_reference",
        lambda *args, **kwargs: SimpleNamespace(plain_lyrics=plain_lyrics),
    )
    runner = FakePipelineRunner()

    RealAnalysisProcessor(config, runner).process(input_path)

    lyrics_call = next(c for c in runner.calls if runner._stage(c.argv) == "lyrics")
    assert "--language" not in lyrics_call.argv


def test_without_a_reference_detection_stays_automatic(processor_context):
    config, input_path = processor_context
    runner = FakePipelineRunner()

    RealAnalysisProcessor(_multilingual(config), runner).process(input_path)

    lyrics_call = next(c for c in runner.calls if runner._stage(c.argv) == "lyrics")
    assert "--language" not in lyrics_call.argv


SINHALA_LINES = [
    "මන්දාරම් හැන්දෑවේ",
    "ආදරයෙන් වෙලා ඔබ",
    "රාගයක මා හට පෙම්",
    "කරන මාලයේ රඟා",
    "නෙතන් ගෙවූ සිහිනේ",
]
SYNCED_SINHALA = "\n".join(
    f"[00:{10 + index * 8:02d}.00] {line}" for index, line in enumerate(SINHALA_LINES)
)


def _reference_config(config, **updates):
    return AnalysisPipelineConfig(
        **{
            **config.__dict__,
            "multilingual_lyrics_enabled": True,
            "lrclib_reference_enabled": True,
            **updates,
        }
    )


def _patch_reference(monkeypatch, *, plain, synced):
    monkeypatch.setattr(
        "backend.api.app.services.real_analysis_processor.obtain_lrclib_reference",
        lambda *args, **kwargs: SimpleNamespace(plain_lyrics=plain, synced_lyrics=synced),
    )


def _lyrics_calls(runner):
    return [call for call in runner.calls if runner._stage(call.argv) == "lyrics"]


def test_synced_reference_lyrics_replace_transcription_for_non_english_songs(
    processor_context, monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    config, input_path = processor_context
    _patch_reference(monkeypatch, plain="\n".join(SINHALA_LINES), synced=SYNCED_SINHALA)
    runner = FakePipelineRunner()

    outcome = RealAnalysisProcessor(_reference_config(config), runner).analyze(
        input_path
    )

    assert _lyrics_calls(runner) == []  # no speech recognition was run
    segments = runner.fusion_whisperx_payload["segments"]
    assert [segment["text"].strip() for segment in segments] == SINHALA_LINES
    assert segments[0]["start"] == pytest.approx(10.0)
    assert all(segment["words"] for segment in segments)
    assert "built from synced reference" in caplog.text
    assert outcome.timeline is not None
    fuse = next(c for c in runner.calls if runner._stage(c.argv) == "fuse")
    assert fuse.argv[fuse.argv.index("--lyric-source") + 1] == "lrclib-synced"


def test_english_songs_still_use_transcription_even_with_synced_lyrics(
    processor_context, monkeypatch
):
    config, input_path = processor_context
    english = "\n".join(
        f"[00:{10 + i * 8:02d}.00] I know that you are all that I need and the sky"
        for i in range(5)
    )
    _patch_reference(monkeypatch, plain=ENGLISH_LYRICS, synced=english)
    runner = FakePipelineRunner()

    RealAnalysisProcessor(_reference_config(config), runner).analyze(input_path)

    assert len(_lyrics_calls(runner)) == 1
    fuse = next(c for c in runner.calls if runner._stage(c.argv) == "fuse")
    assert fuse.argv[fuse.argv.index("--lyric-source") + 1].startswith("whisperx-")


@pytest.mark.parametrize(
    "synced, flag",
    [
        (None, True),  # the provider has no synced lyrics
        ("[00:10.00] only\n[00:20.00] two lines", True),  # too few to trust
        (SYNCED_SINHALA, False),  # switched off
    ],
)
def test_synced_lyrics_are_only_used_when_suitable(
    processor_context, monkeypatch, synced, flag
):
    config, input_path = processor_context
    _patch_reference(monkeypatch, plain="\n".join(SINHALA_LINES), synced=synced)
    runner = FakePipelineRunner()

    RealAnalysisProcessor(
        _reference_config(config, synced_lyrics_enabled=flag), runner
    ).analyze(input_path)

    assert len(_lyrics_calls(runner)) >= 1


def test_synced_lyrics_follow_the_singer_when_the_vocals_are_readable(
    processor_context, monkeypatch
):
    config, input_path = processor_context
    _patch_reference(monkeypatch, plain="\n".join(SINHALA_LINES), synced=SYNCED_SINHALA)

    class SungRunner(FakePipelineRunner):
        """Writes real vocals: the singer starts 3 s after the provider's lines."""

        def _write_output(self, stage, argv):
            super()._write_output(stage, argv)
            if stage == "separate":
                import struct
                import wave

                output_dir = Path(argv[argv.index("-o") + 1])
                model = argv[argv.index("-n") + 1]
                target = output_dir / model / Path(argv[-1]).stem / "vocals.wav"
                rate = 2000
                loud = struct.pack("<h", 9000) * rate
                quiet = struct.pack("<h", 0) * rate
                singing = {13 + i * 8 + k for i in range(5) for k in range(6)}
                with wave.open(str(target), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(rate)
                    for second in range(60):
                        audio.writeframes(loud if second in singing else quiet)

    runner = SungRunner()

    RealAnalysisProcessor(_reference_config(config), runner).analyze(input_path)

    first = runner.fusion_whisperx_payload["segments"][0]
    assert first["start"] == pytest.approx(13.0, abs=0.2)


def _first_word_start(runner):
    return runner.fusion_whisperx_payload["segments"][0]["words"][0]["start"]


def test_synced_words_are_aligned_to_the_vocals(processor_context, monkeypatch):
    config, input_path = processor_context
    _patch_reference(monkeypatch, plain="\n".join(SINHALA_LINES), synced=SYNCED_SINHALA)
    runner = FakePipelineRunner()

    RealAnalysisProcessor(_reference_config(config), runner).analyze(input_path)

    align = next(c for c in runner.calls if runner._stage(c.argv) == "align")
    assert align.argv[0] == "/env/whisperx/python"
    assert align.argv[1:3] == ["-m", "analysis.lyrics.mms_alignment"]
    assert runner.fusion_whisperx_payload["alignment"] == "mms_fa"
    assert _first_word_start(runner) == pytest.approx(10.25)


@pytest.mark.parametrize("failure", ["failing_stage", "missing_stage"])
def test_a_failed_alignment_keeps_the_even_word_split(
    processor_context, monkeypatch, caplog, failure
):
    caplog.set_level(logging.WARNING)
    config, input_path = processor_context
    _patch_reference(monkeypatch, plain="\n".join(SINHALA_LINES), synced=SYNCED_SINHALA)
    runner = FakePipelineRunner(**{failure: "align"})

    outcome = RealAnalysisProcessor(_reference_config(config), runner).analyze(
        input_path
    )

    assert outcome.timeline is not None
    assert "alignment" not in runner.fusion_whisperx_payload
    assert _first_word_start(runner) == pytest.approx(10.0)
    assert "keeping the even word split" in caplog.text


def test_alignment_can_be_switched_off(processor_context, monkeypatch):
    config, input_path = processor_context
    _patch_reference(monkeypatch, plain="\n".join(SINHALA_LINES), synced=SYNCED_SINHALA)
    runner = FakePipelineRunner()

    RealAnalysisProcessor(
        _reference_config(config, mms_alignment_enabled=False), runner
    ).analyze(input_path)

    assert not any(runner._stage(c.argv) == "align" for c in runner.calls)
    assert _first_word_start(runner) == pytest.approx(10.0)


def test_english_songs_are_not_aligned_with_mms(processor_context, monkeypatch):
    config, input_path = processor_context
    _patch_reference(monkeypatch, plain=ENGLISH_LYRICS, synced=None)
    runner = FakePipelineRunner()

    RealAnalysisProcessor(_reference_config(config), runner).analyze(input_path)

    assert not any(runner._stage(c.argv) == "align" for c in runner.calls)


def test_the_alignment_model_is_fetched_just_before_it_is_needed(
    processor_context, monkeypatch
):
    config, input_path = processor_context
    _patch_reference(monkeypatch, plain="\n".join(SINHALA_LINES), synced=SYNCED_SINHALA)
    runner = FakePipelineRunner()
    fetched = []

    def installer(role):
        fetched.append((role, [c for c in runner.calls if runner._stage(c.argv) == "align"]))

    RealAnalysisProcessor(
        _reference_config(config), runner, model_installer=installer
    ).analyze(input_path)

    assert [role.value for role, _ in fetched] == ["alignment_mms"]
    assert fetched[0][1] == []  # fetched before the alignment stage started
    assert any(runner._stage(c.argv) == "align" for c in runner.calls)


def test_a_failed_model_fetch_keeps_the_even_word_split(
    processor_context, monkeypatch, caplog
):
    from backend.api.app.services.model_bootstrap import ModelBootstrapError

    caplog.set_level(logging.WARNING)
    config, input_path = processor_context
    _patch_reference(monkeypatch, plain="\n".join(SINHALA_LINES), synced=SYNCED_SINHALA)
    runner = FakePipelineRunner()

    def installer(role):
        raise ModelBootstrapError("Model object is missing")

    RealAnalysisProcessor(
        _reference_config(config), runner, model_installer=installer
    ).analyze(input_path)

    assert not any(runner._stage(c.argv) == "align" for c in runner.calls)
    assert _first_word_start(runner) == pytest.approx(10.0)
    assert "keeping the even word split" in caplog.text


def test_songs_that_do_not_need_alignment_never_fetch_the_model(
    processor_context, monkeypatch
):
    config, input_path = processor_context
    _patch_reference(monkeypatch, plain=ENGLISH_LYRICS, synced=None)
    fetched = []

    RealAnalysisProcessor(
        _reference_config(config),
        FakePipelineRunner(),
        model_installer=fetched.append,
    ).analyze(input_path)

    assert fetched == []


BAD_SINHALA_WORDS = (
    ["hello", "there", "friend", "again", "today"] * 4
    + ["नमस्ते", "दोस्त", "फिर", "आज"] * 5
)
GOOD_HINDI_WORDS = [f"shabd{i}" for i in range(40)]


def test_an_unusable_non_english_transcript_is_published_as_chords_only(
    processor_context, caplog
):
    caplog.set_level(logging.INFO)
    config, input_path = processor_context
    runner = FakePipelineRunner(whisperx_words=BAD_SINHALA_WORDS, whisperx_language="hi")

    outcome = RealAnalysisProcessor(_reference_config(config, lrclib_reference_enabled=False), runner).analyze(input_path)

    assert runner.fusion_whisperx_payload["segments"] == []
    fuse = next(c for c in runner.calls if runner._stage(c.argv) == "fuse")
    assert fuse.argv[fuse.argv.index("--lyric-source") + 1] == "none"
    assert "lyrics dropped as unreliable (mixed scripts" in caplog.text
    assert outcome.timeline is not None  # the chords are still published


def test_a_usable_non_english_transcript_is_kept(processor_context):
    config, input_path = processor_context
    runner = FakePipelineRunner(whisperx_words=GOOD_HINDI_WORDS, whisperx_language="hi")

    RealAnalysisProcessor(_reference_config(config, lrclib_reference_enabled=False), runner).analyze(input_path)

    assert len(runner.fusion_whisperx_payload["segments"]) == 1


def test_english_transcripts_are_never_dropped(processor_context):
    config, input_path = processor_context
    runner = FakePipelineRunner(whisperx_words=["ahhh"] * 50, whisperx_language="en")

    RealAnalysisProcessor(_reference_config(config, lrclib_reference_enabled=False), runner).analyze(input_path)

    assert len(runner.fusion_whisperx_payload["segments"][0]["words"]) == 3  # loop cut to 3, kept


SINGLISH_WORDS = (
    "Ob my hadeh lehi randindin Mal maavate sar nethu sihinen ahasa diyath manaram "
    "kandulu galaya kiyaa yanna balan inna handa pena hithe ayal"
).split() * 2


def test_sinhala_spelled_in_english_letters_is_published_as_chords_only(
    processor_context, caplog
):
    caplog.set_level(logging.INFO)
    config, input_path = processor_context
    runner = FakePipelineRunner(whisperx_words=SINGLISH_WORDS, whisperx_language="en")

    RealAnalysisProcessor(
        _reference_config(config, lrclib_reference_enabled=False), runner
    ).analyze(input_path)

    assert runner.fusion_whisperx_payload["segments"] == []
    assert "labelled English but only" in caplog.text


def test_real_english_lyrics_are_still_kept(processor_context):
    config, input_path = processor_context
    words = ENGLISH_LYRICS.split() * 2
    runner = FakePipelineRunner(whisperx_words=words, whisperx_language="en")

    RealAnalysisProcessor(
        _reference_config(config, lrclib_reference_enabled=False), runner
    ).analyze(input_path)

    assert len(runner.fusion_whisperx_payload["segments"]) == 1


def test_the_lookup_is_tried_again_before_the_lyrics_step(
    processor_context, monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    config, input_path = processor_context
    answers = [
        None,  # LRCLIB was down at the start of the job
        SimpleNamespace(plain_lyrics="\n".join(SINHALA_LINES), synced_lyrics=SYNCED_SINHALA),
    ]
    monkeypatch.setattr(
        "backend.api.app.services.real_analysis_processor.obtain_lrclib_reference",
        lambda *args, **kwargs: answers.pop(0),
    )
    runner = FakePipelineRunner()

    RealAnalysisProcessor(_reference_config(config), runner).analyze(input_path)

    assert answers == []  # asked twice
    assert _lyrics_calls(runner) == []  # the second answer was used
    assert "matched on the second try" in caplog.text


def test_a_song_with_no_reference_is_only_looked_up_twice(
    processor_context, monkeypatch
):
    config, input_path = processor_context
    calls = []
    monkeypatch.setattr(
        "backend.api.app.services.real_analysis_processor.obtain_lrclib_reference",
        lambda *args, **kwargs: calls.append(1),
    )

    RealAnalysisProcessor(_reference_config(config), FakePipelineRunner()).analyze(
        input_path
    )

    assert len(calls) == 2
