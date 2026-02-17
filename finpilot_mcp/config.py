"""Configuration management for FinPilot MCP Server."""

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from finpilot_mcp.constants import DEFAULT_API_GATEWAY_URL, LOCAL_API_GATEWAY_URL


class Settings(BaseSettings):
    """FinPilot MCP Server settings.
    
    All settings can be overridden via environment variables.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # API Gateway URL (can be overridden via FINPILOT_API_GATEWAY_URL)
    api_gateway_url: str = Field(
        default=DEFAULT_API_GATEWAY_URL,
        description="FinPilot API Gateway URL"
    )
    
    # Authentication (optional - populated from env if available)
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
        default="production",
        description="Environment: production, staging, development"
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
    def effective_gateway_url(self) -> str:
        """Get effective gateway URL (local dev or configured)."""
        if self.is_local_dev:
            return os.getenv("FINPILOT_API_GATEWAY_URL", LOCAL_API_GATEWAY_URL)
        return self.api_gateway_url
    
    @property
    def has_auth(self) -> bool:
        """Check if any authentication is configured."""
        return self.api_key is not None or self.jwt_token is not None


# Global settings instance
settings = Settings()
