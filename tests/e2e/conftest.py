"""E2E test configuration for finpilot-mcp against deployed Cloud Run services.

Tests use the FastMCP in-process client — no subprocess needed for the MCP layer.
Tools make real HTTPS calls through the deployed auth service → orchestrator chain.

Two access modes:
    Guest       No API key — stateless calculation tools only
    Authenticated  fp_... token — full personal finance tools + PDF analysis

Prerequisites (authenticated tests only):
    Generate an API token at https://finpilot-dev.web.app → dashboard → API Tokens

Environment variables:
    FINPILOT_GATEWAY_URL    Auth Service URL (default: dev Cloud Run URL)
    FINPILOT_API_KEY        fp_... token (optional — omit for guest-only tests)
    CREDIT_REPORT_PDF       Absolute path to a CIBIL / Experian / CRIF PDF
    CAS_PDF                 Absolute path to a CAS statement PDF (NSDL/CDSL/CAMS)

Run examples:
    # Guest-mode tests (introspection + inline data tools — no token needed)
    uv run pytest tests/e2e/ -v -m "not authenticated"

    # Full suite (guest + authenticated)
    FINPILOT_API_KEY=fp_your_token \\
    CREDIT_REPORT_PDF=/path/to/cibil.pdf \\
    CAS_PDF=/path/to/cas.pdf \\
    uv run pytest tests/e2e/ -v

    # Against staging
    FINPILOT_GATEWAY_URL=https://auth-service-staging-xxx.a.run.app \\
    FINPILOT_API_KEY=fp_your_token \\
    uv run pytest tests/e2e/ -v
"""

# Set env vars BEFORE any finpilot_mcp imports so pydantic-settings picks them
# up at Settings() initialisation time.
import os

DEFAULT_GATEWAY_URL = "https://auth-service-dev-6rs7xh3scq-el.a.run.app"
os.environ.setdefault("FINPILOT_GATEWAY_URL", DEFAULT_GATEWAY_URL)

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastmcp import Client  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gateway_url() -> str:
    return os.environ.get("FINPILOT_GATEWAY_URL", DEFAULT_GATEWAY_URL)


def _is_gateway_reachable() -> bool:
    try:
        r = httpx.get(f"{_gateway_url()}/health", timeout=10.0)
        return r.status_code < 500
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def gateway_up():
    """Skip all tests if the auth service is not reachable."""
    if not _is_gateway_reachable():
        pytest.skip(
            f"Auth service not reachable at {_gateway_url()}\n"
            "  Check FINPILOT_GATEWAY_URL or verify the dev deployment is healthy."
        )
    return _gateway_url()


@pytest.fixture(scope="session")
async def mcp_client(gateway_up):
    """FastMCP in-process client — guest mode (no API key).

    Works for server introspection and any tools available without authentication.
    The OrchestratorClient sends requests with no Authorization header.
    """
    # Ensure no stale key leaks into this client
    os.environ.pop("FINPILOT_API_KEY", None)

    from finpilot_mcp.server import mcp

    async with Client(mcp) as client:
        yield client


@pytest.fixture(scope="session")
def api_key(gateway_up):
    """fp_... API token for authenticated tests.

    Skips if FINPILOT_API_KEY is not set — authenticated tests are skipped
    automatically; guest-mode tests continue to run.

    Get a token:
      1. Sign in at https://finpilot-dev.web.app
      2. Click the key icon (API Tokens)
      3. Generate a token → export FINPILOT_API_KEY=fp_...
    """
    key = os.environ.get("FINPILOT_API_KEY")
    if not key:
        pytest.skip(
            "FINPILOT_API_KEY not set — skipping authenticated tests\n"
            "  Guest-mode tests still run. To enable full suite:\n"
            "  export FINPILOT_API_KEY=fp_..."
        )
    return key


@pytest.fixture(scope="session")
async def auth_mcp_client(api_key):
    """FastMCP in-process client — authenticated mode (fp_... token).

    Used for tools that require a logged-in user: PDF analysis, credit health, etc.
    """
    os.environ["FINPILOT_API_KEY"] = api_key

    from finpilot_mcp.server import mcp

    async with Client(mcp) as client:
        yield client


@pytest.fixture(scope="session")
def credit_report_pdf(auth_mcp_client):
    """Path to a CIBIL / Experian / CRIF PDF on the local machine."""
    path = os.environ.get("CREDIT_REPORT_PDF")
    if not path:
        pytest.skip(
            "CREDIT_REPORT_PDF not set\n"
            "  Export: CREDIT_REPORT_PDF=/path/to/cibil.pdf"
        )
    if not os.path.exists(path):
        pytest.skip(f"File not found: {path}")
    return path


@pytest.fixture(scope="session")
def cas_pdf(auth_mcp_client):
    """Path to a CAS statement PDF (NSDL / CDSL / CAMS) on the local machine."""
    path = os.environ.get("CAS_PDF")
    if not path:
        pytest.skip(
            "CAS_PDF not set\n"
            "  Export: CAS_PDF=/path/to/cas_statement.pdf"
        )
    if not os.path.exists(path):
        pytest.skip(f"File not found: {path}")
    return path
