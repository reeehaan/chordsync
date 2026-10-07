from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Protocol


class ArtifactRole(str, Enum):
    SOURCE_UPLOAD = "source_upload"
    PLAYBACK_AUDIO = "playback_audio"
    TIMELINE_RESULT = "timeline_result"
    OPTIONAL_DEBUG_ARTIFACT = "optional_debug_artifact"


@dataclass(frozen=True)
class ArtifactKey:
    role: ArtifactRole
    value: str

    def __post_init__(self) -> None:
        path = PurePosixPath(self.value)
        if (
            not self.value
            or self.value.startswith("/")
            or "\\" in self.value
            or ".." in path.parts
            or "." in path.parts
        ):
            raise ValueError("Artifact key must be a safe relative object key")


@dataclass(frozen=True)
class ArtifactMetadata:
    key: ArtifactKey
    content_type: str
    size_bytes: int
    sha256: str


class ArtifactStorage(Protocol):
    def put_bytes(
        self,
        key: ArtifactKey,
        content: bytes,
        *,
        content_type: str,
    ) -> ArtifactMetadata: ...

    def read_bytes(self, key: ArtifactKey) -> bytes: ...

    def exists(self, key: ArtifactKey) -> bool: ...

    def delete(self, key: ArtifactKey) -> None: ...


class ArtifactKeyFactory:
    def __init__(self, owner_id: str | None = None) -> None:
        self._owner_id = _safe_segment(owner_id) if owner_id else None

    def source(self, job_id: str, extension: str) -> ArtifactKey:
        return ArtifactKey(
            ArtifactRole.SOURCE_UPLOAD,
            f"{self._prefix(job_id)}/source/input{_safe_extension(extension)}",
        )

    def playback(self, job_id: str, extension: str) -> ArtifactKey:
        return ArtifactKey(
            ArtifactRole.PLAYBACK_AUDIO,
            f"{self._prefix(job_id)}/playback/audio{_safe_extension(extension)}",
        )

    def timeline(self, job_id: str) -> ArtifactKey:
        return ArtifactKey(
            ArtifactRole.TIMELINE_RESULT,
            f"{self._prefix(job_id)}/results/timeline.json",
        )

    def debug(self, job_id: str, name: str) -> ArtifactKey:
        return ArtifactKey(
            ArtifactRole.OPTIONAL_DEBUG_ARTIFACT,
            f"{self._prefix(job_id)}/debug/{_safe_segment(name)}",
        )

    def _prefix(self, job_id: str) -> str:
        safe_job_id = _safe_segment(job_id)
        if self._owner_id:
            return f"users/{self._owner_id}/jobs/{safe_job_id}"
        return f"jobs/{safe_job_id}"


class LocalArtifactStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put_bytes(
        self,
        key: ArtifactKey,
        content: bytes,
        *,
        content_type: str,
    ) -> ArtifactMetadata:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.part")
        try:
            temporary.write_bytes(content)
            temporary.replace(destination)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise
        return ArtifactMetadata(
            key=key,
            content_type=content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def read_bytes(self, key: ArtifactKey) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: ArtifactKey) -> bool:
        return self._path(key).is_file()

    def delete(self, key: ArtifactKey) -> None:
        self._path(key).unlink(missing_ok=True)

    def _path(self, key: ArtifactKey) -> Path:
        return self.root.joinpath(*PurePosixPath(key.value).parts)


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_SAFE_EXTENSIONS = frozenset({".wav", ".mp3", ".m4a"})


def _safe_segment(value: str) -> str:
    if not _SAFE_SEGMENT.fullmatch(value) or value in {".", ".."}:
        raise ValueError("Object-key segment is invalid")
    return value


def _safe_extension(value: str) -> str:
    extension = value.casefold()
    if extension not in _SAFE_EXTENSIONS:
        raise ValueError("Audio extension is unsupported")
    return extension
