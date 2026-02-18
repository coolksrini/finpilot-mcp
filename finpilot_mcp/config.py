"""Configuration management for FinPilot MCP Server."""

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from finpilot_mcp.constants import (
    DEFAULT_API_GATEWAY_URL,
    LOCAL_API_GATEWAY_URL,
    LOCAL_ORCHESTRATOR_URL,
)


class Settings(BaseSettings):
    """FinPilot MCP Server settings.

    All settings can be overridden via environment variables.

    LOCAL DEVELOPMENT (default):
    - Calls orchestrator directly (http://localhost:3000)
    - No authentication required
    - Set ENVIRONMENT=development

    PRODUCTION:
    - Calls API Gateway (https://api.finpilot.ai)
    - Authentication required (API key or JWT)
    - Set ENVIRONMENT=production
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Gateway URL (production only)
    api_gateway_url: str = Field(
        default=DEFAULT_API_GATEWAY_URL,
        description="FinPilot API Gateway URL (production)"
    )

    # Orchestrator URL (local development - direct connection)
    orchestrator_url: str = Field(
        default=LOCAL_ORCHESTRATOR_URL,
        description="ADK Orchestrator URL (local dev)"
    )

    # Authentication (optional for local dev, required for production)
    api_key: Optional[str] = Field(
        default=None,
        description="FinPilot API Key (for API key auth)"
    )

    jwt_token: Optional[str] = Field(
        default=None,
        description="JWT token (for JWT auth)"
    )

    # Environment
    environment: str = Field(
        default="development",  # Default to local development
        description="Environment: production, staging, development"
    )

    # Use direct orchestrator connection (bypasses gateway)
    use_direct_orchestrator: bool = Field(
        default=True,  # Default to direct for local dev
        description="Use direct orchestrator connection (local dev only)"
    )

    # Timeouts
    request_timeout: float = Field(
        default=30.0,
        description="Default request timeout in seconds"
    )

    upload_timeout: float = Field(
        default=120.0,
        description="Upload request timeout in seconds"
    )

    @property
    def is_local_dev(self) -> bool:
        """Check if running in local development mode."""
        return self.environment == "development"

    @property
    def effective_orchestrator_url(self) -> str:
        """Get effective orchestrator URL for direct connection."""
        return os.getenv("FINPILOT_ORCHESTRATOR_URL", self.orchestrator_url)

    @property
    def effective_backend_url(self) -> str:
        """Get effective backend URL (orchestrator direct or API gateway).

        LOCAL DEV: http://localhost:3000 (orchestrator direct)
        PRODUCTION: https://api.finpilot.ai (API gateway)
        """
        if self.is_local_dev and self.use_direct_orchestrator:
            return self.effective_orchestrator_url

        # Production or when gateway is explicitly set
        return os.getenv("FINPILOT_API_GATEWAY_URL", self.api_gateway_url)

    @property
    def has_auth(self) -> bool:
        """Check if any authentication is configured.

        Auth is optional for local development, required for production.
        """
        if self.is_local_dev:
            return True  # Allow unauthenticated local development
        return self.api_key is not None or self.jwt_token is not None


# Global settings instance
settings = Settings()
