"""Constants for FinPilot MCP Server.

These can be overridden via environment variables.
"""

# Default API Gateway URL (production)
DEFAULT_API_GATEWAY_URL = "https://api.finpilot.ai"

# Local development gateway
LOCAL_API_GATEWAY_URL = "http://localhost:8000"

# API endpoints
ENDPOINTS = {
    "credit_analyze": "/v1/credit/analyze",
    "credit_health": "/v1/credit/health",
    "portfolio_analyze": "/v1/portfolio/analyze",
    "loan_optimize": "/v1/loans/optimize",
    "financial_plan": "/v1/plan/create",
}

# Timeout settings
DEFAULT_TIMEOUT = 30.0  # seconds
UPLOAD_TIMEOUT = 120.0  # seconds for file uploads
