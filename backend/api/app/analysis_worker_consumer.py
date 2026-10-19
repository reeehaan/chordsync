from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any, Callable

from backend.api.app.services.analysis_worker_consumer import AnalysisWorkerConsumer
from backend.api.app.services.artifact_cleanup import ArtifactCleanup
from backend.api.app.services.cloud_runtime import (
    CloudRuntimeConfig,
    RuntimeMode,
    compose_cloud_runtime,
)
from backend.api.app.services.model_bootstrap import (
    AssetRole,
    ModelBootstrapError,
    bootstrap_from_environment,
    build_bootstrap,
)
from backend.api.app.services.real_analysis_processor import RealAnalysisProcessor
from backend.api.app.services.result_publication import AnalysisResultPublisher
from backend.api.app.services.source_materialization import SourceMaterializer


logger = logging.getLogger(__name__)

# Distinct from Python's generic 1 so a failed bootstrap is visible in ECS.
BOOTSTRAP_FAILED_EXIT_CODE = 3


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Consume ChordSync analysis queue deliveries. In AWS mode, model "
            "assets are installed and verified from S3 before the queue is polled."
        )
    )
    parser.add_argument("--once", action="store_true", required=True)
    return parser.parse_args(argv)


def build_consumer(config: CloudRuntimeConfig) -> AnalysisWorkerConsumer:
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
        RealAnalysisProcessor(model_installer=on_demand_model_installer(config)),
        AnalysisResultPublisher(runtime.repository, runtime.artifact_storage),
        ArtifactCleanup(workspace_root, runtime.artifact_storage),
    )


def on_demand_model_installer(
    config: CloudRuntimeConfig,
    s3_client: Any | None = None,
) -> Callable[[AssetRole], None] | None:
    """Fetch an on-demand model asset (e.g. the aligner) the first time it is needed."""
    if config.mode is not RuntimeMode.AWS:
        return None

    def install(role: AssetRole) -> None:
        client = s3_client
        if client is None:
            import boto3

            client = boto3.session.Session(region_name=config.aws_region).client("s3")
        build_bootstrap(
            os.environ, bucket=config.s3_bucket or "", s3_client=client
        ).install_role(role)

    return install


def bootstrap_models(config: CloudRuntimeConfig, s3_client: Any | None = None) -> None:
    """Install verified model assets; raises SystemExit so the queue is never polled."""
    if config.mode is not RuntimeMode.AWS:
        logger.info("model bootstrap skipped in %s mode", config.mode.value)
        return
    try:
        if s3_client is None:
            import boto3

            s3_client = boto3.session.Session(region_name=config.aws_region).client("s3")
        bootstrap_from_environment(
            os.environ,
            bucket=config.s3_bucket or "",
            s3_client=s3_client,
        )
    except ModelBootstrapError as error:
        logger.error("model bootstrap failed: %s; queue not polled", error)
        raise SystemExit(BOOTSTRAP_FAILED_EXIT_CODE) from error
    except Exception as error:
        logger.error(
            "model bootstrap failed (%s); queue not polled", type(error).__name__
        )
        raise SystemExit(BOOTSTRAP_FAILED_EXIT_CODE) from error


def main(
    argv: list[str] | None = None,
    *,
    consumer_factory: Callable[[CloudRuntimeConfig], AnalysisWorkerConsumer] = build_consumer,
    s3_client: Any | None = None,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parse_arguments(argv)
    config = CloudRuntimeConfig.from_env()
    bootstrap_models(config, s3_client)
    consumer_factory(config).process_once()


if __name__ == "__main__":
    main()
