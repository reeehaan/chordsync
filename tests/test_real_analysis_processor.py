import json
import subprocess
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pytest

from analysis.chords.estimator import ChordEstimator
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
    ) -> None:
        self.failing_stage = failing_stage
        self.missing_stage = missing_stage
        self.malformed_stage = malformed_stage
        self.malformed_final = malformed_final
        self.timeout_stage = timeout_stage
        self.calls: list[RecordedCall] = []

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
            self._write_json(
                output_directory / f"{input_path.stem}.json",
                {
                    "language": "en",
                    "segments": [
                        {
                            "start": 0.1,
                            "end": 0.5,
                            "text": "steady",
                            "words": [
                                {"start": 0.1, "end": 0.5, "word": "steady"}
                            ],
                        }
                    ],
                },
            )
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
            if self.malformed_final:
                self._write_json(output, {"schema_version": "invalid"})
            else:
                timeline = dict(SYNTHETIC_TIMELINE)
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
    assert runner.calls[5].argv[0] == str(config.api_python)
    assert runner.calls[5].argv[
        runner.calls[5].argv.index("--lyric-source") + 1
    ] == "whisperx-small"
    assert [call.timeout for call in runner.calls] == [11, 22, 33, 66, 44, 55]
    assert all(call.cwd == config.repo_root for call in runner.calls)
    assert str(input_path) in runner.calls[0].argv
    assert input_path.read_bytes() == b"original synthetic upload"


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


def test_local_config_defaults_to_chordino_without_btc_paths(monkeypatch):
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

    assert config.chord_estimator is ChordEstimator.CHORDINO
    assert config.btc_python is None
    assert config.btc_checkpoint is None
    assert config.btc_source is None
    assert config.vamp_simple_host_executable is None


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
    storage = LocalAnalysisInputStorage(tmp_path / "job-inputs")
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
    storage = LocalAnalysisInputStorage(tmp_path / "job-inputs")
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
