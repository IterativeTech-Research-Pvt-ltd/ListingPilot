from fastapi import APIRouter
from app.api.v1.endpoints import catalogue, health, drafts, reports, settings

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(catalogue.router, prefix="/catalogue", tags=["Master Catalogue"])
api_router.include_router(drafts.router, prefix="/drafts", tags=["AI Drafts & Approvals"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports & Metrics"])
api_router.include_router(settings.router, prefix="/settings", tags=["Settings & Administration"])

