"""
app/core/config.py
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://localhost/cryptolens"
    anthropic_api_key: str = ""
    env: str = "development"
    log_level: str = "INFO"

    # CoinGecko
    coingecko_api_url: str = "https://api.coingecko.com/api/v3"
    coingecko_api_key: str = ""  # optional — pro key for higher rate limits

    # Fear & Greed
    fear_greed_url: str = "https://api.alternative.me/fng/"

    # Defaults
    default_lookback_days: int = 365
    default_coins: list = ["bitcoin", "ethereum", "solana", "binancecoin"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
