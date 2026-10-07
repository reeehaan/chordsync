from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pytest

from backend.api.app.services.artifact_storage import ArtifactKeyFactory
from backend.api.app.services.aws_errors import (
    CloudProviderError,
    CloudProviderErrorKind,
)
from backend.api.app.services.cloud_job import CloudJobRecord, CloudJobStatus
from backend.api.app.services.cloud_job_repository import JobWriteConflictError
from backend.api.app.services.dynamodb_cloud_job_repository import (
    DynamoDbCloudJobRepository,
)
from backend.api.app.services.s3_artifact_storage import S3ArtifactStorage


class FakeAwsError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__("provider details must not escape")
        self.response = {"Error": {"Code": code, "Message": "private details"}}


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_operation: tuple[str, str] | None = None

    def _record(self, operation: str, values: dict) -> None:
        self.calls.append((operation, values))
        if self.fail_operation and self.fail_operation[0] == operation:
            raise FakeAwsError(self.fail_operation[1])

    def put_object(self, **values):
        self._record("put", values)
        self.objects[values["Key"]] = dict(values)
        return {"ETag": '"transport-only"'}

    def get_object(self, **values):
        self._record("get", values)
        if values["Key"] not in self.objects:
            raise FakeAwsError("NoSuchKey")
        return {"Body": BytesIO(self.objects[values["Key"]]["Body"])}

    def head_object(self, **values):
        self._record("head", values)
        if values["Key"] not in self.objects:
            raise FakeAwsError("404")
        stored = self.objects[values["Key"]]
        return {
            "ContentLength": len(stored["Body"]),
            "ContentType": stored["ContentType"],
            "Metadata": stored["Metadata"],
        }

    def delete_object(self, **values):
        self._record("delete", values)
        self.objects.pop(values["Key"], None)
        return {}


def test_s3_storage_put_read_exists_delete_and_private_metadata():
    client = FakeS3Client()
    storage = S3ArtifactStorage(client, "private-bucket")
    key = ArtifactKeyFactory().source("job-one", ".mp3")

    metadata = storage.put_bytes(key, b"audio", content_type="audio/mpeg")

    put = client.calls[0][1]
    assert put["Key"] == "jobs/job-one/source/input.mp3"
    assert put["ContentType"] == "audio/mpeg"
    assert put["Metadata"]["sha256"] == metadata.sha256
    assert put["ServerSideEncryption"] == "AES256"
    assert "ACL" not in put
    assert metadata.size_bytes == 5
    assert storage.exists(key)
    assert storage.read_bytes(key) == b"audio"
    storage.delete(key)
    assert not storage.exists(key)


def test_s3_read_maps_not_found_and_exists_maps_missing():
    client = FakeS3Client()
    storage = S3ArtifactStorage(client, "private-bucket")
    key = ArtifactKeyFactory().timeline("job-one")

    assert storage.exists(key) is False
    with pytest.raises(CloudProviderError) as captured:
        storage.read_bytes(key)
    assert captured.value.kind is CloudProviderErrorKind.NOT_FOUND
    assert "private" not in str(captured.value)


def test_s3_translates_provider_failure_without_leaking_response():
    client = FakeS3Client()
    client.fail_operation = ("put", "ServiceUnavailable")
    storage = S3ArtifactStorage(client, "private-bucket")

    with pytest.raises(CloudProviderError) as captured:
        storage.put_bytes(
            ArtifactKeyFactory().timeline("job-one"),
            b"{}",
            content_type="application/json",
        )
    assert captured.value.kind is CloudProviderErrorKind.TEMPORARY_UNAVAILABLE
    assert "private-bucket" not in str(captured.value)


class FakeDynamoTable:
    def __init__(self) -> None:
        self.items: dict[str, dict] = {}
        self.last_put: dict | None = None
        self.fail_code: str | None = None

    def put_item(self, **values):
        self.last_put = values
        if self.fail_code:
            raise FakeAwsError(self.fail_code)
        item = values["Item"]
        existing = self.items.get(item["PK"])
        condition = values["ConditionExpression"]
        if condition == "attribute_not_exists(PK)" and existing:
            raise FakeAwsError("ConditionalCheckFailedException")
        if condition != "attribute_not_exists(PK)":
            expected = values["ExpressionAttributeValues"]
            if (
                not existing
                or existing["version"] != expected[":version"]
                or existing["status"] != expected[":expected_status"]
            ):
                raise FakeAwsError("ConditionalCheckFailedException")
        self.items[item["PK"]] = dict(item)
        return {}

    def get_item(self, **values):
        if self.fail_code:
            raise FakeAwsError(self.fail_code)
        item = self.items.get(values["Key"]["PK"])
        return {"Item": dict(item)} if item else {}

    def scan(self, **values):
        if self.fail_code:
            raise FakeAwsError(self.fail_code)
        queued = values["ExpressionAttributeValues"][":queued"]
        pending = values["ExpressionAttributeValues"][":pending"]
        items = [
            dict(item)
            for item in self.items.values()
            if item["status"] == queued
            and item.get("dispatch_pending", False) is pending
        ]
        return {"Items": items[: values["Limit"]]}


