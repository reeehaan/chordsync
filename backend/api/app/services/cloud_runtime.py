from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from backend.api.app.services.artifact_storage import (
    ArtifactStorage,
    LocalArtifactStorage,
)
from backend.api.app.services.analysis_job_dispatcher import (
    AnalysisJobDispatcher,
    LocalInProcessDispatcher,
    QueueBackedDispatcher,
)
from backend.api.app.services.analysis_job_executor import AnalysisJobExecutor
from backend.api.app.services.analysis_job_queue import (
    AnalysisJobQueue,
    InMemoryAnalysisJobQueue,
)
from backend.api.app.services.aws_errors import (
    CloudProviderError,
    CloudProviderErrorKind,
)
from backend.api.app.services.cloud_job_repository import (
    CloudJobRepository,
    SqliteCloudJobRepository,
)
from backend.api.app.services.dynamodb_cloud_job_repository import (
    DynamoDbCloudJobRepository,
)
from backend.api.app.services.s3_artifact_storage import S3ArtifactStorage
from backend.api.app.services.source_upload_store import (
    S3SourceUploadStore,
    SourceUploadStore,
)
from backend.api.app.services.worker_dispatch_trigger import (
    LambdaWorkerDispatchTrigger,
    WorkerDispatchTrigger,
)
from backend.api.app.services.sqs_analysis_job_queue import SqsAnalysisJobQueue


class RuntimeMode(str, Enum):
    LOCAL = "local"
    AWS = "aws"


class DispatchMode(str, Enum):
    IN_PROCESS = "in_process"
    QUEUE = "queue"


