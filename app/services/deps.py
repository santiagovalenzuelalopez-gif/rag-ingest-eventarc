from functools import lru_cache

from app.core.config import get_settings
from app.services.adapters.memory import MemoryKnowledgeStore, MemoryTenantRegistry, MemoryTrackingStore
from app.services.ingestion import IngestionService


@lru_cache
def get_service() -> IngestionService:
    settings = get_settings()
    if settings.backend == "gcp":
        # Imports perezosos: el modo memoria no necesita el SDK de Google.
        from app.services.adapters.firestore import FirestoreTenantRegistry, FirestoreTrackingStore
        from app.services.adapters.gemini import GeminiKnowledgeStore

        registry = FirestoreTenantRegistry(settings.gcp_project)
        return IngestionService(
            registry,
            FirestoreTrackingStore(registry),
            GeminiKnowledgeStore(
                settings.gemini_api_key, settings.import_poll_attempts, settings.import_poll_interval_seconds
            ),
        )

    tenants = [t.strip() for t in settings.demo_tenants.split(",") if t.strip()]
    return IngestionService(MemoryTenantRegistry(tenants), MemoryTrackingStore(), MemoryKnowledgeStore())
