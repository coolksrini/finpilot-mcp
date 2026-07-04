"""Tests for OAuth 2.1 + fp_ API-key auth on the public MCP server.

Covers:
- FinPilotApiKeyVerifier: fp_ key validation against the Auth Service
- build_auth(): enabled/disabled based on settings
- OAuth discovery metadata (RFC 8414) + PKCE advertisement when enabled
- resolve_request_credential(): per-request fp_ forwarding vs env fallback
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from finpilot_mcp.auth import (
    FinPilotApiKeyVerifier,
    build_auth,
    resolve_request_credential,
)
from finpilot_mcp.config import settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_async_client(response: httpx.Response | Exception):
    """Return a patched httpx.AsyncClient whose .get returns/raises `response`."""
    client = MagicMock()
    if isinstance(response, Exception):
        client.get = AsyncMock(side_effect=response)
    else:
        client.get = AsyncMock(return_value=response)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, client


# ---------------------------------------------------------------------------
# FinPilotApiKeyVerifier
# ---------------------------------------------------------------------------


class TestFinPilotApiKeyVerifier:
    async def test_valid_fp_key_returns_access_token(self):
        verifier = FinPilotApiKeyVerifier("https://gateway.example.com")
        resp = httpx.Response(
            200,
            json={"user_id": "user_123", "email": "user@example.com", "api_tokens": []},
            request=httpx.Request("GET", "https://gateway.example.com/auth/me"),
        )
        ctx, client = _mock_async_client(resp)
        with patch("finpilot_mcp.auth.httpx.AsyncClient", return_value=ctx):
            token = await verifier.verify_token("fp_validkey123")

        assert token is not None
        assert token.client_id == "user_123"
        assert token.claims["auth_method"] == "finpilot_api_key"
        assert token.claims["email"] == "user@example.com"
        # Verified against /auth/me with the presented key
        client.get.assert_awaited_once()
        call = client.get.await_args
        assert call.args[0] == "https://gateway.example.com/auth/me"
        assert call.kwargs["headers"]["Authorization"] == "Bearer fp_validkey123"

    async def test_invalid_fp_key_rejected(self):
        verifier = FinPilotApiKeyVerifier("https://gateway.example.com")
        resp = httpx.Response(
            401,
            json={"detail": "Invalid API token"},
            request=httpx.Request("GET", "https://gateway.example.com/auth/me"),
        )
        ctx, _ = _mock_async_client(resp)
        with patch("finpilot_mcp.auth.httpx.AsyncClient", return_value=ctx):
            assert await verifier.verify_token("fp_revoked") is None

    async def test_non_fp_token_passed_over(self):
        """Non-fp_ tokens are not ours — return None without calling the gateway."""
        verifier = FinPilotApiKeyVerifier("https://gateway.example.com")
        with patch("finpilot_mcp.auth.httpx.AsyncClient") as client_cls:
            assert await verifier.verify_token("ya29.google-token") is None
            assert await verifier.verify_token("eyJhbGciOi.firebase.token") is None
        client_cls.assert_not_called()

    async def test_gateway_unreachable_fails_closed(self):
        verifier = FinPilotApiKeyVerifier("https://gateway.example.com")
        ctx, _ = _mock_async_client(httpx.ConnectError("connection refused"))
        with patch("finpilot_mcp.auth.httpx.AsyncClient", return_value=ctx):
            assert await verifier.verify_token("fp_validkey123") is None


# ---------------------------------------------------------------------------
# build_auth
# ---------------------------------------------------------------------------


class TestBuildAuth:
    def test_disabled_without_oauth_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "oauth_client_id", None)
        monkeypatch.setattr(settings, "oauth_client_secret", None)
        monkeypatch.setattr(settings, "oauth_base_url", None)
        assert build_auth() is None

    def test_disabled_with_partial_oauth_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "oauth_client_id", "id.apps.googleusercontent.com")
        monkeypatch.setattr(settings, "oauth_client_secret", None)
        monkeypatch.setattr(settings, "oauth_base_url", None)
        assert build_auth() is None

    def test_enabled_with_full_oauth_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "oauth_client_id", "id.apps.googleusercontent.com")
        monkeypatch.setattr(settings, "oauth_client_secret", "GOCSPX-secret")
        monkeypatch.setattr(settings, "oauth_base_url", "https://mcp.myfinpilot.io")
        auth = build_auth()
        assert auth is not None
        # MultiAuth composition: Google OAuth proxy + fp_ key verifier
        from fastmcp.server.auth import MultiAuth

        assert isinstance(auth, MultiAuth)


# ---------------------------------------------------------------------------
# OAuth discovery metadata (remote connector requirements)
# ---------------------------------------------------------------------------


class TestOAuthDiscovery:
    @pytest.fixture()
    def oauth_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "oauth_client_id", "id.apps.googleusercontent.com")
        monkeypatch.setattr(settings, "oauth_client_secret", "GOCSPX-secret")
        monkeypatch.setattr(settings, "oauth_base_url", "https://mcp.myfinpilot.io")

    async def test_authorization_server_metadata(self, oauth_settings):
        """RFC 8414 metadata must advertise the PKCE code flow endpoints."""
        from fastmcp import FastMCP

        server = FastMCP("test-auth", auth=build_auth())
        app = server.http_app()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://mcp.myfinpilot.io") as client:
            # Lifespan is not run by ASGITransport; discovery routes are pure.
            resp = await client.get("/.well-known/oauth-authorization-server")

        assert resp.status_code == 200
        meta = resp.json()
        assert meta["issuer"].rstrip("/") == "https://mcp.myfinpilot.io"
        assert meta["authorization_endpoint"].startswith("https://mcp.myfinpilot.io")
        assert meta["token_endpoint"].startswith("https://mcp.myfinpilot.io")
        assert "registration_endpoint" in meta  # RFC 7591 DCR
        assert "S256" in meta["code_challenge_methods_supported"]  # PKCE
        assert "authorization_code" in meta["grant_types_supported"]

    async def test_protected_resource_metadata(self, oauth_settings):
        """RFC 9728 protected-resource metadata points at this server."""
        from fastmcp import FastMCP

        server = FastMCP("test-auth", auth=build_auth())
        app = server.http_app()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://mcp.myfinpilot.io") as client:
            resp = await client.get("/.well-known/oauth-protected-resource/mcp")
            if resp.status_code == 404:
                resp = await client.get("/.well-known/oauth-protected-resource")

        assert resp.status_code == 200
        meta = resp.json()
        assert "authorization_servers" in meta

    async def test_mcp_endpoint_requires_auth_when_oauth_enabled(self, oauth_settings):
        """Unauthenticated MCP requests must get a 401 challenge, not content."""
        from fastmcp import FastMCP

        server = FastMCP("test-auth", auth=build_auth())
        app = server.http_app()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://mcp.myfinpilot.io") as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                headers={"Accept": "application/json, text/event-stream"},
            )

        assert resp.status_code == 401
        # WWW-Authenticate header guides clients to discovery (MCP auth spec)
        assert "www-authenticate" in {k.lower() for k in resp.headers}


# ---------------------------------------------------------------------------
# resolve_request_credential
# ---------------------------------------------------------------------------


class TestResolveRequestCredential:
    def test_env_api_key_used_outside_http_context(self, monkeypatch):
        monkeypatch.setattr(settings, "api_key", "fp_env_key")
        assert resolve_request_credential() == "fp_env_key"

    def test_no_credential_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "api_key", None)
        assert resolve_request_credential() is None

    def test_http_request_fp_bearer_takes_priority(self, monkeypatch):
        monkeypatch.setattr(settings, "api_key", "fp_env_key")
        request = MagicMock()
        request.headers = {"authorization": "Bearer fp_request_key"}
        with patch("fastmcp.server.dependencies.get_http_request", return_value=request):
            assert resolve_request_credential() == "fp_request_key"

    def test_http_request_non_fp_bearer_falls_back_to_env(self, monkeypatch):
        """OAuth (Google) tokens are never forwarded to the gateway."""
        monkeypatch.setattr(settings, "api_key", "fp_env_key")
        request = MagicMock()
        request.headers = {"authorization": "Bearer ya29.google-access-token"}
        with patch("fastmcp.server.dependencies.get_http_request", return_value=request):
            assert resolve_request_credential() == "fp_env_key"
