"""
Softy Platforma — Adapter Registry & Source Factory (17.H)
Platforma adapterlarini ro'yxatga olish, yangi manba qo'shish va
tayyor adapter bo'lmaganda 'Adapter ishlab chiqilishi kerak' holatini qaytarish.
"""

from typing import Dict, Any, Optional
from app.adapters.base import BasePlatformAdapter
from app.adapters.uzex import UzexAdapter
from app.adapters.xt_xarid import XtXaridAdapter
from app.adapters.ebirja import EbirjaAdapter
from app.adapters.cooperation import CooperationAdapter
from app.database import db_session

class FallbackUnimplementedAdapter(BasePlatformAdapter):
    """
    Hali maxsus adapteri yozilmagan manbalar uchun zaxira adapteri.
    Holati: 'Adapter ishlab chiqilishi kerak'
    """
    def __init__(self, platform_id: str, name: str, base_url: str):
        super().__init__(platform_id, name, base_url)

    def test_connection(self) -> Dict[str, Any]:
        return {
            "status": "WARNING",
            "message": "Ushbu manba uchun maxsus dasturiy adapter mavjud emas. Adapter ishlab chiqilishi kerak."
        }

    def list_lots(self, *args, **kwargs) -> Dict[str, Any]:
        return {"items": [], "total": 0, "has_more": False, "error": "Adapter ishlab chiqilishi kerak"}

    def get_lot_details(self, lot_id: str) -> Dict[str, Any]:
        return {"error": "Adapter ishlab chiqilishi kerak"}

    def get_results(self, lot_id: str) -> Dict[str, Any]:
        return {"error": "Adapter ishlab chiqilishi kerak"}

    def get_contracts(self, lot_id: str) -> list:
        return []

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        return raw_data

    def health_check(self) -> Dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "health": "ADAPTER_REQUIRED",
            "status_text": "Adapter ishlab chiqilishi kerak",
            "operator": "Noma'lum"
        }

# Factory instance registry
_ADAPTERS: Dict[str, BasePlatformAdapter] = {
    "uzex": UzexAdapter(),
    "xt_xarid": XtXaridAdapter(),
    "ebirja": EbirjaAdapter(),
    "cooperation": CooperationAdapter()
}

def get_adapter(platform_id: str) -> BasePlatformAdapter:
    """Berilgan platforma ID si bo'yicha adapterni olish."""
    if platform_id in _ADAPTERS:
        return _ADAPTERS[platform_id]
    
    # Bazadan manbani tekshirish
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, base_url, adapter_ready FROM sources WHERE id = ?", (platform_id,))
        row = cursor.fetchone()
        if row:
            if row["adapter_ready"] and row["id"] in _ADAPTERS:
                return _ADAPTERS[row["id"]]
            return FallbackUnimplementedAdapter(row["id"], row["name"], row["base_url"])

    return FallbackUnimplementedAdapter(platform_id, platform_id, f"https://{platform_id}.uz")

def register_custom_source(source_id: str, name: str, domain: str, base_url: str, operator: str) -> Dict[str, Any]:
    """
    Administrator tomonidan yangi manba qo'shilganda:
    Agar tayyor adapter bo'lmasa, uni 'Adapter ishlab chiqilishi kerak' holatida saqlash.
    """
    has_adapter = source_id in _ADAPTERS or any(d in domain for d in ["uzex", "xt-xarid", "ebirja", "cooperation"])
    status = "faol" if has_adapter else "adapter_kutilmoqda"
    adapter_ready = 1 if has_adapter else 0

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO sources (
            id, name, domain, base_url, operator,
            history_start, loaded_range_start, loaded_range_end,
            records_count, missing_docs_count, status, adapter_ready, health_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?);
        """, (
            source_id, name, domain, base_url, operator,
            "Noma'lum", "Yuklanmagan", "Yuklanmagan",
            status, adapter_ready,
            "OK" if has_adapter else "Adapter ishlab chiqilishi kerak"
        ))

    return {
        "success": True,
        "source_id": source_id,
        "status": status,
        "adapter_ready": bool(adapter_ready),
        "message": "Manba faol" if has_adapter else "Yangi manba qo'shildi. Adapter ishlab chiqilishi kerak holatida saqlandi."
    }
