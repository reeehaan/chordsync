"""Install verified model assets from private S3 before the worker polls.

The manifest names assets by role. Each role maps to an approved local root
derived from trusted task configuration, never from manifest data, so a
manifest can only place files where the runtime already expects them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from backend.api.app.services.aws_errors import provider_error_code


logger = logging.getLogger(__name__)

MANIFEST_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 1024 * 1024
_CHUNK_BYTES = 1024 * 1024

_RELEASE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_KEY = re.compile(r"^models/[A-Za-z0-9._/-]+$")

# File names the runtime libraries look up; see docs/cloud/s6-t13-model-bootstrap.md.
WHISPERX_ASR_CACHE_DIR = "models--Systran--faster-whisper-small"
ALIGNMENT_EN_CHECKPOINT = "wav2vec2_fairseq_base_ls960_asr_ls960.pth"
DEMUCS_HTDEMUCS_CHECKPOINT = "955717e8-8726e21a.th"


class ModelBootstrapError(RuntimeError):
    """Raised when model assets cannot be installed and verified."""


class AssetRole(str, Enum):
    BTC_SOURCE = "btc_source"
    BTC_CHECKPOINT = "btc_checkpoint"
    WHISPERX_ASR = "whisperx_asr"
    ALIGNMENT_EN = "alignment_en"
    DEMUCS_HTDEMUCS = "demucs_htdemucs"


REQUIRED_ROLES = frozenset(AssetRole)


class LicenseStatus(str, Enum):
    PERMISSIVE = "permissive"
    APPROVED = "approved"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ManifestFile:
    artifact_key: str
    destination: PurePosixPath
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ManifestAsset:
    asset_name: str
    role: AssetRole
    required: bool
    source_project: str
    source_revision: str
    license_status: LicenseStatus
    files: tuple[ManifestFile, ...]


@dataclass(frozen=True)
class ModelManifest:
    schema_version: int
    release_id: str
    assets: tuple[ManifestAsset, ...]


@dataclass(frozen=True)
class ApprovedDestination:
    """Local root for one role, optionally restricted to exact file names."""

    root: Path
    allowed_files: frozenset[str] | None = None


@dataclass(frozen=True)
class BootstrapReport:
    release_id: str
    files_installed: int
    files_already_present: int
    bytes_verified: int


def manifest_key_for(release_id: str) -> str:
    return f"models/releases/{release_id}/manifest.json"


def approved_destinations(
    environment: Mapping[str, str],
) -> dict[AssetRole, ApprovedDestination]:
    """Map roles to the paths the image's runtime libraries read from."""

    def required_path(name: str) -> Path:
        value = environment.get(name, "").strip()
        if not value or not os.path.isabs(value):
            raise ModelBootstrapError(f"{name} must be an absolute path")
        return Path(value)

    btc_checkpoint = required_path("CHORDSYNC_BTC_CHECKPOINT")
    torch_checkpoints = required_path("TORCH_HOME") / "hub" / "checkpoints"
    return {
        AssetRole.BTC_SOURCE: ApprovedDestination(
            required_path("CHORDSYNC_BTC_SOURCE")
        ),
        AssetRole.BTC_CHECKPOINT: ApprovedDestination(
            btc_checkpoint.parent, frozenset({btc_checkpoint.name})
        ),
        AssetRole.WHISPERX_ASR: ApprovedDestination(
            required_path("HF_HOME") / "hub" / WHISPERX_ASR_CACHE_DIR
        ),
        AssetRole.ALIGNMENT_EN: ApprovedDestination(
            torch_checkpoints, frozenset({ALIGNMENT_EN_CHECKPOINT})
        ),
        AssetRole.DEMUCS_HTDEMUCS: ApprovedDestination(
            torch_checkpoints, frozenset({DEMUCS_HTDEMUCS_CHECKPOINT})
        ),
    }


