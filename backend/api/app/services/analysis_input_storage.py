import math
from dataclasses import dataclass
from pathlib import Path
from shutil import rmtree
from typing import BinaryIO, Callable, Protocol

from backend.api.app.services.media_inspection import (
    EXTENSION_FORMATS,
    AudioFormat,
    MediaInfo,
    inspect_audio,
)


SUPPORTED_AUDIO_EXTENSIONS = frozenset(EXTENSION_FORMATS)
MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024
MAX_AUDIO_DURATION_SECONDS = 360.0
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ANALYSIS_INPUT_ROOT = _PROJECT_ROOT / "storage/uploads/analysis_jobs"
_COPY_CHUNK_SIZE = 1024 * 1024


class AnalysisInputValidationError(Exception):
    code: str


class UnsupportedAudioFormatError(AnalysisInputValidationError):
    code = "unsupported_audio_format"


class EmptyAudioError(AnalysisInputValidationError):
    code = "empty_audio"


class AudioTooLargeError(AnalysisInputValidationError):
    code = "audio_too_large"


class AudioTooLongError(AnalysisInputValidationError):
    code = "audio_too_long"


class InvalidAudioError(AnalysisInputValidationError):
    code = "invalid_audio"


class AnalysisInputStorageError(Exception):
    pass


@dataclass(frozen=True)
class AnalysisInputMetadata:
    storage_key: str
    original_filename: str
    extension: str
    content_type: str | None
    size_bytes: int
    duration_seconds: float
    # The format found by inspecting the file's contents; it always agrees with
    # ``extension`` for stored uploads.
    detected_format: AudioFormat | None = None


class AnalysisInputStorage(Protocol):
    def store(
        self,
        job_id: str,
        original_filename: str,
        content_type: str | None,
        source: BinaryIO,
    ) -> AnalysisInputMetadata: ...

    def get_path(self, job_id: str) -> Path | None: ...

    def delete(self, job_id: str) -> None: ...


class LocalAnalysisInputStorage:
    def __init__(
        self,
        root: Path = DEFAULT_ANALYSIS_INPUT_ROOT,
        max_size_bytes: int = MAX_AUDIO_SIZE_BYTES,
        max_duration_seconds: float = MAX_AUDIO_DURATION_SECONDS,
        duration_probe: Callable[[Path], float] | None = None,
        media_inspector: Callable[[Path], MediaInfo] | None = None,
    ) -> None:
        if duration_probe is not None and media_inspector is not None:
            raise ValueError("Pass either duration_probe or media_inspector, not both")
        self.root = root
        self.max_size_bytes = max_size_bytes
        self.max_duration_seconds = max_duration_seconds
        if media_inspector is not None:
            self._inspect = media_inspector
        elif duration_probe is not None:
            self._inspect = _inspector_from_duration_probe(duration_probe)
        else:
            self._inspect = inspect_audio

    def store(
        self,
        job_id: str,
        original_filename: str,
        content_type: str | None,
        source: BinaryIO,
    ) -> AnalysisInputMetadata:
        safe_filename = self._safe_filename(original_filename)
        extension = Path(safe_filename).suffix.lower()
        if extension not in SUPPORTED_AUDIO_EXTENSIONS:
            raise UnsupportedAudioFormatError

        job_directory = self._job_directory(job_id)
        final_path = job_directory / f"input{extension}"
        temporary_path = job_directory / f"input{extension}.part"
        size_bytes = 0

        try:
            job_directory.mkdir(parents=True, exist_ok=False)
            with temporary_path.open("xb") as destination:
                while chunk := source.read(_COPY_CHUNK_SIZE):
                    size_bytes += len(chunk)
                    if size_bytes > self.max_size_bytes:
                        raise AudioTooLargeError
                    destination.write(chunk)
            if size_bytes == 0:
                raise EmptyAudioError
            temporary_path.replace(final_path)
            try:
                media = self._inspect(final_path)
            except Exception as error:
                # Parser details never reach the client.
                raise InvalidAudioError from error
            if media.format is not EXTENSION_FORMATS[extension]:
                raise InvalidAudioError
            duration_seconds = media.duration_seconds
            if not math.isfinite(duration_seconds) or duration_seconds <= 0:
                raise InvalidAudioError
            if duration_seconds > self.max_duration_seconds:
                raise AudioTooLongError
        except AnalysisInputValidationError:
            self._remove_job_directory(job_directory)
            raise
        except OSError as error:
            self._remove_job_directory(job_directory)
            raise AnalysisInputStorageError from error

        return AnalysisInputMetadata(
            storage_key=job_id,
            original_filename=safe_filename,
            extension=extension,
            content_type=content_type,
            size_bytes=size_bytes,
            duration_seconds=duration_seconds,
            detected_format=media.format,
        )

    def get_path(self, job_id: str) -> Path | None:
        job_directory = self._job_directory(job_id)
        if not job_directory.is_dir():
            return None
        matches = list(job_directory.glob("input.*"))
        return matches[0] if len(matches) == 1 else None

    def delete(self, job_id: str) -> None:
        job_directory = self._job_directory(job_id)
        try:
            self._remove_job_directory(job_directory)
        except OSError as error:
            raise AnalysisInputStorageError from error

    def _job_directory(self, job_id: str) -> Path:
        if (
            not job_id
            or job_id in {".", ".."}
            or Path(job_id).name != job_id
            or "/" in job_id
            or "\\" in job_id
        ):
            raise AnalysisInputStorageError("Invalid storage key")
        return self.root / job_id

    @staticmethod
    def _safe_filename(original_filename: str) -> str:
        return original_filename.replace("\\", "/").rsplit("/", 1)[-1]

    @staticmethod
    def _remove_job_directory(job_directory: Path) -> None:
        if job_directory.exists():
            rmtree(job_directory)


def _inspector_from_duration_probe(
    probe: Callable[[Path], float],
) -> Callable[[Path], MediaInfo]:
    """Adapt a duration-only probe (a test seam) to the inspector interface.

    The format is taken from the extension, so the mismatch check passes.
    """

    def inspect(path: Path) -> MediaInfo:
        return MediaInfo(
            EXTENSION_FORMATS[path.suffix.lower()],
            probe(path),
            path.stat().st_size,
        )

    return inspect
