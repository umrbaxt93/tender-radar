#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Softy — bitta cron hamma ishni qiladi (hPanel'da faqat bitta cron qo'yilgan):
#   1) Boyitish tugamaguncha: har chaqiruvda bir bo'lak eski yozuvni to'ldiradi.
#   2) Boyitish tugagach: kuniga bir marta (03:00 dan keyin) yangi lotlarni oladi.
#   3) Ish qolmasa: bo'sh yuradi (hech narsa qilmaydi) — cron zararsiz.
# Hostinger cron ishni 1800s (30 daqiqa) da o'ldiradi, shuning uchun har qadam
# 30 daqiqadan past.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
APP_DIR="/home/u475605112/domains/softy.uz/public_html/tender"
PY="/opt/alt/python311/bin/python3"
LOG="$APP_DIR/data/backfill_ebirja.log"
LOCK="$APP_DIR/data/backfill.lock"
cd "$APP_DIR" || exit 1

# Bir vaqtda faqat bitta nusxa
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then exit 0; fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

REMAIN=$("$PY" remaining.py 2>/dev/null)

if [ -n "$REMAIN" ] && [ "$REMAIN" -gt 50 ]; then
    # 1) hali boyitilmagan yozuv bor — bir bo'lak (2x250 ≈ 25 daqiqa)
    "$PY" backfill_ebirja.py 250 2 >> "$LOG" 2>&1
else
    # 2) boyitish tugadi
    if [ ! -f "$APP_DIR/data/backfill.done" ]; then
        echo "$(date '+%Y-%m-%d %H:%M') ✅ BOYITISH TUGADI (${REMAIN:-0} qoldi). Endi cron kundalik sync rejimida." >> "$LOG"
        touch "$APP_DIR/data/backfill.done"
    fi
    # kuniga bir marta, 03:00 dan keyin — yangi lotlarni olish
    TODAY=$(date '+%Y-%m-%d'); HOUR=$(date '+%H')
    LAST=$(cat "$APP_DIR/data/last_sync_day" 2>/dev/null || echo "")
    if [ "$LAST" != "$TODAY" ] && [ "$HOUR" -ge 3 ]; then
        echo "$TODAY" > "$APP_DIR/data/last_sync_day"
        echo "$(date '+%Y-%m-%d %H:%M') kundalik sync boshlandi" >> "$APP_DIR/data/sync_cron.log"
        "$PY" run_sync.py 150 20 >> "$APP_DIR/data/sync_cron.log" 2>&1
        # Yangi kelgan lotlarni IT/IT-emas deb tasniflash — busiz ular
        # is_it=NULL holida qolib, /it/ sahifasida va IT raqobatchilar
        # qidiruvida hafta bo'lib ko'rinmay qolardi (faqat haftalik
        # cooperation sinxronizatsiyasi tasodifan tasniflardi).
        "$PY" classify_it.py 50000 >> "$APP_DIR/data/sync_cron.log" 2>&1
        echo "$(date '+%Y-%m-%d %H:%M') kundalik sync tugadi" >> "$APP_DIR/data/sync_cron.log"
    fi
fi
tail -n 3000 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG" || true
