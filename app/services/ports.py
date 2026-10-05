"""Puertos (interfaces) del dominio de ingesta.

La lógica de sincronización depende solo de estos contratos; Gemini/Firestore son adaptadores
intercambiables, por lo que la idempotencia y el orden de eventos se prueban sin red.
"""

from typing import Protocol


class KnowledgeImportError(Exception):
    """El import al almacén de conocimiento falló o se atascó (no queda nada registrado)."""


class TenantRegistry(Protocol):
    def get_active(self, tenant_id: str) -> dict | None:
        """Doc del tenant si existe y está activo; None si no (evita auto-provisionar)."""

    def set_store_name(self, tenant_id: str, store_name: str) -> None: ...


class TrackingStore(Protocol):
    """Qué documento del almacén corresponde a cada archivo del bucket, y de qué generación."""

    def get(self, tenant_id: str, rel_path: str) -> dict | None: ...

    def save(self, tenant_id: str, rel_path: str, document_name: str, generation: int | None) -> None: ...

    def delete(self, tenant_id: str, rel_path: str) -> None: ...


class KnowledgeStore(Protocol):
    """Almacén de conocimiento por tenant (Gemini File Search Store)."""

    def find_or_create_store(self, display_name: str) -> str: ...

    def import_object(self, store_name: str, gcs_uri: str, metadata: dict[str, str]) -> str:
        """Importa un objeto y devuelve el nombre del documento. Lanza KnowledgeImportError si falla.

        Debe dejar el almacén limpio ante un fallo (sin documentos a medias)."""

    def delete_document(self, document_name: str) -> None:
        """Idempotente: borrar un documento que ya no existe no es un error."""
