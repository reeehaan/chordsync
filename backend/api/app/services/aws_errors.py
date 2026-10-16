from __future__ import annotations

from enum import Enum


try:
    from botocore.exceptions import (
        ConnectionClosedError,
        ConnectTimeoutError,
        EndpointConnectionError,
        ReadTimeoutError,
    )

    # Network-level failures reach no AWS service, so they carry no error code.
    _TRANSIENT_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
        ConnectionClosedError,
        ConnectTimeoutError,
        EndpointConnectionError,
        ReadTimeoutError,
    )
except ImportError:  # botocore is optional outside AWS runtime mode
    _TRANSIENT_NETWORK_ERRORS = ()


class CloudProviderErrorKind(str, Enum):
    TEMPORARY_UNAVAILABLE = "temporary_unavailable"
    NOT_FOUND = "not_found"
    CONDITIONAL_CONFLICT = "conditional_conflict"
    CONFIGURATION = "configuration_error"
    UNEXPECTED = "unexpected_provider_error"


class CloudProviderError(RuntimeError):
    def __init__(self, kind: CloudProviderErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


_TEMPORARY_CODES = frozenset(
    {
        "InternalError",
        "InternalServerError",
        "ProvisionedThroughputExceededException",
        "RequestLimitExceeded",
        "ServiceUnavailable",
        "SlowDown",
        "Throttling",
        "ThrottlingException",
    }
)


def provider_error_code(error: BaseException) -> str | None:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return None
    details = response.get("Error")
    if not isinstance(details, dict):
        return None
    code = details.get("Code")
    return str(code) if code else None


def translate_provider_error(error: BaseException) -> CloudProviderError:
    if isinstance(error, _TRANSIENT_NETWORK_ERRORS):
        return CloudProviderError(
            CloudProviderErrorKind.TEMPORARY_UNAVAILABLE,
            "Cloud service is temporarily unreachable",
        )
    code = provider_error_code(error)
    if code in _TEMPORARY_CODES:
        return CloudProviderError(
            CloudProviderErrorKind.TEMPORARY_UNAVAILABLE,
            "Cloud storage is temporarily unavailable",
        )
    if code in {"NoSuchKey", "NotFound", "ResourceNotFoundException"}:
        return CloudProviderError(
            CloudProviderErrorKind.NOT_FOUND,
            "Cloud object was not found",
        )
    if code in {"AccessDenied", "AccessDeniedException", "InvalidAccessKeyId"}:
        return CloudProviderError(
            CloudProviderErrorKind.CONFIGURATION,
            "Cloud access is not configured correctly",
        )
    return CloudProviderError(
        CloudProviderErrorKind.UNEXPECTED,
        "Cloud provider request failed",
    )
