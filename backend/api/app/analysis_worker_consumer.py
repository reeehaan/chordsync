from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from analysis.preprocessing.playback_encoder import prepare_playback
from backend.api.app.services.analysis_worker_consumer import (
    AnalysisWorkerConsumer,
    WorkerOutcome,
)
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


@dataclass(frozen=True)
class WarmWorkerSettings:
    """How long the worker waits for work before it exits.

    Both zero (the default) is the original behaviour: one pass, then exit.
    initial_wait: after starting, wait this long for the first message (the worker
        may be started while the audio is still uploading).
    linger: after finishing a song, stay this long for the next one, so the next
        song skips the cold start.
    """

    initial_wait_seconds: int = 0
    linger_seconds: int = 0
    max_lifetime_seconds: int = 7200
    poll_pause_seconds: float = 1.0

    @property
    def enabled(self) -> bool:
        return self.initial_wait_seconds > 0 or self.linger_seconds > 0

    @classmethod
    def from_env(cls, environment: dict[str, str] | os._Environ) -> "WarmWorkerSettings":
        def number(name: str, default: int, low: int, high: int) -> int:
            raw = str(environment.get(name, "")).strip()
            if not raw:
                return default
            try:
                value = int(raw)
            except ValueError:
                return default
            return value if low <= value <= high else default

        return cls(
            initial_wait_seconds=number("CHORDSYNC_WORKER_INITIAL_WAIT_SECONDS", 0, 0, 900),
            linger_seconds=number("CHORDSYNC_WORKER_LINGER_SECONDS", 0, 0, 3600),
            max_lifetime_seconds=number(
                "CHORDSYNC_WORKER_MAX_LIFETIME_SECONDS", 7200, 600, 14400
            ),
        )


def run_worker(
    consumer: AnalysisWorkerConsumer,
    settings: WarmWorkerSettings,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Process songs until there is nothing to do for long enough. Returns how
    many deliveries were handled."""
    if not settings.enabled:
        consumer.process_once()
        return 0
    started = clock()
    deadline = started + settings.initial_wait_seconds
    handled = 0
    while True:
        outcome = consumer.process_once()
        now = clock()
        if outcome is WorkerOutcome.EMPTY:
            if now >= deadline:
                break
            sleep(settings.poll_pause_seconds)
        else:
            handled += 1
            if settings.linger_seconds <= 0:
                break  # a warm start only; exit after the song, as before
            deadline = now + settings.linger_seconds
            logger.info("worker staying warm for up to %ds", settings.linger_seconds)
        if clock() - started >= settings.max_lifetime_seconds:
            logger.info("worker reached its maximum lifetime; exiting")
            break
    return handled


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
    processor = RealAnalysisProcessor(model_installer=on_demand_model_installer(config))
    return AnalysisWorkerConsumer(
        runtime.queue,
        runtime.repository,
        runtime.artifact_storage,
        SourceMaterializer(runtime.artifact_storage, workspace_root),
        processor,
        AnalysisResultPublisher(runtime.repository, runtime.artifact_storage),
        # The processor works in <processor workspace root>/<job_id>; remove that too, or a
        # warm worker keeps every earlier job's derived audio and its retry of the
        # same job fails because the folder already exists.
        ArtifactCleanup(
            workspace_root,
            runtime.artifact_storage,
            extra_workspace_roots=(processor.workspace_root,),
        ),
        playback_encoder=prepare_playback,
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
    run_worker(consumer_factory(config), WarmWorkerSettings.from_env(os.environ))


if __name__ == "__main__":
    main()
