"""Shared fixtures for authenticated hosted-API tests. Tokens here are test-only."""

from __future__ import annotations

from backend.api.app import auth
from backend.api.app.routers import analysis_jobs

TOKEN_A = "test-token-A-0123456789abcdefghijklmnopqrstuv"
TOKEN_B = "test-token-B-0123456789abcdefghijklmnopqrstuv"
HEADERS_A = {"Authorization": f"Bearer {TOKEN_A}"}
HEADERS_B = {"Authorization": f"Bearer {TOKEN_B}"}
OWNER_A = "demo:tester-a"
OWNER_B = "demo:tester-b"
PARAMETER = "/chordsync/test/demo-tokens"


def verifier() -> auth.DemoTokenVerifier:
    return auth.DemoTokenVerifier(
        {
            "tester-a": auth.token_sha256(TOKEN_A),
            "tester-b": auth.token_sha256(TOKEN_B),
        }
    )


def install(monkeypatch, provider: auth.VerifierProvider | None = None) -> auth.VerifierProvider:
    """Make the hosted app authenticate against two known test principals."""
    provider = provider or auth.StaticVerifierProvider(verifier())
    monkeypatch.setattr(analysis_jobs, "_auth_provider", lambda _hosting: provider)
    return provider
