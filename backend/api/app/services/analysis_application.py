from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import BinaryIO, Callable, NoReturn, Protocol
from uuid import uuid4

from pydantic import ValidationError

from analysis.fusion.models import SharedTimeline
from backend.api.app.auth import AuthenticationRequiredError
from backend.api.app.models.analysis_job import (
    AnalysisJobCreateRequest,
    AnalysisJobError,
    AnalysisJobResponse,
    AnalysisJobStatus,
    UploadInitiationRequest,
    UploadInitiationResponse,
)
from backend.api.app.services.analysis_input_storage import (
    MAX_AUDIO_SIZE_BYTES,
    SUPPORTED_AUDIO_EXTENSIONS,
    AnalysisInputMetadata,
    AnalysisInputStorage,
    AnalysisInputStorageError,
    AnalysisInputValidationError,
    AudioTooLargeError,
    EmptyAudioError,
    UnsupportedAudioFormatError,
)
from backend.api.app.services.analysis_job_dispatcher import AnalysisJobDispatcher
from backend.api.app.services.analysis_job_executor import AnalysisJobExecutor
from backend.api.app.services.analysis_jobs import AnalysisJobService
from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactKeyFactory,
    ArtifactRole,
    ArtifactStorage,
)
from backend.api.app.services.aws_errors import CloudProviderError
from backend.api.app.services.aws_errors import CloudProviderErrorKind
from backend.api.app.services.cloud_job import (
    CloudJobRecord,
    CloudJobStatus,
    new_cloud_job,
)
from backend.api.app.services.cloud_job_repository import (
    CloudJobRepository,
    JobWriteConflictError,
)
from backend.api.app.services.source_upload_store import (
    ACCEPTED_ENCRYPTIONS,
    SourceUploadStore,
)

logger = logging.getLogger(__name__)

DEFAULT_UPLOAD_URL_TTL_SECONDS = 600
# A confirm request that dies mid-validation (Lambda timeout, crash) leaves the
# job VALIDATING. After this lease, another confirm may take it over. It must
# exceed the API function's timeout so a live request is never taken over.
VALIDATION_LEASE_SECONDS = 120


class JobNotFoundError(LookupError):
    pass


class ResultNotReadyError(RuntimeError):
    pass


class AnalysisFailedError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ResultArtifactMissingError(RuntimeError):
    pass


class ResultArtifactCorruptError(RuntimeError):
    pass


class ResultArtifactUnavailableError(RuntimeError):
    pass


class SourceArtifactStorageError(RuntimeError):
    pass


class InvalidUploadRequestError(ValueError):
    """The create-upload metadata is malformed (not a media judgement)."""

    code = "invalid_request"


class UnsupportedContentTypeError(InvalidUploadRequestError):
    code = "unsupported_content_type"


class UploadNotConfiguredError(RuntimeError):
    pass


class UploadNotReceivedError(RuntimeError):
    """Confirm arrived before the client's PUT completed; the job is unchanged."""


class UploadExpiredError(RuntimeError):
    """The signed URL expired with nothing uploaded; the job is now EXPIRED."""


class ValidationInProgressError(RuntimeError):
    pass


class InvalidJobStateError(RuntimeError):
    pass


class SourceStorageUnavailableError(RuntimeError):
    """The source bucket refused access (a permission or configuration fault)."""


class UploadRejectedError(AnalysisInputValidationError):
    """The stored object disagrees with what was signed, or is not encrypted."""

    code = "invalid_upload"


@dataclass(frozen=True)
class ConfirmOutcome:
    response: AnalysisJobResponse
    # False when the job had already been confirmed: nothing new was sent.
    newly_confirmed: bool


class AnalysisApplication(Protocol):
    def create(
        self,
        request: AnalysisJobCreateRequest,
        original_filename: str,
        content_type: str | None,
        source: BinaryIO,
        owner_id: str | None = None,
    ) -> AnalysisJobResponse: ...

    def status(
        self, job_id: str, owner_id: str | None = None
    ) -> AnalysisJobResponse | None: ...

    def result(self, job_id: str, owner_id: str | None = None) -> SharedTimeline: ...


