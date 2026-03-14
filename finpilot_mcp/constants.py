"""Constants for FinPilot MCP Server."""

# Default FinPilot gateway URL (Auth Service — deployed dev environment)
# Override with FINPILOT_GATEWAY_URL env var for staging/prod.
DEFAULT_GATEWAY_URL = "https://auth-service-dev-6rs7xh3scq-el.a.run.app"

# FinPilot web app URL — shown in guest notices to drive registration
FINPILOT_WEB_URL = "https://finpilot-dev.web.app"

# Timeout settings
DEFAULT_TIMEOUT = 30.0  # seconds
UPLOAD_TIMEOUT = 120.0  # seconds for file uploads
