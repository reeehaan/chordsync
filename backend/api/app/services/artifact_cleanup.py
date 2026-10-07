from pathlib import Path
from shutil import rmtree

from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactRole,
    ArtifactStorage,
)
from backend.api.app.services.cloud_job import CloudJobRecord


class ArtifactCleanup:
    def __init__(self, workspace_root: Path, storage: ArtifactStorage) -> None:
        self._workspace_root = workspace_root
        self._storage = storage

    def delete_workspace(self, job_id: str) -> None:
        if not job_id or Path(job_id).name != job_id or job_id in {".", ".."}:
            raise ValueError("Invalid job ID")
        workspace = self._workspace_root / job_id
        if workspace.exists():
            rmtree(workspace)

    def delete_transient_source(self, job: CloudJobRecord) -> None:
        if job.source_object_key:
            self._storage.delete(
                ArtifactKey(ArtifactRole.SOURCE_UPLOAD, job.source_object_key)
            )
