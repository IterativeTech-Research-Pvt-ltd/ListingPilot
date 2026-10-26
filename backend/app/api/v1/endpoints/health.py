from fastapi import APIRouter

router = APIRouter()

@router.get("/health", summary="Service health check")
def health_check():
    return {
        "status": "healthy",
        "service": "ListingPilot API",
        "phase": 1,
        "features": ["Master Catalogue", "Excel/CSV/Tally Import", "Full Data Export", "Validation Engine"]
    }
