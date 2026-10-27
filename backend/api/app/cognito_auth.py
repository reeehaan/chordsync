"""Cognito access-token verification for the hosted API.

A signed-in user presents the Cognito *access token* as a bearer token. This
module checks it and returns an AuthenticatedPrincipal whose id is
"cognito:<sub>". Only the standard library is used, so the internet-facing
image gets no new dependency.

What is checked, in this order, and any failure is the same "not signed in":
the token is three base64url parts; the header says RS256 and names a key id we
know; the RSA signature is valid for that key; the issuer is our user pool; the
token is an access token for our app client; it has not expired; the subject
is a UUID. Nothing else is trusted.

The public keys (JWKS) are fetched over https from the pool's own address,
cached, and refreshed when an unknown key id appears (key rotation), at most
once every few minutes.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Mapping

from backend.api.app.auth import AuthenticatedPrincipal, AuthUnavailableError

logger = logging.getLogger(__name__)

JWKS_CACHE_SECONDS = 3600
JWKS_UNKNOWN_KEY_REFRESH_SECONDS = 300
JWKS_MAX_STALE_SECONDS = 24 * 3600
JWKS_TIMEOUT_SECONDS = 5
JWKS_MAX_BYTES = 64 * 1024
MIN_MODULUS_BITS = 2048
CLOCK_SKEW_SECONDS = 60
MAX_TOKEN_LIFETIME_SECONDS = 24 * 3600

_SUB_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_POOL_PATTERN = re.compile(r"^([a-z]{2}-[a-z]+-[0-9])_[A-Za-z0-9]{1,32}$")
_CLIENT_PATTERN = re.compile(r"^[A-Za-z0-9]{1,128}$")
_KID_PATTERN = re.compile(r"^[A-Za-z0-9+/=_-]{1,128}$")
# DER prefix of DigestInfo for SHA-256 (RFC 8017, section 9.2).
_SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


@dataclass(frozen=True)
class RsaKey:
    modulus: int
    exponent: int


KeySet = Mapping[str, RsaKey]


def issuer_for(user_pool_id: str) -> str:
    """The pool's issuer address, from its id such as ``ap-southeast-1_AbCdEf123``."""
    match = _POOL_PATTERN.fullmatch(user_pool_id)
    if match is None:
        raise ValueError("user pool id is malformed")
    return f"https://cognito-idp.{match.group(1)}.amazonaws.com/{user_pool_id}"


def _b64url(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]*", value):
        raise ValueError("not base64url")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def rs256_verify(key: RsaKey, signed: bytes, signature: bytes) -> bool:
    """RSASSA-PKCS1-v1_5 with SHA-256. The whole padded block is compared, so a
    signature with extra bytes or loose padding is rejected."""
    size = (key.modulus.bit_length() + 7) // 8
    if len(signature) != size or key.exponent < 3 or key.exponent % 2 == 0:
        return False
    number = int.from_bytes(signature, "big")
    if number >= key.modulus:
        return False
    decoded = pow(number, key.exponent, key.modulus).to_bytes(size, "big")
    digest_info = _SHA256_PREFIX + hashlib.sha256(signed).digest()
    expected = b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info
    return hmac.compare_digest(decoded, expected)


def parse_jwks(document: bytes) -> dict[str, RsaKey]:
    """Keep only usable RSA signing keys. Anything odd raises ValueError."""
    data = json.loads(document)
    keys: dict[str, RsaKey] = {}
    for item in data["keys"]:
        if item.get("kty") != "RSA" or item.get("use", "sig") != "sig":
            continue
        if item.get("alg", "RS256") != "RS256":
            continue
        kid = item["kid"]
        if not isinstance(kid, str) or not _KID_PATTERN.fullmatch(kid):
            continue
        modulus = int.from_bytes(_b64url(item["n"]), "big")
        exponent = int.from_bytes(_b64url(item["e"]), "big")
        if modulus.bit_length() < MIN_MODULUS_BITS:
            continue
        keys[kid] = RsaKey(modulus, exponent)
    if not keys:
        raise ValueError("no usable keys")
    return keys


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # type: ignore[override]
        return None


