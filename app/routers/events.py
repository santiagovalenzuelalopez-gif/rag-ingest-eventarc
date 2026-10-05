"""Webhook de Eventarc. Sin prefijo /v1: es un endpoint interno, no una API de negocio versionada."""

import asyncio
import logging

from cloudevents.http import from_http
from fastapi import APIRouter, Request, Response

from app.core.config import get_settings
from app.services.deps import get_service
from app.services.ingestion import parse_generation, parse_object_name

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])


@router.post("/events/gcs")
async def handle_gcs_event(request: Request) -> Response:
    """
    Recibe ``google.cloud.storage.object.v1.finalized`` / ``...deleted`` y sincroniza el
    File Search Store del tenant dueño del objeto (``<tenant_id>/knowledge/...``).

    Contrato de respuesta con Eventarc:
    - 204: procesado, o descartado a propósito (no tiene sentido que Eventarc reintente).
    - 500: fallo transitorio; Eventarc reintenta. El flujo es idempotente ante reintentos.
    """
    event = from_http(dict(request.headers), await request.body())
    data = event.data or {}
    bucket, object_name = data.get("bucket"), data.get("name")

    if not bucket or not object_name:
        logger.warning("event_missing_fields", extra={"data": data})
        return Response(status_code=204)

    allowed = get_settings().allowed_bucket
    if allowed and bucket != allowed:
        logger.warning("event_foreign_bucket_ignored", extra={"bucket": bucket})
        return Response(status_code=204)

    try:
        ref = parse_object_name(object_name)
    except ValueError:
        logger.warning("event_ignored_unparseable_path", extra={"object_name": object_name})
        return Response(status_code=204)

    generation = parse_generation(data.get("generation"))
    service = get_service()

    try:
        # Los SDK son síncronos y el import hace polling: fuera del event loop.
        if event["type"].endswith(".deleted"):
            await asyncio.to_thread(service.remove, ref, generation)
        else:
            await asyncio.to_thread(service.upsert, bucket, object_name, ref, generation)
    except Exception:
        logger.error(
            "event_processing_failed",
            exc_info=True,
            extra={"tenant_id": ref.tenant_id, "rel_path": ref.rel_path},
        )
        return Response(status_code=500)

    return Response(status_code=204)
