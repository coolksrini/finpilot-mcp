"""Constants for FinPilot MCP Server."""

# Default FinPilot gateway URL (Auth Service — deployed dev environment)
# Override with FINPILOT_GATEWAY_URL env var for staging/prod.
DEFAULT_GATEWAY_URL = "https://auth-service-dev-6rs7xh3scq-el.a.run.app"

# Timeout settings
DEFAULT_TIMEOUT = 30.0  # seconds
UPLOAD_TIMEOUT = 120.0  # seconds for file uploads
