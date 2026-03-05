"""Configuration management for FinPilot MCP Server."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from finpilot_mcp.constants import DEFAULT_GATEWAY_URL


class Settings(BaseSettings):
    """FinPilot MCP Server settings.

    All settings are read from environment variables (FINPILOT_ prefix):

    FINPILOT_GATEWAY_URL  Auth Service URL — public entry point for all FinPilot
                          API traffic.  Defaults to http://localhost:8080.
                          Set this to your deployed Auth Service URL for production.

    FINPILOT_API_KEY      Optional API key (fp_...).  If set, requests are sent as
                          an authenticated user.  If omitted, guest mode is used
                          (stateless calculation tools only).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FINPILOT_",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gateway_url: str = Field(
        default=DEFAULT_GATEWAY_URL,
        description="FinPilot Auth Service URL (FINPILOT_GATEWAY_URL)",
    )

    api_key: str | None = Field(
        default=None,
        description="FinPilot API key (FINPILOT_API_KEY). Omit for guest mode.",
    )

    request_timeout: float = Field(default=30.0, description="Default request timeout in seconds")

    upload_timeout: float = Field(default=120.0, description="Upload request timeout in seconds")


# Global settings instance
settings = Settings()
