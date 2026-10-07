import json
from pathlib import Path

import pytest

from analysis.fusion.models import SharedTimeline
from backend.api.app.analysis_worker import AnalysisWorkerJob, execute_worker_job
from backend.api.app.analysis_worker_consumer import parse_arguments as parse_consumer_arguments
from backend.api.app.reconcile_dispatch import parse_arguments as parse_reconcile_arguments


def _timeline() -> SharedTimeline:
    return SharedTimeline(
        schema_version=1,
        bpm=120.0,
        beats_per_bar=4,
        beat_source="synthetic-worker",
        lyric_source="synthetic-worker",
        bars=[],
        lyrics=[],
    )


def test_worker_entry_point_uses_workspace_and_writes_atomic_result(tmp_path):
    input_path = tmp_path / "inputs" / "job-one" / "input.mp3"
    input_path.parent.mkdir(parents=True)
    input_path.write_bytes(b"synthetic audio")
    workspace_root = tmp_path / "workspaces"
    result_path = tmp_path / "results" / "job-one" / "timeline.json"
    received = {}

    class FakeProcessor:
        def __init__(self, config):
            received["workspace_root"] = config.workspace_root

        def process(self, path: Path) -> SharedTimeline:
            received["input_path"] = path
            return _timeline()

    execute_worker_job(
        AnalysisWorkerJob(
            job_id="job-one",
            title="Synthetic song",
            input_path=input_path,
            workspace_root=workspace_root,
            result_path=result_path,
        ),
        processor_factory=FakeProcessor,
    )

    assert received == {
        "workspace_root": workspace_root,
        "input_path": input_path,
    }
    assert json.loads(result_path.read_text(encoding="utf-8")) == _timeline().model_dump(
        mode="json"
    )
    assert not result_path.with_suffix(".json.part").exists()


@pytest.mark.parametrize(
    ("job_id", "input_parent", "title"),
    [
        ("../unsafe", "unsafe", "Song"),
        ("..", "safe", "Song"),
        ("job-one", "other-job", "Song"),
        ("job-one", "job-one", "   "),
    ],
)
def test_worker_rejects_invalid_job_descriptor(
    tmp_path,
    job_id,
    input_parent,
    title,
):
    input_path = tmp_path / input_parent / "input.wav"
    input_path.parent.mkdir(parents=True)
    input_path.write_bytes(b"synthetic audio")
    job = AnalysisWorkerJob(
        job_id=job_id,
        title=title,
        input_path=input_path,
        workspace_root=tmp_path / "workspaces",
        result_path=tmp_path / "result.json",
    )

    with pytest.raises(ValueError):
        job.validate()


def test_queue_worker_cli_supports_once():
    assert parse_consumer_arguments(["--once"]).once is True


def test_dispatch_reconciliation_cli_supports_bounded_once():
    arguments = parse_reconcile_arguments(["--once", "--limit", "12"])
    assert arguments.once is True
    assert arguments.limit == 12
