"""Almacén de conocimiento sobre Gemini File Search Stores."""

import logging
import time

from app.services.ports import KnowledgeImportError

logger = logging.getLogger(__name__)


class GeminiKnowledgeStore:
    def __init__(self, api_key: str, poll_attempts: int = 30, poll_interval_seconds: float = 2.0):
        # Imports perezosos: el modo memoria no necesita el SDK ni credenciales.
        import google.auth
        from google import genai

        self._client = genai.Client(api_key=api_key)
        # files.register_files() exige credenciales explícitas de GCP para leer el objeto del
        # bucket. El scope por defecto no alcanza: sin devstorage.read_only explícito la API
        # rechaza la llamada con ACCESS_TOKEN_SCOPE_INSUFFICIENT.
        self._credentials, _ = google.auth.default(
            scopes=[
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/devstorage.read_only",
            ]
        )
        self._poll_attempts = poll_attempts
        self._poll_interval = poll_interval_seconds

    def find_or_create_store(self, display_name: str) -> str:
        for store in self._client.file_search_stores.list():
            if store.display_name == display_name:
                return store.name
        return self._client.file_search_stores.create(config={"display_name": display_name}).name

    def import_object(self, store_name: str, gcs_uri: str, metadata: dict[str, str]) -> str:
        from google.genai import types

        registered = self._client.files.register_files(uris=[gcs_uri], auth=self._credentials)
        operation = self._client.file_search_stores.import_file(
            file_search_store_name=store_name,
            file_name=registered.files[0].name,
            config=types.ImportFileConfig(
                custom_metadata=[types.CustomMetadata(key=k, string_value=v) for k, v in metadata.items()]
            ),
        )

        # import_file es una long-running operation: hay que esperar done=True antes de leer
        # operation.response (si no, document_name viene None).
        attempts = 0
        while not operation.done and attempts < self._poll_attempts:
            time.sleep(self._poll_interval)
            operation = self._client.operations.get(operation)
            attempts += 1

        if not operation.done:
            self._discard_orphan(store_name, operation)
            raise KnowledgeImportError(f"import_file no terminó tras {attempts} intentos ({gcs_uri})")
        if operation.error:
            self._discard_orphan(store_name, operation)
            raise KnowledgeImportError(f"import_file falló para {gcs_uri}: {operation.error}")

        # response.document_name es un ID corto; delete() necesita el resource name completo.
        return f"{store_name}/documents/{operation.response.document_name}"

    def delete_document(self, document_name: str) -> None:
        from google.genai import errors, types

        try:
            # force=True va envuelto en DeleteDocumentConfig, no como kwarg directo.
            self._client.file_search_stores.documents.delete(
                name=document_name, config=types.DeleteDocumentConfig(force=True)
            )
        except errors.ClientError as exc:
            if getattr(exc, "code", None) != 404:
                raise
            logger.info("ingest_delete_already_gone", extra={"document_name": document_name})

    def _discard_orphan(self, store_name: str, operation) -> None:
        """Un import fallido/atascado puede dejar un documento a medias (PENDING/FAILED) sin tracking:
        el emisor reintenta, se importa otra copia y quedaría duplicado en el RAG. El id de la
        operación coincide con el del documento. Mejor esfuerzo: nunca enmascara el error original."""
        try:
            document_id = (getattr(operation, "name", "") or "").rsplit("/", 1)[-1]
            if document_id:
                self.delete_document(f"{store_name}/documents/{document_id}")
                logger.warning("ingest_orphan_discarded", extra={"document_id": document_id})
        except Exception:  # noqa: BLE001
            logger.warning("ingest_orphan_discard_failed", exc_info=True)
