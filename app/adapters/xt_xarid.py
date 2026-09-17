"""
Softy Platforma — XT-Xarid Platform Adapter
xt-xarid.uz (Hayot Birja / XT-Xarid Texnologiyalari AJ) adapteri.
"""

import ssl
import time
import json
import random
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.adapters.base import BasePlatformAdapter
from app.database import db_session

logger = logging.getLogger(__name__)

# xt-xarid.uz ommaviy JSON-RPC. Jonli sahifadan kuzatilgan (2026-09-17):
#   POST https://api.xt-xarid.uz/rpc
# Autentifikatsiya talab qilinmaydi — bular ommaviy shartnoma reestrlari.
RPC_URL = "https://api.xt-xarid.uz/rpc"

# Ommaviy reestrlar. `desc` maydoni faqat do'kon reestrida ro'yxatning
# o'zida keladi; tender/tanlov uchun `contract_detailed` chaqiriladi.
REGISTRIES = [
    # (ref, filters, ro'yxatda desc bormi)
    ("online_shop_contract_public_registry", {"nad": False, "is_comm_shop": False}, True),
    ("contract_public_registry", {"proc_type": "selection"}, False),
    ("contract_public_registry", {"proc_type": "tender"}, False),
]

# Manbani bloklamaslik uchun so'rovlar orasidagi eng kichik tanaffus.
MIN_REQUEST_INTERVAL_S = 3.0

