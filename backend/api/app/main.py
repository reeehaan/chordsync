import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api.app.auth import AuthenticationRequiredError, AuthUnavailableError
from backend.api.app.hosting import ApiHostingConfig
from backend.api.app.routers.analysis_jobs import (
    error_response,
    get_analysis_application_service,
    get_hosted_analysis_application,
    hosted_router,
)
from backend.api.app.routers.analysis_jobs import router as analysis_jobs_router
from backend.api.app.routers.audio import router as audio_router
from backend.api.app.services.aws_errors import (
    CloudProviderError,
    CloudProviderErrorKind,
)

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _dependency_unavailable(_request: Request, error: Exception) -> JSONResponse:
    """Answer 503 when an AWS dependency is temporarily unreachable.

    Only transient failures are mapped. Anything else (configuration, access,
    unexpected provider errors) is re-raised and behaves as it always did. The
    response never includes the provider's message, endpoint, or ARNs.
    """
    if (
        not isinstance(error, CloudProviderError)
        or error.kind is not CloudProviderErrorKind.TEMPORARY_UNAVAILABLE
    ):
        raise error
    logger.warning("analysis dependency unavailable (%s)", error.kind.value)
    return error_response(
        503,
        "service_unavailable",
        "Analysis service is temporarily unavailable.",
    )


def _unauthorized(_request: Request, _error: Exception) -> JSONResponse:
    """One response for every credential failure, so it cannot be used to guess."""
    return error_response(
        401,
        "unauthorized",
        "Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _auth_unavailable(_request: Request, _error: Exception) -> JSONResponse:
    """The verifier could not be loaded: our fault, so 503, never 401."""
    logger.error("authentication backend unavailable")
    return error_response(
        503,
        "service_unavailable",
        "Analysis service is temporarily unavailable.",
    )


def _invalid_request(_request: Request, _error: Exception) -> JSONResponse:
    """Hosted API: malformed bodies (including multipart audio) are a plain 400."""
    return error_response(400, "invalid_request", "Request is invalid.")


def create_app(hosting: ApiHostingConfig | None = None) -> FastAPI:
    hosting = hosting or ApiHostingConfig.from_env()
    application = FastAPI(
        title="ChordSync API",
        version="0.1.0",
        # Hosted: no public schema or docs pages (the gateway does not route them
        # either). ``application.openapi()`` still works for tests and tooling.
        docs_url=None if hosting.is_hosted else "/docs",
        redoc_url=None if hosting.is_hosted else "/redoc",
        openapi_url=None if hosting.is_hosted else "/openapi.json",
    )

    application.state.hosting = hosting
    application.add_exception_handler(AuthenticationRequiredError, _unauthorized)
    application.add_exception_handler(AuthUnavailableError, _auth_unavailable)

    if hosting.is_hosted:
        # The analysis routes use the cloud-only provider, so the local
        # in-process pipeline is never constructed. The legacy upload route,
        # which writes to local disk unauthenticated, is not registered at all.
        application.dependency_overrides[get_analysis_application_service] = (
            get_hosted_analysis_application
        )
        application.add_exception_handler(CloudProviderError, _dependency_unavailable)
        application.add_exception_handler(RequestValidationError, _invalid_request)
        # Create-upload + confirm; no route accepts audio bytes.
        application.include_router(hosted_router)
    else:
        application.include_router(audio_router)
        application.include_router(analysis_jobs_router)

    @application.get("/")
    def root():
        return {
            "name": "ChordSync API",
            "status": "running",
        }

    @application.get("/health")
    def health():
        return {
            "status": "healthy",
        }

    return application


app = create_app()
