"""The signed-in user's own profile. Only accounts have one, and only the
owner can read or change it: the owner is always the token's subject."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, Response

from backend.api.app.auth import AuthenticatedPrincipal
from backend.api.app.models.analysis_job import AnalysisJobErrorResponse
from backend.api.app.models.profile import ProfileRequest, ProfileResponse
from backend.api.app.routers.analysis_jobs import error_response, get_principal
from backend.api.app.services.aws_errors import (
    CloudProviderError,
    CloudProviderErrorKind,
)
from backend.api.app.services.cloud_job_repository import is_catalogue_owner
from backend.api.app.services.profile_store import (
    DynamoDbProfileStore,
    ProfileStore,
    StoredProfile,
)

router = APIRouter(
    prefix="/me", tags=["Your profile"], dependencies=[Depends(get_principal)]
)

_ERRORS = {
    403: {"model": AnalysisJobErrorResponse},
    404: {"model": AnalysisJobErrorResponse},
    503: {"model": AnalysisJobErrorResponse},
}


@lru_cache(maxsize=1)
def _profile_store() -> ProfileStore:
    table = (os.environ.get("CHORDSYNC_DYNAMODB_PROFILE_TABLE") or "").strip()
    region = (os.environ.get("AWS_REGION") or "").strip()
    if not table or not region:
        raise CloudProviderError(
            CloudProviderErrorKind.CONFIGURATION, "Profile storage is not configured"
        )
    import boto3

    return DynamoDbProfileStore(
        boto3.session.Session(region_name=region).resource("dynamodb").Table(table)
    )


def get_profile_store() -> ProfileStore:
    return _profile_store()


def _owner(principal: AuthenticatedPrincipal | None) -> str | None:
    """The account id, or None for callers who have no profile (demo tokens)."""
    if principal is None or is_catalogue_owner(principal.principal_id):
        return None
    return principal.principal_id


def _response(profile: StoredProfile) -> ProfileResponse:
    return ProfileResponse(
        name=profile.name,
        birth_year=profile.birth_year,
        genres=profile.genres,
        experience=profile.experience,  # type: ignore[arg-type]
        updated_at=profile.updated_at,
    )


@router.get("/profile", response_model=ProfileResponse, responses=_ERRORS)
def read_profile(
    principal: AuthenticatedPrincipal | None = Depends(get_principal),
    store: ProfileStore = Depends(get_profile_store),
) -> ProfileResponse | Response:
    owner = _owner(principal)
    if owner is None:
        return error_response(403, "account_required", "Sign in with an account.")
    profile = store.get(owner)
    if profile is None:
        return error_response(404, "profile_not_found", "There is no profile yet.")
    return _response(profile)


@router.put("/profile", response_model=ProfileResponse, responses=_ERRORS)
def save_profile(
    request: ProfileRequest,
    principal: AuthenticatedPrincipal | None = Depends(get_principal),
    store: ProfileStore = Depends(get_profile_store),
) -> ProfileResponse | Response:
    owner = _owner(principal)
    if owner is None:
        return error_response(403, "account_required", "Sign in with an account.")
    profile = StoredProfile(
        name=request.name,
        birth_year=request.birth_year,
        genres=list(request.genres),
        experience=request.experience,
        updated_at=datetime.now(timezone.utc),
    )
    store.put(owner, profile)
    return _response(profile)
