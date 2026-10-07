from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from backend.api.app.services.analysis_worker_consumer import AnalysisWorkerConsumer
from backend.api.app.services.artifact_cleanup import ArtifactCleanup
from backend.api.app.services.cloud_runtime import (
    CloudRuntimeConfig,
    compose_cloud_runtime,
)
from backend.api.app.services.real_analysis_processor import RealAnalysisProcessor
from backend.api.app.services.result_publication import AnalysisResultPublisher
from backend.api.app.services.source_materialization import SourceMaterializer


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consume ChordSync analysis queue deliveries"
    )
    parser.add_argument("--once", action="store_true", required=True)
    return parser.parse_args(argv)


def build_consumer() -> AnalysisWorkerConsumer:
    config = CloudRuntimeConfig.from_env()
    runtime = compose_cloud_runtime(config)
    if runtime.queue is None:
        raise RuntimeError("Queue consumer requires queue dispatch mode")
    workspace_root = Path(
        os.environ.get("CHORDSYNC_WORKSPACE_ROOT", "/tmp/chordsync-worker")
    ) / "materialized"
    return AnalysisWorkerConsumer(
        runtime.queue,
        runtime.repository,
        runtime.artifact_storage,
        SourceMaterializer(runtime.artifact_storage, workspace_root),
        RealAnalysisProcessor(),
        AnalysisResultPublisher(runtime.repository, runtime.artifact_storage),
        ArtifactCleanup(workspace_root, runtime.artifact_storage),
    )


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parse_arguments(argv)
    build_consumer().process_once()


if __name__ == "__main__":
    main()
