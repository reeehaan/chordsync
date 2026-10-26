from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactRole,
    ArtifactStorage,
)



@dataclass(frozen=True)
class MaterializedSource:
    path: Path
    content: bytes


class SourceMaterializer:
    def __init__(self, storage: ArtifactStorage, workspace_root: Path) -> None:
        self._storage = storage
        self._workspace_root = workspace_root

    def materialize(
        self,
        job_id: str,
        source_object_key: str,
        *,
        expected_etag: str | None = None,
    ) -> MaterializedSource:
        """Download the uploaded file for analysis.

        With ``expected_etag`` (recorded when the API validated the upload) the
        file is read only if it still has that exact version; a replaced file
        raises SourceChangedError instead of being analysed.
        """
        if not job_id or Path(job_id).name != job_id or job_id in {".", ".."}:
            raise ValueError("Invalid job ID")
        key = ArtifactKey(ArtifactRole.SOURCE_UPLOAD, source_object_key)
        extension = PurePosixPath(source_object_key).suffix.casefold()
        if extension not in {".wav", ".mp3", ".m4a"}:
            raise ValueError("Unsupported source artifact extension")
        content = (
            self._storage.read_bytes(key, if_match=expected_etag)
            if expected_etag
            else self._storage.read_bytes(key)
        )
        workspace = self._workspace_root / job_id
        workspace.mkdir(parents=True, exist_ok=True)
        path = workspace / f"input{extension}"
        temporary = workspace / f".input{extension}.part"
        temporary.write_bytes(content)
        temporary.replace(path)
        return MaterializedSource(path=path, content=content)
