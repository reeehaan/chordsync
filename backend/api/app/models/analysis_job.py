from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class AnalysisJobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


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