class LocalAnalysisApplication:
    def __init__(
        self,
        jobs: AnalysisJobService,
        executor: AnalysisJobExecutor,
    ) -> None:
        self._jobs = jobs
        self._executor = executor

    def create(
        self,
        request: AnalysisJobCreateRequest,
        original_filename: str,
        content_type: str | None,
        source: BinaryIO,
        owner_id: str | None = None,  # local jobs are not owner-scoped
    ) -> AnalysisJobResponse:
        response = self._jobs.create(
            request,
            original_filename,
            content_type,
            source,
        )
        self._executor.submit(response.job_id)
        return response

    def status(
        self, job_id: str, owner_id: str | None = None
    ) -> AnalysisJobResponse | None:
        job = self._jobs.get(job_id)
        return self._jobs.response(job) if job else None

    def result(self, job_id: str, owner_id: str | None = None) -> SharedTimeline:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        if job.status in {AnalysisJobStatus.QUEUED, AnalysisJobStatus.PROCESSING}:
            raise ResultNotReadyError
        if job.status is AnalysisJobStatus.FAILED:
            error = job.error or AnalysisJobError(
                code="analysis_failed",
                message="Analysis could not be completed.",
            )
            raise AnalysisFailedError(error.code, error.message)
        if job.result is None:
            raise ResultNotReadyError
        return job.result


