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
from backend.api.app.services.analysis_application import (
    AnalysisApplication,
    AnalysisFailedError,
    CloudAnalysisApplication,
    JobNotFoundError,
    LocalAnalysisApplication,
    ResultArtifactCorruptError,
    ResultArtifactMissingError,
    ResultArtifactUnavailableError,
    ResultNotReadyError,
    SourceArtifactStorageError,
)
from backend.api.app.services.cloud_runtime import (
    CloudRuntimeConfig,
    RuntimeMode,
    compose_analysis_dispatcher,
    compose_cloud_runtime,
)
from backend.api.app.services.analysis_job_executor import (
    AnalysisJobExecutor,
    InProcessAnalysisJobExecutor,
)
from backend.api.app.services.real_analysis_processor import RealAnalysisProcessor
from backend.api.app.services.analysis_input_storage import (
    AnalysisInputStorageError,
    AudioTooLongError,
    AudioTooLargeError,
    EmptyAudioError,
    InvalidAudioError,
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


_cloud_application: AnalysisApplication | None = None


def get_analysis_application_service(
    service: AnalysisJobService = Depends(get_analysis_job_service),
    executor: AnalysisJobExecutor = Depends(get_analysis_job_executor),
) -> AnalysisApplication:
    config = CloudRuntimeConfig.from_env()
    if config.mode is RuntimeMode.LOCAL:
        return LocalAnalysisApplication(service, executor)
    global _cloud_application
    if _cloud_application is None:
        runtime = compose_cloud_runtime(config)
        dispatcher = compose_analysis_dispatcher(config, runtime)
        staging = LocalAnalysisInputStorage(
            config.storage_root / "cloud_api_staging"
        )
        _cloud_application = CloudAnalysisApplication(
            runtime.repository,
            runtime.artifact_storage,
            dispatcher,
            staging,
        )
    return _cloud_application


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
    application: AnalysisApplication = Depends(get_analysis_application_service),
) -> AnalysisJobResponse | Response:
    request = AnalysisJobCreateRequest(title=title)
    try:
        return application.create(
            request=request,
            original_filename=audio.filename or "",
            content_type=audio.content_type,
            source=audio.file,
        )
    except UnsupportedAudioFormatError:
        return error_response(
            415,
            "unsupported_audio_format",
            "Supported audio formats are WAV, MP3, and M4A.",
        )
    except AudioTooLargeError:
        return error_response(413, "audio_too_large", "Audio exceeds the 25 MB limit.")
    except AudioTooLongError:
        return error_response(
            413,
            "audio_too_long",
            "Audio exceeds the 6-minute limit.",
        )
    except InvalidAudioError:
        return error_response(400, "invalid_audio", "Audio could not be decoded.")
    except EmptyAudioError:
        return error_response(400, "empty_audio", "Audio file must not be empty.")
    except AnalysisInputStorageError:
        return error_response(
            500,
            "audio_storage_failed",
            "Audio could not be stored.",
        )
    except SourceArtifactStorageError:
        return error_response(
            500,
            "source_storage_failed",
            "Audio could not be stored.",
        )


@router.get(
    "/{job_id}",
    response_model=AnalysisJobResponse,
    responses={404: {"model": AnalysisJobErrorResponse}},
)
def get_analysis_job(
    job_id: str,
    application: AnalysisApplication = Depends(get_analysis_application_service),
) -> AnalysisJobResponse | Response:
    response = application.status(job_id)
    if response is None:
        return error_response(404, "job_not_found", "Analysis job was not found.")
    return response


@router.get(
    "/{job_id}/result",
    response_model=SharedTimeline,
    responses={
        404: {"model": AnalysisJobErrorResponse},
        409: {"model": AnalysisJobErrorResponse},
        500: {"model": AnalysisJobErrorResponse},
        503: {"model": AnalysisJobErrorResponse},
    },
)
def get_analysis_job_result(
    job_id: str,
    application: AnalysisApplication = Depends(get_analysis_application_service),
) -> SharedTimeline | Response:
    try:
        return application.result(job_id)
    except JobNotFoundError:
        return error_response(404, "job_not_found", "Analysis job was not found.")
    except ResultNotReadyError:
        return error_response(409, "result_not_ready", "Analysis result is not ready.")
    except AnalysisFailedError as error:
        return error_response(409, error.code, error.message)
    except ResultArtifactMissingError:
        return error_response(
            409,
            "result_artifact_missing",
            "Analysis result is unavailable.",
        )
    except ResultArtifactCorruptError:
        return error_response(
            500,
            "result_artifact_corrupt",
            "Analysis result could not be read.",
        )
    except ResultArtifactUnavailableError:
        return error_response(
            503,
            "result_temporarily_unavailable",
            "Analysis result is temporarily unavailable.",
        )
