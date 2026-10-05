"""Lógica de sincronización: orden de eventos, idempotencia, limpieza y aislamiento."""

import pytest

from app.services.ingestion import IngestionService, Outcome, parse_generation, parse_object_name
from app.services.ports import KnowledgeImportError

BUCKET = "tenants-bucket"
PATH = "acme/knowledge/faq.md"


def up(service, generation=None, path=PATH):
    return service.upsert(BUCKET, path, parse_object_name(path), generation)


def rm(service, generation=None, path=PATH):
    return service.remove(parse_object_name(path), generation)


def test_first_upsert_creates_store_and_imports(service, stores):
    registry, _, knowledge = stores
    assert up(service, 1) == Outcome.IMPORTED
    assert knowledge.stores == {"tenant-acme": "fileSearchStores/tenant-acme"}
    # El nombre del store se persiste en el tenant: la siguiente vez no se vuelve a buscar.
    assert registry.snapshot()["acme"]["file_search_store_name"] == "fileSearchStores/tenant-acme"
    doc = next(iter(knowledge.documents.values()))
    assert doc["uri"] == f"gs://{BUCKET}/{PATH}"
    assert doc["metadata"] == {"tenant_id": "acme", "path": "knowledge/faq.md"}


def test_reupload_replaces_previous_version_without_duplicates(service, stores):
    _, _, knowledge = stores
    up(service, 1)
    up(service, 2)
    assert len(knowledge.documents) == 1


def test_stale_or_duplicate_event_is_skipped(service, stores):
    _, _, knowledge = stores
    up(service, 5)
    assert up(service, 5) == Outcome.STALE_SKIPPED  # duplicado
    assert up(service, 3) == Outcome.STALE_SKIPPED  # fuera de orden
    assert len(knowledge.documents) == 1


def test_late_deleted_event_must_not_delete_the_new_version(service, stores):
    """Sobrescribir emite finalized(v2) y deleted(v1); si deleted llega tarde no borra v2."""
    _, tracking, knowledge = stores
    up(service, 1)
    up(service, 2)
    assert rm(service, 1) == Outcome.DELETE_STALE_SKIPPED
    assert len(knowledge.documents) == 1
    assert tracking.get("acme", "knowledge/faq.md") is not None


def test_real_delete_removes_document_and_tracking(service, stores):
    _, tracking, knowledge = stores
    up(service, 1)
    assert rm(service, 1) == Outcome.DELETED
    assert knowledge.documents == {}
    assert tracking.get("acme", "knowledge/faq.md") is None


def test_delete_of_untracked_file_is_a_noop(service):
    assert rm(service, 1) == Outcome.DELETE_NOOP


def test_failed_import_leaves_nothing_tracked_and_retry_succeeds(service, stores):
    _, tracking, knowledge = stores
    knowledge.fail_next_imports = 1
    with pytest.raises(KnowledgeImportError):
        up(service, 1)
    assert tracking.get("acme", "knowledge/faq.md") is None
    assert up(service, 1) == Outcome.IMPORTED  # el reintento del emisor funciona
    assert len(knowledge.documents) == 1


def test_failed_reimport_recovers_on_retry_without_duplicates(service, stores):
    _, _, knowledge = stores
    up(service, 1)
    knowledge.fail_next_imports = 1
    with pytest.raises(KnowledgeImportError):
        up(service, 2)
    up(service, 2)
    assert len(knowledge.documents) == 1


def test_unknown_tenant_is_dropped_not_provisioned(service, stores):
    registry, _, knowledge = stores
    assert up(service, 1, path="ghost/knowledge/a.md") == Outcome.UNKNOWN_TENANT
    assert knowledge.stores == {} and "ghost" not in registry.snapshot()


def test_config_file_changes_are_not_ingested(service, stores):
    _, _, knowledge = stores
    assert up(service, 1, path="acme/identity.json") == Outcome.CONFIG_IGNORED
    assert rm(service, 1, path="acme/identity.json") == Outcome.CONFIG_IGNORED
    assert knowledge.documents == {}


def test_tenants_with_same_filename_do_not_collide(stores):
    registry, tracking, knowledge = stores
    registry._tenants["beta"] = {"active": True}
    service = IngestionService(registry, tracking, knowledge)
    up(service, 1, path="acme/knowledge/faq.md")
    up(service, 1, path="beta/knowledge/faq.md")
    assert len(knowledge.documents) == 2
    rm(service, 1, path="acme/knowledge/faq.md")
    assert len(knowledge.documents) == 1


@pytest.mark.parametrize(
    "bad",
    [
        "solo-un-segmento",
        "/knowledge/a.md",
        "acme/",
        "ACME/knowledge/a.md",
        "acme/knowledge/../../x.md",
        "../acme/knowledge/a.md",
    ],
)
def test_parse_object_name_rejects_invalid_or_traversal(bad):
    with pytest.raises(ValueError):
        parse_object_name(bad)


def test_parse_generation():
    assert parse_generation("1700000000000002") == 1700000000000002
    assert parse_generation(None) is None
    assert parse_generation("abc") is None
