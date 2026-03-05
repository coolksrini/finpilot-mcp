"""Constants for FinPilot MCP Server."""

# Default FinPilot gateway URL (Auth Service — local dev default)
# Override with FINPILOT_GATEWAY_URL env var for production.
DEFAULT_GATEWAY_URL = "http://localhost:8080"

# Timeout settings
DEFAULT_TIMEOUT = 30.0  # seconds
UPLOAD_TIMEOUT = 120.0  # seconds for file uploads
