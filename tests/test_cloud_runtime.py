from __future__ import annotations

import pytest

from backend.api.app.services.artifact_storage import LocalArtifactStorage
from backend.api.app.services.aws_errors import CloudProviderError
from backend.api.app.services.cloud_job import CloudJobStatus, new_cloud_job
from backend.api.app.services.cloud_job_repository import SqliteCloudJobRepository
from backend.api.app.services.cloud_runtime import (
    CloudRuntimeConfig,
    DispatchMode,
    RuntimeMode,
    compose_analysis_dispatcher,
    compose_cloud_runtime,
)
from backend.api.app.services.dynamodb_cloud_job_repository import (
    DynamoDbCloudJobRepository,
)
from backend.api.app.services.s3_artifact_storage import S3ArtifactStorage
from backend.api.app.services.result_publication import (
    AnalysisResultPublisher,
    PublicationRequest,
)
from tests.test_aws_cloud_adapters import FakeDynamoTable, FakeS3Client
from tests.test_analysis_job_queue import FakeSqsClient


class FakeDynamoResource:
    def __init__(self) -> None:
        self.requested_tables: list[str] = []
        self.table = FakeDynamoTable()

    def Table(self, name: str):
        self.requested_tables.append(name)
        return self.table


def test_config_defaults_to_local(tmp_path):
    config = CloudRuntimeConfig.from_env({"STORAGE_PATH": str(tmp_path)})

    assert config.mode is RuntimeMode.LOCAL
    assert config.dispatch_mode is DispatchMode.IN_PROCESS


@pytest.mark.parametrize("mode", ["invalid", ""])
def test_config_rejects_invalid_runtime_mode(mode):
    with pytest.raises(CloudProviderError, match="local.*aws"):
        CloudRuntimeConfig.from_env({"CHORDSYNC_RUNTIME_MODE": mode})


def test_aws_config_requires_region_bucket_and_table():
    with pytest.raises(CloudProviderError) as captured:
        CloudRuntimeConfig.from_env({"CHORDSYNC_RUNTIME_MODE": "aws"})

    message = str(captured.value)
    assert "AWS_REGION" in message
    assert "CHORDSYNC_S3_BUCKET" in message
    assert "CHORDSYNC_DYNAMODB_JOB_TABLE" in message


def test_local_composition_selects_durable_adapters_and_survives_restart(tmp_path):
    config = CloudRuntimeConfig.from_env(
        {"CHORDSYNC_RUNTIME_MODE": "local", "STORAGE_PATH": str(tmp_path)}
    )
    first = compose_cloud_runtime(config)

    assert isinstance(first.repository, SqliteCloudJobRepository)
    assert isinstance(first.artifact_storage, LocalArtifactStorage)
    job = new_cloud_job("job-one", "Song")
    first.repository.add(job)

    second = compose_cloud_runtime(config)
    assert second.repository.get(job.job_id) == job


def test_local_composition_publishes_artifacts(tmp_path):
    config = CloudRuntimeConfig.from_env(
        {"CHORDSYNC_RUNTIME_MODE": "local", "STORAGE_PATH": str(tmp_path)}
    )
    runtime = compose_cloud_runtime(config)
    job = new_cloud_job("job-one", "Song")
    job.transition_to(CloudJobStatus.AWAITING_UPLOAD)
    job.transition_to(CloudJobStatus.QUEUED)
    job.transition_to(CloudJobStatus.PROCESSING)
    runtime.repository.add(job)

    completed = AnalysisResultPublisher(
        runtime.repository, runtime.artifact_storage
    ).publish(
        PublicationRequest(
            job_id=job.job_id,
            playback_bytes=b"audio",
            playback_extension=".mp3",
            playback_content_type="audio/mpeg",
            timeline_bytes=b"{}",
        )
    )

    assert completed.status is CloudJobStatus.COMPLETED
    assert completed.playback_object_key
    assert completed.timeline_object_key


def test_aws_composition_uses_injected_clients_without_network():
    config = CloudRuntimeConfig.from_env(
        {
            "CHORDSYNC_RUNTIME_MODE": "aws",
            "AWS_REGION": "ap-south-1",
            "CHORDSYNC_S3_BUCKET": "private-bucket",
            "CHORDSYNC_DYNAMODB_JOB_TABLE": "jobs-table",
            "CHORDSYNC_SQS_ANALYSIS_QUEUE_URL": "https://sqs.invalid/queue",
        }
    )
    dynamodb = FakeDynamoResource()

    runtime = compose_cloud_runtime(
        config,
        s3_client=FakeS3Client(),
        dynamodb_resource=dynamodb,
        sqs_client=FakeSqsClient(),
    )

    assert isinstance(runtime.repository, DynamoDbCloudJobRepository)
    assert isinstance(runtime.artifact_storage, S3ArtifactStorage)
    assert runtime.queue is not None
    assert dynamodb.requested_tables == ["jobs-table"]


def test_aws_queue_mode_requires_sqs_url():
    with pytest.raises(CloudProviderError, match="CHORDSYNC_SQS_ANALYSIS_QUEUE_URL"):
        CloudRuntimeConfig.from_env(
            {
                "CHORDSYNC_RUNTIME_MODE": "aws",
                "AWS_REGION": "ap-south-1",
                "CHORDSYNC_S3_BUCKET": "private-bucket",
                "CHORDSYNC_DYNAMODB_JOB_TABLE": "jobs-table",
            }
        )


def test_local_dispatcher_composition_requires_and_uses_executor(tmp_path):
    class Executor:
        def __init__(self):
            self.jobs = []

        def submit(self, job_id):
            self.jobs.append(job_id)

    config = CloudRuntimeConfig.from_env({"STORAGE_PATH": str(tmp_path)})
    runtime = compose_cloud_runtime(config)
    executor = Executor()
    dispatcher = compose_analysis_dispatcher(
        config, runtime, local_executor=executor
    )

    dispatcher.dispatch("job-one")
    assert executor.jobs == ["job-one"]


def test_local_queue_dispatch_mode_uses_in_memory_queue(tmp_path):
    config = CloudRuntimeConfig.from_env(
        {
            "STORAGE_PATH": str(tmp_path),
            "CHORDSYNC_DISPATCH_MODE": "queue",
        }
    )
    runtime = compose_cloud_runtime(config)

    assert runtime.queue is not None
