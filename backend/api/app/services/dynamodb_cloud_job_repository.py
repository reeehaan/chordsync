from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from backend.api.app.services.aws_errors import (
    provider_error_code,
    translate_provider_error,
)
from backend.api.app.services.cloud_job import CloudJobRecord, CloudJobStatus
from backend.api.app.services.cloud_job_repository import JobWriteConflictError


logger = logging.getLogger(__name__)

# One Scan page reads up to 1 MB. A library request must not read an unbounded
# table: past this many pages the list is cut short (and the cut is logged)
# instead of running into the Lambda timeout and failing for every tester.
MAX_LIBRARY_SCAN_PAGES = 20


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

    def list_completed(self, *, limit: int = 200) -> list[CloudJobRecord]:
        # A scan: the table holds a few hundred jobs at most. Move this to an
        # index on status if it ever grows well beyond that.
        jobs: list[CloudJobRecord] = []
        start_key = None
        pages = 0
        while True:
            request: dict[str, Any] = {
                "FilterExpression": "#status = :completed",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":completed": CloudJobStatus.COMPLETED.value,
                },
            }
            if start_key:
                request["ExclusiveStartKey"] = start_key
            try:
                response = self._table.scan(**request)
            except Exception as error:
                raise translate_provider_error(error) from error
            jobs.extend(_from_item(item) for item in response.get("Items", []))
            pages += 1
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
            if pages >= MAX_LIBRARY_SCAN_PAGES:
                logger.warning(
                    "library scan stopped after %d pages; the list may be incomplete",
                    pages,
                )
                break
        jobs.sort(key=lambda job: job.created_at, reverse=True)
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
