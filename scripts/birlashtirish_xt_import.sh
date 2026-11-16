#!/bin/bash
# Birlashtirish 1-qadam (2026-10-06): eski Softy platformadagi REAL XT-Xarid lotlarini
# tender-radar bazasiga qo'shadi. Idempotent — qayta ishga tushirilsa takror yaratmaydi.
# UZEX/ebirja ko'chirilmaydi: tender-radar ularni rasmiy API'dan o'zi yig'adi
# (sabab: ../BIRLASHTIRISH_REJASI.md). `radar migrate-sqlite` ni ISHLATMANG.
set -euo pipefail
cd "$(dirname "$0")/.."
PGBIN=/Applications/Postgres.app/Contents/Versions/16/bin
DBURL=$(grep '^DATABASE_URL=' .env | cut -d= -f2-)
TS=$(date +%Y%m%d-%H%M)
BK="../data/arxiv/tender_radar_backup"
mkdir -p "$BK"

echo "1) Zaxira nusxa (pg_dump)..."
"$PGBIN/pg_dump" -Fc -f "$BK/tender_radar_$TS.dump" "$DBURL"
ls -lh "$BK/tender_radar_$TS.dump"

echo "2) Import oldidan:"
.venv/bin/python -m radar stats

echo "3) XT-Xarid real lotlarini import qilish..."
.venv/bin/python -m radar migrate-xt --sqlite-path ../data/softy_procurement.db

echo "4) Import'dan keyin:"
.venv/bin/python -m radar stats
echo "Tayyor. Muammo bo'lsa tiklash: $PGBIN/pg_restore --clean -d \"\$DATABASE_URL\" $BK/tender_radar_$TS.dump"
