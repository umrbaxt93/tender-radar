"""
Softy Platforma — Configuration Module
Tizim sozlamalari, vaqt mintaqalari (Asia/Tashkent) va platformalar reyestri.
"""

import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "softy_procurement.db"

# Ensure directories
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Timezone & Regional Settings
TIMEZONE = "Asia/Tashkent"
DEFAULT_CURRENCY = "UZS"

# Hostinger & Domain Settings
HOST = "0.0.0.0"
PORT = 8080
DOMAIN = "tender.softy.uz"
BASE_APP_URL = "http://tender.softy.uz:8080"
DEFAULT_START_DATE = "2024-01-01"

# Hostinger Infrastructure
HOSTINGER_IP = "62.72.50.47"
HOSTINGER_USER = "u475605112"
HOSTINGER_APP_DIR = "/home/u475605112/domains/softy.uz/tender"

# Anti-Blocking Daily Sync Settings (1 kunda 1 marta)
SYNC_SETTINGS = {
    "interval_hours": 24,
    "preferred_sync_hour": 3, # 03:00 AM Toshkent vaqti
    "anti_blocking_delay_min": 2.5,
    "anti_blocking_delay_max": 5.5,
    "baseline_start_date": "2024-01-01",
    "max_retries": 3,
    "backoff_seconds": 15
}

# Verified Platforms Registry (Baza 2024-01-01 dan boshlab qamrab olingan)
PLATFORMS = {
    "uzex": {
        "id": "uzex",
        "name": "xarid.uzex.uz (O'zRTXB Davlat xaridlari)",
        "domain": "xarid.uzex.uz",
        "base_url": "https://xarid.uzex.uz",
        "operator": "O'zbekiston Respublika tovar-xom ashyo birjasi (O'zRTXB AJ)",
        "history_start": "2024-01-01",
        "loaded_range_start": "2024-01-01",
        "loaded_range_end": "2026-09-12",
        "is_active": True,
        "adapter_ready": True
    },
    "xt_xarid": {
        "id": "xt_xarid",
        "name": "xt-xarid.uz (Hayot Birja / XT-Xarid)",
        "domain": "xt-xarid.uz",
        "base_url": "https://xt-xarid.uz",
        "operator": "XT-Xarid Texnologiyalari AJ / Hayot Birja AJ",
        "history_start": "2024-01-01",
        "loaded_range_start": "2024-01-01",
        "loaded_range_end": "2026-09-12",
        "is_active": True,
        "adapter_ready": True
    },
    "ebirja": {
        "id": "ebirja",
        "name": "xarid.ebirja.uz (Toshkent tovar xomashyo birjasi)",
        "domain": "xarid.ebirja.uz",
        "base_url": "https://xarid.ebirja.uz",
        "operator": "Toshkent tovar xomashyo birjasi AJ (ТТСБ / TTXB)",
        "history_start": "2024-01-01",
        "loaded_range_start": "2024-01-01",
        "loaded_range_end": "2026-09-12",
        "is_active": True,
        "adapter_ready": True
    },
    "cooperation": {
        "id": "cooperation",
        "name": "new.cooperation.uz (Yangi Kooperatsiya Portali)",
        "domain": "new.cooperation.uz",
        "base_url": "https://new.cooperation.uz",
        "operator": "O'zbekiston Respublika tovar-xom ashyo birjasi (O'zRTXB AJ)",
        "history_start": "2024-01-01",
        "loaded_range_start": "2024-01-01",
        "loaded_range_end": "2026-09-12",
        "is_active": True,
        "adapter_ready": True
    }
}

# Team members for assignment (from company profile)
STAFF_MEMBERS = [
    {"id": "umid", "name": "Umidjon Fatullayev", "role": "CEO"},
    {"id": "yoqubxon", "name": "Yoqubxon", "role": "E-Shop rahbari (Kanal #1)"},
    {"id": "usmon", "name": "Usmon", "role": "Litsenziya yangilash (Kanal #2)"},
    {"id": "shohruh", "name": "Shohruh", "role": "Vendor narxlash / Bitrix24 Admin"},
    {"id": "komiljon", "name": "Komiljon", "role": "Tender saralash (Kanal #3)"},
    {"id": "siyovush", "name": "Siyovush", "role": "Presale / Vendor narxlash"}
]
