"""How the API is hosted: local dev server or AWS Lambda.

The mode is set explicitly (CHORDSYNC_API_HOSTING_MODE), so a bad deployment
fails at startup instead of quietly running local-only behaviour.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping

from backend.api.app.cognito_auth import _CLIENT_PATTERN, issuer_for


LAMBDA_WRITABLE_ROOT = Path("/tmp")
DEFAULT_LAMBDA_STAGING_ROOT = LAMBDA_WRITABLE_ROOT / "chordsync-api"
DEFAULT_UPLOAD_URL_TTL_SECONDS = 600
MIN_UPLOAD_URL_TTL_SECONDS = 60
MAX_UPLOAD_URL_TTL_SECONDS = 3600


class HostingMode(str, Enum):
    LOCAL = "local"
    LAMBDA = "lambda"


class HostingConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApiHostingConfig:
    mode: HostingMode
    # Lambda mode only; local mode uses STORAGE_PATH.
    staging_root: Path = DEFAULT_LAMBDA_STAGING_ROOT
    # How long a presigned upload URL stays valid.
    upload_url_ttl_seconds: int = DEFAULT_UPLOAD_URL_TTL_SECONDS
    # SSM parameter with the token verifiers. Required when hosted.
    demo_token_parameter: str | None = None
    # Local only: the verifier document inline. Ignored when hosted.
    demo_token_verifier_document: str | None = None
    # Cognito sign-in: the user pool id (such as "ap-southeast-1_AbCdEf123") and
    # the app client id. Both are set, or neither is.
    cognito_user_pool_id: str | None = None
    cognito_client_id: str | None = None

    @property
    def auth_enabled(self) -> bool:
        return self.is_hosted or bool(
            self.demo_token_parameter
            or self.demo_token_verifier_document
            or self.cognito_user_pool_id
        )

    @property
    def is_hosted(self) -> bool:
        return self.mode is HostingMode.LAMBDA

    @classmethod
    def from_env(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> ApiHostingConfig:
        values = os.environ if environment is None else environment
        raw_mode = values.get("CHORDSYNC_API_HOSTING_MODE", "local").strip().casefold()
        try:
            mode = HostingMode(raw_mode)
        except ValueError as error:
            raise HostingConfigurationError(
                "CHORDSYNC_API_HOSTING_MODE must be 'local' or 'lambda'"
            ) from error
        if mode is HostingMode.LOCAL:
            return cls(
                mode,
                demo_token_parameter=_parameter_name(
                    values.get("CHORDSYNC_DEMO_TOKEN_PARAMETER"), required=False
                ),
                demo_token_verifier_document=(
                    values.get("CHORDSYNC_DEMO_TOKEN_VERIFIER") or None
                ),
                **_cognito_settings(values),
            )

        runtime_mode = values.get("CHORDSYNC_RUNTIME_MODE", "").strip().casefold()
        if runtime_mode != "aws":
            # The local runtime runs analysis in-process, never in Lambda.
            raise HostingConfigurationError(
                "Lambda hosting requires CHORDSYNC_RUNTIME_MODE=aws"
            )
        staging_root = lambda_staging_root(
            values.get("CHORDSYNC_API_STAGING_ROOT", str(DEFAULT_LAMBDA_STAGING_ROOT))
        )
        return cls(
            mode,
            staging_root,
            upload_url_ttl_seconds=_upload_ttl(
                values.get("CHORDSYNC_UPLOAD_URL_TTL_SECONDS")
            ),
            # The demo-token parameter stays optional once Cognito is set up, so
            # demo tokens can be switched off for good. Never both absent.
            demo_token_parameter=_parameter_name(
                values.get("CHORDSYNC_DEMO_TOKEN_PARAMETER"),
                required=not _cognito_settings(values),
            ),
            **_cognito_settings(values),
        )


def _cognito_settings(values: Mapping[str, str]) -> dict[str, str]:
    """The two Cognito settings, validated, or an empty dict if neither is set."""
    pool = (values.get("CHORDSYNC_COGNITO_USER_POOL_ID") or "").strip()
    client = (values.get("CHORDSYNC_COGNITO_CLIENT_ID") or "").strip()
    if not pool and not client:
        return {}
    if not pool or not client:
        raise HostingConfigurationError(
            "CHORDSYNC_COGNITO_USER_POOL_ID and CHORDSYNC_COGNITO_CLIENT_ID go together"
        )
    try:
        issuer_for(pool)
    except ValueError as error:
        raise HostingConfigurationError("CHORDSYNC_COGNITO_USER_POOL_ID is not valid") from error
    if not _CLIENT_PATTERN.fullmatch(client):
        raise HostingConfigurationError("CHORDSYNC_COGNITO_CLIENT_ID is not valid")
    return {"cognito_user_pool_id": pool, "cognito_client_id": client}


_PARAMETER_NAME = re.compile(r"^/?[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)*$")


def _parameter_name(value: str | None, *, required: bool) -> str | None:
    name = (value or "").strip()
    if not name:
        if required:
            # Never fall back to no authentication.
            raise HostingConfigurationError(
                "Lambda hosting requires CHORDSYNC_DEMO_TOKEN_PARAMETER"
            )
        return None
    if (
        len(name) > 1011
        or not _PARAMETER_NAME.fullmatch(name)
        or any(part in {".", ".."} for part in name.split("/"))
    ):
        raise HostingConfigurationError("CHORDSYNC_DEMO_TOKEN_PARAMETER is not a valid name")
    return name


def _upload_ttl(value: str | None) -> int:
    if value is None or not value.strip():
        return DEFAULT_UPLOAD_URL_TTL_SECONDS
    try:
        seconds = int(value.strip())
    except ValueError as error:
        raise HostingConfigurationError(
            "CHORDSYNC_UPLOAD_URL_TTL_SECONDS must be a whole number"
        ) from error
    if not MIN_UPLOAD_URL_TTL_SECONDS <= seconds <= MAX_UPLOAD_URL_TTL_SECONDS:
        raise HostingConfigurationError(
            "CHORDSYNC_UPLOAD_URL_TTL_SECONDS must be between "
            f"{MIN_UPLOAD_URL_TTL_SECONDS} and {MAX_UPLOAD_URL_TTL_SECONDS}"
        )
    return seconds


def lambda_staging_root(value: str) -> Path:
    """Validate a staging root: absolute, normalised, and strictly under /tmp."""
    if not value or "\x00" in value:
        raise HostingConfigurationError("API staging root is empty or invalid")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise HostingConfigurationError("API staging root must be an absolute path under /tmp")
    if path == LAMBDA_WRITABLE_ROOT or not path.is_relative_to(LAMBDA_WRITABLE_ROOT):
        raise HostingConfigurationError("API staging root must be a directory under /tmp")
    return path
