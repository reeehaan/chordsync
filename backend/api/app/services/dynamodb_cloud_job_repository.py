from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.api.app.services.aws_errors import (
    provider_error_code,
    translate_provider_error,
)
from backend.api.app.services.cloud_job import CloudJobRecord, CloudJobStatus
from backend.api.app.services.cloud_job_repository import JobWriteConflictError


class DynamoDbCloudJobRepository:
    def __init__(self, table: Any) -> None:
        self._table = table

    def add(self, job: CloudJobRecord) -> None:
        try:
            self._table.put_item(
                Item=_to_item(job),
                ConditionExpression="attribute_not_exists(PK)",
            )
        except Exception as error:
            self._raise_write_error(error, "Job already exists")

    def get(self, job_id: str) -> CloudJobRecord | None:
        try:
            response = self._table.get_item(
                Key={"PK": _partition_key(job_id)},
                ConsistentRead=True,
            )
        except Exception as error:
            raise translate_provider_error(error) from error
        item = response.get("Item")
        return _from_item(item) if item else None

    def pending_dispatch(self, *, limit: int = 100) -> list[CloudJobRecord]:
        jobs: list[CloudJobRecord] = []
        start_key = None
        while len(jobs) < limit:
            request = {
                "FilterExpression": (
                    "#status = :queued AND dispatch_pending = :pending"
                ),
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":queued": CloudJobStatus.QUEUED.value,
                    ":pending": True,
                },
                "Limit": limit - len(jobs),
            }
            if start_key:
                request["ExclusiveStartKey"] = start_key
            try:
                response = self._table.scan(**request)
            except Exception as error:
                raise translate_provider_error(error) from error
            jobs.extend(_from_item(item) for item in response.get("Items", []))
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return jobs[:limit]

    def save(
        self,
        job: CloudJobRecord,
        *,
        expected_status: CloudJobStatus,
    ) -> None:
        next_version = job.version + 1
        item = _to_item(job, version=next_version)
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression=(
                    "#version = :version AND #status = :expected_status"
                ),
                ExpressionAttributeNames={
                    "#version": "version",
                    "#status": "status",
                },
                ExpressionAttributeValues={
                    ":version": job.version,
                    ":expected_status": expected_status.value,
                },
            )
        except Exception as error:
            self._raise_write_error(error, "Job state changed concurrently")
        job.version = next_version

    @staticmethod
    def _raise_write_error(error: BaseException, message: str) -> None:
        if provider_error_code(error) == "ConditionalCheckFailedException":
            raise JobWriteConflictError(message) from error
        raise translate_provider_error(error) from error


def _partition_key(job_id: str) -> str:
    return f"JOB#{job_id}"


def _to_item(job: CloudJobRecord, *, version: int | None = None) -> dict[str, Any]:
    payload = job.to_dict()
    payload["version"] = job.version if version is None else version
    if payload["duration_seconds"] is not None:
        payload["duration_seconds"] = Decimal(str(payload["duration_seconds"]))
    return {"PK": _partition_key(job.job_id), **payload}


def _from_item(item: dict[str, Any]) -> CloudJobRecord:
    payload = dict(item)
    payload.pop("PK", None)
    return CloudJobRecord.from_dict(payload)
