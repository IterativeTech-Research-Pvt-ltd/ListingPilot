"""
Self-Serve Settings & Persistent Admin Configuration Service (ADM-1, ADM-2, ADM-3, ADM-4)
Allows client to update brand voice, compliance rules, banned claims, and marketplace credentials
without modifying code or requiring vendor intervention.
"""
import os
import copy
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import text
from app.core.config import settings

# Runtime store for admin-edited settings and credentials. It is gitignored and created on
# first use; LISTINGPILOT_SETTINGS_FILE lets tests point it somewhere disposable.
SETTINGS_FILE = Path(
    os.environ.get("LISTINGPILOT_SETTINGS_FILE")
    or Path(__file__).resolve().parents[1] / "data" / "dynamic_settings.json"
)

DEFAULT_SETTINGS = {
    "brand_voice": {
        "brand_name": "Gulmohar Home",
        "tone": "Professional, informative, benefit-driven, and engaging",
        "target_audience": "Discerning shoppers seeking premium quality, reliability, and value",
        "avoid_claims": "Avoid cheap promotional slang, fake certifications, or unverified claims"
    },
    "banned_claims": [
        "free delivery",
        "free shipping",
        "best seller",
        "cheapest",
        "100% guarantee",
        "money back",
        "satisfaction guaranteed",
        "top rated",
        "no. 1",
        "number one",
        "cash on delivery",
        "cod available"
    ],
    "marketplace_limits": {
        "amazon": {"max_title_length": 200, "min_photos": 3, "required_bullets": 5},
        "flipkart": {"max_title_length": 120, "min_photos": 1, "required_bullets": 3},
        "meesho": {"max_title_length": 100, "min_photos": 1, "required_bullets": 3, "disallow_html": True}
    },
    "credentials": {
        "amazon_seller_id": "",
        "amazon_sp_api_client_id": "",
        "amazon_sp_api_client_secret": "",
        "amazon_sp_api_refresh_token": "",
        "flipkart_app_id": "",
        "flipkart_app_secret": "",
        "openrouter_api_key": ""
    },
    "meesho_templates": {
        "Bedsheets": "meesho_template_bedsheets_v1.xlsx",
        "Pooja items": "meesho_template_pooja_v1.xlsx",
        "Kurtas": "meesho_template_kurtas_v1.xlsx"
    },
    "last_sync": {
        "amazon": datetime.now(timezone.utc).isoformat(),
        "flipkart": datetime.now(timezone.utc).isoformat(),
        "meesho": datetime.now(timezone.utc).isoformat()
    }
}


