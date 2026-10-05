from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Observabilidad
    service_name: str = "rag-ingest-eventarc"
    service_version: str = "1.0.0"
    environment: str = "dev"
    log_level: str = "INFO"

    # "memory": adaptadores en memoria (demo y tests, sin red). "gcp": Firestore + Gemini File Search.
    backend: Literal["memory", "gcp"] = "memory"

    # Solo backend "memory": tenants activos de demo, separados por coma.
    demo_tenants: str = "demo"

    # Solo backend "gcp"
    gcp_project: str = ""
    gemini_api_key: str = ""

    # Si se define, los eventos de cualquier otro bucket se ignoran (defensa en profundidad).
    allowed_bucket: str = ""

    # import_file es una long-running operation: intentos de polling x intervalo antes de darla por atascada.
    import_poll_attempts: int = 30
    import_poll_interval_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
