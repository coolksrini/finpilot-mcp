"""Authentication for the public FinPilot MCP server.

Two credential paths, composed with FastMCP's MultiAuth:

1. OAuth 2.1 (remote connectors — Claude / ChatGPT custom connectors)
   GoogleProvider implements the OAuth Proxy pattern against Google
   (the same identity provider that backs Firebase Auth on the FinPilot
   web app). FastMCP serves the RFC 8414 authorization-server metadata,
   RFC 7591 dynamic client registration, and the PKCE authorization-code
   flow that MCP remote connectors require:

       /.well-known/oauth-authorization-server   metadata discovery
       /.well-known/oauth-protected-resource     resource metadata (RFC 9728)
       /register                                 dynamic client registration
       /authorize   /token   /auth/callback      PKCE code flow (proxied to Google)

   Enabled when FINPILOT_OAUTH_CLIENT_ID / FINPILOT_OAUTH_CLIENT_SECRET /
   FINPILOT_OAUTH_BASE_URL are set (see Settings in config.py).

2. Bearer fp_ API keys (stdio / dev / scripted fallback)
   FinPilotApiKeyVerifier validates fp_ tokens against the FinPilot Auth
   Service (GET /auth/me), which owns fp_ token hashing + Firestore lookup.
   This keeps the existing key path working when the server runs over HTTP
   with OAuth enabled. (In stdio mode no server-side auth applies at all —
   the key is simply forwarded to the gateway, unchanged behavior.)

If OAuth is not configured, build_auth() returns None and the server runs
unauthenticated, exactly as before — credential checks then happen only at
the Auth Service gateway.
"""

from __future__ import annotations

import logging

import httpx
from fastmcp.server.auth import AccessToken, MultiAuth, TokenVerifier
from fastmcp.server.auth.providers.google import GoogleProvider

from finpilot_mcp.config import settings

logger = logging.getLogger(__name__)

# Scopes requested from Google during the proxied OAuth flow.
GOOGLE_OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]


class FinPilotApiKeyVerifier(TokenVerifier):
    """Validates ``fp_`` API keys against the FinPilot Auth Service.

    The Auth Service owns fp_ token hashing and Firestore lookup, so this
    verifier simply calls GET /auth/me with the presented token. A 200 means
    the key is valid and active; anything else rejects it.
    """

    def __init__(self, gateway_url: str | None = None, timeout: float = 10.0):
        super().__init__()
        self.gateway_url = (gateway_url or settings.gateway_url).rstrip("/")
        self.timeout = timeout

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token.startswith("fp_"):
            return None  # not ours — let other verifiers try
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.gateway_url}/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            # Auth Service unreachable — fail closed, but say why.
            logger.error("fp_ key verification failed: Auth Service unreachable at %s: %s", self.gateway_url, exc)
            return None

        if resp.status_code != 200:
            logger.warning("fp_ key rejected by Auth Service (HTTP %s)", resp.status_code)
            return None

        try:
            profile = resp.json()
        except ValueError:
            profile = {}

        return AccessToken(
            token=token,
            client_id=str(profile.get("user_id") or "finpilot-api-key"),
            scopes=[],
            expires_at=None,
            claims={
                "auth_method": "finpilot_api_key",
                "user_id": profile.get("user_id"),
                "email": profile.get("email"),
            },
        )


def build_auth() -> MultiAuth | None:
    """Build the server auth provider from settings.

    Returns None (no server-side auth) unless OAuth is configured — this
    preserves existing stdio/dev behavior where credentials are only checked
    by the Auth Service gateway.
    """
    if not (settings.oauth_client_id and settings.oauth_client_secret and settings.oauth_base_url):
        return None

    google = GoogleProvider(
        client_id=settings.oauth_client_id,
        client_secret=settings.oauth_client_secret,
        base_url=settings.oauth_base_url,
        required_scopes=GOOGLE_OAUTH_SCOPES,
        jwt_signing_key=settings.oauth_jwt_signing_key,
        redirect_path=settings.oauth_redirect_path,
    )

    return MultiAuth(
        server=google,
        verifiers=[FinPilotApiKeyVerifier(settings.gateway_url)],
    )


def resolve_request_credential() -> str | None:
    """Return the fp_ credential to forward to the Auth Service gateway.

    Priority:
    1. The incoming HTTP request's own ``Bearer fp_...`` header (remote/HTTP
       mode — each caller's key is forwarded, not the server's).
    2. FINPILOT_API_KEY from the environment (stdio / dev mode).

    OAuth (Google) access tokens are NOT forwarded — the Auth Service only
    accepts fp_ keys and Firebase ID tokens, so OAuth-authenticated users
    currently reach the gateway as guests unless they also configure an
    fp_ key.
    """
    try:
        from fastmcp.server.dependencies import get_http_request

        request = get_http_request()
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").removeprefix("bearer ").strip()
        if token.startswith("fp_"):
            return token
    except Exception:
        # Not in an HTTP request context (stdio mode, tests, prompts)
        pass
    return settings.api_key
