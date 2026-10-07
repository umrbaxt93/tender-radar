# SOFTY ma'lumotlari — qayerda nima turadi (yagona xarita)

Yangilangan: 2026-10-06. Qoida: yangi tahlil/eksport fayllarini `~/.gemini/antigravity/scratch`
yoki suhbat papkalariga emas, shu `data/` papkasiga saqlang.

## Davlat xaridlari
| Ma'lumot | Joyi | Holati |
|---|---|---|
| **Asosiy (jonli) baza** | tender-radar PostgreSQL `tender_radar` (Mac, 127.0.0.1:5432) | ~2 soatda bir yangilanadi (ebirja + UZEX), ~106 ming yakunlangan shartnoma |
| Jonli sahifa | softy.uz/radar (tender-radar worker yuklaydi) | Har siklda yangilanadi |
| Sahifa skripti va ma'lumoti | `tender-radar/dashboard/` (build_dashboard.py, dashboard_data.json, index.html) | 2026-10-06 da Antigravity suhbat papkasidan ko'chirildi |
| Excel eksport | `tender-radar/out/renewal_radar.xlsx` | |
| cooperation.uz xarid rejalari | scrape: `~/.gemini/antigravity/scripts/cooperation/cooperation_latest.json` (har dushanba) → tender-radar bazasi (`source=cooperation`, `PLANNED`) | 6-okt: 3 818 reja |
| Eski platforma bazasi | `data/softy_procurement.db` (SQLite, 17-sentabr holati, 101 664 lot) | tender-radar'ga `migrate-sqlite` bilan ko'chirish manbasi (BIRLASHTIRISH_REJASI.md) |
| Eski platforma jonli nusxasi | tender.softy.uz serveri (Hostinger, 62.72.50.47) | birlashtirilgach to'xtatiladi |

## Arxiv (`data/arxiv/`, GitHub'ga yuborilmaydi)
- `eski_platforma/` — eski SQLite bazaning 17-sentabrdagi zaxira nusxasi.
- `xaridlar_tahlili_2026-08-31/` — 31-avgustdagi qo'lda UZEX/etender auditlari (Antigravity scratch'dan ko'chirildi).
- `didox/didox_complete_audit.json` — Didox auditi (Didox MCP serveri shu fayldan o'qiydi).
- `boshqa_jadvallar/` — litsenziyalar, oylar, viloyatlar kesimidagi bir martalik jadvallar.
- `boshqa/` — test hujjatlari.

## Boshqa manbalar
- Bitrix24 CRM nusxasi: Obsidian → `Mijozlar-CRM/` — 2 ta doimiy fayl (har kuni yangilanadi); eski kunlik nusxalar `Mijozlar-CRM/_arxiv/`.
- Davomat (to'g'ri manba): `Desktop/Softy Xodimlar nazorati/SOFTY_kelish_nazorati_2026-09.xlsx`.
- e-auksion lot hujjatlari (kadastr, soliq): `Desktop/Fatullayev Umidjon/e-auksion lot hujjatlari/`.
