from pathlib import Path
from shutil import rmtree
from typing import Sequence

from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactRole,
    ArtifactStorage,
)
from backend.api.app.services.cloud_job import CloudJobRecord


class ArtifactCleanup:
    def __init__(
        self,
        workspace_root: Path,
        storage: ArtifactStorage,
        *,
        extra_workspace_roots: Sequence[Path] = (),
    ) -> None:
        """``workspace_root`` holds the downloaded input. A job's analysis also
        works in its own folder under another root (the processor's workspace:
        normalised audio, stems, lyrics, timeline). Pass those as
        ``extra_workspace_roots`` so they go too: a warm worker runs many jobs
        in one container and would otherwise keep every earlier job's files.
        """
        self._workspace_roots = (workspace_root, *extra_workspace_roots)
        self._storage = storage

    def delete_workspace(self, job_id: str) -> None:
        if not job_id or Path(job_id).name != job_id or job_id in {".", ".."}:
            raise ValueError("Invalid job ID")
        for root in self._workspace_roots:
            workspace = root / job_id
            if workspace.exists():
                rmtree(workspace)

    def delete_transient_source(self, job: CloudJobRecord) -> None:
        if job.source_object_key:
            self._storage.delete(
                ArtifactKey(ArtifactRole.SOURCE_UPLOAD, job.source_object_key)
            )
