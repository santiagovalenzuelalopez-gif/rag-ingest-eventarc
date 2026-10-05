"""Contrato HTTP con Eventarc: 204 = procesado/descartado, 500 = que reintente."""

import json

import pytest

BUCKET = "tenants-bucket"
FINALIZED = "google.cloud.storage.object.v1.finalized"
DELETED = "google.cloud.storage.object.v1.deleted"


def post(client, event_type, name, bucket=BUCKET, generation=None):
    """CloudEvent en modo binario, como lo entrega Eventarc."""
    body = {"bucket": bucket}
    if name is not None:
        body["name"] = name
    if generation is not None:
        body["generation"] = str(generation)
    return client.post(
        "/events/gcs",
        content=json.dumps(body),
        headers={
            "ce-specversion": "1.0",
            "ce-id": "evt-1",
            "ce-source": f"//storage.googleapis.com/projects/_/buckets/{bucket}",
            "ce-type": event_type,
            "content-type": "application/json",
        },
    )


def test_finalized_knowledge_is_imported(client, stores):
    _, _, knowledge = stores
    assert post(client, FINALIZED, "acme/knowledge/a.md", generation=1).status_code == 204
    assert len(knowledge.documents) == 1


def test_deleted_removes_document(client, stores):
    _, _, knowledge = stores
    post(client, FINALIZED, "acme/knowledge/a.md", generation=1)
    assert post(client, DELETED, "acme/knowledge/a.md", generation=1).status_code == 204
    assert knowledge.documents == {}


def test_processing_error_returns_500_so_eventarc_retries_then_succeeds(client, stores):
    _, _, knowledge = stores
    knowledge.fail_next_imports = 1
    assert post(client, FINALIZED, "acme/knowledge/a.md", generation=1).status_code == 500
    assert post(client, FINALIZED, "acme/knowledge/a.md", generation=1).status_code == 204
    assert len(knowledge.documents) == 1


@pytest.mark.parametrize("name", [None, "archivo-en-la-raiz.md", "acme/knowledge/../../x.md"])
def test_unprocessable_events_are_acknowledged_not_retried(client, stores, name):
    _, _, knowledge = stores
    assert post(client, FINALIZED, name).status_code == 204
    assert knowledge.documents == {}


def test_unknown_tenant_is_acknowledged(client, stores):
    _, _, knowledge = stores
    assert post(client, FINALIZED, "ghost/knowledge/a.md").status_code == 204
    assert knowledge.documents == {}


def test_foreign_bucket_is_ignored_when_allowed_bucket_is_set(client, stores, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "allowed_bucket", BUCKET)
    _, _, knowledge = stores
    assert post(client, FINALIZED, "acme/knowledge/a.md", bucket="otro-bucket").status_code == 204
    assert knowledge.documents == {}


def test_health_and_version(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert "version" in client.get("/version").json()
