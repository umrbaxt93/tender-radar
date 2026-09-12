"""Generate clearly-labelled SYNTHETIC source fixtures for offline development.

These are NOT real xarid.uzex.uz responses. Every source id starts with "SYN-",
every customer name contains "(SYNTHETIC)" and STIRs are in the 9xxxxxxxx range.
The JSON shape follows radar/source/uzex_mapping.yaml.

Usage: python scripts/gen_synthetic_fixtures.py OUT_DIR --count 500 [--seed 42]
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

PAGE_SIZE = 50

IT_TEMPLATES = [
    ("Kaspersky Endpoint Security for Business litsenziyasi (12 oy)", "Kaspersky Endpoint Security", "dona", True),
    ("Microsoft 365 Business Standard obunasi 1 yil", "Microsoft 365 Business Standard", "dona", True),
    ("Приобретение лицензий Microsoft Windows Server 2022 Standard", "Microsoft Windows Server 2022", "шт", False),
    ("Fortinet FortiGate 100F межсетевой экран с подпиской UTM 1 год", "FortiGate 100F UTP bundle", "шт", True),
    ("Server HPE ProLiant DL380 Gen11 xarid qilish", "HPE ProLiant DL380 Gen11", "dona", False),
    ("Коммутатор Cisco Catalyst 9200 48 портов", "Cisco Catalyst C9200-48P", "шт", False),
    ("Noutbuk Lenovo ThinkPad L15 sotib olish", "Lenovo ThinkPad L15 Gen4", "dona", False),
    ("Принтер МФУ HP LaserJet Pro MFP", "HP LaserJet Pro MFP 4103", "шт", False),
    ("ИБП APC Smart-UPS 3000VA", "APC SMT3000RMI2UC", "шт", False),
    ("Видеонаблюдение тизими (CCTV) kameralar va NVR", "Hikvision DS-2CD2043G2", "dona", False),
    ("Zoom Business obunasi 12 oy", "Zoom Business", "dona", True),
    ("Антивирус Dr.Web Enterprise Security Suite продление на 1 год", "Dr.Web ESS", "шт", True),
    ("Система хранения данных Dell PowerVault ME5024", "Dell PowerVault ME5024", "шт", False),
    ("Bulutli hosting xizmati (VPS) 12 oy", "VPS 8 vCPU 32GB", "oy", True),
    ("Dasturiy ta'minotni ishlab chiqish xizmatlari (ERP moduli)", "ERP moduli ishlab chiqish", "xizmat", False),
    ("Google Workspace Business Starter obunasi", "Google Workspace Business Starter", "dona", True),
    ("DLP tizimi litsenziyasi InfoWatch Traffic Monitor 1 yil", "InfoWatch Traffic Monitor", "dona", True),
    ("Компьютер в сборе (системный блок, монитор)", "Kompyuter i5 16GB 512GB", "шт", False),
]
NON_IT_TEMPLATES = [
    ("Ofis mebeli (stol, stul, shkaf) xarid qilish", "Ofis stoli", "dona"),
    ("Qurilish materiallari (sement, g'isht)", "Sement M400", "tonna"),
    ("Приобретение продуктов питания для столовой", "Мука высший сорт", "кг"),
    ("Avtomobil Chevrolet Cobalt sotib olish", "Chevrolet Cobalt", "dona"),
    ("Kanselyariya tovarlari (qog'oz, ruchka)", "A4 qog'oz 80g", "pachka"),
    ("Dori vositalari va tibbiy sarf materiallari", "Paratsetamol 500mg", "quti"),
    ("Ремонт кровли административного здания", "Кровельные работы", "м2"),
    ("Kommunal xizmatlar: elektr energiyasi", "Elektr energiyasi", "kVt·soat"),
    ("Yoqilg'i-moylash materiallari (AI-92 benzin)", "AI-92", "litr"),
    ("Приобретение спецодежды и СИЗ", "Спецодежда летняя", "компл"),
]
CUSTOMERS = [
    ("Toshkent shahar hokimligi axborot-kommunikatsiya boshqarmasi (SYNTHETIC)", "Toshkent shahri"),
    ("Samarqand viloyati tibbiyot birlashmasi (SYNTHETIC)", "Samarqand viloyati"),
    ("Buxoro davlat universiteti (SYNTHETIC)", "Buxoro viloyati"),
    ("Andijon viloyat moliya boshqarmasi (SYNTHETIC)", "Andijon viloyati"),
    ("Farg'ona shahar maktabgacha ta'lim bo'limi (SYNTHETIC)", "Farg'ona viloyati"),
    ("Namangan viloyati statistika boshqarmasi (SYNTHETIC)", "Namangan viloyati"),
    ("Qashqadaryo viloyat hokimligi (SYNTHETIC)", "Qashqadaryo viloyati"),
    ("Xorazm viloyati soliq boshqarmasi (SYNTHETIC)", "Xorazm viloyati"),
    ("Navoiy kon-metallurgiya kolleji (SYNTHETIC)", "Navoiy viloyati"),
    ("Jizzax politexnika instituti (SYNTHETIC)", "Jizzax viloyati"),
    ("Sirdaryo viloyati suv xo'jaligi (SYNTHETIC)", "Sirdaryo viloyati"),
    ("Surxondaryo viloyat kutubxonasi (SYNTHETIC)", "Surxondaryo viloyati"),
]
SUPPLIERS = ["IT Solutions Group MChJ (SYNTHETIC)", "Uzbek Digital Systems OOO (SYNTHETIC)",
             "Secure Networks LLC (SYNTHETIC)", "Universal Trade MChJ (SYNTHETIC)"]


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build(count: int, seed: int, now: datetime) -> list[dict]:
    rng = random.Random(seed)
    lots = []
    for n in range(1, count + 1):
        is_it = rng.random() < 0.55
        if is_it:
            title, item, unit, _ = rng.choice(IT_TEMPLATES)
        else:
            title, item, unit = rng.choice(NON_IT_TEMPLATES)
        cust_idx = rng.randrange(len(CUSTOMERS))
        cust_name, region = CUSTOMERS[cust_idx]
        # completed between 1 and 450 days ago so that 12-month lifecycles land around now
        completed = now - timedelta(days=rng.randint(1, 450), hours=rng.randint(0, 23))
        published = completed - timedelta(days=rng.randint(7, 30))
        deadline = published + timedelta(days=rng.randint(5, 20))
        qty = rng.choice([1, 2, 5, 10, 25, 50, 100])
        unit_price = rng.choice([450_000, 1_200_000, 3_800_000, 12_500_000, 48_000_000, 95_000_000])
        start_price = qty * unit_price
        lot = {
            "id": f"SYN-{n:06d}",
            "procedure_type": rng.choice(["auction", "tender", "selection", "e-shop"]),
            "title": title,
            "status": "completed",
            "published_at": iso(published),
            "deadline_at": iso(deadline),
            "completed_at": iso(completed),
            "currency": "UZS",
            "start_price": start_price,
            "customer": {"name": cust_name, "stir": f"9{cust_idx:08d}", "region": region},
            "items": [{"name": item, "quantity": qty, "unit": unit, "unit_price": str(unit_price)}],
        }
        if rng.random() < 0.8:
            s_idx = rng.randrange(len(SUPPLIERS))
            lot["award"] = {
                "supplier": {"name": SUPPLIERS[s_idx], "stir": f"8{s_idx:08d}"},
                "amount": round(start_price * rng.uniform(0.7, 0.99), 2),
                "awarded_at": iso(completed),
            }
        lots.append(lot)
    lots.sort(key=lambda lot: lot["completed_at"], reverse=True)
    return lots


def write(out: Path, lots: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "README.md").write_text(
        "SYNTHETIC fixtures generated by scripts/gen_synthetic_fixtures.py.\n"
        "Not real procurement data. Do not present as real results.\n")
    pages = [lots[i:i + PAGE_SIZE] for i in range(0, len(lots), PAGE_SIZE)]
    for page_no, page in enumerate(pages, start=1):
        entries = [{"id": lot["id"], "completed_at": lot["completed_at"], "title": lot["title"]}
                   for lot in page]
        (out / f"list_page_{page_no}.json").write_text(json.dumps(
            {"synthetic": True, "data": {"items": entries, "total": len(lots),
                                         "page": page_no, "size": PAGE_SIZE}},
            ensure_ascii=False, indent=1))
    for lot in lots:
        (out / f"detail_{lot['id']}.json").write_text(
            json.dumps({"synthetic": True, **lot}, ensure_ascii=False, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--now", default=None, help="ISO timestamp anchoring 'today' (UTC)")
    args = ap.parse_args()
    now = datetime.fromisoformat(args.now).replace(tzinfo=UTC) if args.now else datetime.now(UTC)
    lots = build(args.count, args.seed, now)
    write(Path(args.out), lots)
    print(f"wrote {len(lots)} synthetic lots to {args.out}")


if __name__ == "__main__":
    main()