class CloudAnalysisApplication:
    def __init__(
        self,
        repository: CloudJobRepository,
        artifact_storage: ArtifactStorage,
        dispatcher: AnalysisJobDispatcher,
        staging_storage: AnalysisInputStorage,
        *,
        source_uploads: SourceUploadStore | None = None,
        upload_url_ttl_seconds: int = DEFAULT_UPLOAD_URL_TTL_SECONDS,
        clock: Callable[[], datetime] | None = None,
        enforce_ownership: bool = False,
    ) -> None:
        self._repository = repository
        self._artifacts = artifact_storage
        self._dispatcher = dispatcher
        self._staging = staging_storage
        self._uploads = source_uploads
        self._upload_ttl = upload_url_ttl_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # Hosted mode: a job is visible only to the principal that created it.
        self._enforce_ownership = enforce_ownership

    def create(
        self,
        request: AnalysisJobCreateRequest,
        original_filename: str,
        content_type: str | None,
        source: BinaryIO,
        owner_id: str | None = None,
    ) -> AnalysisJobResponse:
        job_id = str(uuid4())
        metadata = self._staging.store(
            job_id,
            original_filename,
            content_type,
            source,
        )
        local_path = self._staging.get_path(job_id)
        if local_path is None:
            self._staging.delete(job_id)
            raise SourceArtifactStorageError

        job = new_cloud_job(job_id, request.title)
        job.owner_id = owner_id
        source_key = ArtifactKeyFactory().source(job_id, metadata.extension)
        try:
            self._repository.add(job)
            self._artifacts.put_bytes(
                source_key,
                local_path.read_bytes(),
                # The stored type comes from the validated file, never from the
                # client's Content-Type header.
                content_type=_content_type(metadata.extension),
            )
            job.source_object_key = source_key.value
            job.duration_seconds = metadata.duration_seconds
            job.file_type = metadata.extension
            job.transition_to(CloudJobStatus.AWAITING_UPLOAD, stage="source_stored")
            self._repository.save(job, expected_status=CloudJobStatus.CREATED)
        except (CloudProviderError, OSError) as error:
            raise SourceArtifactStorageError from error
        finally:
            self._staging.delete(job_id)

        try:
            self._dispatcher.dispatch(job_id)
        except CloudProviderError:
            # QUEUED + dispatch_pending is durable and can be reconciled without
            # another upload. Return the existing compatible queued response.
            pass
        current = self._repository.get(job_id)
        if current is None:
            raise JobNotFoundError(job_id)
        return _cloud_response(current)

    def status(
        self, job_id: str, owner_id: str | None = None
    ) -> AnalysisJobResponse | None:
        job = self._repository.get(job_id)
        if job is None or not self._visible_to(job, owner_id):
            return None
        return _cloud_response(job)

    def _visible_to(self, job: CloudJobRecord, owner_id: str | None) -> bool:
        """Cross-owner (and ownerless) jobs look exactly like missing ones."""
        if not self._enforce_ownership:
            return True
        return owner_id is not None and job.owner_id == owner_id

    # --- hosted presigned-upload lifecycle ---------------------------------

    def initiate_upload(
        self, request: UploadInitiationRequest, owner_id: str | None = None
    ) -> UploadInitiationResponse:
        """Phase 1: record the job and sign one PUT. No audio passes through here."""
        uploads = self._require_uploads()
        if self._enforce_ownership and owner_id is None:
            raise AuthenticationRequiredError  # a hosted job always has an owner
        extension = _extension_of(request.filename)
        canonical = _content_type(extension)
        _check_declared_content_type(request.content_type, extension)
        if request.declared_size_bytes <= 0:
            raise InvalidUploadRequestError("declared size must be positive")
        if request.declared_size_bytes > MAX_AUDIO_SIZE_BYTES:
            raise AudioTooLargeError

        job_id = str(uuid4())
        # The key is derived here from the job ID and validated extension only.
        key = ArtifactKeyFactory().source(job_id, extension)
        expires_at = self._clock() + timedelta(seconds=self._upload_ttl)
        presigned = uploads.presign_put(
            key,
            content_type=canonical,
            content_length=request.declared_size_bytes,
            expires_in=self._upload_ttl,
        )
        job = new_cloud_job(job_id, request.title)
        job.owner_id = owner_id
        job.source_object_key = key.value
        job.file_type = extension
        job.declared_size_bytes = request.declared_size_bytes
        job.upload_expires_at = expires_at
        job.transition_to(CloudJobStatus.AWAITING_UPLOAD, stage="upload_pending")
        self._repository.add(job)  # one atomic write; nothing is queued yet
        return UploadInitiationResponse(
            job_id=job_id,
            status=AnalysisJobStatus.AWAITING_UPLOAD,
            upload_url=presigned.url,
            upload_method=presigned.method,
            required_headers=presigned.headers,
            expires_at=expires_at,
            source_object_key=key.value,
        )

    def confirm_upload(
        self, job_id: str, owner_id: str | None = None
    ) -> ConfirmOutcome:
        """Phase 2: validate the uploaded object, then queue the job exactly once.

        A job owned by someone else is reported as not found, before any state
        change, S3 call, or SQS message.
        """
        uploads = self._require_uploads()
        job = self._claim_for_validation(job_id, owner_id)
        if isinstance(job, ConfirmOutcome):
            return job
        return self._validate_and_dispatch(job, uploads)

    def _claim_for_validation(
        self, job_id: str, owner_id: str | None
    ) -> CloudJobRecord | ConfirmOutcome:
        """Move AWAITING_UPLOAD (or an abandoned VALIDATING) to VALIDATING.

        The versioned conditional save lets exactly one caller win; the others
        see the new state and are answered without touching S3 or SQS.
        """
        for _ in range(3):
            job = self._repository.get(job_id)
            if job is None or not self._visible_to(job, owner_id):
                raise JobNotFoundError(job_id)
            if job.status in _ALREADY_CONFIRMED:
                return ConfirmOutcome(_cloud_response(job), newly_confirmed=False)
            if job.status is CloudJobStatus.VALIDATING:
                if not self._lease_expired(job):
                    raise ValidationInProgressError
            elif job.status is not CloudJobStatus.AWAITING_UPLOAD:
                raise InvalidJobStateError(job.status.value)
            previous = job.status
            if previous is CloudJobStatus.AWAITING_UPLOAD:
                job.transition_to(CloudJobStatus.VALIDATING, stage="validating")
            else:  # take over an abandoned validation: refresh the lease
                job.updated_at = self._clock()
                job.stage = "validating"
            try:
                self._repository.save(job, expected_status=previous)
            except JobWriteConflictError:
                continue
            return job
        raise ValidationInProgressError

    def _lease_expired(self, job: CloudJobRecord) -> bool:
        age = self._clock() - job.updated_at
        return age > timedelta(seconds=VALIDATION_LEASE_SECONDS)

    def _validate_and_dispatch(
        self, job: CloudJobRecord, uploads: SourceUploadStore
    ) -> ConfirmOutcome:
        job_id = job.job_id
        try:
            key, extension = self._expected_source_key(job)
            self._check_object(uploads, job, key, extension)
            metadata = self._stage_and_inspect(uploads, job_id, key, extension)
        except AnalysisInputValidationError as error:
            self._reject(job, key, uploads, error)
            raise
        except (UploadNotReceivedError, UploadExpiredError, InvalidJobStateError):
            raise
        except CloudProviderError as error:
            if error.kind is CloudProviderErrorKind.NOT_FOUND:
                self._not_received(job)
            self._release(job)
            if error.kind is CloudProviderErrorKind.CONFIGURATION:
                raise SourceStorageUnavailableError from error
            raise
        except (AnalysisInputStorageError, OSError) as error:
            self._release(job)
            raise SourceArtifactStorageError from error
        finally:
            self._remove_staged(job_id)

        job.duration_seconds = metadata.duration_seconds
        job.file_type = extension
        try:
            self._repository.save(job, expected_status=CloudJobStatus.VALIDATING)
            self._dispatcher.dispatch(job_id)
        except JobWriteConflictError:
            # Another request took over after our lease lapsed. It owns dispatch.
            current = self._repository.get(job_id)
            if current is None:
                raise JobNotFoundError(job_id)
            return ConfirmOutcome(_cloud_response(current), newly_confirmed=False)
        except CloudProviderError:
            current = self._repository.get(job_id)
            if current is not None and current.status is CloudJobStatus.QUEUED:
                # QUEUED + dispatch_pending is durable and is reconciled later;
                # the upload does not need to be repeated.
                return ConfirmOutcome(_cloud_response(current), newly_confirmed=True)
            self._release(job)
            raise
        current = self._repository.get(job_id)
        if current is None:
            raise JobNotFoundError(job_id)
        return ConfirmOutcome(_cloud_response(current), newly_confirmed=True)

    def _expected_source_key(self, job: CloudJobRecord) -> tuple[ArtifactKey, str]:
        extension = job.file_type or ""
        try:
            key = ArtifactKeyFactory().source(job.job_id, extension)
        except ValueError as error:
            self._release(job)
            raise InvalidJobStateError("job has no valid source extension") from error
        if job.source_object_key != key.value:
            # The record names a key this job would never be given.
            self._release(job)
            raise InvalidJobStateError("job source key does not match the job")
        return key, extension

    def _check_object(
        self,
        uploads: SourceUploadStore,
        job: CloudJobRecord,
        key: ArtifactKey,
        extension: str,
    ) -> None:
        info = uploads.head(key)
        if info is None:
            self._not_received(job)
        if info.size_bytes <= 0:
            raise EmptyAudioError
        if info.size_bytes > MAX_AUDIO_SIZE_BYTES:
            raise AudioTooLargeError
        if job.declared_size_bytes is not None and info.size_bytes != job.declared_size_bytes:
            raise UploadRejectedError
        if info.content_type is not None and (
            info.content_type.split(";")[0].strip().casefold() != _content_type(extension)
        ):
            raise UploadRejectedError
        if info.server_side_encryption not in ACCEPTED_ENCRYPTIONS:
            raise UploadRejectedError

    def _stage_and_inspect(
        self,
        uploads: SourceUploadStore,
        job_id: str,
        key: ArtifactKey,
        extension: str,
    ) -> AnalysisInputMetadata:
        # /tmp persists between warm invocations: clear any leftovers first.
        self._staging.delete(job_id)
        stream = uploads.open(key)
        try:
            # Streams with a hard size cap, then runs inspect_audio, requires the
            # detected format to match the extension, and enforces 360 s.
            return self._staging.store(
                job_id, f"input{extension}", _content_type(extension), stream
            )
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()

    def _remove_staged(self, job_id: str) -> None:
        try:
            self._staging.delete(job_id)
        except AnalysisInputStorageError:
            logger.warning("could not remove staged upload for a job")

    def _not_received(self, job: CloudJobRecord) -> NoReturn:
        """Nothing is stored. Expired URL -> EXPIRED; otherwise stay recoverable."""
        expired = job.upload_expires_at is not None and self._clock() >= job.upload_expires_at
        if expired:
            job.error_code = "upload_expired"
            job.error_message = "The upload link expired before the audio was uploaded."
            job.transition_to(CloudJobStatus.EXPIRED, stage="upload_expired")
            self._save_quietly(job, CloudJobStatus.VALIDATING)
            raise UploadExpiredError
        self._release(job)
        raise UploadNotReceivedError

    def _release(self, job: CloudJobRecord) -> None:
        """Hand the job back to AWAITING_UPLOAD so confirm can be retried."""
        if job.status is not CloudJobStatus.VALIDATING:
            return
        job.transition_to(CloudJobStatus.AWAITING_UPLOAD, stage="upload_pending")
        self._save_quietly(job, CloudJobStatus.VALIDATING)

    def _reject(
        self,
        job: CloudJobRecord,
        key: ArtifactKey | None,
        uploads: SourceUploadStore,
        error: AnalysisInputValidationError,
    ) -> None:
        """Terminal failure. Marked first so no later confirm can succeed, then
        the stored object is deleted; the bucket lifecycle is the backstop."""
        job.error_code = error.code
        job.error_message = _REJECTION_MESSAGES.get(error.code, "Audio could not be validated.")
        job.transition_to(CloudJobStatus.FAILED, stage="upload_rejected")
        self._save_quietly(job, CloudJobStatus.VALIDATING)
        if key is not None:
            try:
                uploads.delete(key)
            except CloudProviderError:
                logger.warning("could not delete a rejected upload")

    def _save_quietly(self, job: CloudJobRecord, expected: CloudJobStatus) -> None:
        try:
            self._repository.save(job, expected_status=expected)
        except (JobWriteConflictError, CloudProviderError):
            # The lease covers a failed hand-back; a conflict means someone else
            # already moved the job.
            logger.warning("could not record a job state change")

    def _require_uploads(self) -> SourceUploadStore:
        if self._uploads is None:
            raise UploadNotConfiguredError
        return self._uploads

    def result(self, job_id: str, owner_id: str | None = None) -> SharedTimeline:
        job = self._repository.get(job_id)
        if job is None or not self._visible_to(job, owner_id):
            raise JobNotFoundError(job_id)
        if job.status is CloudJobStatus.FAILED:
            raise AnalysisFailedError(
                job.error_code or "analysis_failed",
                job.error_message or "Analysis could not be completed.",
            )
        if job.status is not CloudJobStatus.COMPLETED:
            raise ResultNotReadyError
        if not job.timeline_object_key:
            raise ResultArtifactMissingError
        key = ArtifactKey(ArtifactRole.TIMELINE_RESULT, job.timeline_object_key)
        try:
            if not self._artifacts.exists(key):
                raise ResultArtifactMissingError
            raw = self._artifacts.read_bytes(key).decode("utf-8")
            payload = json.loads(raw)
            return SharedTimeline.model_validate(payload)
        except CloudProviderError as error:
            if error.kind is CloudProviderErrorKind.NOT_FOUND:
                raise ResultArtifactMissingError from error
            raise ResultArtifactUnavailableError from error
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError) as error:
            raise ResultArtifactCorruptError from error


