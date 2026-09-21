"""
Softy Platforma — Cooperation Platform Adapter
cooperation.uz — Elektron kooperatsiya portali (O'zRTXB).

MUHIM: bu manba JSON API bermaydi — server tomonda render qilinadigan Yii2
GridView jadvallari (HTML). Ma'lumot xarid REJALARI (shartnoma emas):
tashkilot, mahsulot nomi, TN VED kod, hajm, funksionallik, texnik xususiyatlar.
INN, narx, yetkazib beruvchi yo'q — bu erta talab signali (radar uchun qimmatli).

Ikki reja turi: /plans/budjet (byudjet) va /plans/korporativ (korporativ).
"""

import re
import ssl
import time
import json
import html
import hashlib
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.adapters.base import BasePlatformAdapter
from app.database import db_session

logger = logging.getLogger(__name__)

BASE = "https://cooperation.uz"
PLAN_TYPES = [("budjet", "Byudjet"), ("korporativ", "Korporativ")]
MIN_REQUEST_INTERVAL_S = 3.0
MAX_PAGES_PER_TYPE = 200
# Ustunlar tartibi: #, sana, tashkilot, chorak, mahsulot, TN VED, hajm,
# funksionallik, texnik xususiyatlar
COLS = 9


class CooperationAdapter(BasePlatformAdapter):
    def __init__(self):
        super().__init__(
            platform_id="cooperation",
            name="cooperation.uz (Elektron Kooperatsiya Portali)",
            base_url=BASE,
        )

    _last_ts = 0.0

    def _throttle(self):
        el = time.time() - CooperationAdapter._last_ts
        if el < MIN_REQUEST_INTERVAL_S:
            time.sleep(MIN_REQUEST_INTERVAL_S - el)
        CooperationAdapter._last_ts = time.time()

    def test_connection(self) -> Dict[str, Any]:
        t0 = time.time()
        try:
            req = urllib.request.Request(BASE, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                ms = int((time.time() - t0) * 1000)
                return {"status": "OK", "code": resp.getcode(), "latency_ms": ms,
                        "message": f"cooperation.uz aloqa OK ({ms} ms)"}
        except Exception as e:
            return {"status": "ERROR", "code": 0,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "message": f"cooperation.uz ulanish xatosi: {e}"}

    # ── HTML olish va parsing ────────────────────────────────────────────────

    def _fetch(self, path: str) -> str:
        self._throttle()
        req = urllib.request.Request(BASE + path, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html",
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.read().decode("utf-8", errors="replace")

    @staticmethod
    def _clean(cell: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", " ", cell)).strip()

    def _parse_rows(self, page_html: str) -> List[List[str]]:
        m = re.search(r"<table[^>]*>(.*?)</table>", page_html, re.S)
        if not m:
            return []
        out = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
            cells = [self._clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(cells) >= COLS and any(cells[1:]):
                out.append(cells)
        return out

    @staticmethod
    def _row_id(plan_type: str, cells: List[str]) -> str:
        # Barqaror ID: jadvalda shartnoma raqami yo'q, shuning uchun mazmundan
        # hash. Ayni reja qayta ko'rilganda ayni hash — INSERT OR IGNORE dedup.
        key = "|".join([plan_type, cells[2], cells[3], cells[4], cells[5]])
        return "coop_" + hashlib.md5(key.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _parse_date(s: str) -> Optional[str]:
        # "10:45 11-09-2026" -> "2026-09-11"
        m = re.search(r"(\d{2})-(\d{2})-(\d{4})", s or "")
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None

    def _map(self, plan_type: str, label: str, cells: List[str]) -> Dict[str, Any]:
        org, quarter, product = cells[2], cells[3], cells[4]
        hs_code, volume = cells[5], cells[6]
        functionality = cells[7] if len(cells) > 7 else ""
        tech = cells[8] if len(cells) > 8 else ""
        return {
            "id": self._row_id(plan_type, cells),
            "lot_number": self._row_id(plan_type, cells).replace("coop_", ""),
            "title": (product or "Kooperatsiya rejasi")[:500],
            "description": " | ".join(filter(None, [functionality, tech]))[:2000],
            "platform_id": "cooperation",
            "source_url": f"{BASE}/plans/{plan_type}",
            "procurement_type": f"Xarid rejasi ({label})",
            "official_status": "REJA",
            "announcement_date": self._parse_date(cells[1]),
            "start_price": 0.0,
            "currency": "UZS",
            "buyer_inn": None,          # jadvalda INN yo'q — FK uchun NULL shart
            "buyer_name": org or None,
            "region": quarter or None,   # chorak (davr) shu ustunda
            "extracted_text": " ".join(filter(None, [product, functionality, tech, hs_code]))[:4000],
            "raw_data_json": json.dumps({"tn_ved": hs_code, "hajm": volume,
                                         "chorak": quarter, "tashkilot": org,
                                         "mahsulot": product, "funksionallik": functionality,
                                         "texnik": tech}, ensure_ascii=False),
        }

    def _insert(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        cols = list(rows[0].keys())
        marks = ",".join("?" * len(cols))
        sql = (f"INSERT OR IGNORE INTO lots ({','.join(cols)}, created_in_db_date) "
               f"VALUES ({marks}, ?);")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        added = 0
        with db_session() as conn:
            cur = conn.cursor()
            for r in rows:
                cur.execute(sql, [r[c] for c in cols] + [now])
                added += cur.rowcount
        return added

    def fetch_updates(self, since_date: str = "2024-09-01") -> Dict[str, Any]:
        added = seen = 0
        try:
            for plan_type, label in PLAN_TYPES:
                prev_ids = None
                for page in range(1, MAX_PAGES_PER_TYPE + 1):
                    rows = self._parse_rows(self._fetch(f"/plans/{plan_type}?page={page}"))
                    if not rows:
                        break
                    seen += len(rows)
                    mapped = [self._map(plan_type, label, c) for c in rows]
                    ids = tuple(m["id"] for m in mapped)
                    # Yii GridView oxirgi sahifadan keyin o'sha sahifani takrorlaydi —
                    # ayni id lar ketma-ket kelsa, tugadi.
                    if ids == prev_ids:
                        break
                    prev_ids = ids
                    added += self._insert(mapped)
            return {"platform": self.platform_id, "status": "SUCCESS",
                    "since_date": since_date, "records_added": added,
                    "records_updated": 0,
                    "message": f"{added} ta reja qo'shildi ({seen} qator ko'rildi)"}
        except Exception as ex:
            logger.error(f"Cooperation yuklashda xato: {ex}")
            return {"platform": self.platform_id, "status": "ERROR",
                    "since_date": since_date, "records_added": added,
                    "records_updated": 0, "message": f"Cooperation xatosi: {ex}"}

    # ── Base talab qiladigan qolgan metodlar (minimal) ───────────────────────

    def list_lots(self, keyword=None, date_from=None, date_to=None,
                  page=1, limit=50, cursor=None) -> Dict[str, Any]:
        return {"items": [], "total": 0, "has_more": False,
                "next_cursor": None, "platform": self.platform_id}

    def get_lot_details(self, lot_id: str) -> Dict[str, Any]:
        return {"lot_id": lot_id, "platform": self.platform_id}

    def get_results(self, lot_id: str) -> Dict[str, Any]:
        return {"lot_id": lot_id, "winner": None, "final_price": None}

    def get_contracts(self, lot_id: str) -> List[Dict[str, Any]]:
        return []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return raw

    def health_check(self) -> Dict[str, Any]:
        t = self.test_connection()
        return {"platform_id": self.platform_id, "health": t["status"],
                "latency_ms": t.get("latency_ms", 0),
                "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
