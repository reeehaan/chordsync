from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any


class CloudJobStatus(str, Enum):
    CREATED = "created"
    AWAITING_UPLOAD = "awaiting_upload"
    # A confirm-upload request holds the job while it checks the uploaded object.
    VALIDATING = "validating"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


_ALLOWED_TRANSITIONS = {
    CloudJobStatus.CREATED: {
        CloudJobStatus.AWAITING_UPLOAD,
        CloudJobStatus.CANCELLED,
        CloudJobStatus.EXPIRED,
    },
    CloudJobStatus.AWAITING_UPLOAD: {
        CloudJobStatus.VALIDATING,
        CloudJobStatus.QUEUED,
        CloudJobStatus.CANCELLED,
        CloudJobStatus.EXPIRED,
    },
    CloudJobStatus.VALIDATING: {
        CloudJobStatus.AWAITING_UPLOAD,
        CloudJobStatus.QUEUED,
        CloudJobStatus.FAILED,
        CloudJobStatus.CANCELLED,
        CloudJobStatus.EXPIRED,
    },
    CloudJobStatus.QUEUED: {
        CloudJobStatus.PROCESSING,
        CloudJobStatus.CANCELLED,
        CloudJobStatus.EXPIRED,
    },
    CloudJobStatus.PROCESSING: {
        CloudJobStatus.COMPLETED,
        CloudJobStatus.FAILED,
        CloudJobStatus.CANCELLED,
    },
    CloudJobStatus.COMPLETED: {CloudJobStatus.EXPIRED},
    CloudJobStatus.FAILED: {CloudJobStatus.QUEUED, CloudJobStatus.EXPIRED},
    CloudJobStatus.CANCELLED: {CloudJobStatus.EXPIRED},
    CloudJobStatus.EXPIRED: set(),
}


@dataclass
class CloudJobRecord:
    job_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    status: CloudJobStatus = CloudJobStatus.CREATED
    stage: str | None = None
    source_object_key: str | None = None
    playback_object_key: str | None = None
    timeline_object_key: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    duration_seconds: float | None = None
    file_type: str | None = None
    owner_id: str | None = None
    last_attempt_at: datetime | None = None
    dispatch_pending: bool = False
    version: int = 0
    # Presigned-upload lifecycle (hosted API); unset for multipart uploads.
    declared_size_bytes: int | None = None
    upload_expires_at: datetime | None = None

    def validate(self) -> None:
        if (
            not self.job_id
            or self.job_id in {".", ".."}
            or Path(self.job_id).name != self.job_id
        ):
            raise ValueError("job_id must be one safe path segment")
        if not self.title.strip():
            raise ValueError("title must not be blank")
        for key in (
            self.source_object_key,
            self.playback_object_key,
            self.timeline_object_key,
        ):
            if key is not None:
                _validate_object_key(key)

    def transition_to(
        self,
        status: CloudJobStatus,
        *,
        stage: str | None = None,
    ) -> None:
        if status not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(
                f"Invalid job transition: {self.status.value} -> {status.value}"
            )
        now = datetime.now(timezone.utc)
        if status is CloudJobStatus.PROCESSING:
            if self.attempt_count >= self.max_attempts:
                raise ValueError("Job attempt limit reached")
            self.attempt_count += 1
            self.last_attempt_at = now
        self.status = status
        self.stage = stage
        self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "job_id": self.job_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status.value,
            "stage": self.stage,
            "source_object_key": self.source_object_key,
            "playback_object_key": self.playback_object_key,
            "timeline_object_key": self.timeline_object_key,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "duration_seconds": self.duration_seconds,
            "file_type": self.file_type,
            "owner_id": self.owner_id,
            "last_attempt_at": (
                self.last_attempt_at.isoformat() if self.last_attempt_at else None
            ),
            "dispatch_pending": self.dispatch_pending,
            "version": self.version,
            "declared_size_bytes": self.declared_size_bytes,
            "upload_expires_at": (
                self.upload_expires_at.isoformat() if self.upload_expires_at else None
            ),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CloudJobRecord":
        record = cls(
            job_id=str(value["job_id"]),
            title=str(value["title"]),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            updated_at=datetime.fromisoformat(str(value["updated_at"])),
            status=CloudJobStatus(str(value["status"])),
            stage=_optional_text(value.get("stage")),
            source_object_key=_optional_text(value.get("source_object_key")),
            playback_object_key=_optional_text(value.get("playback_object_key")),
            timeline_object_key=_optional_text(value.get("timeline_object_key")),
            error_code=_optional_text(value.get("error_code")),
            error_message=_optional_text(value.get("error_message")),
            attempt_count=int(value.get("attempt_count", 0)),
            max_attempts=int(value.get("max_attempts", 3)),
            duration_seconds=(
                float(value["duration_seconds"])
                if value.get("duration_seconds") is not None
                else None
            ),
            file_type=_optional_text(value.get("file_type")),
            owner_id=_optional_text(value.get("owner_id")),
            last_attempt_at=(
                datetime.fromisoformat(str(value["last_attempt_at"]))
                if value.get("last_attempt_at")
                else None
            ),
            dispatch_pending=bool(value.get("dispatch_pending", False)),
            version=int(value.get("version", 0)),
            declared_size_bytes=(
                int(value["declared_size_bytes"])
                if value.get("declared_size_bytes") is not None
                else None
            ),
            upload_expires_at=(
                datetime.fromisoformat(str(value["upload_expires_at"]))
                if value.get("upload_expires_at")
                else None
            ),
        )
        record.validate()
        return record


def new_cloud_job(job_id: str, title: str) -> CloudJobRecord:
    now = datetime.now(timezone.utc)
    return CloudJobRecord(
        job_id=job_id,
        title=title,
        created_at=now,
        updated_at=now,
    )


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _validate_object_key(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or "." in path.parts
        or ".." in path.parts
    ):
        raise ValueError("Artifact references must be safe logical object keys")