@dataclass(frozen=True)
class CloudRuntimeConfig:
    mode: RuntimeMode
    storage_root: Path
    aws_region: str | None = None
    s3_bucket: str | None = None
    dynamodb_job_table: str | None = None
    dispatch_mode: DispatchMode = DispatchMode.IN_PROCESS
    sqs_analysis_queue_url: str | None = None
    # Optional: asynchronously nudge the worker dispatcher after a job is queued.
    worker_dispatcher_function: str | None = None

    @classmethod
    def from_env(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "CloudRuntimeConfig":
        values = os.environ if environment is None else environment
        raw_mode = values.get("CHORDSYNC_RUNTIME_MODE", "local").strip().casefold()
        try:
            mode = RuntimeMode(raw_mode)
        except ValueError as error:
            raise CloudProviderError(
                CloudProviderErrorKind.CONFIGURATION,
                "CHORDSYNC_RUNTIME_MODE must be 'local' or 'aws'",
            ) from error
        raw_dispatch_mode = values.get("CHORDSYNC_DISPATCH_MODE")
        if raw_dispatch_mode is None:
            dispatch_mode = (
                DispatchMode.QUEUE
                if mode is RuntimeMode.AWS
                else DispatchMode.IN_PROCESS
            )
        else:
            try:
                dispatch_mode = DispatchMode(raw_dispatch_mode.strip().casefold())
            except ValueError as error:
                raise CloudProviderError(
                    CloudProviderErrorKind.CONFIGURATION,
                    "CHORDSYNC_DISPATCH_MODE must be 'in_process' or 'queue'",
                ) from error
        config = cls(
            mode=mode,
            storage_root=Path(values.get("STORAGE_PATH", "./storage")),
            aws_region=_clean(values.get("AWS_REGION")),
            s3_bucket=_clean(values.get("CHORDSYNC_S3_BUCKET")),
            dynamodb_job_table=_clean(values.get("CHORDSYNC_DYNAMODB_JOB_TABLE")),
            dispatch_mode=dispatch_mode,
            sqs_analysis_queue_url=_clean(
                values.get("CHORDSYNC_SQS_ANALYSIS_QUEUE_URL")
            ),
            worker_dispatcher_function=_clean(
                values.get("CHORDSYNC_WORKER_DISPATCHER_FUNCTION")
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.mode is RuntimeMode.AWS:
            missing = [
                name
                for name, value in (
                    ("AWS_REGION", self.aws_region),
                    ("CHORDSYNC_S3_BUCKET", self.s3_bucket),
                    ("CHORDSYNC_DYNAMODB_JOB_TABLE", self.dynamodb_job_table),
                )
                if not value
            ]
            if missing:
                raise CloudProviderError(
                    CloudProviderErrorKind.CONFIGURATION,
                    "Missing AWS runtime configuration: " + ", ".join(missing),
                )
        if (
            self.mode is RuntimeMode.AWS
            and self.dispatch_mode is DispatchMode.QUEUE
            and not self.sqs_analysis_queue_url
        ):
            raise CloudProviderError(
                CloudProviderErrorKind.CONFIGURATION,
                "Missing queue runtime configuration: "
                "CHORDSYNC_SQS_ANALYSIS_QUEUE_URL",
            )
        if (
            self.mode is RuntimeMode.AWS
            and self.dispatch_mode is DispatchMode.IN_PROCESS
        ):
            raise CloudProviderError(
                CloudProviderErrorKind.CONFIGURATION,
                "AWS runtime mode requires queue dispatch",
            )


@dataclass(frozen=True)
class CloudRuntime:
    repository: CloudJobRepository
    artifact_storage: ArtifactStorage
    queue: AnalysisJobQueue | None = None
    # Presigned source uploads (AWS runtime only).
    source_uploads: SourceUploadStore | None = None
    worker_trigger: WorkerDispatchTrigger | None = None


def compose_cloud_runtime(
    config: CloudRuntimeConfig,
    *,
    s3_client: Any | None = None,
    dynamodb_resource: Any | None = None,
    sqs_client: Any | None = None,
    lambda_client: Any | None = None,
) -> CloudRuntime:
    config.validate()
    if config.mode is RuntimeMode.LOCAL:
        root = config.storage_root / "cloud_local"
        return CloudRuntime(
            repository=SqliteCloudJobRepository(root / "jobs.sqlite3"),
            artifact_storage=LocalArtifactStorage(root / "artifacts"),
            queue=(
                InMemoryAnalysisJobQueue()
                if config.dispatch_mode is DispatchMode.QUEUE
                else None
            ),
        )

    if s3_client is None or dynamodb_resource is None or sqs_client is None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as error:
            raise CloudProviderError(
                CloudProviderErrorKind.CONFIGURATION,
                "boto3 is required for AWS runtime mode",
            ) from error
        session = boto3.session.Session(region_name=config.aws_region)
        # Signature Version 4 with the regional endpoint: presigned URLs must be
        # SigV4 so the Content-Length and encryption headers are signed.
        s3_client = s3_client or session.client(
            "s3",
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
        dynamodb_resource = dynamodb_resource or session.resource("dynamodb")
        sqs_client = sqs_client or session.client("sqs")

    # validate() guarantees these in AWS mode; the check narrows the types.
    if (
        config.s3_bucket is None
        or config.dynamodb_job_table is None
        or config.sqs_analysis_queue_url is None
    ):
        raise CloudProviderError(
            CloudProviderErrorKind.CONFIGURATION,
            "AWS runtime configuration is incomplete",
        )
    worker_trigger: WorkerDispatchTrigger | None = None
    if config.worker_dispatcher_function:
        if lambda_client is None:
            import boto3

            lambda_client = boto3.session.Session(region_name=config.aws_region).client(
                "lambda"
            )
        worker_trigger = LambdaWorkerDispatchTrigger(
            lambda_client, config.worker_dispatcher_function
        )
    return CloudRuntime(
        repository=DynamoDbCloudJobRepository(
            dynamodb_resource.Table(config.dynamodb_job_table)
        ),
        artifact_storage=S3ArtifactStorage(s3_client, config.s3_bucket),
        queue=SqsAnalysisJobQueue(sqs_client, config.sqs_analysis_queue_url),
        source_uploads=S3SourceUploadStore(s3_client, config.s3_bucket),
        worker_trigger=worker_trigger,
    )


def compose_analysis_dispatcher(
    config: CloudRuntimeConfig,
    runtime: CloudRuntime,
    *,
    local_executor: AnalysisJobExecutor | None = None,
) -> AnalysisJobDispatcher:
    if config.dispatch_mode is DispatchMode.IN_PROCESS:
        if local_executor is None:
            raise CloudProviderError(
                CloudProviderErrorKind.CONFIGURATION,
                "Local in-process dispatch requires an analysis executor",
            )
        return LocalInProcessDispatcher(local_executor)
    if runtime.queue is None:
        raise CloudProviderError(
            CloudProviderErrorKind.CONFIGURATION,
            "Queue dispatch requires a configured analysis queue",
        )
    return QueueBackedDispatcher(
        runtime.repository,
        runtime.artifact_storage,
        runtime.queue,
        runtime.worker_trigger,
    )


def _clean(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None