_ALREADY_CONFIRMED = frozenset(
    {CloudJobStatus.QUEUED, CloudJobStatus.PROCESSING, CloudJobStatus.COMPLETED}
)
_REJECTION_MESSAGES = {
    "audio_too_large": "Audio exceeds the 25 MB limit.",
    "audio_too_long": "Audio exceeds the 6-minute limit.",
    "empty_audio": "Audio file must not be empty.",
    "invalid_audio": "Audio could not be decoded.",
    "unsupported_audio_format": "Supported audio formats are WAV, MP3, and M4A.",
    "invalid_upload": "The uploaded file does not match the upload request.",
}
_CONTENT_TYPE_ALIASES = {
    ".mp3": {"audio/mpeg", "audio/mp3", "audio/x-mpeg"},
    ".wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
    ".m4a": {"audio/mp4", "audio/x-m4a", "audio/m4a"},
}


def _extension_of(filename: str) -> str:
    if "\x00" in filename:
        raise InvalidUploadRequestError("filename is invalid")
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    extension = ("." + name.rsplit(".", 1)[-1]).lower() if "." in name else ""
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:
        raise UnsupportedAudioFormatError
    return extension


def _check_declared_content_type(declared: str | None, extension: str) -> None:
    """The declared type is a hint only; reject one that contradicts the extension."""
    if declared is None or not declared.strip():
        return
    base = declared.split(";")[0].strip().casefold()
    if base == "application/octet-stream" or base in _CONTENT_TYPE_ALIASES[extension]:
        return
    raise UnsupportedContentTypeError(base)


def _cloud_response(job: CloudJobRecord) -> AnalysisJobResponse:
    if job.status is CloudJobStatus.AWAITING_UPLOAD:
        status = AnalysisJobStatus.AWAITING_UPLOAD
    elif job.status is CloudJobStatus.VALIDATING:
        status = AnalysisJobStatus.VALIDATING
    elif job.status in {
        CloudJobStatus.CREATED,
        CloudJobStatus.QUEUED,
    }:
        status = AnalysisJobStatus.QUEUED
    elif job.status is CloudJobStatus.PROCESSING:
        status = AnalysisJobStatus.PROCESSING
    elif job.status is CloudJobStatus.COMPLETED:
        status = AnalysisJobStatus.COMPLETED
    else:
        status = AnalysisJobStatus.FAILED
    error = None
    if status is AnalysisJobStatus.FAILED:
        error = AnalysisJobError(
            code=job.error_code or "analysis_failed",
            message=job.error_message or "Analysis could not be completed.",
        )
    return AnalysisJobResponse(
        job_id=job.job_id,
        status=status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=error,
        result_available=(
            job.status is CloudJobStatus.COMPLETED
            and job.timeline_object_key is not None
        ),
    )


def _content_type(extension: str) -> str:
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
    }[extension]
