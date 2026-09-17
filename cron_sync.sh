#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# SOFTY PROCUREMENT — Serverdagi kunlik sinxronizatsiya (cron orqali)
#
# Nega serverda: ilgari sync faqat Umidning Mac'ida ishlardi, shuning uchun
# kompyuter uxlaganda yoki tarmoqdan uzilganda "Connection refused" xatolari
# to'planardi. Server 24/7 ishlaydi va manbalarga chiqa oladi.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

APP_DIR="/home/u475605112/domains/softy.uz/public_html/tender"
PY="/opt/alt/python311/bin/python3"
LOG="$APP_DIR/data/sync_cron.log"

cd "$APP_DIR" || exit 1
echo "=== $(date '+%Y-%m-%d %H:%M:%S') sinxronizatsiya boshlandi ===" >> "$LOG"
"$PY" run_sync.py 150 20 >> "$LOG" 2>&1
echo "=== $(date '+%Y-%m-%d %H:%M:%S') yakunlandi (kod: $?) ===" >> "$LOG"

# Jurnal haddan tashqari o'smasin
tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
