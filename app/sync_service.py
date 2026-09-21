"""
Softy Platforma — Anti-Blocking Daily Synchronization Service
Har kuni 1 marta davlat xaridlari platformalaridan yangi xaridlarni avtomat yuklash,
Cloudflare / WAF bloklanishlarini oldini oluvchi ehtiyotkor (polite) va xavfsiz skanerlash.
"""

import os
import sys
import ssl
import time
import json
import random
import logging
import threading
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from app.config import (
    BASE_DIR, PLATFORMS, SYNC_SETTINGS, TIMEZONE
)
from app.database import db_session
from app.adapters.registry import get_adapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("softy_sync")

# Desktop Browser User-Agents (Anti-blocking rotating list)
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
]

def get_anti_blocking_headers(referer: Optional[str] = None, platform_id: Optional[str] = None) -> Dict[str, str]:
    """
    Haqiqiy foydalanuvchi brauzeriga 100% o'xshash sarlavhalar (headers) va E-IMZO sessiyasi
    """
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "uz,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "identity",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0"
    }
    # E-IMZO elektron kalit / sessiya tekshiruvi
    try:
        from app.eimzo_auth import EImzoAuthManager
        sess = EImzoAuthManager.get_session()
        if sess.get("authenticated"):
            if sess.get("token"):
                headers["Authorization"] = f"Bearer {sess['token']}"
                headers["user-key"] = sess["token"]
            if sess.get("cookie"):
                headers["Cookie"] = sess["cookie"]
    except Exception:
        pass

    if referer:
        headers["Referer"] = referer
    return headers

def polite_sleep(min_sec: float = 2.5, max_sec: float = 5.5):
    """
    Bloklanishdan saqlovchi tasodifiy tanaffus (Jitter delay)
    """
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)

