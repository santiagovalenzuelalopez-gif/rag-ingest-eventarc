"""Inspección del estado en memoria. Solo se registra con ``BACKEND=memory`` (nunca en producción)."""

from fastapi import APIRouter

from app.services.deps import get_service

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/state")
async def state():
    service = get_service()
    return {
        "tenants": service._tenants.snapshot(),
        "tracking": service._tracking.snapshot(),
        "documents": service._knowledge.documents,
    }
