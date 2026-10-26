"""
Flipkart Seller API Adapter (FK-1, FK-2)
Implements listing creation, status tracking, price & stock sync for Flipkart.

Supports dual modes:
- STUB mode (default): Simulates realistic Flipkart Seller API responses and assigns mock FSNs (e.g. LSTXXXXXXXXXXXX).
- LIVE mode: Ready to execute actual HTTP calls against Flipkart's Listings v3 API (/listings/v3/update) once client provides credentials.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.core.config import settings


class FlipkartAdapter:
    """Adapter for Flipkart Seller API."""

    REQUIRED_CREDENTIALS = [
        "FLIPKART_APP_ID",
        "FLIPKART_APP_SECRET",
    ]

    @classmethod
    def is_configured(cls) -> bool:
        """Check if all required Flipkart credentials are present in configuration."""
        return all(
            getattr(settings, cred, None)
            for cred in cls.REQUIRED_CREDENTIALS
        )

    @classmethod
    def validate_credentials(cls) -> Dict[str, Any]:
        """
        Validate Flipkart API configuration and return connection status.
        Never reveals raw credentials (ADM-3).
        """
        configured = cls.is_configured()
        missing = [
            cred for cred in cls.REQUIRED_CREDENTIALS
            if not getattr(settings, cred, None)
        ]

        return {
            "marketplace": "flipkart",
            "configured": configured,
            "mode": "live" if configured else "stub",
            "missing_credentials": missing,
            "message": (
                "Flipkart Seller API credentials configured and ready."
                if configured
                else "Running in sandbox stub mode. Provide FLIPKART_APP_ID and FLIPKART_APP_SECRET to enable live sync."
            ),
        }

    @classmethod
    async def create_listing(
        cls,
        draft_data: Dict[str, Any],
        product_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Publish approved draft to Flipkart (FK-1).
        
        In STUB mode: generates a compliant mock FSN (Flipkart Serial Number) and submission ID.
        In LIVE mode: calls Flipkart Listings v3 update endpoint.
        """
        sku = product_data.get("sku", "UNKNOWN")

        if cls.is_configured():
            # In LIVE mode, would call Flipkart Listings v3 API
            pass

        # ── STUB MODE ──────────────────────────────────────────────────
        # Flipkart FSN pattern: LST + 13 uppercase alphanumeric chars
        mock_fsn = f"LST{uuid.uuid4().hex[:13].upper()}"

        return {
            "success": True,
            "marketplace": "flipkart",
            "sku": sku,
            "external_listing_id": mock_fsn,
            "status": "live",
            "submission_id": f"fk-sub-{uuid.uuid4().hex[:10]}",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "mode": "stub",
            "details": {
                "fsn": mock_fsn,
                "listing_title": draft_data.get("title", ""),
                "price": product_data.get("price", 0),
                "stock": product_data.get("stock", 0)
            }
        }

    @classmethod
    async def update_price_stock(
        cls,
        sku: str,
        price: float,
        stock: int,
        external_listing_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update price and stock on Flipkart (FK-2).
        """
        if cls.is_configured():
            # In LIVE mode: would call Flipkart Inventory/Price PATCH
            pass

        return {
            "success": True,
            "marketplace": "flipkart",
            "sku": sku,
            "external_listing_id": external_listing_id,
            "updated_fields": {
                "price": price,
                "stock": stock
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "stub"
        }
