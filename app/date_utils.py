"""
Softy Platforma — Date Calculation Utilities
Shartnoma tugash sanalarini (contract_end_date) xarid turi, litsenziya muddati
va davlat xaridlari qoidalariga mos ravishda aniq hisoblash.
"""

import re
from datetime import datetime, timedelta
from typing import Optional


def calculate_accurate_end_date(
    title: str,
    contract_date: Optional[str],
    license_end_date: Optional[str] = None,
    category: str = ""
) -> str:
    """
    Shartnoma tugash sanasini aniq hisoblash.
    1. Agar bazada license_end_date mavjud bo'lsa — o'shani oladi.
    2. Agar nomida '3 yil', '2 yil', '1 yil', '6 oy' bo'lsa — mos muddat qo'shadi.
    3. Agar IT dastur, antivirus, litsenziya, texnik xizmat bo'lsa — 1 yil (standart).
    4. Agar oddiy tovar, shop yoki auksion bo'lsa — yetkazib berish muddati (30 kun) yoki yil oxiri.
    """
    if license_end_date and len(str(license_end_date).strip()) >= 10:
        return str(license_end_date).strip()[:10]

    if not contract_date or len(str(contract_date).strip()) < 10:
        return ""

    try:
        dt = datetime.strptime(str(contract_date).strip()[:10], "%Y-%m-%d")
    except Exception:
        return ""

    text = f"{title or ''} {category or ''}".lower()

    # 1. Nomda aniq ko'rsatilgan muddatlar
    if re.search(r'3\s*(yil|god|year|36\s*oy)', text):
        try:
            return dt.replace(year=dt.year + 3).strftime("%Y-%m-%d")
        except ValueError:
            return (dt + timedelta(days=365 * 3)).strftime("%Y-%m-%d")

    if re.search(r'2\s*(yil|goda|year|24\s*oy)', text):
        try:
            return dt.replace(year=dt.year + 2).strftime("%Y-%m-%d")
        except ValueError:
            return (dt + timedelta(days=365 * 2)).strftime("%Y-%m-%d")

    if re.search(r'1\s*(yil|god|year|12\s*oy)|yillik|annual', text):
        try:
            return dt.replace(year=dt.year + 1).strftime("%Y-%m-%d")
        except ValueError:
            return (dt + timedelta(days=365)).strftime("%Y-%m-%d")

    if re.search(r'6\s*oy|polgoda|half-year', text):
        return (dt + timedelta(days=182)).strftime("%Y-%m-%d")

    if re.search(r'3\s*oy|kvartal', text):
        return (dt + timedelta(days=91)).strftime("%Y-%m-%d")

    # 2. IT Litsenziyalar, Dasturiy ta'minot, Antivirus, Bulut, Server xizmati (1 yil)
    it_license_keywords = [
        "litsenziya", "licen", "dastur", "software", "antivirus", "kaspersky",
        "fortinet", "microsoft", "1c", "obuna", "subscri", "texnik xizmat",
        "texnik qo'llab", "monitoring", "eset", "autocad", "windows", "cloud"
    ]
    if any(kw in text for kw in it_license_keywords):
        try:
            return dt.replace(year=dt.year + 1).strftime("%Y-%m-%d")
        except ValueError:
            return (dt + timedelta(days=365)).strftime("%Y-%m-%d")

    # 3. Davlat xaridlaridagi oddiy tovar va mahsulotlar (Shop, e-shop, auksion):
    # Standart yetkazib berish muddati: 30 kalendar kuni!
    # Agar dekabr oyi bo'lsa -> 31-dekabr (moliya yili oxiri)
    if dt.month == 12:
        return f"{dt.year}-12-31"
    elif dt.month in (10, 11):
        end_30 = dt + timedelta(days=30)
        year_end = datetime(dt.year, 12, 31)
        return min(end_30, year_end).strftime("%Y-%m-%d")
    else:
        return (dt + timedelta(days=30)).strftime("%Y-%m-%d")
