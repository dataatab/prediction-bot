"""
Application configuration using Pydantic settings.

Loads configuration from environment variables with validation and type safety.
Supports .env files for local development.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class KalshiConfig(BaseSettings):
    """Configuration for Kalshi API connectivity."""

    model_config = SettingsConfigDict(
        env_prefix="KALSHI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = Field(
        ...,
        description="Kalshi API key (member ID)",
    )
    private_key_path: Path | None = Field(
        default=None,
        description="Path to RSA private key file",
    )
    private_key: SecretStr | None = Field(
        default=None,
        description="RSA private key as PEM string (alternative to file path)",
    )
    base_url: str = Field(
        default="https://trading-api.kalshi.com",
        description="Kalshi API base URL",
    )
    ws_url: str = Field(
        default="wss://trading-api.kalshi.com/trade-api/ws/v2",
        description="Kalshi WebSocket URL",
    )
    environment: Literal["demo", "prod"] = Field(
        default="demo",
        description="Trading environment (demo or prod)",
    )

    @field_validator("private_key_path", mode="before")
    @classmethod
    def expand_path(cls, v: str | Path | None) -> Path | None:
        """Expand user home directory in paths."""
        if v is None:
            return None
        return Path(v).expanduser().resolve()

    def get_effective_base_url(self) -> str:
        """Get the base URL based on environment."""
        if self.environment == "demo":
            return "https://demo-api.kalshi.co"
        return self.base_url


class PolymarketConfig(BaseSettings):
    """Configuration for Polymarket API connectivity."""

    model_config = SettingsConfigDict(
        env_prefix="POLYMARKET_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    private_key: SecretStr = Field(
        ...,
        description="Ethereum private key for signing",
    )
    rpc_url: str = Field(
        default="https://polygon-rpc.com",
        description="Polygon RPC endpoint",
    )
    clob_api_url: str = Field(
        default="https://clob.polymarket.com",
        description="Polymarket CLOB API URL",
    )
    chain_id: int = Field(
        default=137,
        description="Polygon chain ID (137 for mainnet)",
    )


class TradingConfig(BaseSettings):
    """Trading strategy configuration."""

    model_config = SettingsConfigDict(
        env_prefix="TRADING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    min_spread_cents: int = Field(
        default=2,
        ge=1,
        description="Minimum spread in cents to consider for arbitrage",
    )
    crypto_market_min_spread_cents: int = Field(
        default=4,
        ge=1,
        description="Minimum spread for crypto markets (higher due to dynamic fees)",
    )
    max_position_size_usd: float = Field(
        default=1000.0,
        gt=0,
        description="Maximum position size per market in USD",
    )
    max_balance_percent: float = Field(
        default=0.02,
        gt=0,
        le=1.0,
        description="Maximum percent of balance per trade (0.02 = 2%)",
    )
    max_open_positions: int = Field(
        default=10,
        gt=0,
        description="Maximum number of open positions allowed",
    )


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: SecretStr = Field(
        default=SecretStr("postgresql+asyncpg://localhost:5432/prediction_bot"),
        description="PostgreSQL connection URL",
    )
    pool_size: int = Field(
        default=5,
        ge=1,
        description="Database connection pool size",
    )
    echo_sql: bool = Field(
        default=False,
        description="Echo SQL statements for debugging",
    )


class AppConfig(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "production", "testing"] = Field(
        default="development",
        description="Application environment",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )
    log_json: bool = Field(
        default=False,
        description="Output logs in JSON format",
    )


class Settings(BaseSettings):
    """Aggregated settings with all configuration sections."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app: AppConfig = Field(default_factory=AppConfig)
    kalshi: KalshiConfig | None = None
    polymarket: PolymarketConfig | None = None
    trading: TradingConfig = Field(default_factory=TradingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    @classmethod
    def load(cls) -> Settings:
        """
        Load settings from environment, with optional sub-configs.

        Exchange configs (kalshi, polymarket) are only loaded if their
        required environment variables are present.
        """
        settings = cls()

        # Try to load Kalshi config if API key is present
        try:
            settings.kalshi = KalshiConfig()
        except Exception:
            settings.kalshi = None

        # Try to load Polymarket config if private key is present
        try:
            settings.polymarket = PolymarketConfig()
        except Exception:
            settings.polymarket = None

        return settings


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Returns:
        Settings instance loaded from environment.

    Example:
        >>> settings = get_settings()
        >>> print(settings.app.log_level)
    """
    return Settings.load()
