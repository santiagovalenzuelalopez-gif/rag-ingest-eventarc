"""Registro de tenants y tracking de documentos en Firestore.

Modelo::

    tenants/{tenant_id}                      -> {active, file_search_store_name, ...}
    tenants/{tenant_id}/kb_documents/{id}    -> {document_name, rel_path, generation}
"""

from urllib.parse import quote


def _doc_id(rel_path: str) -> str:
    # Los ids de Firestore no admiten "/". quote() es inyectivo (a diferencia de reemplazar
    # "/" por "__", que colisionaría con rutas que ya contengan "__").
    return quote(rel_path, safe="")


class FirestoreTenantRegistry:
    def __init__(self, project: str):
        # Import perezoso: el modo memoria no necesita las dependencias de GCP.
        from google.cloud import firestore

        self._db = firestore.Client(project=project or None)

    def _ref(self, tenant_id: str):
        return self._db.collection("tenants").document(tenant_id)

    def get_active(self, tenant_id: str) -> dict | None:
        snapshot = self._ref(tenant_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        return data if data.get("active", False) else None

    def set_store_name(self, tenant_id: str, store_name: str) -> None:
        self._ref(tenant_id).update({"file_search_store_name": store_name})


class FirestoreTrackingStore:
    def __init__(self, registry: FirestoreTenantRegistry):
        self._registry = registry

    def _ref(self, tenant_id: str, rel_path: str):
        return self._registry._ref(tenant_id).collection("kb_documents").document(_doc_id(rel_path))

    def get(self, tenant_id: str, rel_path: str) -> dict | None:
        snapshot = self._ref(tenant_id, rel_path).get()
        return snapshot.to_dict() if snapshot.exists else None

    def save(self, tenant_id: str, rel_path: str, document_name: str, generation: int | None) -> None:
        record = {"document_name": document_name, "rel_path": rel_path}
        if generation is not None:
            record["generation"] = generation
        self._ref(tenant_id, rel_path).set(record)

    def delete(self, tenant_id: str, rel_path: str) -> None:
        self._ref(tenant_id, rel_path).delete()
