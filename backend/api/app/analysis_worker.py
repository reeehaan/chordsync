import argparse
import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from backend.api.app.services.analysis_processor import AnalysisProcessor
from backend.api.app.services.real_analysis_processor import (
    AnalysisPipelineConfig,
    RealAnalysisProcessor,
)


@dataclass(frozen=True)
class AnalysisWorkerJob:
    job_id: str
    title: str
    input_path: Path
    workspace_root: Path
    result_path: Path

    def validate(self) -> None:
        if (
            not self.job_id
            or self.job_id in {".", ".."}
            or Path(self.job_id).name != self.job_id
        ):
            raise ValueError("job_id must be one safe path segment")
        if self.input_path.parent.name != self.job_id:
            raise ValueError("input path must be inside its job-id directory")
        if not self.input_path.is_file():
            raise ValueError("input audio does not exist")
        if not self.title.strip():
            raise ValueError("title must not be blank")


ProcessorFactory = Callable[[AnalysisPipelineConfig], AnalysisProcessor]


def execute_worker_job(
    job: AnalysisWorkerJob,
    *,
    processor_factory: ProcessorFactory = RealAnalysisProcessor,
) -> None:
    job.validate()
    config = replace(
        AnalysisPipelineConfig.local(),
        workspace_root=job.workspace_root,
    )
    timeline = processor_factory(config).process(job.input_path)
    job.result_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_result = job.result_path.with_suffix(f"{job.result_path.suffix}.part")
    temporary_result.write_text(
        json.dumps(timeline.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    temporary_result.replace(job.result_path)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one ChordSync analysis job")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    arguments = parse_arguments(argv)
    execute_worker_job(
        AnalysisWorkerJob(
            job_id=arguments.job_id,
            title=arguments.title,
            input_path=arguments.input,
            workspace_root=arguments.workspace_root,
            result_path=arguments.result,
        )
    )


if __name__ == "__main__":
    main()
