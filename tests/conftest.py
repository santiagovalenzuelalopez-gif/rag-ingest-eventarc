import os

os.environ["BACKEND"] = "memory"
os.environ["DEMO_TENANTS"] = "acme"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.routers.events as events  # noqa: E402
from app.main import app  # noqa: E402
from app.services.adapters.memory import (  # noqa: E402
    MemoryKnowledgeStore,
    MemoryTenantRegistry,
    MemoryTrackingStore,
)
from app.services.ingestion import IngestionService  # noqa: E402


@pytest.fixture
def stores():
    return MemoryTenantRegistry(["acme"]), MemoryTrackingStore(), MemoryKnowledgeStore()


@pytest.fixture
def service(stores):
    return IngestionService(*stores)


@pytest.fixture
def client(service, monkeypatch):
    # Servicio nuevo por test: el estado en memoria no se filtra entre tests.
    monkeypatch.setattr(events, "get_service", lambda: service)
    return TestClient(app)
