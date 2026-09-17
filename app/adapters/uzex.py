"""
Softy Platforma — UZEX Platform Adapter
xarid.uzex.uz / etender.uzex.uz bilan ishlash adapteri.
"""

import ssl
import time
import urllib.request
import urllib.error
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.adapters.base import BasePlatformAdapter
from app.database import db_session

logger = logging.getLogger(__name__)

# Tasdiqlangan ommaviy API (docs/SOURCE_API.md, 2026-09-14 da jonli tekshirilgan)
API_BASE = "https://xarid-api-purchase.uzex.uz"
LIST_PATH = "/Common/GetCompetitions"
DETAIL_PATH = "/Common/GetCompetition"

# Manbani bloklamaslik uchun so'rovlar orasidagi eng kichik tanaffus.
# Bu chegara hech qachon pasaytirilmasin.
MIN_REQUEST_INTERVAL_S = 3.0

PAGE_SIZE = 50
MAX_PAGES_PER_RUN = 20
MAX_NEW_PER_RUN = 150

class UzexAdapter(BasePlatformAdapter):
    """
    O'zRTXB Davlat xaridlari (xarid.uzex.uz) adapteri.
    """

    def __init__(self):
        super().__init__(
            platform_id="uzex",
            name="xarid.uzex.uz (O'zRTXB Davlat xaridlari)",
            base_url="https://xarid.uzex.uz"
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
                    "message": f"xarid.uzex.uz bilan aloqa muvaffaqiyatli ({latency} ms)"
                }
        except Exception as e:
            return {
                "status": "ERROR",
                "code": 0,
                "latency_ms": int((time.time() - t0) * 1000),
                "message": f"xarid.uzex.uz ulanish xatosi: {str(e)}"
            }

    def list_lots(self, keyword: Optional[str] = None, 
                  date_from: Optional[str] = None, 
                  date_to: Optional[str] = None,
                  page: int = 1, limit: int = 50,
                  cursor: Optional[str] = None) -> Dict[str, Any]:
        # Jonli yoki keshdagi lotlar ro'yxatini qaytarish
        return {
            "items": [],
            "total": 0,
            "has_more": False,
            "next_cursor": None,
            "platform": self.platform_id
        }

    def get_lot_details(self, lot_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/dx/deals/{lot_id}"
        return {
            "lot_id": lot_id,
            "url": url,
            "platform": self.platform_id
        }

    def get_results(self, lot_id: str) -> Dict[str, Any]:
        return {
            "lot_id": lot_id,
            "winner": None,
            "final_price": None
        }

    def get_contracts(self, lot_id: str) -> List[Dict[str, Any]]:
        return []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        lot_id = str(raw.get("id") or raw.get("lot_id") or "")
        return {
            "id": f"uzex_{lot_id}",
            "lot_number": str(raw.get("lot_number") or lot_id),
            "title": raw.get("title", ""),
            "description": raw.get("description", ""),
            "platform_id": self.platform_id,
            "source_url": raw.get("source_url") or f"{self.base_url}/dx/deals/{lot_id}",
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

    # ────────────────────────────────────────────────────────────────────
    # HAQIQIY YUKLASH — tasdiqlangan ommaviy UZEX API orqali
    # ────────────────────────────────────────────────────────────────────

    _last_request_ts = 0.0

    def _throttle(self):
        """So'rovlar orasida MIN_REQUEST_INTERVAL_S tanaffusni kafolatlaydi."""
        elapsed = time.time() - UzexAdapter._last_request_ts
        if elapsed < MIN_REQUEST_INTERVAL_S:
            time.sleep(MIN_REQUEST_INTERVAL_S - elapsed)
        UzexAdapter._last_request_ts = time.time()

    def _api_call(self, url: str, payload: Optional[dict] = None) -> Any:
        self._throttle()
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    def _existing_ids(self, ids: List[int]) -> set:
        """Bazada allaqachon bor bo'lgan id larni qaytaradi."""
        if not ids:
            return set()
        found = set()
        with db_session() as conn:
            cur = conn.cursor()
            # SQLite bind-parametr chegarasidan oshmaslik uchun bo'laklab
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                cur.execute(
                    f"SELECT id FROM lots WHERE id IN ({marks});",
                    [f"uzex_comp_{x}" for x in chunk],
                )
                found.update(r["id"] for r in cur.fetchall())
        return found

    def _map_detail(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """API javobini `lots` jadvali sxemasiga o'tkazish."""
        cid = d.get("id")
        items = d.get("js_details") or []
        first = items[0] if isinstance(items, list) and items else {}

        title = (first.get("product_name")
                 or d.get("competition_description")
                 or d.get("category_name")
                 or f"UZEX xaridi {cid}")

        def _date(v):
            return str(v)[:10] if v else None

        return {
            "id": f"uzex_comp_{cid}",
            "lot_number": f"comp_{cid}",
            "title": str(title)[:500],
            "description": d.get("competition_description") or d.get("description"),
            "platform_id": "uzex",
            "source_url": f"{API_BASE}{DETAIL_PATH}/{cid}",
            "procurement_type": "Tanlov (Competition)",
            "lot_category": d.get("category_name"),
            "official_status": d.get("status_name"),
            "announcement_date": _date(d.get("published_date")),
            "deadline_date": _date(d.get("end_date_submitting_offers")),
            "result_date": _date(d.get("date_of_opening_offers")),
            "start_price": float(d.get("cost") or 0),
            "currency": d.get("currency_name") or "UZS",
            "buyer_inn": str(d.get("customer_inn") or "").strip(),
            "buyer_name": d.get("customer_name"),
            "region": d.get("customer_region_name"),
            "extracted_text": " ".join(
                str(it.get("product_name", "")) for it in items if isinstance(it, dict)
            )[:4000],
            "raw_data_json": json.dumps(d, ensure_ascii=False),
        }

    def _upsert_companies(self, rows: List[Dict[str, Any]], conn) -> None:
        """
        Buyurtmachilarni `companies` ga kiritish.
        `lots.buyer_inn` -> `companies.inn` tashqi kaliti shuni talab qiladi;
        busiz yozuv FOREIGN KEY xatosi bilan rad etiladi.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        cur = conn.cursor()
        for r in rows:
            inn = (r.get("buyer_inn") or "").strip()
            if not inn:
                continue
            cur.execute("""
                INSERT INTO companies (inn, name, region, first_seen_date, last_seen_date,
                                       total_lots_count, proof_status)
                VALUES (?, ?, ?, ?, ?, 0, 'ANNOUNCED_ONLY')
                ON CONFLICT(inn) DO UPDATE SET
                    last_seen_date = excluded.last_seen_date,
                    region = COALESCE(companies.region, excluded.region);
            """, (inn, r.get("buyer_name") or inn, r.get("region"), today, today))

    def _insert(self, rows: List[Dict[str, Any]]) -> int:
        """Yangi yozuvlarni kiritish. Mavjudlari o'tkazib yuboriladi (idempotent)."""
        if not rows:
            return 0
        cols = list(rows[0].keys())
        marks = ",".join("?" * len(cols))
        sql = (f"INSERT OR IGNORE INTO lots ({','.join(cols)}, created_in_db_date) "
               f"VALUES ({marks}, ?);")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        added = 0
        with db_session() as conn:
            self._upsert_companies(rows, conn)
            cur = conn.cursor()
            for r in rows:
                cur.execute(sql, [r[c] for c in cols] + [now])
                added += cur.rowcount
        return added

    def fetch_updates(self, since_date: str = "2024-09-01") -> Dict[str, Any]:
        """
        Yangi UZEX tanlovlarini yuklab, `lots` jadvaliga kiritadi.

        Ro'yxat eng yangisidan boshlanadi, shuning uchun allaqachon ma'lum
        yozuvlarga duch kelinganda to'xtaymiz — kunlik sync shu tarzda tez ishlaydi.
        """
        added = total_seen = 0
        pages_done = 0
        errors: List[str] = []

        try:
            for page in range(MAX_PAGES_PER_RUN):
                frm = page * PAGE_SIZE + 1
                batch = self._api_call(f"{API_BASE}{LIST_PATH}",
                                       {"from": frm, "to": frm + PAGE_SIZE - 1})
                if not isinstance(batch, list) or not batch:
                    break

                pages_done += 1
                total_seen += len(batch)
                ids = [int(x["id"]) for x in batch if x.get("id") is not None]
                known = self._existing_ids(ids)
                new_ids = [i for i in ids if f"uzex_comp_{i}" not in known]

                if not new_ids:
                    # Butun sahifa tanish — bundan narigisi ham tanish
                    break

                rows = []
                for cid in new_ids:
                    if added + len(rows) >= MAX_NEW_PER_RUN:
                        break
                    try:
                        rows.append(self._map_detail(self._api_call(
                            f"{API_BASE}{DETAIL_PATH}/{cid}")))
                    except Exception as ex:
                        errors.append(f"id={cid}: {ex}")

                added += self._insert(rows)
                if added >= MAX_NEW_PER_RUN:
                    break

            msg = f"{added} ta yangi tanlov qo'shildi ({pages_done} sahifa, {total_seen} yozuv ko'rildi)"
            if errors:
                msg += f"; {len(errors)} ta yozuvda xato"
            return {
                "platform": self.platform_id,
                "status": "SUCCESS",
                "since_date": since_date,
                "records_added": added,
                "records_updated": 0,
                "message": msg,
            }

        except Exception as ex:
            logger.error(f"UZEX yuklashda xato: {ex}")
            return {
                "platform": self.platform_id,
                "status": "ERROR",
                "since_date": since_date,
                "records_added": added,
                "records_updated": 0,
                "message": f"UZEX yuklash xatosi: {ex}",
            }

    def health_check(self) -> Dict[str, Any]:
        conn_test = self.test_connection()
        return {
            "platform_id": self.platform_id,
            "health": conn_test["status"],
            "latency_ms": conn_test.get("latency_ms", 0),
            "operator": "O'zRTXB AJ",
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
