from __future__ import annotations

import hashlib
from typing import Any

from backend.api.app.services.artifact_storage import (
    ArtifactKey,
    ArtifactMetadata,
)
from backend.api.app.services.aws_errors import (
    CloudProviderError,
    CloudProviderErrorKind,
    provider_error_code,
    translate_provider_error,
)


class S3ArtifactStorage:
    """Private S3 adapter; bucket creation and URL generation are out of scope."""

    def __init__(
        self,
        client: Any,
        bucket: str,
        *,
        server_side_encryption: str = "AES256",
    ) -> None:
        if not bucket.strip():
            raise CloudProviderError(
                CloudProviderErrorKind.CONFIGURATION,
                "S3 bucket configuration is required",
            )
        self._client = client
        self._bucket = bucket
        self._encryption = server_side_encryption

    def put_bytes(
        self,
        key: ArtifactKey,
        content: bytes,
        *,
        content_type: str,
    ) -> ArtifactMetadata:
        checksum = hashlib.sha256(content).hexdigest()
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key.value,
                Body=content,
                ContentType=content_type,
                Metadata={"sha256": checksum},
                ServerSideEncryption=self._encryption,
            )
        except Exception as error:
            raise translate_provider_error(error) from error
        return ArtifactMetadata(key, content_type, len(content), checksum)

    def read_bytes(self, key: ArtifactKey) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key.value)
            body = response["Body"]
            return body.read() if hasattr(body, "read") else bytes(body)
        except Exception as error:
            if provider_error_code(error) in {"NoSuchKey", "NotFound"}:
                raise CloudProviderError(
                    CloudProviderErrorKind.NOT_FOUND,
                    "Cloud object was not found",
                ) from error
            raise translate_provider_error(error) from error

    def exists(self, key: ArtifactKey) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key.value)
            return True
        except Exception as error:
            if provider_error_code(error) in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise translate_provider_error(error) from error

    def delete(self, key: ArtifactKey) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key.value)
        except Exception as error:
            raise translate_provider_error(error) from error
