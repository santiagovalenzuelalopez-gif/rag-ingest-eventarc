from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.middleware import CorrelationMiddleware
from app.routers import demo, events, health

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(
    title="RAG Ingest (Eventarc)",
    description="Sincroniza el conocimiento de cada tenant desde un bucket hacia su File Search Store.",
    version=settings.service_version,
)

app.add_middleware(CorrelationMiddleware)

app.include_router(health.router)
app.include_router(events.router)
if settings.backend == "memory":
    app.include_router(demo.router)