PAGE_SIZE = 51
MAX_PAGES_PER_REGISTRY = 6
MAX_NEW_PER_RUN = 120

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

    # ────────────────────────────────────────────────────────────────────
    # HAQIQIY YUKLASH — xt-xarid.uz ommaviy JSON-RPC orqali
    # ────────────────────────────────────────────────────────────────────

    _last_request_ts = 0.0

    def _throttle(self):
        elapsed = time.time() - XtXaridAdapter._last_request_ts
        if elapsed < MIN_REQUEST_INTERVAL_S:
            time.sleep(MIN_REQUEST_INTERVAL_S - elapsed)
        XtXaridAdapter._last_request_ts = time.time()

    def _rpc(self, method: str, params: dict, url_on: str = "https://xt-xarid.uz/contract/") -> Any:
        """Bitta JSON-RPC chaqiruvi. Server takroriy so'rovni rad etadi,
        shuning uchun har chaqiruvda yangi idempotency-key yuboriladi."""
        self._throttle()
        body = json.dumps({"id": 1, "jsonrpc": "2.0",
                           "method": method, "params": params}).encode("utf-8")
        req = urllib.request.Request(RPC_URL, data=body, headers={
            "Content-Type": "application/json;charset=utf-8",
            "Accept": "application/json",
            "X-DBRPC-Language": "uz_UZ@cyrillic",
            "x-url-on": url_on,
            "x-idempotency-key": str(random.randint(10**17, 10**18)),
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(str(payload["error"])[:200])
        return payload.get("result") if isinstance(payload, dict) else payload

    def _existing_numbers(self, numbers: List[str]) -> set:
        """
        Bazada allaqachon bor shartnoma raqamlarini qaytaradi.

        Bazada tarixan IKKI xil id shakli bor: `xt_<raqam>` va
        `xt_xarid_<raqam>`. Ikkalasini ham tekshiramiz, aks holda mavjud
        yozuvlar uchinchi marta takrorlanadi.
        """
        if not numbers:
            return set()
        found = set()
        with db_session() as conn:
            cur = conn.cursor()
            for i in range(0, len(numbers), 400):
                chunk = numbers[i:i + 400]
                keys = [f"xt_xarid_{n}" for n in chunk] + [f"xt_{n}" for n in chunk]
                # lot_number bo'yicha ham tekshiramiz — eski yozuvlarda
                # raqam ".1.1" qo'shimchasisiz saqlangan bo'lishi mumkin
                bare = [str(n).split(".")[0] for n in chunk]
                marks_id = ",".join("?" * len(keys))
                marks_ln = ",".join("?" * (len(chunk) + len(bare)))
                cur.execute(
                    f"SELECT id, lot_number FROM lots "
                    f"WHERE id IN ({marks_id}) OR lot_number IN ({marks_ln});",
                    keys + chunk + bare,
                )
                for r in cur.fetchall():
                    found.add(str(r["id"]))
                    found.add(f"xt_xarid_{r['lot_number']}")
                    found.add(f"xt_{r['lot_number']}")
        return found

    def _map_contract(self, c: Dict[str, Any], desc: Optional[str] = None) -> Dict[str, Any]:
        number = str(c.get("number") or "")
        org = c.get("org_company") or {}
        agent = c.get("contragent_company") or {}
        spec = c.get("spec") if isinstance(c.get("spec"), list) else []

        text = desc or c.get("desc") or c.get("contract_name") or f"XT-Xarid {number}"
        spec_text = " ".join(
            str(it.get("product_name") or it.get("name") or "")
            for it in spec if isinstance(it, dict)
        ).strip()

        def _d(v):
            return str(v)[:10] if v else None

        return {
            "id": f"xt_xarid_{number}",
            "lot_number": number,
            "title": str(text)[:500],
            "description": str(text)[:2000],
            "platform_id": "xt_xarid",
            "source_url": f"https://xt-xarid.uz/contract/{number}",
            "procurement_type": c.get("type") or c.get("contract_name"),
            "official_status": c.get("status"),
            "announcement_date": _d(c.get("inserted_at")),
            "result_date": _d(c.get("contract_close_at")),
            "delivery_date": _d(c.get("real_end_date")),
            "start_price": float(c.get("spec_totalcost") or c.get("contract_totalcost") or 0),
            "final_price": float(c.get("contract_totalcost") or 0),
            "contract_amount": float(c.get("contract_totalcost") or 0),
            "contract_date": _d(c.get("contract_close_at")),
            "contract_number": number,
            "contract_url": f"https://xt-xarid.uz/contract/{number}",
            "has_contract": 1,
            "currency": c.get("currency") or "UZS",
            "buyer_inn": str(org.get("inn") or "").strip(),
            "buyer_name": org.get("company_title"),
            "supplier_inn": str(agent.get("inn") or "").strip(),
            "supplier_name": agent.get("company_title"),
            "winner_name": agent.get("company_title"),
            "extracted_text": (str(text) + " " + spec_text).strip()[:4000],
            "raw_data_json": json.dumps(c, ensure_ascii=False, default=str),
        }

    def _upsert_companies(self, rows: List[Dict[str, Any]], conn) -> None:
        """Buyurtmachi va yetkazib beruvchini `companies` ga kiritish.
        `lots.buyer_inn -> companies.inn` tashqi kaliti shuni talab qiladi."""
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

    def fetch_updates(self, since_date: str = "2024-09-01") -> Dict[str, Any]:
        """Yangi XT-Xarid shartnomalarini yuklab, `lots` jadvaliga kiritadi."""
        added = 0
        seen = 0
        errors: List[str] = []

        try:
            for ref, filters, desc_inline in REGISTRIES:
                if added >= MAX_NEW_PER_RUN:
                    break
                for page in range(MAX_PAGES_PER_REGISTRY):
                    if added >= MAX_NEW_PER_RUN:
                        break
                    batch = self._rpc("contract_ref", {
                        "ref": ref, "op": "read",
                        "limit": PAGE_SIZE, "offset": page * PAGE_SIZE,
                        "filters": filters,
                    })
                    if not isinstance(batch, list) or not batch:
                        break

                    seen += len(batch)
                    nums = [str(c.get("number")) for c in batch if c.get("number")]
                    known = self._existing_numbers(nums)
                    fresh = [c for c in batch
                             if c.get("number") and f"xt_xarid_{c['number']}" not in known]

                    if not fresh:
                        # Butun sahifa tanish — reestr eng yangisidan boshlanadi
                        break

                    rows = []
                    for c in fresh:
                        if added + len(rows) >= MAX_NEW_PER_RUN:
                            break
                        try:
                            extra = None
                            if not desc_inline:
                                det = self._rpc(
                                    "contract_detailed", {"number": str(c["number"])},
                                    url_on=f"https://xt-xarid.uz/contract/{c['number']}")
                                if isinstance(det, dict):
                                    extra = det.get("desc")
                                    # brend/ishlab chiqaruvchi tahlil uchun qimmatli
                                    for k in ("brand", "producer", "spec", "license"):
                                        if k in det:
                                            c[k] = det[k]
                            rows.append(self._map_contract(c, extra))
                        except Exception as ex:
                            errors.append(f"{c.get('number')}: {ex}")

                    added += self._insert(rows)

            msg = f"{added} ta yangi shartnoma qo'shildi ({seen} yozuv ko'rildi)"
            if errors:
                msg += f"; {len(errors)} ta yozuvda xato"
            return {"platform": self.platform_id, "status": "SUCCESS",
                    "since_date": since_date, "records_added": added,
                    "records_updated": 0, "message": msg}

        except Exception as ex:
            logger.error(f"XT-Xarid yuklashda xato: {ex}")
            return {"platform": self.platform_id, "status": "ERROR",
                    "since_date": since_date, "records_added": added,
                    "records_updated": 0,
                    "message": f"XT-Xarid yuklash xatosi: {ex}"}

    def health_check(self) -> Dict[str, Any]:
        conn_test = self.test_connection()
        return {
            "platform_id": self.platform_id,
            "health": conn_test["status"],
            "latency_ms": conn_test.get("latency_ms", 0),
            "operator": "Hayot Birja AJ / XT-Xarid",
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
