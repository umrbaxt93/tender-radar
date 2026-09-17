"""
Softy Platforma — CSV/XLSX Import Adapter (17.H)
Fayllarni yuklash, ustunlarni maydonlarga moslash (mapping),
oldindan ko'rish (preview), format tekshiruvi va dublikat nazorati.
"""

import csv
import io
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.database import db_session

class CsvXlsxAdapter:
    """
    CSV va Excel fayllarni xaritalash va import qilish adapteri.
    """

    # Standart maydonlar ro'yxati
    STANDARD_FIELDS = {
        "lot_number": "Lot raqami / Identifikator",
        "title": "Lot nomi / Sarlavha",
        "buyer_inn": "Buyurtmachi STIR (9 xonali)",
        "buyer_name": "Buyurtmachi nomi",
        "supplier_inn": "Yetkazib beruvchi STIR",
        "supplier_name": "Yetkazib beruvchi / G'olib nomi",
        "announcement_date": "E'lon sanasi (YYYY-MM-DD)",
        "contract_date": "Shartnoma sanasi (YYYY-MM-DD)",
        "contract_number": "Shartnoma raqami",
        "contract_url": "Asl shartnoma havolasi",
        "final_price": "Shartnoma summasi",
        "currency": "Valyuta (UZS/USD)",
        "product_name": "Mahsulot nomi",
        "brand": "Brend (Kaspersky, Autodesk, MS, ESET)",
        "quantity": "Miqdor",
        "license_end_date": "Litsenziya tugash sanasi",
        "region": "Hudud / Viloyat"
    }

    @staticmethod
    def parse_csv_preview(file_content: str, max_rows: int = 5) -> Dict[str, Any]:
        """CSV faylni o'qish va dastlabki qatorlarni ko'rsatish."""
        reader = csv.reader(io.StringIO(file_content))
        rows = list(reader)
        if not rows:
            return {"headers": [], "preview_rows": [], "total_rows": 0}
        
        headers = [h.strip() for h in rows[0]]
        preview = rows[1:max_rows+1]
        
        # Avtomatik ustun taxminlari (auto-guess mapping)
        suggested_mapping = {}
        for idx, h in enumerate(headers):
            h_lower = h.lower()
            if any(k in h_lower for k in ["stir", "tin", "инн"]):
                if "yetkazib" in h_lower or "поставщик" in h_lower:
                    suggested_mapping[h] = "supplier_inn"
                else:
                    suggested_mapping[h] = "buyer_inn"
            elif any(k in h_lower for k in ["lot", "лот"]) and any(k in h_lower for k in ["raqam", "id", "№", "номер"]):
                suggested_mapping[h] = "lot_number"
            elif any(k in h_lower for k in ["buyurtmachi", "заказчик", "korxona", "клиент"]):
                suggested_mapping[h] = "buyer_name"
            elif any(k in h_lower for k in ["nomi", "sarlavha", "наименование", "title"]):
                suggested_mapping[h] = "title"
            elif any(k in h_lower for k in ["summa", "narx", "qiymat", "цена", "amount"]):
                suggested_mapping[h] = "final_price"
            elif any(k in h_lower for k in ["shartnoma", "договор", "contract"]) and "№" in h_lower or "raqam" in h_lower:
                suggested_mapping[h] = "contract_number"
            elif any(k in h_lower for k in ["havola", "link", "url"]):
                suggested_mapping[h] = "contract_url"
            elif any(k in h_lower for k in ["sana", "date", "дата"]):
                suggested_mapping[h] = "announcement_date"

        return {
            "headers": headers,
            "preview_rows": preview,
            "total_rows": max(0, len(rows) - 1),
            "suggested_mapping": suggested_mapping,
            "standard_fields": CsvXlsxAdapter.STANDARD_FIELDS
        }

    @staticmethod
    def import_mapped_data(file_content: str, column_mapping: Dict[str, str], 
                           platform_id: str = "custom_import") -> Dict[str, Any]:
        """
        Xaritalangan ustunlar asosida bazaga import qilish va dublikatlarni nazorat qilish.
        """
        reader = csv.DictReader(io.StringIO(file_content))
        added_lots = 0
        updated_lots = 0
        added_companies = 0
        skipped_duplicates = 0
        errors = []

        with db_session() as conn:
            cursor = conn.cursor()

            for row_idx, raw_row in enumerate(reader, start=2):
                try:
                    # Map row to standard fields
                    mapped = {}
                    for file_col, std_field in column_mapping.items():
                        if file_col in raw_row and std_field:
                            mapped[std_field] = str(raw_row[file_col]).strip()

                    lot_num = mapped.get("lot_number")
                    title = mapped.get("title") or f"Import qilingan lot #{lot_num}"
                    buyer_inn = mapped.get("buyer_inn", "").replace(" ", "")
                    buyer_name = mapped.get("buyer_name") or "Noma'lum buyurtmachi"

                    if not lot_num and not title:
                        continue

                    lot_id = f"{platform_id}_{lot_num or row_idx}"

                    # 1. Check / Add Company
                    if buyer_inn and len(buyer_inn) >= 7:
                        cursor.execute("SELECT inn FROM companies WHERE inn = ?", (buyer_inn,))
                        existing_comp = cursor.fetchone()
                        if not existing_comp:
                            cursor.execute("""
                            INSERT INTO companies (
                                inn, name, region, first_seen_date, last_seen_date, 
                                total_lots_count, verified_purchases_count, proof_status
                            ) VALUES (?, ?, ?, ?, ?, 1, 1, 'VERIFIED_BUYER');
                            """, (
                                buyer_inn, buyer_name, mapped.get("region"),
                                mapped.get("contract_date") or mapped.get("announcement_date"),
                                mapped.get("contract_date") or mapped.get("announcement_date")
                            ))
                            added_companies += 1
                        else:
                            cursor.execute("""
                            UPDATE companies SET 
                                total_lots_count = total_lots_count + 1,
                                verified_purchases_count = verified_purchases_count + 1
                            WHERE inn = ?;
                            """, (buyer_inn,))

                    # 2. Check duplicate lot
                    cursor.execute("SELECT id FROM lots WHERE id = ? OR lot_number = ?", (lot_id, lot_num))
                    existing_lot = cursor.fetchone()

                    final_price = 0.0
                    try:
                        clean_price = str(mapped.get("final_price", "0")).replace(" ", "").replace(",", ".")
                        final_price = float(clean_price)
                    except ValueError:
                        pass

                    if existing_lot:
                        skipped_duplicates += 1
                        continue

                    # Insert Lot
                    cursor.execute("""
                    INSERT INTO lots (
                        id, lot_number, title, description, platform_id, source_url,
                        procurement_type, official_status, announcement_date, contract_date,
                        start_price, final_price, currency, buyer_inn, buyer_name,
                        supplier_name, winner_name, region, verification_status,
                        has_contract, contract_url, contract_number, license_end_date,
                        created_in_db_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'TASDIQLANGAN', ?, ?, ?, ?, ?);
                    """, (
                        lot_id, lot_num or str(row_idx), title, mapped.get("product_name", ""),
                        platform_id, mapped.get("contract_url") or f"https://softy.uz/archive/{lot_id}",
                        "Fayldan import", mapped.get("announcement_date"), mapped.get("contract_date"),
                        final_price, final_price, mapped.get("currency", "UZS"),
                        buyer_inn or None, buyer_name, mapped.get("supplier_name"),
                        mapped.get("supplier_name"), mapped.get("region"),
                        bool(mapped.get("contract_url") or mapped.get("contract_number")),
                        mapped.get("contract_url"), mapped.get("contract_number"),
                        mapped.get("license_end_date"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))
                    added_lots += 1

                    # 3. Add Line Item if product exists
                    product_name = mapped.get("product_name") or title
                    brand = mapped.get("brand")
                    if not brand:
                        # Auto-detect brand from text
                        p_low = product_name.lower()
                        if "kaspersky" in p_low: brand = "Kaspersky"
                        elif "autocad" in p_low or "autodesk" in p_low: brand = "Autodesk"
                        elif "eset" in p_low or "nod32" in p_low: brand = "ESET"
                        elif "microsoft" in p_low or "windows" in p_low or "office" in p_low: brand = "Microsoft"
                        elif "zoom" in p_low: brand = "Zoom"
                        elif "fortinet" in p_low or "fortigate" in p_low: brand = "Fortinet"

                    cursor.execute("""
                    INSERT INTO contract_items (
                        lot_id, product_name, brand, quantity, unit_price, total_price, is_purchased_product
                    ) VALUES (?, ?, ?, 1, ?, ?, 1);
                    """, (lot_id, product_name, brand, final_price, final_price))

                    # 4. Add to FTS
                    cursor.execute("""
                    INSERT INTO lots_fts (
                        lot_id, title, description, buyer_name, buyer_inn,
                        supplier_name, winner_name, contract_number, items_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        lot_id, title, mapped.get("product_name", ""), buyer_name, buyer_inn,
                        mapped.get("supplier_name", ""), mapped.get("supplier_name", ""),
                        mapped.get("contract_number", ""), product_name
                    ))

                except Exception as row_err:
                    errors.append(f"Qator {row_idx}: {str(row_err)}")

        return {
            "success": True,
            "added_lots": added_lots,
            "added_companies": added_companies,
            "skipped_duplicates": skipped_duplicates,
            "errors": errors[:10]
        }
