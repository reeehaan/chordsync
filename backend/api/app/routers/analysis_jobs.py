from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from fastapi.responses import JSONResponse

from analysis.fusion.models import SharedTimeline
from backend.api.app.models.analysis_job import (
    AnalysisJobCreateRequest,
    AnalysisJobError,
    AnalysisJobErrorResponse,
    AnalysisJobResponse,
    AnalysisJobStatus,
)
from backend.api.app.services.analysis_jobs import (
    AnalysisJobService,
    InMemoryAnalysisJobRepository,
)
from backend.api.app.services.analysis_job_executor import (
    AnalysisJobExecutor,
    InProcessAnalysisJobExecutor,
)
from backend.api.app.services.real_analysis_processor import RealAnalysisProcessor
from backend.api.app.services.analysis_input_storage import (
    AnalysisInputStorageError,
    AudioTooLargeError,
    EmptyAudioError,
    LocalAnalysisInputStorage,
    UnsupportedAudioFormatError,
)


router = APIRouter(prefix="/analysis/jobs", tags=["Analysis jobs"])

_repository = InMemoryAnalysisJobRepository()
_input_storage = LocalAnalysisInputStorage()
_service = AnalysisJobService(_repository, _input_storage)
_executor = InProcessAnalysisJobExecutor(
    _service,
    _input_storage,
    RealAnalysisProcessor(),
)


def get_analysis_job_service() -> AnalysisJobService:
    return _service


def get_analysis_job_executor() -> AnalysisJobExecutor:
    return _executor


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    payload = AnalysisJobErrorResponse(
        error=AnalysisJobError(code=code, message=message)
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


@router.post(
    "",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": AnalysisJobErrorResponse},
        413: {"model": AnalysisJobErrorResponse},
        415: {"model": AnalysisJobErrorResponse},
        500: {"model": AnalysisJobErrorResponse},
    },
)
def create_analysis_job(
    title: Annotated[
        str,
        Form(min_length=1, max_length=200, pattern=r".*\S.*"),
    ],
    audio: Annotated[UploadFile, File()],
    service: AnalysisJobService = Depends(get_analysis_job_service),
    executor: AnalysisJobExecutor = Depends(get_analysis_job_executor),
) -> AnalysisJobResponse | Response:
    request = AnalysisJobCreateRequest(title=title)
    try:
        response = service.create(
            request=request,
            original_filename=audio.filename or "",
            content_type=audio.content_type,
            source=audio.file,
        )
        executor.submit(response.job_id)
        return response
    except UnsupportedAudioFormatError:
        return error_response(
            415,
            "unsupported_audio_format",
            "Supported audio formats are WAV, MP3, and M4A.",
        )
    except AudioTooLargeError:
        return error_response(413, "audio_too_large", "Audio exceeds the 25 MB limit.")
    except EmptyAudioError:
        return error_response(400, "empty_audio", "Audio file must not be empty.")
    except AnalysisInputStorageError:
        return error_response(
            500,
            "audio_storage_failed",
            "Audio could not be stored.",
        )


@router.get(
    "/{job_id}",
    response_model=AnalysisJobResponse,
    responses={404: {"model": AnalysisJobErrorResponse}},
)
def get_analysis_job(
    job_id: str,
    service: AnalysisJobService = Depends(get_analysis_job_service),
) -> AnalysisJobResponse | Response:
    job = service.get(job_id)
    if job is None:
        return error_response(404, "job_not_found", "Analysis job was not found.")
    return service.response(job)


@router.get(
    "/{job_id}/result",
    response_model=SharedTimeline,
    responses={
        404: {"model": AnalysisJobErrorResponse},
        409: {"model": AnalysisJobErrorResponse},
    },
)
def get_analysis_job_result(
    job_id: str,
    service: AnalysisJobService = Depends(get_analysis_job_service),
) -> SharedTimeline | Response:
    job = service.get(job_id)
    if job is None:
        return error_response(404, "job_not_found", "Analysis job was not found.")
    if job.status in (AnalysisJobStatus.QUEUED, AnalysisJobStatus.PROCESSING):
        return error_response(409, "result_not_ready", "Analysis result is not ready.")
    if job.status == AnalysisJobStatus.FAILED:
        error = job.error or AnalysisJobError(
            code="analysis_failed",
            message="Analysis could not be completed.",
        )
        return error_response(409, error.code, error.message)
    if job.result is None:
        return error_response(409, "result_not_ready", "Analysis result is not ready.")
    return job.result
