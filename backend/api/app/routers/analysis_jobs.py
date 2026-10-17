from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse

from analysis.fusion.models import SharedTimeline
from backend.api.app.auth import (
    AuthenticatedPrincipal,
    AuthUnavailableError,
    CachedVerifierProvider,
    DemoTokenVerifier,
    SsmDocumentLoader,
    StaticVerifierProvider,
    VerifierProvider,
    authenticate,
)
from backend.api.app.models.analysis_job import (
    AnalysisJobCreateRequest,
    AnalysisJobError,
    AnalysisJobErrorResponse,
    AnalysisJobResponse,
    UploadInitiationRequest,
    UploadInitiationResponse,
)
from backend.api.app.hosting import ApiHostingConfig
from backend.api.app.services.analysis_jobs import (
    AnalysisJobService,
    InMemoryAnalysisJobRepository,
)
from backend.api.app.services.analysis_application import (
    AnalysisApplication,
    AnalysisFailedError,
    CloudAnalysisApplication,
    InvalidJobStateError,
    JobCancelledError,
    InvalidUploadRequestError,
    JobNotFoundError,
    LocalAnalysisApplication,
    ResultArtifactCorruptError,
    ResultArtifactMissingError,
    ResultArtifactUnavailableError,
    ResultNotReadyError,
    SourceArtifactStorageError,
    SourceStorageUnavailableError,
    UploadExpiredError,
    UploadNotConfiguredError,
    UploadNotReceivedError,
    ValidationInProgressError,
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
from backend.api.app.services.analysis_input_storage import (
    AnalysisInputStorageError,
    AnalysisInputValidationError,
    AudioTooLongError,
    AudioTooLargeError,
    EmptyAudioError,
    InvalidAudioError,
    LocalAnalysisInputStorage,
    UnsupportedAudioFormatError,
)


# Components are built on first use and reused, so importing has no side
# effects. Tests replace the get_* dependencies via dependency_overrides.


@lru_cache(maxsize=1)
def _runtime_config() -> CloudRuntimeConfig:
    return CloudRuntimeConfig.from_env()


@lru_cache(maxsize=1)
def _local_input_storage() -> LocalAnalysisInputStorage:
    return LocalAnalysisInputStorage()


@lru_cache(maxsize=1)
def _local_job_service() -> AnalysisJobService:
    return AnalysisJobService(
        InMemoryAnalysisJobRepository(),
        _local_input_storage(),
    )


@lru_cache(maxsize=1)
def _local_job_executor() -> AnalysisJobExecutor:
    # Imported here so the hosted API never loads the analysis pipeline.
    from backend.api.app.services.real_analysis_processor import RealAnalysisProcessor

    return InProcessAnalysisJobExecutor(
        _local_job_service(),
        _local_input_storage(),
        RealAnalysisProcessor(),
    )


@lru_cache(maxsize=1)
def _hosting_config() -> ApiHostingConfig:
    return ApiHostingConfig.from_env()


@lru_cache(maxsize=4)
def _auth_provider(hosting: ApiHostingConfig) -> VerifierProvider | None:
    """Where token verifiers come from, or None if auth is not configured.

    Hosted mode always has one. The SSM client is created on first use.
    """
    if hosting.demo_token_parameter:
        try:
            import boto3
        except ImportError as error:
            raise AuthUnavailableError("boto3 is unavailable") from error
        client = boto3.session.Session().client("ssm")
        return CachedVerifierProvider(SsmDocumentLoader(client, hosting.demo_token_parameter))
    if hosting.demo_token_verifier_document and not hosting.is_hosted:
        return StaticVerifierProvider(
            DemoTokenVerifier.from_document(hosting.demo_token_verifier_document)
        )
    return None


def get_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedPrincipal | None:
    """Authenticate the caller: 401 for bad credentials, 503 if the verifier is down.

    Uses the hosting config the app was built with, so a hosted app can't run unauthenticated.
    """
    hosting = getattr(request.app.state, "hosting", None) or _hosting_config()
    provider = _auth_provider(hosting)
    if provider is None:
        if hosting.is_hosted:
            raise AuthUnavailableError("authentication is not configured")
        return None  # local dev, auth not enabled
    return authenticate(authorization, provider)


def _owner(principal: AuthenticatedPrincipal | None) -> str | None:
    return principal.principal_id if principal else None


@lru_cache(maxsize=1)
def _cloud_application(
    config: CloudRuntimeConfig,
    staging_root: Path,
) -> CloudAnalysisApplication:
    runtime = compose_cloud_runtime(config)
    return CloudAnalysisApplication(
        runtime.repository,
        runtime.artifact_storage,
        compose_analysis_dispatcher(config, runtime),
        LocalAnalysisInputStorage(staging_root),
        source_uploads=runtime.source_uploads,
        upload_url_ttl_seconds=_hosting_config().upload_url_ttl_seconds,
        enforce_ownership=_hosting_config().is_hosted,
    )


def get_analysis_job_service() -> AnalysisJobService:
    return _local_job_service()


def get_analysis_job_executor() -> AnalysisJobExecutor:
    return _local_job_executor()


def get_analysis_application_service(
    service: AnalysisJobService = Depends(get_analysis_job_service),
    executor: AnalysisJobExecutor = Depends(get_analysis_job_executor),
) -> AnalysisApplication:
    config = _runtime_config()
    if config.mode is RuntimeMode.LOCAL:
        return LocalAnalysisApplication(service, executor)
    return _cloud_application(config, config.storage_root / "cloud_api_staging")


def get_hosted_analysis_application() -> CloudAnalysisApplication:
    """Hosted provider: cloud runtime only, staging under /tmp, no local pipeline."""
    config = _runtime_config()
    if config.mode is not RuntimeMode.AWS:
        raise RuntimeError("Hosted API requires the AWS runtime mode")
    return _cloud_application(config, _hosting_config().staging_root / "cloud_api_staging")


# Local: multipart create. Hosted: create-upload + confirm. Both share the
# status and result routes. Every route needs a principal (a no-op only in
# local mode without auth), so new routes are protected by default.
router = APIRouter(
    prefix="/analysis/jobs", tags=["Analysis jobs"], dependencies=[Depends(get_principal)]
)
hosted_router = APIRouter(
    prefix="/analysis/jobs", tags=["Analysis jobs"], dependencies=[Depends(get_principal)]
)
_read_routes = APIRouter()


def error_response(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = AnalysisJobErrorResponse(
        error=AnalysisJobError(code=code, message=message)
    )
    return JSONResponse(
        status_code=status_code, content=payload.model_dump(), headers=headers
    )


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
    principal: AuthenticatedPrincipal | None = Depends(get_principal),
) -> AnalysisJobResponse | Response:
    request = AnalysisJobCreateRequest(title=title)
    try:
        return application.create(
            request=request,
            original_filename=audio.filename or "",
            content_type=audio.content_type,
            source=audio.file,
            owner_id=_owner(principal),
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


@_read_routes.get(
    "/{job_id}",
    response_model=AnalysisJobResponse,
    responses={404: {"model": AnalysisJobErrorResponse}},
)
def get_analysis_job(
    job_id: str,
    application: AnalysisApplication = Depends(get_analysis_application_service),
    principal: AuthenticatedPrincipal | None = Depends(get_principal),
) -> AnalysisJobResponse | Response:
    response = application.status(job_id, _owner(principal))
    if response is None:
        return error_response(404, "job_not_found", "Analysis job was not found.")
    return response


@_read_routes.get(
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
    principal: AuthenticatedPrincipal | None = Depends(get_principal),
) -> SharedTimeline | Response:
    try:
        return application.result(job_id, _owner(principal))
    except JobNotFoundError:
        return error_response(404, "job_not_found", "Analysis job was not found.")
    except ResultNotReadyError:
        return error_response(409, "result_not_ready", "Analysis result is not ready.")
    except JobCancelledError:
        return error_response(409, "job_cancelled", "This analysis was cancelled.")
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


router.include_router(_read_routes)
hosted_router.include_router(_read_routes)


# --- hosted presigned upload ---

_UPLOAD_ERRORS = {
    503: {"model": AnalysisJobErrorResponse},
    409: {"model": AnalysisJobErrorResponse},
    404: {"model": AnalysisJobErrorResponse},
}


@hosted_router.post(
    "",
    response_model=UploadInitiationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": AnalysisJobErrorResponse},
        413: {"model": AnalysisJobErrorResponse},
        503: {"model": AnalysisJobErrorResponse},
    },
)
def create_upload(
    request: UploadInitiationRequest,
    application: CloudAnalysisApplication = Depends(get_hosted_analysis_application),
    principal: AuthenticatedPrincipal | None = Depends(get_principal),
) -> UploadInitiationResponse | Response:
    """Phase 1: JSON metadata in, one signed S3 PUT out. No audio is accepted."""
    try:
        return application.initiate_upload(request, _owner(principal))
    except UnsupportedAudioFormatError:
        return error_response(
            400, "unsupported_audio_format", "Supported audio formats are WAV, MP3, and M4A."
        )
    except AudioTooLargeError:
        return error_response(413, "audio_too_large", "Audio exceeds the 25 MB limit.")
    except InvalidUploadRequestError as error:
        return error_response(400, error.code, "Upload request is invalid.")
    except UploadNotConfiguredError:
        return error_response(500, "upload_unavailable", "Uploads are not available.")


@hosted_router.post(
    "/{job_id}/confirm-upload",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: {"model": AnalysisJobErrorResponse},
        409: {"model": AnalysisJobErrorResponse},
        413: {"model": AnalysisJobErrorResponse},
        422: {"model": AnalysisJobErrorResponse},
        503: {"model": AnalysisJobErrorResponse},
    },
)
def confirm_upload(
    job_id: str,
    http_response: Response,
    application: CloudAnalysisApplication = Depends(get_hosted_analysis_application),
    principal: AuthenticatedPrincipal | None = Depends(get_principal),
) -> AnalysisJobResponse | Response:
    """Phase 2: validate the stored object and queue the job once.

    Returns 202 when this call queued it, or 200 with the current state if it
    was already confirmed.
    """
    try:
        outcome = application.confirm_upload(job_id, _owner(principal))
    except JobNotFoundError:
        return error_response(404, "job_not_found", "Analysis job was not found.")
    except UploadNotReceivedError:
        return error_response(
            409, "upload_not_received", "The audio has not been uploaded yet."
        )
    except UploadExpiredError:
        return error_response(
            409, "upload_expired", "The upload link expired. Create a new job."
        )
    except ValidationInProgressError:
        return error_response(
            409, "validation_in_progress", "The upload is already being validated."
        )
    except InvalidJobStateError:
        return error_response(
            409, "invalid_job_state", "This job cannot accept an upload confirmation."
        )
    except AudioTooLargeError:
        return error_response(413, "audio_too_large", "Audio exceeds the 25 MB limit.")
    except AudioTooLongError:
        return error_response(422, "audio_too_long", "Audio exceeds the 6-minute limit.")
    except EmptyAudioError:
        return error_response(422, "empty_audio", "Audio file must not be empty.")
    except AnalysisInputValidationError as error:
        code = error.code if error.code in _UNPROCESSABLE_CODES else "invalid_audio"
        return error_response(422, code, _UNPROCESSABLE_CODES.get(code, "Audio could not be decoded."))
    except SourceArtifactStorageError:
        return error_response(500, "source_storage_failed", "Audio could not be read.")
    except SourceStorageUnavailableError:
        # Same response as any dependency outage; the cause is in the log.
        return error_response(
            503, "service_unavailable", "Analysis service is temporarily unavailable."
        )
    except UploadNotConfiguredError:
        return error_response(500, "upload_unavailable", "Uploads are not available.")
    if not outcome.newly_confirmed:
        http_response.status_code = status.HTTP_200_OK
    return outcome.response


@hosted_router.post(
    "/{job_id}/cancel",
    response_model=AnalysisJobResponse,
    responses={
        404: {"model": AnalysisJobErrorResponse},
        409: {"model": AnalysisJobErrorResponse},
        503: {"model": AnalysisJobErrorResponse},
    },
)
def cancel_job(
    job_id: str,
    application: CloudAnalysisApplication = Depends(get_hosted_analysis_application),
    principal: AuthenticatedPrincipal | None = Depends(get_principal),
) -> AnalysisJobResponse | Response:
    """Stop a job. Cancelling an already-cancelled job returns 200 again."""
    try:
        return application.cancel(job_id, _owner(principal))
    except JobNotFoundError:
        return error_response(404, "job_not_found", "Analysis job was not found.")
    except InvalidJobStateError:
        return error_response(
            409, "invalid_job_state", "This job can no longer be cancelled."
        )


_UNPROCESSABLE_CODES = {
    "invalid_audio": "Audio could not be decoded.",
    "unsupported_audio_format": "Supported audio formats are WAV, MP3, and M4A.",
    "invalid_upload": "The uploaded file does not match the upload request.",
}
