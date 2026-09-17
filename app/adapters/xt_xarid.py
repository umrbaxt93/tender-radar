"""
Softy Platforma — XT-Xarid Platform Adapter
xt-xarid.uz (Hayot Birja / XT-Xarid Texnologiyalari AJ) adapteri.
"""

import ssl
import time
import urllib.request
import urllib.error
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.adapters.base import BasePlatformAdapter

class XtXaridAdapter(BasePlatformAdapter):
    """
    XT-Xarid portali (https://xt-xarid.uz) adapteri.
    """

    def __init__(self):
        super().__init__(
            platform_id="xt_xarid",
            name="xt-xarid.uz (Hayot Birja / XT-Xarid)",
            base_url="https://xt-xarid.uz"
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
                    "message": f"xt-xarid.uz bilan aloqa muvaffaqiyatli ({latency} ms)"
                }
        except Exception as e:
            return {
                "status": "ERROR",
                "code": 0,
                "latency_ms": int((time.time() - t0) * 1000),
                "message": f"xt-xarid.uz ulanish xatosi: {str(e)}"
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
            "url": f"{self.base_url}/contract/{lot_id}.1.1" if "." not in str(lot_id) else f"{self.base_url}/contract/{lot_id}",
            "platform": self.platform_id
        }

    def get_results(self, lot_id: str) -> Dict[str, Any]:
        return {"lot_id": lot_id}

    def get_contracts(self, lot_id: str) -> List[Dict[str, Any]]:
        return [{
            "contract_url": f"{self.base_url}/contract/{lot_id}.1.1",
            "pdf_url": f"{self.base_url}/contract/{lot_id}.1.1/pdf"
        }]

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        lot_id = str(raw.get("lot_id") or raw.get("id") or "")
        contract_num = raw.get("contract_number") or raw.get("contract_id") or lot_id
        contract_url = raw.get("contract_url")
        if not contract_url and contract_num:
            contract_url = f"{self.base_url}/contract/{contract_num}" if "/" not in str(contract_num) else contract_num
            if not contract_url.startswith("http"):
                contract_url = f"{self.base_url}/contract/{contract_num}.1.1"

        return {
            "id": f"xt_{lot_id}",
            "lot_number": str(raw.get("lot_number") or lot_id),
            "title": raw.get("title", ""),
            "description": raw.get("description", ""),
            "platform_id": self.platform_id,
            "source_url": contract_url or f"{self.base_url}/contract/{lot_id}.1.1",
            "procurement_type": raw.get("procurement_type", "Elektron do‘kon"),
            "official_status": raw.get("status", "COMPLETED"),
            "announcement_date": raw.get("date"),
            "start_price": float(raw.get("start_price") or raw.get("amount") or 0),
            "final_price": float(raw.get("final_price") or raw.get("amount") or 0),
            "currency": raw.get("currency", "UZS"),
            "buyer_inn": str(raw.get("buyer_inn", "")).strip(),
            "buyer_name": raw.get("buyer_name", ""),
            "winner_name": raw.get("winner_name", ""),
            "has_contract": bool(contract_url),
            "contract_url": contract_url,
            "contract_number": str(contract_num),
            "license_end_date": raw.get("license_end_date")
        }

    def health_check(self) -> Dict[str, Any]:
        conn_test = self.test_connection()
        return {
            "platform_id": self.platform_id,
            "health": conn_test["status"],
            "latency_ms": conn_test.get("latency_ms", 0),
            "operator": "Hayot Birja AJ / XT-Xarid",
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
