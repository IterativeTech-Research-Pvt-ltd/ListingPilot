from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.settings_service import SettingsService

router = APIRouter()


class BrandVoiceUpdate(BaseModel):
    brand_name: Optional[str] = Field(
        None, json_schema_extra={"example": "Gulmohar Home"}
    )
    tone: Optional[str] = Field(
        None,
        json_schema_extra={
            "example": "Premium, artisanal, authentic Indian heritage craftsmanship"
        },
    )
    target_audience: Optional[str] = Field(
        None,
        json_schema_extra={"example": "Discerning households seeking regional craft"},
    )
    avoid_claims: Optional[str] = Field(
        None,
        json_schema_extra={
            "example": "Avoid cheap promotional slang or unverified claims"
        },
    )


class BannedClaimsUpdate(BaseModel):
    banned_claims: List[str] = Field(
        ..., json_schema_extra={"example": ["free delivery", "best seller", "cheapest"]}
    )


class CredentialsUpdate(BaseModel):
    amazon_seller_id: Optional[str] = None
    amazon_sp_api_client_id: Optional[str] = None
    amazon_sp_api_client_secret: Optional[str] = None
    amazon_sp_api_refresh_token: Optional[str] = None
    flipkart_app_id: Optional[str] = None
    flipkart_app_secret: Optional[str] = None
    openrouter_api_key: Optional[str] = None


@router.get("", response_model=Dict[str, Any])
def get_all_settings():
    """Returns dynamic configuration and masked marketplace credentials (ADM-1, ADM-3)."""
    return SettingsService.get_all_settings()


@router.put("/brand-voice", response_model=Dict[str, str])
def update_brand_voice(payload: BrandVoiceUpdate):
    """Updates brand name, tone, audience, and guidance for AI listing generation (ADM-1)."""
    data = payload.model_dump(exclude_unset=True)
    return SettingsService.update_brand_voice(data)


@router.get("/banned-claims", response_model=List[str])
def get_banned_claims():
    """Returns the active list of prohibited marketplace superlatives and claims (ADM-1)."""
    return SettingsService.get_banned_claims()


@router.put("/banned-claims", response_model=List[str])
def update_banned_claims(payload: BannedClaimsUpdate):
    """Updates the active list of prohibited claims without code changes or redeployment (ADM-1)."""
    if not payload.banned_claims:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Banned claims list cannot be empty",
        )
    return SettingsService.update_banned_claims(payload.banned_claims)


@router.get("/credentials", response_model=Dict[str, Any])
def get_credentials():
    """Returns masked credentials and connection statuses for marketplaces and AI engine (ADM-3)."""
    return SettingsService.get_masked_credentials()


@router.put("/credentials", response_model=Dict[str, Any])
def update_credentials(payload: CredentialsUpdate):
    """Safely updates marketplace and AI credentials without exposing plaintext secrets (ADM-3)."""
    data = payload.model_dump(exclude_unset=True)
    return SettingsService.update_credentials(data)


@router.get("/system-health", response_model=Dict[str, Any])
def get_system_health(db: Session = Depends(get_db)):
    """Returns comprehensive system health, sync heartbeats, and active alerts (ADM-4)."""
    return SettingsService.get_system_health(db)

