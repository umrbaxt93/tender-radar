"""
Softy Platforma — Database Layer
SQLite bazani ishga tushirish, jadvallarni yaratish va ulanish boshqaruvi.
"""

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from app.config import DB_PATH, PLATFORMS, TIMEZONE

def get_connection():
    """SQLite ulanishini yaratish (WAL mode va xorijiy kalitlar faol)"""
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

@contextmanager
def db_session():
    """Kontekst menejeri avtomatik commit/rollback bilan"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Barcha jadvallarni va FTS5 indekslarini yaratish"""
    with db_session() as conn:
        cursor = conn.cursor()

        # 1. Sources (Platformalar)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            domain TEXT NOT NULL,
            base_url TEXT NOT NULL,
            operator TEXT NOT NULL,
            history_start TEXT,
            loaded_range_start TEXT,
            loaded_range_end TEXT,
            unverified_periods TEXT,
            records_count INTEGER DEFAULT 0,
            missing_docs_count INTEGER DEFAULT 0,
            last_successful_sync TEXT,
            status TEXT DEFAULT 'faol',
            adapter_ready BOOLEAN DEFAULT 1,
            health_status TEXT DEFAULT 'OK'
        );
        """)

        # 2. Companies (Korxonalar)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            inn TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            legal_address TEXT,
            region TEXT,
            first_seen_date TEXT,
            last_seen_date TEXT,
            total_lots_count INTEGER DEFAULT 0,
            verified_purchases_count INTEGER DEFAULT 0,
            proof_status TEXT DEFAULT 'ANNOUNCED_ONLY', -- 'VERIFIED_BUYER', 'ANNOUNCED_ONLY', 'SUPPLIER'
            assigned_staff_id TEXT,
            assigned_staff_name TEXT,
            crm_deal_id TEXT,
            crm_status TEXT DEFAULT 'YANGI',
            next_task_text TEXT,
            next_task_date TEXT
        );
        """)

        # 3. Lots (Xaridlar / Tenderlar / Bitimlar)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS lots (
            id TEXT PRIMARY KEY,
            lot_number TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            platform_id TEXT NOT NULL,
            source_url TEXT NOT NULL,
            procurement_type TEXT DEFAULT 'Auksion', -- 'Elektron do‘kon', 'Auksion', 'Tender', 'Tanlash', 'Boshqa'
            lot_category TEXT DEFAULT 'SOF_MAHSULOT', -- 'SOF_MAHSULOT', 'ARALASH_PAKET', 'BOSHQA'
            official_status TEXT DEFAULT 'COMPLETED', -- 'COMPLETED', 'CANCELED', 'WINNER_SELECTED', 'CONTRACTED', 'EXECUTED', 'ACTIVE'
            announcement_date TEXT,
            deadline_date TEXT,
            result_date TEXT,
            delivery_date TEXT,
            created_in_db_date TEXT,
            start_price REAL DEFAULT 0,
            final_price REAL DEFAULT 0,
            currency TEXT DEFAULT 'UZS',
            buyer_inn TEXT,
            buyer_name TEXT,
            supplier_inn TEXT,
            supplier_name TEXT,
            winner_name TEXT,
            region TEXT,
            verification_status TEXT DEFAULT 'TASDIQLANGAN', -- 'TASDIQLANGAN', 'TEKSHIRILMAGAN'
            has_contract BOOLEAN DEFAULT 0,
            contract_id TEXT,
            contract_url TEXT,
            contract_number TEXT,
            contract_amount REAL DEFAULT 0,
            contract_date TEXT,
            license_end_date TEXT,
            support_end_date TEXT,
            extracted_text TEXT,
            raw_data_json TEXT,
            FOREIGN KEY (platform_id) REFERENCES sources (id) ON DELETE RESTRICT,
            FOREIGN KEY (buyer_inn) REFERENCES companies (inn) ON DELETE SET NULL
        );
        """)

        # Indexes on lots for fast filtering
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lots_platform ON lots (platform_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lots_buyer_inn ON lots (buyer_inn);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lots_status ON lots (official_status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lots_announcement_date ON lots (announcement_date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lots_contract_date ON lots (contract_date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lots_license_end_date ON lots (license_end_date);")

        # 4. Contract Items (Mahsulot qatorlari)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS contract_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lot_id TEXT NOT NULL,
            contract_id TEXT,
            product_name TEXT NOT NULL,
            brand TEXT,
            product_family TEXT,
            sku TEXT,
            quantity REAL DEFAULT 1,
            unit TEXT DEFAULT 'dona',
            unit_price REAL DEFAULT 0,
            total_price REAL DEFAULT 0,
            is_purchased_product BOOLEAN DEFAULT 1, -- 1: 'Xarid mahsuloti sifatida aniqlandi', 0: 'Matnda uchradi'
            detection_confidence TEXT DEFAULT 'HIGH',
            FOREIGN KEY (lot_id) REFERENCES lots (id) ON DELETE CASCADE
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_lot_id ON contract_items (lot_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_brand ON contract_items (brand);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_family ON contract_items (product_family);")

        # 5. Saved Searches (Saqlangan qidiruvlar va bildirishnomalar)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            search_query TEXT,
            filters_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            notify_enabled BOOLEAN DEFAULT 1,
            last_matching_lot_id TEXT
        );
        """)

        # 6. Tasks and Proposals (Vazifalar, Takliflar va Bitrix24 lidlari)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks_and_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_inn TEXT NOT NULL,
            lot_id TEXT,
            task_type TEXT NOT NULL, -- 'TAKTAK_TAYYORLASH', 'BOGLANISH', 'BITRIXGA_YUBORISH'
            task_title TEXT NOT NULL,
            assigned_staff_id TEXT,
            assigned_staff_name TEXT,
            proposal_summary TEXT,
            proposal_items_json TEXT,
            status TEXT DEFAULT 'YANGI', -- 'YANGI', 'JARAYONDA', 'BAJARILDI'
            bitrix_deal_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (company_inn) REFERENCES companies (inn) ON DELETE CASCADE
        );
        """)

        # 7. Sync Logs (Platformalar sinxronizatsiya tarixi)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform_id TEXT NOT NULL,
            sync_start TEXT NOT NULL,
            sync_end TEXT,
            records_added INTEGER DEFAULT 0,
            records_updated INTEGER DEFAULT 0,
            status TEXT DEFAULT 'SUCCESS',
            error_message TEXT
        );
        """)

        # 8. Full-Text Search Table (FTS5) for High-Speed Multilingual Search
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS lots_fts USING fts5(
            lot_id UNINDEXED,
            title,
            description,
            buyer_name,
            buyer_inn,
            supplier_name,
            supplier_inn,
            winner_name,
            contract_number,
            extracted_text,
            items_text,
            tokenize = 'unicode61 remove_diacritics 2'
        );
        """)

        # Pre-populate sources table with verified default platforms
        for p_id, p_info in PLATFORMS.items():
            cursor.execute("""
            INSERT OR IGNORE INTO sources (
                id, name, domain, base_url, operator, history_start, 
                loaded_range_start, loaded_range_end, unverified_periods,
                records_count, missing_docs_count, last_successful_sync,
                status, adapter_ready, health_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                p_info["id"], p_info["name"], p_info["domain"], p_info["base_url"],
                p_info["operator"], p_info["history_start"], p_info["loaded_range_start"],
                p_info["loaded_range_end"], "2021-yilgacha bo'lgan arxivlar",
                0, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "faol", 1, "OK"
            ))

if __name__ == "__main__":
    init_db()
    print("Softy Procurement Database initialized successfully at:", DB_PATH)
