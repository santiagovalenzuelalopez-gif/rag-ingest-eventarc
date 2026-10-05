"""Adaptadores en memoria: demo local y tests. Sin red ni credenciales."""

from app.services.ports import KnowledgeImportError


class MemoryTenantRegistry:
    def __init__(self, active_tenants: list[str] | None = None):
        self._tenants: dict[str, dict] = {t: {"active": True} for t in (active_tenants or [])}

    def get_active(self, tenant_id: str) -> dict | None:
        tenant = self._tenants.get(tenant_id)
        return dict(tenant) if tenant and tenant.get("active") else None

    def set_store_name(self, tenant_id: str, store_name: str) -> None:
        self._tenants[tenant_id]["file_search_store_name"] = store_name

    def snapshot(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self._tenants.items()}


class MemoryTrackingStore:
    def __init__(self):
        self._records: dict[tuple[str, str], dict] = {}

    def get(self, tenant_id: str, rel_path: str) -> dict | None:
        record = self._records.get((tenant_id, rel_path))
        return dict(record) if record else None

    def save(self, tenant_id: str, rel_path: str, document_name: str, generation: int | None) -> None:
        record = {"document_name": document_name, "rel_path": rel_path}
        if generation is not None:
            record["generation"] = generation
        self._records[(tenant_id, rel_path)] = record

    def delete(self, tenant_id: str, rel_path: str) -> None:
        self._records.pop((tenant_id, rel_path), None)

    def snapshot(self) -> list[dict]:
        return [{"tenant_id": t, **r} for (t, _), r in self._records.items()]


class MemoryKnowledgeStore:
    """Simula un File Search Store. ``fail_next_imports`` permite probar reintentos."""

    def __init__(self):
        self.stores: dict[str, str] = {}          # display_name -> store_name
        self.documents: dict[str, dict] = {}      # document_name -> {"uri", "metadata"}
        self.fail_next_imports = 0
        self._counter = 0

    def find_or_create_store(self, display_name: str) -> str:
        return self.stores.setdefault(display_name, f"fileSearchStores/{display_name}")

    def import_object(self, store_name: str, gcs_uri: str, metadata: dict[str, str]) -> str:
        if self.fail_next_imports > 0:
            self.fail_next_imports -= 1
            raise KnowledgeImportError(f"import simulado fallido: {gcs_uri}")
        self._counter += 1
        document_name = f"{store_name}/documents/doc-{self._counter}"
        self.documents[document_name] = {"uri": gcs_uri, "metadata": dict(metadata)}
        return document_name

    def delete_document(self, document_name: str) -> None:
        self.documents.pop(document_name, None)  # idempotente
