"""Bearer-token authentication for the hosted API.

Routes only see an AuthenticatedPrincipal. The demo-token check sits behind
TokenVerifier, so it can be swapped for Cognito later.

The server keeps only SHA-256 hashes of the tokens, in one SSM parameter:

    {"version": 1, "tokens": [{"id": "tester-1", "sha256": "<64 hex>"}]}

A token's owner id is "demo:<id>".
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

logger = logging.getLogger(__name__)

MAX_TOKEN_CHARS = 256
MIN_TOKEN_CHARS = 16
DEFAULT_CACHE_SECONDS = 300
DEFAULT_FAILURE_BACKOFF_SECONDS = 5
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~+/=-]+$")
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_DOCUMENT_BYTES = 8 * 1024
_MAX_ENTRIES = 50


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Who is calling. ``principal_id`` is stable and never a secret."""

    principal_id: str


class AuthenticationRequiredError(Exception):
    """Missing, malformed, or unrecognised credentials (always the same 401)."""


class AuthUnavailableError(Exception):
    """The verifier could not be loaded or is malformed: an infrastructure fault
    (503), never a statement about the caller's credentials."""


class TokenVerifier(Protocol):
    def verify(self, token: str) -> AuthenticatedPrincipal | None: ...


class VerifierProvider(Protocol):
    def get(self) -> TokenVerifier:
        """Return a verifier, or raise ``AuthUnavailableError``."""
        ...


# --- bearer header ---


def bearer_token(authorization: str | None) -> str:
    """Return the token from "Authorization: Bearer <token>".

    Every bad header raises the same error, so callers can't tell the cases apart.
    """
    if not authorization:
        raise AuthenticationRequiredError
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].casefold() != "bearer":
        raise AuthenticationRequiredError
    token = parts[1]
    if not MIN_TOKEN_CHARS <= len(token) <= MAX_TOKEN_CHARS or not _TOKEN_PATTERN.fullmatch(token):
        raise AuthenticationRequiredError
    return token


def authenticate(authorization: str | None, provider: VerifierProvider) -> AuthenticatedPrincipal:
    token = bearer_token(authorization)
    principal = provider.get().verify(token)
    if principal is None:
        raise AuthenticationRequiredError
    return principal


# --- demo-token verifier ---


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class DemoTokenVerifier:
    def __init__(self, entries: Mapping[str, str]) -> None:
        """``entries`` maps a token label (``id``) to its SHA-256 hex verifier."""
        if not entries:
            raise AuthUnavailableError("no tokens configured")
        self._entries = [(label, bytes.fromhex(digest)) for label, digest in entries.items()]

    @classmethod
    def from_document(cls, document: str) -> DemoTokenVerifier:
        """Parse the verifier document. Any problem raises AuthUnavailableError,
        without echoing the document.
        """
        if not isinstance(document, str) or len(document.encode("utf-8")) > _MAX_DOCUMENT_BYTES:
            raise AuthUnavailableError("verifier document is unusable")
        try:
            data = json.loads(document)
        except ValueError as error:
            raise AuthUnavailableError("verifier document is not JSON") from error
        if not isinstance(data, dict) or data.get("version") != 1:
            raise AuthUnavailableError("verifier document version is unsupported")
        tokens = data.get("tokens")
        if not isinstance(tokens, list) or not 1 <= len(tokens) <= _MAX_ENTRIES:
            raise AuthUnavailableError("verifier document has no usable tokens")
        entries: dict[str, str] = {}
        for item in tokens:
            if not isinstance(item, dict):
                raise AuthUnavailableError("verifier entry is malformed")
            label, digest = item.get("id"), item.get("sha256")
            if (
                not isinstance(label, str)
                or not _ID_PATTERN.fullmatch(label)
                or not isinstance(digest, str)
                or not _HEX_SHA256.fullmatch(digest)
                or label in entries
            ):
                raise AuthUnavailableError("verifier entry is malformed")
            entries[label] = digest
        return cls(entries)

    def verify(self, token: str) -> AuthenticatedPrincipal | None:
        presented = hashlib.sha256(token.encode("ascii", "replace")).digest()
        match: str | None = None
        for label, digest in self._entries:  # no early exit, so timing doesn't leak
            if hmac.compare_digest(presented, digest) and match is None:
                match = label
        return AuthenticatedPrincipal(f"demo:{match}") if match is not None else None


# --- providers ---


class StaticVerifierProvider:
    """A fixed verifier (inline local configuration and tests)."""

    def __init__(self, verifier: TokenVerifier) -> None:
        self._verifier = verifier

    def get(self) -> TokenVerifier:
        return self._verifier


class CachedVerifierProvider:
    """Loads the verifier document once and caches it, instead of once per request.

    The cache refreshes after cache_seconds. If a refresh fails, the last good
    verifier keeps working. If nothing is loaded yet, the failure raises
    AuthUnavailableError and is remembered briefly to avoid hammering SSM.
    """

    def __init__(
        self,
        load_document: Callable[[], str],
        *,
        cache_seconds: float = DEFAULT_CACHE_SECONDS,
        failure_backoff_seconds: float = DEFAULT_FAILURE_BACKOFF_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._load_document = load_document
        self._cache_seconds = cache_seconds
        self._backoff = failure_backoff_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._verifier: DemoTokenVerifier | None = None
        self._expires_at = 0.0
        self._failed_until = 0.0

    def get(self) -> TokenVerifier:
        now = self._clock()
        verifier = self._verifier
        if verifier is not None and now < self._expires_at:
            return verifier
        with self._lock:
            now = self._clock()
            if self._verifier is not None and now < self._expires_at:
                return self._verifier
            if now < self._failed_until:
                if self._verifier is not None:
                    return self._verifier
                raise AuthUnavailableError("verifier unavailable")
            try:
                loaded = DemoTokenVerifier.from_document(self._load_document())
            except AuthUnavailableError as error:
                return self._failed(now, error)
            except Exception as error:  # only the error type is logged
                return self._failed(now, AuthUnavailableError(type(error).__name__))
            self._verifier = loaded
            self._expires_at = now + self._cache_seconds
            return loaded

    def _failed(self, now: float, error: AuthUnavailableError) -> TokenVerifier:
        self._failed_until = now + self._backoff
        if self._verifier is not None:
            logger.warning("auth verifier refresh failed (%s); keeping the last good one", error)
            return self._verifier
        logger.error("auth verifier unavailable (%s)", error)
        raise AuthUnavailableError("verifier unavailable") from error


class SsmDocumentLoader:
    """Reads one SSM parameter (``ssm:GetParameter`` on exactly that name)."""

    def __init__(self, client: Any, parameter_name: str) -> None:
        self._client = client
        self._name = parameter_name

    def __call__(self) -> str:
        response = self._client.get_parameter(Name=self._name, WithDecryption=True)
        return str(response["Parameter"]["Value"])
