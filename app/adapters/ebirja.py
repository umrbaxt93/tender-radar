"""
Softy Platforma — E-Birja Platform Adapter
xarid.ebirja.uz (Toshkent tovar xomashyo birjasi AJ - ТТСБ / TTXB) adapteri.
"""

import ssl
import time
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.adapters.base import BasePlatformAdapter
from app.database import db_session

logger = logging.getLogger(__name__)

# E-Birja ommaviy REST API. Jonli sahifadan kuzatilgan (2026-09-17).
# MUHIM: E-IMZO talab qilinmaydi. Eski xulosa (`xarid.ebirja.uz` 404 qaytaradi,
# faqat EDS bilan kiriladi) eskirgan — sayt `ebirja.uz` ga ko'chgan va
# `/common/` endpointlari autentifikatsiyasiz ochiq.
API_BASE = "https://xarid-api.ebirja.uz"
LIST_PATH = "/common/contract/shop-list"
VIEW_PATH = "/common/contract/shop-view"

MIN_REQUEST_INTERVAL_S = 3.0

PAGE_SIZE = 100
MAX_PAGES_PER_RUN = 12
MAX_NEW_PER_RUN = 120

# Mavjud 28 000+ yozuv INN va mahsulot nomisiz saqlangan. Ularni to'ldirish
# har biriga bitta so'rov talab qiladi (3s tanaffus bilan ~3s/yozuv), shuning
# uchun ish bo'lak-bo'lak bajariladi va qayta boshlanadi.
#
# 400 ta ≈ 20 daqiqa — tungi cron uchun mos. Bir martalik katta backfill
# uchun `backfill_ebirja.py` skripti bu qiymatni oshirib chaqiradi.
MAX_ENRICH_PER_RUN = 400

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

    # ────────────────────────────────────────────────────────────────────
    # HAQIQIY YUKLASH — ebirja.uz ommaviy REST API orqali (E-IMZO kerak emas)
    # ────────────────────────────────────────────────────────────────────

    _last_request_ts = 0.0

    def _throttle(self):
        elapsed = time.time() - EbirjaAdapter._last_request_ts
        if elapsed < MIN_REQUEST_INTERVAL_S:
            time.sleep(MIN_REQUEST_INTERVAL_S - elapsed)
        EbirjaAdapter._last_request_ts = time.time()

    def _get(self, path: str, params: dict) -> Any:
        self._throttle()
        url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        return payload.get("result") if isinstance(payload, dict) else payload

    def _detail(self, contract_id: int) -> Dict[str, Any]:
        res = self._get(VIEW_PATH, {"id": contract_id})
        return res if isinstance(res, dict) else {}

    @staticmethod
    def _row_id(contract_id: Any) -> str:
        # Bazadagi tarixiy shakl: ebirja_ebirja_c_<id>
        return f"ebirja_ebirja_c_{contract_id}"

    def _map(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """shop-view javobini `lots` sxemasiga o'tkazish."""
        cid = d.get("id")
        cust = d.get("customer") or {}
        prod = d.get("producer") or {}
        order = d.get("order") or {}
        plog = order.get("product_log") or {}

        # Fallback ATAYIN "E-Birja shartnoma" bilan boshlanmaydi: bu naqsh
        # boyitilmagan yozuvni belgilaydi, shuning uchun boyitilgan yozuv undan
        # farq qilishi shart — aks holda qayta-qayta tanlanadi.
        title = (plog.get("title") or plog.get("description")
                 or f"E-shop lot {d.get('number')}")

        def _dt(v):
            return str(v)[:10] if v else None

        return {
            "id": self._row_id(cid),
            "lot_number": f"ebirja_c_{cid}",
            "title": str(title)[:500],
            "description": str(plog.get("description") or title)[:2000],
            "platform_id": "ebirja",
            "source_url": f"https://ebirja.uz/uz/contracts/shop?search={d.get('number')}",
            "procurement_type": plog.get("platform_display") or "e-shop",
            "official_status": str(d.get("status")),
            "announcement_date": _dt(d.get("created_at")),
            "result_date": _dt(order.get("trade_end_date")),
            "start_price": float(order.get("total_price") or d.get("price") or 0),
            "final_price": float(d.get("price") or 0),
            "contract_amount": float(d.get("price") or 0),
            "contract_number": d.get("number"),
            "contract_date": _dt(d.get("created_at")),
            "contract_url": f"https://ebirja.uz/uz/contracts/shop?search={d.get('number')}",
            "has_contract": 1,
            "currency": "UZS",
            "buyer_inn": str(cust.get("tin") or "").strip(),
            "buyer_name": cust.get("title"),
            "supplier_inn": str(prod.get("tin") or "").strip(),
            "supplier_name": prod.get("title"),
            "winner_name": prod.get("title"),
            "region": cust.get("region") if isinstance(cust.get("region"), str) else None,
            "extracted_text": " ".join(filter(None, [
                str(plog.get("title") or ""), str(plog.get("brand_title") or ""),
                str(plog.get("product_model") or ""), str(plog.get("description") or ""),
            ]))[:4000],
            "raw_data_json": json.dumps(d, ensure_ascii=False, default=str),
        }

    def _upsert_companies(self, rows: List[Dict[str, Any]], conn) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        cur = conn.cursor()
        for r in rows:
            for inn, name in ((r.get("buyer_inn"), r.get("buyer_name")),
                              (r.get("supplier_inn"), r.get("supplier_name"))):
                inn = (inn or "").strip()
                if not inn:
                    continue
                cur.execute("""
                    INSERT INTO companies (inn, name, first_seen_date, last_seen_date,
                                           total_lots_count, proof_status)
                    VALUES (?, ?, ?, ?, 0, 'ANNOUNCED_ONLY')
                    ON CONFLICT(inn) DO UPDATE SET last_seen_date = excluded.last_seen_date;
                """, (inn, name or inn, today, today))

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
            self._upsert_companies(rows, conn)
            cur = conn.cursor()
            for r in rows:
                cur.execute(sql, [r[c] for c in cols] + [now])
                added += cur.rowcount
        return added

    def enrich_existing(self, limit: int = MAX_ENRICH_PER_RUN) -> int:
        """
        Eski yozuvlarni to'ldirish.

        Bazadagi 28 000+ e-birja qatori INN va mahsulot nomisiz saqlangan
        (sarlavha o'rnida "E-Birja shartnoma XD... (Shop)" turadi), chunki
        ro'yxat endpointi bu maydonlarni bermaydi. Detal endpointi beradi.

        Har yozuv uchun bitta so'rov kerak, shuning uchun ish bo'laklab
        bajariladi va qayta boshlanadi: to'ldirilmagan qator qolmaguncha
        har yurish navbatdagi bo'lakni oladi.
        """
        # Tanlash FAQAT placeholder sarlavhaga qaraydi ("E-Birja shartnoma ...").
        # Bu — boyitilmaganning yagona ishonchli va MONOTON belgisi: har boyitilgan
        # yozuv placeholder'dan chiqadi va qayta tanlanmaydi. Supplier yoki buyer
        # bo'shligiga qarab bo'lmaydi — ba'zi shartnomalarda yetkazib beruvchi
        # umuman yo'q, ular boyitilgan bo'lsa ham supplier bo'sh qoladi va aks holda
        # abadiy qayta tanlanardi (bu jarayonni to'sib turardi).
        #
        # `id LIKE 'ebirja_ebirja_c_%'` sharti muhim: qo'lda kiritilgan namuna
        # qatorlar (ebirja_ms_445 kabi) API id siga ega emas, ular tanlansa
        # LIMIT o'rnini bekorga egallab, har yurishda qayta tanlanardi.
        with db_session() as conn:
            rows = conn.execute("""
                SELECT id FROM lots
                 WHERE platform_id = 'ebirja'
                   AND id LIKE 'ebirja_ebirja_c_%'
                   AND title LIKE 'E-Birja shartnoma%'
                 ORDER BY announcement_date DESC
                 LIMIT ?;""", (limit,)).fetchall()

        done = 0
        for r in rows:
            raw_id = str(r["id"]).replace("ebirja_ebirja_c_", "")
            if not raw_id.isdigit():
                continue
            try:
                d = self._detail(int(raw_id))
                if not d:
                    # API ma'lumot bermadi — sentinel sarlavha qo'yamiz, aks holda
                    # bu qator har bo'lakda qayta tanlanib, jarayonni to'sib turadi.
                    with db_session() as conn:
                        conn.execute("UPDATE lots SET title = ? WHERE id = ?;",
                                     (f"E-shop lot {raw_id}", r["id"]))
                    done += 1
                    continue
                m = self._map(d)
                with db_session() as conn:
                    self._upsert_companies([m], conn)
                    conn.execute("""
                        UPDATE lots SET title = ?, description = ?, buyer_inn = ?,
                               buyer_name = ?, supplier_inn = ?, supplier_name = ?,
                               winner_name = ?, extracted_text = ?, raw_data_json = ?
                         WHERE id = ?;""",
                        (m["title"], m["description"], m["buyer_inn"], m["buyer_name"],
                         m["supplier_inn"], m["supplier_name"], m["winner_name"],
                         m["extracted_text"], m["raw_data_json"], r["id"]))
                done += 1
            except Exception as ex:
                logger.warning(f"E-Birja boyitish xatosi ({raw_id}): {ex}")
        return done

    def fetch_updates(self, since_date: str = "2024-09-01") -> Dict[str, Any]:
        """Yangi shartnomalarni yuklaydi, so'ng eski yozuvlarni boyitadi."""
        added = seen = 0
        errors: List[str] = []

        try:
            for page in range(MAX_PAGES_PER_RUN):
                if added >= MAX_NEW_PER_RUN:
                    break
                res = self._get(LIST_PATH, {
                    "type": "e-shop", "currentPage": page,
                    "perPage": PAGE_SIZE, "search": " ",
                })
                batch = (res or {}).get("data") or []
                if not batch:
                    break
                seen += len(batch)

                ids = [c.get("id") for c in batch if c.get("id") is not None]
                with db_session() as conn:
                    marks = ",".join("?" * len(ids))
                    known = {r["id"] for r in conn.execute(
                        f"SELECT id FROM lots WHERE id IN ({marks});",
                        [self._row_id(i) for i in ids]).fetchall()}
                fresh = [i for i in ids if self._row_id(i) not in known]

                if not fresh:
                    # Ro'yxat eng yangisidan boshlanadi — narigisi ham tanish
                    break

                rows = []
                for cid in fresh:
                    if added + len(rows) >= MAX_NEW_PER_RUN:
                        break
                    try:
                        d = self._detail(int(cid))
                        if d:
                            rows.append(self._map(d))
                    except Exception as ex:
                        errors.append(f"{cid}: {ex}")
                added += self._insert(rows)

            enriched = self.enrich_existing()

            msg = (f"{added} ta yangi shartnoma, {enriched} ta eski yozuv to'ldirildi "
                   f"({seen} yozuv ko'rildi)")
            if errors:
                msg += f"; {len(errors)} ta xato"
            return {"platform": self.platform_id, "status": "SUCCESS",
                    "since_date": since_date, "records_added": added,
                    "records_updated": enriched, "message": msg}

        except Exception as ex:
            logger.error(f"E-Birja yuklashda xato: {ex}")
            return {"platform": self.platform_id, "status": "ERROR",
                    "since_date": since_date, "records_added": added,
                    "records_updated": 0,
                    "message": f"E-Birja yuklash xatosi: {ex}"}

    def health_check(self) -> Dict[str, Any]:
        conn_test = self.test_connection()
        return {
            "platform_id": self.platform_id,
            "health": conn_test["status"],
            "latency_ms": conn_test.get("latency_ms", 0),
            "operator": "Toshkent tovar xomashyo birjasi AJ (TTXB)",
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
