from dataclasses import dataclass
from pathlib import Path
from shutil import rmtree
from typing import BinaryIO, Protocol


SUPPORTED_AUDIO_EXTENSIONS = frozenset({".wav", ".mp3", ".m4a"})
MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024
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


class AnalysisInputStorageError(Exception):
    pass


@dataclass(frozen=True)
class AnalysisInputMetadata:
    storage_key: str
    original_filename: str
    extension: str
    content_type: str | None
    size_bytes: int


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
    ) -> None:
        self.root = root
        self.max_size_bytes = max_size_bytes

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
        if not job_id or Path(job_id).name != job_id or "/" in job_id or "\\" in job_id:
            raise AnalysisInputStorageError("Invalid storage key")
        return self.root / job_id

    @staticmethod
    def _safe_filename(original_filename: str) -> str:
        return original_filename.replace("\\", "/").rsplit("/", 1)[-1]

    @staticmethod
    def _remove_job_directory(job_directory: Path) -> None:
        if job_directory.exists():
            rmtree(job_directory)
