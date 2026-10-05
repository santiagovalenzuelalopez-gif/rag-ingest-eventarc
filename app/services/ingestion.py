"""Lógica de sincronización bucket -> almacén de conocimiento, independiente de la infraestructura.

Los eventos de GCS son *at-least-once* y pueden llegar duplicados o fuera de orden. Las
reglas que lo hacen seguro:

- Un evento con una generación <= a la ya registrada es viejo/duplicado: se omite.
- Sobrescribir un objeto emite ``finalized`` (nueva) Y ``deleted`` (vieja). Si el ``deleted``
  llega después de importar la nueva, NO debe borrarla: se omite si hay una generación más nueva.
- Reimportar = borrar la versión previa y luego importar; ante un fallo se devuelve error para
  que el emisor reintente, y el flujo es idempotente.
- Un tenant desconocido se descarta (un archivo mal ubicado no crea clientes fantasma).
"""

import logging
import re
from dataclasses import dataclass
from enum import StrEnum

from app.services.ports import KnowledgeStore, TenantRegistry, TrackingStore

logger = logging.getLogger(__name__)

_TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
KNOWLEDGE_PREFIX = "knowledge/"


class Outcome(StrEnum):
    IMPORTED = "imported"
    STALE_SKIPPED = "stale_skipped"
    CONFIG_IGNORED = "config_ignored"
    UNKNOWN_TENANT = "unknown_tenant"
    DELETED = "deleted"
    DELETE_STALE_SKIPPED = "delete_stale_skipped"
    DELETE_NOOP = "delete_noop"
    IGNORED = "ignored"


@dataclass(frozen=True)
class ObjectRef:
    tenant_id: str
    rel_path: str


def parse_object_name(object_name: str) -> ObjectRef:
    """'acme/knowledge/faq/envios.md' -> ObjectRef('acme', 'knowledge/faq/envios.md'). ValueError si no aplica."""
    parts = object_name.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(object_name)
    tenant_id, rel_path = parts
    if not _TENANT_ID_RE.match(tenant_id) or ".." in rel_path.split("/"):
        raise ValueError(object_name)
    return ObjectRef(tenant_id, rel_path)


def parse_generation(raw) -> int | None:
    """La generación viaja como string en el CloudEvent; None si falta o no es numérica."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class IngestionService:
    def __init__(self, tenants: TenantRegistry, tracking: TrackingStore, knowledge: KnowledgeStore):
        self._tenants = tenants
        self._tracking = tracking
        self._knowledge = knowledge

    def upsert(self, bucket: str, object_name: str, ref: ObjectRef, generation: int | None) -> Outcome:
        if not ref.rel_path.startswith(KNOWLEDGE_PREFIX):
            # identity/protocol/respuestas cambiaron: no hay nada que ingestar; el servicio de
            # chat recoge el cambio cuando vence el TTL de su caché.
            logger.info("event_config_changed", extra={"tenant_id": ref.tenant_id, "rel_path": ref.rel_path})
            return Outcome.CONFIG_IGNORED

        tenant = self._tenants.get_active(ref.tenant_id)
        if tenant is None:
            logger.warning("event_unknown_tenant", extra={"tenant_id": ref.tenant_id, "object_name": object_name})
            return Outcome.UNKNOWN_TENANT

        store_name = self._ensure_store(ref.tenant_id, tenant)

        tracked = self._tracking.get(ref.tenant_id, ref.rel_path) or {}
        tracked_generation = tracked.get("generation")
        if generation is not None and tracked_generation is not None and tracked_generation >= generation:
            logger.info(
                "ingest_stale_event_skipped",
                extra={"tenant_id": ref.tenant_id, "rel_path": ref.rel_path,
                       "generation": generation, "tracked_generation": tracked_generation},
            )
            return Outcome.STALE_SKIPPED

        old_document = tracked.get("document_name")
        if old_document:
            try:
                self._knowledge.delete_document(old_document)
            except Exception:  # noqa: BLE001 - mejor esfuerzo: peor un duplicado que perder el update
                logger.warning("ingest_delete_old_doc_failed", exc_info=True,
                               extra={"tenant_id": ref.tenant_id, "document_name": old_document})

        document_name = self._knowledge.import_object(
            store_name,
            f"gs://{bucket}/{object_name}",
            {"tenant_id": ref.tenant_id, "path": ref.rel_path},
        )
        self._tracking.save(ref.tenant_id, ref.rel_path, document_name, generation)
        logger.info("ingest_ok", extra={"tenant_id": ref.tenant_id, "rel_path": ref.rel_path,
                                        "document_name": document_name})
        return Outcome.IMPORTED

    def remove(self, ref: ObjectRef, generation: int | None) -> Outcome:
        if not ref.rel_path.startswith(KNOWLEDGE_PREFIX):
            return Outcome.CONFIG_IGNORED

        tracked = self._tracking.get(ref.tenant_id, ref.rel_path) or {}
        tracked_generation = tracked.get("generation")
        if generation is not None and tracked_generation is not None and tracked_generation > generation:
            logger.info("ingest_delete_stale_skipped",
                        extra={"tenant_id": ref.tenant_id, "rel_path": ref.rel_path,
                               "generation": generation, "tracked_generation": tracked_generation})
            return Outcome.DELETE_STALE_SKIPPED

        document_name = tracked.get("document_name")
        if not document_name:
            logger.warning("ingest_delete_noop", extra={"tenant_id": ref.tenant_id, "rel_path": ref.rel_path})
            return Outcome.DELETE_NOOP

        self._knowledge.delete_document(document_name)
        self._tracking.delete(ref.tenant_id, ref.rel_path)
        logger.info("ingest_deleted", extra={"tenant_id": ref.tenant_id, "rel_path": ref.rel_path,
                                             "document_name": document_name})
        return Outcome.DELETED

    def _ensure_store(self, tenant_id: str, tenant: dict) -> str:
        """El store se crea la primera vez y su nombre se persiste en el tenant."""
        store_name = tenant.get("file_search_store_name")
        if store_name:
            return store_name
        store_name = self._knowledge.find_or_create_store(f"tenant-{tenant_id}")
        self._tenants.set_store_name(tenant_id, store_name)
        logger.info("ingest_store_ready", extra={"tenant_id": tenant_id, "store_name": store_name})
        return store_name