def parse_manifest(content: bytes, *, expected_release_id: str) -> ModelManifest:
    """Validate manifest structure, safety, and completeness. Fails closed."""
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ModelBootstrapError("Model manifest is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ModelBootstrapError("Model manifest must be a JSON object")
    _require_keys(payload, {"schema_version", "release_id", "assets"}, "manifest")

    if payload["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ModelBootstrapError("Unsupported model manifest schema_version")
    release_id = payload["release_id"]
    if release_id != expected_release_id:
        raise ModelBootstrapError("Model manifest release_id does not match")
    raw_assets = payload["assets"]
    if not isinstance(raw_assets, list) or not raw_assets:
        raise ModelBootstrapError("Model manifest assets must be a non-empty list")

    assets = tuple(_parse_asset(item) for item in raw_assets)
    roles = [asset.role for asset in assets]
    if len(set(roles)) != len(roles):
        raise ModelBootstrapError("Model manifest lists a role more than once")
    missing = REQUIRED_ROLES - {asset.role for asset in assets if asset.required}
    if missing:
        raise ModelBootstrapError(
            "Model manifest is missing required assets: "
            + ", ".join(sorted(role.value for role in missing))
        )
    return ModelManifest(MANIFEST_SCHEMA_VERSION, release_id, assets)


class ModelBootstrap:
    def __init__(
        self,
        s3_client: Any,
        bucket: str,
        *,
        release_id: str,
        manifest_key: str,
        destinations: Mapping[AssetRole, ApprovedDestination],
    ) -> None:
        if not bucket.strip():
            raise ModelBootstrapError("Model bucket is not configured")
        if not _RELEASE_ID.fullmatch(release_id):
            raise ModelBootstrapError("Model release id is invalid")
        if manifest_key != manifest_key_for(release_id):
            raise ModelBootstrapError(
                "Model manifest key must be models/releases/<release>/manifest.json"
            )
        self._s3 = s3_client
        self._bucket = bucket
        self._release_id = release_id
        self._manifest_key = manifest_key
        self._destinations = dict(destinations)

    def run(self) -> BootstrapReport:
        manifest = parse_manifest(
            self._read_manifest(),
            expected_release_id=self._release_id,
        )
        plan = self._plan(manifest)
        installed = present = verified_bytes = 0
        for manifest_file, destination in plan:
            if _matches(destination, manifest_file):
                present += 1
            else:
                self._download_verified(manifest_file, destination)
                installed += 1
            verified_bytes += manifest_file.size_bytes
        logger.info(
            "model bootstrap release=%s installed=%d already_present=%d "
            "verified_bytes=%d",
            manifest.release_id,
            installed,
            present,
            verified_bytes,
        )
        return BootstrapReport(manifest.release_id, installed, present, verified_bytes)

    def _plan(self, manifest: ModelManifest) -> list[tuple[ManifestFile, Path]]:
        plan: list[tuple[ManifestFile, Path]] = []
        seen: set[Path] = set()
        for asset in manifest.assets:
            if asset.license_status is LicenseStatus.UNRESOLVED:
                raise ModelBootstrapError(
                    f"Model asset {asset.asset_name} has unresolved licensing"
                )
            approved = self._destinations.get(asset.role)
            if approved is None:
                raise ModelBootstrapError(f"No approved destination for {asset.role.value}")
            for manifest_file in asset.files:
                destination = _resolve_destination(approved, manifest_file.destination)
                if destination in seen:
                    raise ModelBootstrapError("Model manifest repeats a destination")
                seen.add(destination)
                plan.append((manifest_file, destination))
        return plan

    def _read_manifest(self) -> bytes:
        body = self._get_object(self._manifest_key)
        content = body.read(MAX_MANIFEST_BYTES + 1)
        if len(content) > MAX_MANIFEST_BYTES:
            raise ModelBootstrapError("Model manifest is too large")
        return bytes(content)

    def _download_verified(self, manifest_file: ManifestFile, destination: Path) -> None:
        body = self._get_object(manifest_file.artifact_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent, prefix=".bootstrap-", suffix=".partial"
        )
        temporary = Path(temporary_name)
        try:
            digest = hashlib.sha256()
            size = 0
            with os.fdopen(descriptor, "wb") as output:
                while chunk := body.read(_CHUNK_BYTES):
                    size += len(chunk)
                    if size > manifest_file.size_bytes:
                        raise ModelBootstrapError(
                            f"Model object is larger than expected: {manifest_file.artifact_key}"
                        )
                    digest.update(chunk)
                    output.write(chunk)
            if size != manifest_file.size_bytes:
                raise ModelBootstrapError(
                    f"Model object size mismatch: {manifest_file.artifact_key}"
                )
            if digest.hexdigest() != manifest_file.sha256:
                raise ModelBootstrapError(
                    f"Model object SHA-256 mismatch: {manifest_file.artifact_key}"
                )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _get_object(self, key: str) -> Any:
        try:
            return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"]
        except Exception as error:
            if provider_error_code(error) in {"NoSuchKey", "404", "NotFound"}:
                raise ModelBootstrapError(f"Model object is missing: {key}") from error
            raise ModelBootstrapError(
                f"Model object could not be read: {key} ({type(error).__name__})"
            ) from error


def bootstrap_from_environment(
    environment: Mapping[str, str],
    *,
    bucket: str,
    s3_client: Any,
) -> BootstrapReport:
    release_id = environment.get("CHORDSYNC_MODEL_RELEASE", "").strip()
    manifest_key = environment.get("CHORDSYNC_MODEL_MANIFEST_KEY", "").strip()
    if not release_id or not manifest_key:
        raise ModelBootstrapError(
            "CHORDSYNC_MODEL_RELEASE and CHORDSYNC_MODEL_MANIFEST_KEY are required"
        )
    return ModelBootstrap(
        s3_client,
        bucket,
        release_id=release_id,
        manifest_key=manifest_key,
        destinations=approved_destinations(environment),
    ).run()


def _parse_asset(item: object) -> ManifestAsset:
    if not isinstance(item, dict):
        raise ModelBootstrapError("Model manifest asset must be an object")
    _require_keys(
        item,
        {
            "asset_name",
            "role",
            "required",
            "source_project",
            "source_revision",
            "license_status",
            "files",
        },
        "asset",
    )
    try:
        role = AssetRole(item["role"])
        license_status = LicenseStatus(item["license_status"])
    except ValueError as error:
        raise ModelBootstrapError("Model manifest asset has an unknown role or license") from error
    if not isinstance(item["required"], bool):
        raise ModelBootstrapError("Model manifest asset required must be boolean")
    for field in ("asset_name", "source_project", "source_revision"):
        if not isinstance(item[field], str) or not item[field].strip():
            raise ModelBootstrapError(f"Model manifest asset {field} must be text")
    raw_files = item["files"]
    if not isinstance(raw_files, list) or not raw_files:
        raise ModelBootstrapError("Model manifest asset files must be a non-empty list")
    return ManifestAsset(
        asset_name=item["asset_name"],
        role=role,
        required=item["required"],
        source_project=item["source_project"],
        source_revision=item["source_revision"],
        license_status=license_status,
        files=tuple(_parse_file(entry) for entry in raw_files),
    )


def _parse_file(entry: object) -> ManifestFile:
    if not isinstance(entry, dict):
        raise ModelBootstrapError("Model manifest file must be an object")
    _require_keys(entry, {"artifact_key", "destination", "sha256", "size_bytes"}, "file")
    key = entry["artifact_key"]
    if (
        not isinstance(key, str)
        or not _ARTIFACT_KEY.fullmatch(key)
        or ".." in key.split("/")
        or "//" in key
        or key.endswith("/")
        or key.startswith("models/releases/")
    ):
        raise ModelBootstrapError("Model manifest artifact_key is not an allowed models/ key")
    sha256 = entry["sha256"]
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise ModelBootstrapError("Model manifest sha256 must be 64 lowercase hex digits")
    size = entry["size_bytes"]
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ModelBootstrapError("Model manifest size_bytes must be a non-negative integer")
    return ManifestFile(key, _safe_relative_path(entry["destination"]), sha256, size)


def _safe_relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ModelBootstrapError("Model manifest destination is unsafe")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ModelBootstrapError("Model manifest destination is unsafe")
    return path


def _resolve_destination(approved: ApprovedDestination, relative: PurePosixPath) -> Path:
    if approved.allowed_files is not None and str(relative) not in approved.allowed_files:
        raise ModelBootstrapError("Model manifest destination is not an approved file")
    root = approved.root.resolve()
    destination = (root / relative).resolve()
    if not destination.is_relative_to(root) or destination == root:
        raise ModelBootstrapError("Model manifest destination escapes its approved root")
    return destination


def _matches(destination: Path, manifest_file: ManifestFile) -> bool:
    if not destination.is_file() or destination.stat().st_size != manifest_file.size_bytes:
        return False
    digest = hashlib.sha256()
    with destination.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest() == manifest_file.sha256


def _require_keys(payload: Mapping[str, object], expected: set[str], label: str) -> None:
    keys = set(payload)
    if keys != expected:
        raise ModelBootstrapError(
            f"Model manifest {label} fields must be exactly: {', '.join(sorted(expected))}"
        )
