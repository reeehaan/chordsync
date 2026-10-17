from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class AnalysisJobStatus(str, Enum):
    # Hosted presigned-upload lifecycle only; local jobs start at QUEUED.
    AWAITING_UPLOAD = "awaiting_upload"
    VALIDATING = "validating"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    # Hosted only: the owner stopped the job before it finished.
    CANCELLED = "cancelled"


class AnalysisJobCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def title_must_contain_text(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("title must contain text")
        return title


class AnalysisJobError(BaseModel):
    code: str
    message: str


class AnalysisJobErrorResponse(BaseModel):
    error: AnalysisJobError


class AnalysisJobResponse(BaseModel):
    job_id: str
    status: AnalysisJobStatus
    created_at: datetime
    updated_at: datetime
    error: AnalysisJobError | None = None
    result_available: bool


class UploadInitiationRequest(BaseModel):
    """Hosted create: metadata only. Nothing here is trusted as validation."""

    title: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=255)
    declared_size_bytes: int
    content_type: str | None = Field(default=None, max_length=100)

    @field_validator("title")
    @classmethod
    def title_must_contain_text(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("title must contain text")
        return title


class UploadInitiationResponse(BaseModel):
    job_id: str
    status: AnalysisJobStatus
    upload_url: str
    upload_method: str
    required_headers: dict[str, str]
    expires_at: datetime
    source_object_key: str
