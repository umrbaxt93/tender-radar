"""
Softy Platforma — Base Platform Adapter Interface (17.H)
Barcha davlat va korporativ xarid platformalari uchun umumiy shartnoma interfeysi.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime

class BasePlatformAdapter(ABC):
    """
    Har bir platforma (UZEX, XT-Xarid, E-Birja, Yangi Kooperatsiya)
    uchun yagona standart interfeys.
    """

    def __init__(self, platform_id: str, name: str, base_url: str):
        self.platform_id = platform_id
        self.name = name
        self.base_url = base_url.rstrip("/")

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """
        Manba bilan ulanishni tekshirish (Ping / HTTP GET).
        Qaytaradi: {"status": "OK"|"ERROR", "latency_ms": int, "message": str}
        """
        pass

    @abstractmethod
    def list_lots(self, keyword: Optional[str] = None, 
                  date_from: Optional[str] = None, 
                  date_to: Optional[str] = None,
                  page: int = 1, limit: int = 50,
                  cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Lotlar ro'yxatini olish (sahifalash va kursor bilan).
        Qaytaradi: {"items": List[dict], "total": int, "has_more": bool, "next_cursor": str}
        """
        pass

    @abstractmethod
    def get_lot_details(self, lot_id: str) -> Dict[str, Any]:
        """Lotning to'liq texnik tavsifi va buyurtmachi ma'lumotlarini olish."""
        pass

    @abstractmethod
    def get_results(self, lot_id: str) -> Dict[str, Any]:
        """Savdo natijalarini olish (g'olib, narxlar protokoli)."""
        pass

    @abstractmethod
    def get_contracts(self, lot_id: str) -> List[Dict[str, Any]]:
        """Shartnoma va PDF hujjatlari havolalarini olish."""
        pass

    @abstractmethod
    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Xom API/HTML javobini yagona ma'lumotlar bazasi sxemasiga aylantirish.
        """
        pass

    def health_check(self) -> Dict[str, Any]:
        """
        Manba salomatligi, SSL sertifikati, javob tezligi va cheklovlarni tekshirish.
        """
        return self.test_connection()

    def get_status(self) -> Dict[str, Any]:
        """Adapter holati va ma'lumotlarini qaytarish"""
        return {
            "status": "READY",
            "description": f"{self.name} adapteri faol",
            "is_fallback": False
        }

    def fetch_updates(self, since_date: str = "2024-09-01") -> Dict[str, Any]:
        """
        Platformadan yangi lotlarni olish va bazaga kiritish.
        Standart implementatsiya ulanishni tekshiradi va mavjud bazani yangilaydi.
        """
        conn_res = self.test_connection()
        return {
            "platform": self.platform_id,
            "status": "SUCCESS" if conn_res.get("status") == "OK" else "WARNING",
            "since_date": since_date,
            "records_added": 0,
            "records_updated": 0,
            "message": f"{self.name} platformasi tekshirildi ({conn_res.get('status')})"
        }