def fetch_jwks(issuer: str) -> dict[str, RsaKey]:
    """Download the pool's public keys. https only, no redirects, size-capped."""
    url = f"{issuer}/.well-known/jwks.json"
    if not url.startswith("https://"):
        raise AuthUnavailableError("jwks address is not https")
    opener = urllib.request.build_opener(_NoRedirects)
    try:
        with opener.open(url, timeout=JWKS_TIMEOUT_SECONDS) as response:  # noqa: S310 - https only
            body = response.read(JWKS_MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise AuthUnavailableError(type(error).__name__) from error
    if len(body) > JWKS_MAX_BYTES:
        raise AuthUnavailableError("jwks too large")
    try:
        return parse_jwks(body)
    except (ValueError, KeyError, TypeError, binascii.Error) as error:
        raise AuthUnavailableError("jwks malformed") from error


class JwksCache:
    """Holds the keys. A failed refresh keeps the last good keys for a day."""

    def __init__(
        self,
        load: Callable[[], dict[str, RsaKey]],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._load = load
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, RsaKey] = {}
        self._loaded_at = 0.0
        self._last_attempt = float("-inf")

    def key(self, kid: str) -> RsaKey | None:
        now = self._clock()
        with self._lock:
            fresh = self._keys and now - self._loaded_at < JWKS_CACHE_SECONDS
            if fresh and kid in self._keys:
                return self._keys[kid]
            # Reload when stale, or when the key id is unknown (rotation), but
            # not more than once every few minutes.
            if now - self._last_attempt >= JWKS_UNKNOWN_KEY_REFRESH_SECONDS:
                self._last_attempt = now
                try:
                    self._keys = self._load()
                    self._loaded_at = now
                except AuthUnavailableError as error:
                    if not self._keys or now - self._loaded_at > JWKS_MAX_STALE_SECONDS:
                        self._keys = {}
                        raise
                    logger.warning("jwks refresh failed (%s); keeping the last good keys", error)
            elif not self._keys:
                raise AuthUnavailableError("jwks unavailable")
            return self._keys.get(kid)


class CognitoTokenVerifier:
    def __init__(
        self,
        issuer: str,
        client_id: str,
        keys: JwksCache,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not issuer.startswith("https://") or not _CLIENT_PATTERN.fullmatch(client_id):
            raise ValueError("cognito settings are malformed")
        self._issuer = issuer
        self._client_id = client_id
        self._keys = keys
        self._clock = clock

    def verify(self, token: str) -> AuthenticatedPrincipal | None:
        """The principal for a valid access token, or None. Raises
        AuthUnavailableError only when the keys cannot be loaded."""
        try:
            header_part, payload_part, signature_part = token.split(".")
            header = json.loads(_b64url(header_part))
            payload = json.loads(_b64url(payload_part))
            signature = _b64url(signature_part)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return None
        if not isinstance(header, dict) or not isinstance(payload, dict):
            return None
        if header.get("alg") != "RS256":  # never "none", never HS256
            return None
        kid = header.get("kid")
        if not isinstance(kid, str):
            return None
        key = self._keys.key(kid)
        if key is None:
            return None
        signed = f"{header_part}.{payload_part}".encode("ascii")
        if not rs256_verify(key, signed, signature):
            return None
        return self._principal(payload)

    def _principal(self, claims: dict) -> AuthenticatedPrincipal | None:
        if claims.get("iss") != self._issuer:
            return None
        if claims.get("token_use") != "access" or claims.get("client_id") != self._client_id:
            return None
        now = self._clock()
        expires, issued = claims.get("exp"), claims.get("iat")
        if not _is_number(expires) or now >= expires:
            return None
        if _is_number(issued):
            if issued - CLOCK_SKEW_SECONDS > now or expires - issued > MAX_TOKEN_LIFETIME_SECONDS:
                return None
        not_before = claims.get("nbf")
        if _is_number(not_before) and not_before - CLOCK_SKEW_SECONDS > now:
            return None
        subject = claims.get("sub")
        if not isinstance(subject, str) or not _SUB_PATTERN.fullmatch(subject):
            return None
        return AuthenticatedPrincipal(f"cognito:{subject}")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
