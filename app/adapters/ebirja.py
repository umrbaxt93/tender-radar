"""
Softy Platforma — E-Birja Platform Adapter
xarid.ebirja.uz (Toshkent tovar xomashyo birjasi AJ - ТТСБ / TTXB) adapteri.
"""

import ssl
import time
import urllib.request
import urllib.error
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.adapters.base import BasePlatformAdapter

class EbirjaAdapter(BasePlatformAdapter):
    """
    Toshkent tovar xomashyo birjasi AJ davlat xaridlari portali (https://xarid.ebirja.uz).
    """

    def __init__(self):
        super().__init__(
            platform_id="ebirja",
            name="xarid.ebirja.uz (Toshkent tovar xomashyo birjasi)",
            base_url="https://xarid.ebirja.uz"
        )

    def test_connection(self) -> Dict[str, Any]:
        t0 = time.time()
        try:
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(
                self.base_url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"}
            )
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                latency = int((time.time() - t0) * 1000)
                return {
                    "status": "OK",
                    "code": resp.getcode(),
                    "latency_ms": latency,
                    "operator": "Toshkent tovar xomashyo birjasi AJ",
                    "message": f"xarid.ebirja.uz bilan aloqa muvaffaqiyatli ({latency} ms)"
                }
        except Exception as e:
            return {
                "status": "ERROR",
                "code": 0,
                "latency_ms": int((time.time() - t0) * 1000),
                "operator": "Toshkent tovar xomashyo birjasi AJ",
                "message": f"xarid.ebirja.uz ulanish xatosi: {str(e)}"
            }

    def list_lots(self, keyword: Optional[str] = None, 
                  date_from: Optional[str] = None, 
                  date_to: Optional[str] = None,
                  page: int = 1, limit: int = 50,
                  cursor: Optional[str] = None) -> Dict[str, Any]:
        return {
            "items": [],
            "total": 0,
            "has_more": False,
            "next_cursor": None,
            "platform": self.platform_id
        }

    def get_lot_details(self, lot_id: str) -> Dict[str, Any]:
        return {
            "lot_id": lot_id,
            "url": f"{self.base_url}/uz/auction/{lot_id}",
            "platform": self.platform_id
        }

    def get_results(self, lot_id: str) -> Dict[str, Any]:
        return {"lot_id": lot_id}

    def get_contracts(self, lot_id: str) -> List[Dict[str, Any]]:
        return []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        lot_id = str(raw.get("id") or raw.get("lot_id") or "")
        return {
            "id": f"ebirja_{lot_id}",
            "lot_number": str(raw.get("lot_number") or lot_id),
            "title": raw.get("title", ""),
            "description": raw.get("description", ""),
            "platform_id": self.platform_id,
            "source_url": raw.get("source_url") or f"{self.base_url}/uz/auction/{lot_id}",
            "procurement_type": raw.get("procurement_type", "Auksion"),
            "official_status": raw.get("status", "COMPLETED"),
            "announcement_date": raw.get("date"),
            "deadline_date": raw.get("deadline"),
            "start_price": float(raw.get("start_price") or 0),
            "final_price": float(raw.get("final_price") or raw.get("start_price") or 0),
            "currency": raw.get("currency", "UZS"),
            "buyer_inn": str(raw.get("buyer_inn", "")).strip(),
            "buyer_name": raw.get("buyer_name", ""),
            "winner_name": raw.get("winner_name", ""),
            "has_contract": bool(raw.get("contract_url")),
            "contract_url": raw.get("contract_url"),
            "license_end_date": raw.get("license_end_date")
        }

    def health_check(self) -> Dict[str, Any]:
        conn_test = self.test_connection()
        return {
            "platform_id": self.platform_id,
            "health": conn_test["status"],
            "latency_ms": conn_test.get("latency_ms", 0),
            "operator": "Toshkent tovar xomashyo birjasi AJ (TTXB)",
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
