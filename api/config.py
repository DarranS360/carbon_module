"""
api/config.py

Application settings loaded from environment variables (or a .env file).
Uses pydantic-settings so all values are validated and typed.

Copy .env.example to .env and adjust before starting the server.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    cors_allowed_origins: str = "http://localhost:5173"

    # Leave empty to disable API-key authentication.
    api_key: str = ""

    embodied_refresh_enabled: bool = True
    embodied_refresh_max_age_days: int = 7

    # AWS (used by live-scan and CCFT routes)
    aws_default_region: str = "eu-west-1"
    aws_profile: str = ""          # optional named profile; leave empty for default
    aws_access_key_id: str = ""    # leave empty to fall back to boto3 credential chain
    aws_secret_access_key: str = ""
    
    # Leave empty to return data for all accounts.
    aws_ccft_account_id: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Allow extra environment variables without raising a validation error
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        """Return CORS origins as a list."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


# Single shared instance imported by the rest of the application
settings = Settings()
