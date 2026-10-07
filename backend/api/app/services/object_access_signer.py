from __future__ import annotations

from enum import Enum
from typing import Protocol

from backend.api.app.services.artifact_storage import ArtifactKey


class ObjectAccessOperation(str, Enum):
    UPLOAD = "upload"
    DOWNLOAD = "download"


class ObjectAccessSigner(Protocol):
    """Future API-level seam for short-lived access to private objects."""

    def sign(
        self,
        key: ArtifactKey,
        *,
        operation: ObjectAccessOperation,
        expires_in_seconds: int,
        content_type: str | None = None,
    ) -> str: ...
