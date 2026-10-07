from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from backend.api.app.services.artifact_storage import ArtifactKey, ArtifactRole


QUEUE_MESSAGE_SCHEMA_VERSION = 1


class QueueMessageError(ValueError):
    pass


@dataclass(frozen=True)
class AnalysisJobDescriptor:
    job_id: str
    source_artifact_key: str
    title: str
    schema_version: int = QUEUE_MESSAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != QUEUE_MESSAGE_SCHEMA_VERSION:
            raise QueueMessageError("Unsupported queue message schema version")
        if (
            not self.job_id
            or self.job_id in {".", ".."}
            or "/" in self.job_id
            or "\\" in self.job_id
        ):
            raise QueueMessageError("Invalid queue job identifier")
        if not self.title.strip():
            raise QueueMessageError("Queue job title must not be blank")
        try:
            ArtifactKey(ArtifactRole.SOURCE_UPLOAD, self.source_artifact_key)
        except ValueError as error:
            raise QueueMessageError("Invalid source artifact reference") from error

    def to_json(self) -> str:
        return json.dumps(
            {
                "job_id": self.job_id,
                "schema_version": self.schema_version,
                "source_artifact_key": self.source_artifact_key,
                "title": self.title,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, value: str) -> "AnalysisJobDescriptor":
        try:
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise TypeError
            if set(payload) != {
                "job_id",
                "schema_version",
                "source_artifact_key",
                "title",
            }:
                raise KeyError
            if (
                not isinstance(payload["schema_version"], int)
                or not isinstance(payload["job_id"], str)
                or not isinstance(payload["source_artifact_key"], str)
                or not isinstance(payload["title"], str)
            ):
                raise TypeError
            return cls(
                schema_version=payload["schema_version"],
                job_id=payload["job_id"],
                source_artifact_key=payload["source_artifact_key"],
                title=payload["title"],
            )
        except QueueMessageError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise QueueMessageError("Malformed queue message") from error


@dataclass(frozen=True)
class QueueDelivery:
    descriptor: AnalysisJobDescriptor
    receipt_handle: str
    receive_count: int = 1


class AnalysisJobQueue(Protocol):
    def enqueue(self, descriptor: AnalysisJobDescriptor) -> None: ...

    def receive(self) -> QueueDelivery | None: ...

    def acknowledge(self, delivery: QueueDelivery) -> None: ...

    def release(
        self,
        delivery: QueueDelivery,
        *,
        visibility_timeout_seconds: int = 0,
    ) -> None: ...

    def extend_visibility(
        self,
        delivery: QueueDelivery,
        *,
        visibility_timeout_seconds: int,
    ) -> None: ...


class InMemoryAnalysisJobQueue:
    def __init__(self) -> None:
        self._available: deque[tuple[AnalysisJobDescriptor, int]] = deque()
        self._inflight: dict[str, tuple[AnalysisJobDescriptor, int]] = {}
        self._next_receipt = 1

    def enqueue(self, descriptor: AnalysisJobDescriptor) -> None:
        self._available.append((descriptor, 0))

    def receive(self) -> QueueDelivery | None:
        if not self._available:
            return None
        descriptor, previous_count = self._available.popleft()
        receipt = f"local-{self._next_receipt}"
        self._next_receipt += 1
        receive_count = previous_count + 1
        self._inflight[receipt] = (descriptor, receive_count)
        return QueueDelivery(descriptor, receipt, receive_count)

    def acknowledge(self, delivery: QueueDelivery) -> None:
        self._inflight.pop(delivery.receipt_handle, None)

    def release(
        self,
        delivery: QueueDelivery,
        *,
        visibility_timeout_seconds: int = 0,
    ) -> None:
        item = self._inflight.pop(delivery.receipt_handle, None)
        if item:
            self._available.append(item)

    def extend_visibility(
        self,
        delivery: QueueDelivery,
        *,
        visibility_timeout_seconds: int,
    ) -> None:
        if delivery.receipt_handle not in self._inflight:
            raise QueueMessageError("Delivery is not in flight")
