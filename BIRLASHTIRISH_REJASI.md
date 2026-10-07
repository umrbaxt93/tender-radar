# Davlat xaridlari: ikki tizimni bittaga birlashtirish (2026-10-06)

## Qaror: asosiy tizim — `tender-radar/`

| | tender-radar | Eski Softy platforma (ildiz papka, tender.softy.uz) |
|---|---|---|
| Ishlayaptimi | Ha — Mac'da har ~2 soat 17 daqiqada (kuniga ~10 sikl), natija softy.uz/radar ga chiqadi | Lokal nusxa 16-sentabrda to'xtagan; serverdagi cron holati tekshirilmagan |
| Ma'lumot | PostgreSQL, ~106 ming yakunlangan shartnoma, rasmiy API, xom snapshot saqlanadi | SQLite, 101 664 lot — **100 122 tasi aynan tender-radar formatidagi o'sha UZEX/ebirja yozuvlari** (`uzex_uzex_et_*`, `ebirja_ebirja_c_*`) |
| Sifat | 137+ test, dedup, tasniflash, renewal radar, Bitrix CRM, Telegram, AI maslahatchi | Testlar kam, sun'iy (seed) yozuvlar aralash (`uzex_kasp_*`, `ebirja_zoom_*`, `coop_forti_*`, `synthetic_*`) |

## Nima ko'chiriladi
| Eski bazadagi ma'lumot | Soni | Qaror |
|---|---|---|
| XT-Xarid real lotlari (`xt_xarid_*`) | 187 | **Ko'chiriladi** — `scripts/birlashtirish_xt_import.sh` (`radar migrate-xt`, idempotent) |
| UZEX/ebirja (`uzex_uzex_*`, `ebirja_ebirja_*`) | 100 122 | Ko'chirilmaydi — tender-radar'da allaqachon bor |
| SOFTY kabineti shartnomalari (`uzex_dash_*`) va 31-avgust auditi (`uzex_<raqam>`) | 313 + 867 | Ko'rib chiqiladi — SOFTY'ning o'z shartnomalari bo'lishi mumkin; avtomatik ko'chirilmaydi |
| Sun'iy/seed yozuvlar | ~15 | Ko'chirilmaydi |

⚠️ `radar migrate-sqlite` ni **ishlatmang**: u eski ID'larni (`lot_number`) ishlatadi va
tender-radar'dagi (`uzex_et_*`, `ebirja_c_*`) yozuvlarni tanimaydi — ~100 ming takror yaratadi.

## Qadamlar
1. ✅ Bajarildi (6-okt): dashboard skripti/ma'lumoti Antigravity suhbat papkasidan `tender-radar/dashboard/` ga ko'chirildi; `.env` yangilandi; ma'lumotlar xaritasi `data/README_MALUMOTLAR.md`; tarqoq fayllar `data/arxiv/` ga yig'ildi.
2. XT import (Terminal): `bash "tender-radar/scripts/birlashtirish_xt_import.sh"` — avval pg_dump zaxira oladi.
3. Hosting: tender-radar veb-ilovasi (qidiruv, CRM, AI) uchun VPS 93.127.213.246 kerak. 14-sentabr holatiga muddati **11-oktabr** va avtomatik uzaytirish o'chiq edi → hPanel'da uzaytiring. Keyin `tender-radar/deploy/deploy_vps.sh` + nginx + parol (docs/DEPLOYMENT.md).
4. `tender.softy.uz` → VPS: Ahost DNS'da A yozuvi 62.72.50.47 → 93.127.213.246 (3-qadam ishlagach).
5. Eski platformani to'xtatish (4-qadamdan keyin): hPanel → Cron Jobs → `chunk_runner.sh` ni o'chirish; `sync_deploy.sh` ni ishlatmaslik; Mac'da `launchctl bootout gui/$(id -u)/com.softy.procurementsync` (agar yuklangan bo'lsa).
6. ✅ cooperation.uz (6-okt): tender-radar'ga ko'chirildi — `radar/source/cooperation.py`, `radar import-cooperation`, worker'dagi `sync_cooperation` bosqichi. Haftalik scrape (dushanba 04:00, `~/.gemini/antigravity/scripts/cooperation/`) JSON yozadi, tender-radar worker uni keyingi siklda o'zi import qiladi (rejalar `PLANNED` holatida, renewal radar'ga kirmaydi). O'chirish: `.env` da `COOPERATION_IMPORT=0`. Eski serverga yuborish ham hozircha davom etadi (eski platforma yopilguncha).
7. Kodni ajratish: eski platforma kodini alohida repo/arxivga; `umrbaxt93/tender-radar` `main` ← tender-radar kodi.