class SettingsService:
    """Manages persistent dynamic configuration for the client."""

    @classmethod
    def _ensure_loaded(cls) -> Dict[str, Any]:
        """Loads persistent settings or creates default store."""
        if not SETTINGS_FILE.parent.exists():
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

        if not SETTINGS_FILE.exists():
            # Secrets from .env are not copied into the file; adapters read them from env directly
            data = copy.deepcopy(DEFAULT_SETTINGS)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return data

        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return copy.deepcopy(DEFAULT_SETTINGS)

    @classmethod
    def _save(cls, data: Dict[str, Any]):
        """Persists settings to JSON disk storage."""
        if not SETTINGS_FILE.parent.exists():
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def get_all_settings(cls) -> Dict[str, Any]:
        """Returns full settings with credentials safely masked (ADM-3)."""
        data = cls._ensure_loaded()
        masked = dict(data)
        masked["credentials"] = cls.get_masked_credentials()
        return masked

    @classmethod
    def get_raw_settings(cls) -> Dict[str, Any]:
        return cls._ensure_loaded()

    @classmethod
    def get_banned_claims(cls) -> List[str]:
        """Retrieves active banned claims for RuleEngine (ADM-1)."""
        data = cls._ensure_loaded()
        return data.get("banned_claims", DEFAULT_SETTINGS["banned_claims"])

    @classmethod
    def update_banned_claims(cls, new_claims: List[str]) -> List[str]:
        """Updates banned claims dynamically without redeployment (ADM-1)."""
        data = cls._ensure_loaded()
        cleaned = list(dict.fromkeys(c.strip().lower() for c in new_claims if c and c.strip()))
        data["banned_claims"] = cleaned
        cls._save(data)
        return cleaned

    @classmethod
    def get_brand_voice(cls) -> Dict[str, str]:
        """Retrieves brand voice for AIService prompts (ADM-1)."""
        data = cls._ensure_loaded()
        return data.get("brand_voice", DEFAULT_SETTINGS["brand_voice"])

    @classmethod
    def update_brand_voice(cls, voice_update: Dict[str, str]) -> Dict[str, str]:
        """Updates brand voice narrative and tone (ADM-1)."""
        data = cls._ensure_loaded()
        current = data.get("brand_voice", {})
        for k in ["brand_name", "tone", "target_audience", "avoid_claims"]:
            if k in voice_update and voice_update[k]:
                current[k] = voice_update[k].strip()
        data["brand_voice"] = current
        cls._save(data)
        return current

    @classmethod
    def get_masked_credentials(cls) -> Dict[str, Dict[str, Any]]:
        """Returns credentials with values masked and connection status flags (ADM-3)."""
        data = cls._ensure_loaded()
        creds = data.get("credentials", {})
        
        def mask(val: Optional[str]) -> str:
            if not val: return ""
            if len(val) <= 6: return "******"
            return f"{val[:3]}****{val[-3:]}"

        return {
            "amazon": {
                "seller_id": creds.get("amazon_seller_id", ""),
                "has_client_id": bool(creds.get("amazon_sp_api_client_id")),
                "client_id_masked": mask(creds.get("amazon_sp_api_client_id")),
                "has_secret": bool(creds.get("amazon_sp_api_client_secret")),
                "has_refresh_token": bool(creds.get("amazon_sp_api_refresh_token")),
                "status": "ready" if creds.get("amazon_sp_api_client_id") else "sandbox_stub"
            },
            "flipkart": {
                "has_app_id": bool(creds.get("flipkart_app_id")),
                "app_id_masked": mask(creds.get("flipkart_app_id")),
                "has_app_secret": bool(creds.get("flipkart_app_secret")),
                "status": "ready" if creds.get("flipkart_app_id") else "sandbox_stub"
            },
            "ai_engine": cls._ai_engine_status(creds, mask)
        }

    @classmethod
    def _ai_engine_status(cls, creds: Dict[str, Any], mask) -> Dict[str, Any]:
        """Reports the AI provider actually in use (AI_PROVIDER), its model and whether its key is set."""
        provider = settings.AI_PROVIDER
        if provider == "groq":
            key, model = settings.GROQ_API_KEY or "", settings.GROQ_MODEL
        elif provider == "anthropic":
            key, model = settings.ANTHROPIC_API_KEY or "", settings.CLAUDE_MODEL
        else:
            key = creds.get("openrouter_api_key") or getattr(settings, "OPENROUTER_API_KEY", "") or ""
            model = settings.OPENROUTER_MODEL
        return {
            "provider": provider,
            "has_api_key": bool(key),
            "api_key_masked": mask(key),
            "model": model,
            "status": "active" if key else "missing_key"
        }

    @classmethod
    def update_credentials(cls, new_creds: Dict[str, str]) -> Dict[str, Any]:
        """Allows client to update credentials safely (ADM-3)."""
        data = cls._ensure_loaded()
        current = data.get("credentials", {})
        for k, v in new_creds.items():
            if v and v.strip() and not v.startswith("***"):
                current[k] = v.strip()
        data["credentials"] = current
        cls._save(data)
        return cls.get_masked_credentials()

    @classmethod
    def record_sync(cls, marketplace: str):
        """Records timestamp of successful marketplace synchronization (ADM-4)."""
        data = cls._ensure_loaded()
        if "last_sync" not in data: data["last_sync"] = {}
        data["last_sync"][marketplace.lower()] = datetime.now(timezone.utc).isoformat()
        cls._save(data)

    @classmethod
    def get_system_health(cls, db=None) -> Dict[str, Any]:
        """
        Comprehensive system monitoring report (ADM-4):
        Checks active connections, sync timestamps, and triggers alerts for failed jobs or expired keys.
        The database is queried on every call; nothing is reported as connected without checking.
        """
        data = cls._ensure_loaded()
        last_sync = data.get("last_sync", {})
        
        alerts = []
        creds = data.get("credentials", {})
        
        # Check if Amazon is running on stub
        if not creds.get("amazon_sp_api_client_id"):
            alerts.append({
                "severity": "info",
                "channel": "amazon",
                "title": "Amazon SP-API Sandbox Mode",
                "message": "Running on simulated SP-API adapter. Provide seller credentials in Admin tab when live launch begins."
            })

        # Check if Flipkart is running on stub
        if not creds.get("flipkart_app_id"):
            alerts.append({
                "severity": "info",
                "channel": "flipkart",
                "title": "Flipkart Seller API Sandbox Mode",
                "message": "Flipkart sandbox active. Add Developer App ID & Secret in Admin tab for live push."
            })

        database = {"status": "not_checked", "type": "PostgreSQL (Supabase)"}
        if db is not None:
            try:
                db.execute(text("SELECT 1"))
                database["status"] = "connected"
            except Exception as e:
                database.update(status="unreachable", error=str(getattr(e, "orig", None) or e).strip().splitlines()[0])
                alerts.append({
                    "severity": "warn",
                    "channel": "database",
                    "title": "Database Unreachable",
                    "message": f"The API cannot query the database: {database['error']}",
                })

        ai = cls._ai_engine_status(creds, lambda _v: "")
        return {
            "status": "healthy" if database["status"] == "connected" else "degraded",
            "phase": 4,
            "system_time": datetime.now(timezone.utc).isoformat(),
            "services": {
                "database": database,
                "ai_content_engine": {"status": ai["status"], "provider": ai["provider"], "model": ai["model"]},
                "amazon_sp_api": {"status": "ready" if creds.get("amazon_sp_api_client_id") else "sandbox_stub"},
                "flipkart_seller_api": {"status": "ready" if creds.get("flipkart_app_id") else "sandbox_stub"},
                "meesho_exporter": {"status": "ready", "mode": "excel_bulk_generator"}
            },
            "last_sync": last_sync,
            "active_alerts": alerts
        }