def execute_safe_request(url: str, referer: Optional[str] = None, max_retries: int = 3) -> Optional[str]:
    """
    Bloklanishga chidamli va xatolarda qayta urinuvchi HTTP so'rov
    """
    ctx = ssl._create_unverified_context()

    for attempt in range(1, max_retries + 1):
        try:
            headers = get_anti_blocking_headers(referer)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                if resp.status == 200:
                    return resp.read().decode("utf-8", errors="replace")
                elif resp.status == 429 or resp.status == 503:
                    # Rate limit or server busy: exponential backoff
                    wait_time = attempt * 12 + random.uniform(2, 5)
                    logger.warning(f"Server {resp.status} qaytardi. {wait_time:.1f}s kutilmoqda (urinish {attempt}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"URL {url} HTTP {resp.status} bilan javob berdi")
                    return None
        except urllib.error.HTTPError as e:
            if e.code in [403, 429, 503] and attempt < max_retries:
                wait_time = attempt * 15
                logger.warning(f"HTTP {e.code} xatosi ({url}). {wait_time}s kutilmoqda...")
                time.sleep(wait_time)
            else:
                logger.error(f"HTTP xatosi {url}: {e.code} - {e.reason}")
                return None
        except Exception as ex:
            logger.warning(f"Ulanish xatosi ({url}): {str(ex)}")
            if attempt < max_retries:
                time.sleep(attempt * 5)
            else:
                return None
        finally:
            polite_sleep(SYNC_SETTINGS["anti_blocking_delay_min"], SYNC_SETTINGS["anti_blocking_delay_max"])

    return None

class DailySyncManager:
    """
    Kunlik avtomatik sinxronizatsiya boshqaruvchisi
    """

    def __init__(self):
        self.is_running = False
        self._stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start_background_scheduler(self):
        """Fonda kunlik sinxronlashni ishga tushirish"""
        if self.thread and self.thread.is_alive():
            logger.info("DailySyncManager allaqachon fonda ishlamoqda.")
            return

        self._stop_event.clear()
        self.thread = threading.Thread(target=self._scheduler_loop, daemon=True, name="DailySyncScheduler")
        self.thread.start()
        logger.info("DailySyncManager muvaffaqiyatli ishga tushirildi (Kuniga 1 marta, 03:00 da).")

    def stop_background_scheduler(self):
        self._stop_event.set()

    def _scheduler_loop(self):
        """
        Kuniga 1 marta rejalashtirilgan vaqtda (03:00 Tashkent) sinxronizatsiya qilish
        """
        while not self._stop_event.is_set():
            now = datetime.now()
            preferred_hour = SYNC_SETTINGS.get("preferred_sync_hour", 3)

            # Agar soat 03:00 bo'lsa va bugun hali ishga tushmagan bo'lsa
            # Yoki oxirgi sinxronizatsiyadan 24 soat o'tgan bo'lsa
            last_sync_time = self._get_last_sync_time()
            hours_since_last = (now - last_sync_time).total_seconds() / 3600 if last_sync_time else 999

            if hours_since_last >= 24 or (now.hour == preferred_hour and hours_since_last >= 20):
                logger.info(f"Kunlik rejalashtirilgan sinxronizatsiya boshlanmoqda (Oxirgi sinx: {hours_since_last:.1f} soat oldin)...")
                try:
                    self.run_full_sync_cycle()
                except Exception as e:
                    logger.error(f"Sinxronizatsiyada xatolik yuz berdi: {str(e)}")

            # Har 30 daqiqada tekshirish
            self._stop_event.wait(timeout=1800)

    def _get_last_sync_time(self) -> Optional[datetime]:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(sync_start) FROM sync_logs WHERE status = 'SUCCESS';")
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    return datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
        return None

    def run_full_sync_cycle(self, since_date: str = "2024-09-01") -> Dict[str, Any]:
        """
        Barcha platformalar bo'yicha ehtiyotkor, bloklanmaydigan sinxronizatsiya
        """
        if self.is_running:
            return {"status": "IN_PROGRESS", "message": "Sinxronizatsiya allaqachon bajarilmoqda"}

        self.is_running = True
        start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_added = 0
        total_updated = 0
        platform_reports = {}

        logger.info(f"=== KUNLIK SINXRONIZATSIYA BOSHLANDI ({since_date} dan boshlab) ===")

        try:
            # cooperation.uz chet el/datacenter IP'larni bloklaydi — production
            # server (Hostinger) unga ulana olmaydi. Uning ma'lumoti O'zbekiston
            # IP'sidan (Mac yoki VPS) alohida yuklanadi, shuning uchun kundalik
            # server sync'da o'tkazib yuboriladi va health holati o'zgartirilmaydi.
            SKIP_LIVE_SYNC = {"cooperation"}

            for platform_id, config in PLATFORMS.items():
                if platform_id in SKIP_LIVE_SYNC:
                    logger.info(f"{platform_id}: serverdan ulana olmaydi — o'tkazib yuborildi")
                    platform_reports[platform_id] = {"status": "SKIPPED", "added": 0,
                                                     "message": "Server ulana olmaydi (IP blok); ma'lumot alohida yuklanadi"}
                    continue
                logger.info(f"Platforma tekshirilmoqda: {config['name']}...")

                # Sinxronlash jurnali yozuvi
                log_id = self._log_sync_start(platform_id, start_time)

                adapter = get_adapter(platform_id)
                status_info = adapter.get_status()

                if status_info.get("is_fallback") or status_info.get("status") == "UNIMPLEMENTED":
                    msg = f"Adapter ishlab chiqilishi kerak (Fallback rejimida)"
                    self._log_sync_end(log_id, 0, 0, status="UNIMPLEMENTED", error=msg)
                    platform_reports[platform_id] = {"status": "UNIMPLEMENTED", "added": 0, "message": msg}
                    continue

                # Anti-blocking ulanish testi
                conn_test = adapter.test_connection()
                if conn_test.get("status") != "OK":
                    msg = conn_test.get("message", "Ulanish xatosi")
                    logger.warning(f"{platform_id}: {msg}")
                    self._log_sync_end(log_id, 0, 0, status="ERROR", error=msg)
                    platform_reports[platform_id] = {"status": "ERROR", "added": 0, "message": msg}
                    continue

                # Yangilanishlarni olish (Polite rate-limited fetch)
                res = adapter.fetch_updates(since_date=since_date)
                added = res.get("records_added", 0)
                updated = res.get("records_updated", 0)
                total_added += added
                total_updated += updated

                # Adapter qaytargan holatni o'zi yozamiz. Ilgari bu yerda qattiq
                # "SUCCESS" turardi, shuning uchun yuklash umuman ishlamagan
                # adapterlar ham muvaffaqiyatli sync qilingandek ko'rinardi.
                real_status = res.get("status", "SUCCESS")
                msg = res.get("message")
                self._log_sync_end(log_id, added, updated, status=real_status,
                                   error=None if real_status == "SUCCESS" else msg)
                platform_reports[platform_id] = {
                    "status": real_status, "added": added,
                    "updated": updated, "message": msg,
                }

                # Platformalar o'rtasida ehtiyotkor tanaffus
                polite_sleep(3.0, 6.0)

            # Bazadagi manbalar metrikalarini yangilash
            self._update_source_stats(platform_reports)

            logger.info(f"=== KUNLIK SINXRONIZATSIYA YAKUNLANDI: Jami {total_added} ta yangi lot qo'shildi ===")

            return {
                "status": "SUCCESS",
                "start_time": start_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_records_added": total_added,
                "total_records_updated": total_updated,
                "platform_reports": platform_reports
            }

        finally:
            self.is_running = False

    def _log_sync_start(self, platform_id: str, start_time: str) -> int:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO sync_logs (platform_id, sync_start, status)
            VALUES (?, ?, 'RUNNING');
            """, (platform_id, start_time))
            return cursor.lastrowid

    def _log_sync_end(self, log_id: int, added: int, updated: int, status: str = "SUCCESS", error: Optional[str] = None):
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE sync_logs SET 
                sync_end = ?, records_added = ?, records_updated = ?, status = ?, error_message = ?
            WHERE id = ?;
            """, (end_time, added, updated, status, error, log_id))

    def _update_source_stats(self, platform_reports: Optional[Dict[str, Any]] = None):
        """
        Manba metrikalarini yangilash.

        `last_successful_sync` va `health_status` FAQAT haqiqiy natijaga qarab
        yoziladi. Ilgari bu maydonlar har siklda so'zsiz "hozir" va "OK" deb
        yangilanardi — natijada barcha sinxronizatsiyalar xato bilan tugasa ham
        panel "hammasi joyida" deb ko'rsatardi.
        """
        reports = platform_reports or {}
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT platform_id, COUNT(*) as cnt, MIN(announcement_date) as min_d, MAX(announcement_date) as max_d
            FROM lots GROUP BY platform_id;
            """)
            rows = cursor.fetchall()

            for row in rows:
                pid = row["platform_id"]
                status = (reports.get(pid) or {}).get("status")

                # Yozuvlar soni va sana oralig'i — bular shunchaki bazadagi fakt
                cursor.execute("""
                UPDATE sources SET
                    records_count = ?,
                    loaded_range_start = COALESCE(?, loaded_range_start),
                    loaded_range_end = COALESCE(?, loaded_range_end)
                WHERE id = ?;
                """, (row["cnt"], row["min_d"], row["max_d"], pid))

                if status == "SUCCESS":
                    cursor.execute("""
                    UPDATE sources SET last_successful_sync = ?, health_status = 'OK'
                    WHERE id = ?;""", (now_str, pid))
                elif status is not None:
                    # ERROR yoki UNIMPLEMENTED — last_successful_sync TEGILMAYDI
                    cursor.execute("""
                    UPDATE sources SET health_status = ? WHERE id = ?;""", (status, pid))

# Global Singleton Manager
sync_manager = DailySyncManager()

def run_cli_sync():
    """CLI dan to'g'ridan-to'g'ri ishga tushirish"""
    print("=====================================================")
    print("  SOFTY PLATFORMA — Anti-Blocking Kunlik Sinxronizatsiya")
    print("  Baza boshlanish sanasi: 2024-09-01")
    print("=====================================================")
    mgr = DailySyncManager()
    result = mgr.run_full_sync_cycle(since_date="2024-09-01")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    run_cli_sync()
