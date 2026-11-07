"""
config.py — Application settings loaded from environment variables.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Nexus API
    NEXUS_API_KEY: str = "not-set"
    NEXUS_BASE_URL: str = "https://api.nexus.navigatelabs.ai/v1"
    NEXUS_VISION_MODEL: str = "nexus-vision-latest"
    NEXUS_STT_MODEL: str = "nexus-stt-latest"
    NEXUS_LLM_A: str = "nexus-llm-pro"
    NEXUS_LLM_B: str = "nexus-llm-fast"
    NEXUS_TTS_MODEL: str = "nexus-tts-latest"

    # Database
    DATABASE_URL: str = "sqlite:///./resourcelens.db"

    # App
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me"

    # Anomaly detection thresholds (code — not AI)
    ANOMALY_THRESHOLD_PCT: float = 20.0   # % above baseline
    ANOMALY_SIGMA: float = 2.0            # standard deviations
    BASELINE_WEEKS: int = 4               # look-back window

    # Water balance threshold (kL/day before flagging)
    WATER_UNACCOUNTED_THRESHOLD_KL: float = 5.0

    # Cost (stretch)
    ENERGY_TARIFF_PER_KWH: float = 7.5   # ₹
    WATER_TARIFF_PER_KL: float = 45.0    # ₹
    TOD_PEAK_TARIFF: float = 9.0          # ₹/kWh peak
    TOD_PEAK_HOURS: str = "09:00-23:00"

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

