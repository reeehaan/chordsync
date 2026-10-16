"""Direct-to-S3 uploads: sign, inspect, read and delete one source object.

The API never receives audio. It signs a PUT for a server-chosen key, then
checks and reads back what the client stored.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Protocol

from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactRole,
    ArtifactStorage,
)
from backend.api.app.services.aws_errors import (
    CloudProviderError,
    CloudProviderErrorKind,
    provider_error_code,
    translate_provider_error,
)

logger = logging.getLogger(__name__)

SSE_S3 = "AES256"
# Every upload carries this tag, so a lifecycle rule can expire abandoned
# uploads without touching other objects.
UPLOAD_TAG = "chordsync-upload=presigned"
ACCEPTED_ENCRYPTIONS = frozenset({"AES256", "aws:kms"})


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    method: str
    # Headers the client must send exactly (they are signed).
    headers: dict[str, str]


@dataclass(frozen=True)
class SourceObjectInfo:
    size_bytes: int
    content_type: str | None
    server_side_encryption: str | None


class SourceUploadStore(Protocol):
    def presign_put(
        self,
        key: ArtifactKey,
        *,
        content_type: str,
        content_length: int,
        expires_in: int,
    ) -> PresignedUpload: ...

    def head(self, key: ArtifactKey) -> SourceObjectInfo | None: ...

    def open(self, key: ArtifactKey) -> BinaryIO: ...

    def delete(self, key: ArtifactKey) -> None: ...


class S3SourceUploadStore:
    """Private-bucket adapter. Uses only PutObject (via the signed URL),
    HeadObject/GetObject, and DeleteObject on the exact key."""

    def __init__(self, client: Any, bucket: str) -> None:
        if not bucket.strip():
            raise CloudProviderError(
                CloudProviderErrorKind.CONFIGURATION,
                "S3 bucket configuration is required",
            )
        self._client = client
        self._bucket = bucket

    def presign_put(
        self,
        key: ArtifactKey,
        *,
        content_type: str,
        content_length: int,
        expires_in: int,
    ) -> PresignedUpload:
        # Content-Type, Content-Length and encryption are signed, so S3 rejects
        # an upload that differs from what was declared.
        try:
            url = self._client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key.value,
                    "ContentType": content_type,
                    "ContentLength": content_length,
                    "ServerSideEncryption": SSE_S3,
                    "Tagging": UPLOAD_TAG,
                },
                ExpiresIn=expires_in,
                HttpMethod="PUT",
            )
        except Exception as error:
            raise translate_provider_error(error) from error
        return PresignedUpload(
            url=url,
            method="PUT",
            headers={
                "Content-Type": content_type,
                "Content-Length": str(content_length),
                "x-amz-server-side-encryption": SSE_S3,
                "x-amz-tagging": UPLOAD_TAG,
            },
        )

    def head(self, key: ArtifactKey) -> SourceObjectInfo | None:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key.value)
        except Exception as error:
            code = provider_error_code(error)
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            if code in {"403", "AccessDenied", "Forbidden"}:
                # Only a 404 means "not uploaded". A 403 is a permission or
                # config problem, reported as 503 and logged.
                logger.error("source object access denied (%s): check the API role", code)
                raise CloudProviderError(
                    CloudProviderErrorKind.CONFIGURATION,
                    "Source object access was denied",
                ) from error
            raise translate_provider_error(error) from error
        return SourceObjectInfo(
            size_bytes=int(response["ContentLength"]),
            content_type=response.get("ContentType"),
            server_side_encryption=response.get("ServerSideEncryption"),
        )

    def open(self, key: ArtifactKey) -> BinaryIO:
        try:
            return self._client.get_object(Bucket=self._bucket, Key=key.value)["Body"]
        except Exception as error:
            if provider_error_code(error) in {"NoSuchKey", "404", "NotFound"}:
                raise CloudProviderError(
                    CloudProviderErrorKind.NOT_FOUND, "Cloud object was not found"
                ) from error
            raise translate_provider_error(error) from error

    def delete(self, key: ArtifactKey) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key.value)
        except Exception as error:
            raise translate_provider_error(error) from error


@dataclass
class _StoredObject:
    data: bytes
    content_type: str | None
    server_side_encryption: str | None


@dataclass
class InMemorySourceUploadStore:
    """Test double: records signing requests and holds "uploaded" objects."""

    # Optional store that mirrors uploads, so other fakes can see them.
    mirror: ArtifactStorage | None = None
    objects: dict[str, _StoredObject] = field(default_factory=dict)
    presign_requests: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    def presign_put(
        self,
        key: ArtifactKey,
        *,
        content_type: str,
        content_length: int,
        expires_in: int,
    ) -> PresignedUpload:
        self.presign_requests.append(
            {
                "key": key.value,
                "content_type": content_type,
                "content_length": content_length,
                "expires_in": expires_in,
            }
        )
        return PresignedUpload(
            url=f"https://upload.invalid/{key.value}?signature=test",
            method="PUT",
            headers={
                "Content-Type": content_type,
                "Content-Length": str(content_length),
                "x-amz-server-side-encryption": SSE_S3,
                "x-amz-tagging": UPLOAD_TAG,
            },
        )

    def client_upload(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        server_side_encryption: str | None = SSE_S3,
    ) -> None:
        """What the client's PUT to the signed URL would leave in the bucket."""
        self.objects[key] = _StoredObject(data, content_type, server_side_encryption)
        if self.mirror is not None:
            self.mirror.put_bytes(
                ArtifactKey(ArtifactRole.SOURCE_UPLOAD, key),
                data,
                content_type=content_type or "application/octet-stream",
            )

    def head(self, key: ArtifactKey) -> SourceObjectInfo | None:
        stored = self.objects.get(key.value)
        if stored is None:
            return None
        return SourceObjectInfo(
            len(stored.data), stored.content_type, stored.server_side_encryption
        )

    def open(self, key: ArtifactKey) -> BinaryIO:
        import io

        stored = self.objects.get(key.value)
        if stored is None:
            raise CloudProviderError(
                CloudProviderErrorKind.NOT_FOUND, "Cloud object was not found"
            )
        return io.BytesIO(stored.data)

    def delete(self, key: ArtifactKey) -> None:
        self.objects.pop(key.value, None)
        if self.mirror is not None:
            self.mirror.delete(key)
        self.deleted.append(key.value)