def _processing_job() -> CloudJobRecord:
    now = datetime.now(timezone.utc)
    return CloudJobRecord(
        job_id="job-one",
        title="Tagged song",
        created_at=now,
        updated_at=now,
        status=CloudJobStatus.PROCESSING,
        stage="whisperx",
        source_object_key="jobs/job-one/source/input.mp3",
        playback_object_key="jobs/job-one/playback/audio.mp3",
        timeline_object_key="jobs/job-one/results/timeline.json",
        attempt_count=1,
        duration_seconds=123.4,
        file_type=".mp3",
        owner_id=None,
        last_attempt_at=now,
    )


def test_dynamodb_add_get_and_full_serialization_round_trip():
    table = FakeDynamoTable()
    repository = DynamoDbCloudJobRepository(table)
    job = _processing_job()

    repository.add(job)
    restored = repository.get(job.job_id)

    assert table.last_put["ConditionExpression"] == "attribute_not_exists(PK)"
    assert table.last_put["Item"]["PK"] == "JOB#job-one"
    assert restored == job
    assert restored.owner_id is None
    assert restored.attempt_count == 1
    assert restored.last_attempt_at is not None
    assert restored.timeline_object_key == job.timeline_object_key


def test_dynamodb_duplicate_add_is_conditional_conflict():
    repository = DynamoDbCloudJobRepository(FakeDynamoTable())
    job = _processing_job()
    repository.add(job)

    with pytest.raises(JobWriteConflictError, match="already exists"):
        repository.add(job)


def test_dynamodb_get_missing_returns_none():
    assert DynamoDbCloudJobRepository(FakeDynamoTable()).get("missing") is None


def test_dynamodb_save_checks_version_and_expected_state():
    table = FakeDynamoTable()
    repository = DynamoDbCloudJobRepository(table)
    job = _processing_job()
    repository.add(job)
    job.transition_to(CloudJobStatus.COMPLETED, stage="published")

    repository.save(job, expected_status=CloudJobStatus.PROCESSING)

    assert job.version == 1
    assert repository.get(job.job_id).status is CloudJobStatus.COMPLETED
    values = table.last_put["ExpressionAttributeValues"]
    assert values == {":version": 0, ":expected_status": "processing"}


@pytest.mark.parametrize(
    ("mutate", "expected_status"),
    [
        (lambda job: setattr(job, "version", 8), CloudJobStatus.PROCESSING),
        (lambda job: None, CloudJobStatus.QUEUED),
    ],
)
def test_dynamodb_save_rejects_stale_version_or_wrong_expected_state(
    mutate, expected_status
):
    table = FakeDynamoTable()
    repository = DynamoDbCloudJobRepository(table)
    job = _processing_job()
    repository.add(job)
    mutate(job)

    with pytest.raises(JobWriteConflictError, match="changed concurrently"):
        repository.save(job, expected_status=expected_status)


def test_dynamodb_terminal_state_is_protected_by_conditional_state():
    table = FakeDynamoTable()
    repository = DynamoDbCloudJobRepository(table)
    stored = _processing_job()
    stored.transition_to(CloudJobStatus.COMPLETED)
    repository.add(stored)
    stale_worker = _processing_job()

    with pytest.raises(JobWriteConflictError):
        repository.save(
            stale_worker,
            expected_status=CloudJobStatus.PROCESSING,
        )


def test_dynamodb_translates_nonconditional_provider_failure():
    table = FakeDynamoTable()
    table.fail_code = "ProvisionedThroughputExceededException"

    with pytest.raises(CloudProviderError) as captured:
        DynamoDbCloudJobRepository(table).get("job-one")
    assert captured.value.kind is CloudProviderErrorKind.TEMPORARY_UNAVAILABLE
