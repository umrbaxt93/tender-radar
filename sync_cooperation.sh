#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# SOFTY — cooperation.uz haftalik avtomatik sinxronizatsiyasi
#
# cooperation.uz chet el IP'larni bloklaydi, Hostinger server (Germaniya)
# unga ulana olmaydi. Shu sabab bu skript SERVERDA emas, shu Mac'da (launchd
# orqali) ishlaydi: manbani shu yerda o'qiydi, natijani serverga uzatadi.
#
# Qadamlar: 1) shu Mac'dan scrape  2) JSON'ni serverga scp  3) serverdagi
# doimiy load_coop_remote.py'ni ishga tushirish  4) yangi qatorlarni
# IT/IT-emas deb tasniflash  5) vaqtinchalik JSON'ni tozalash.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")"

SSH_HOST="u475605112@62.72.50.47"
SSH_PORT="65002"
SSH_KEY="$HOME/.ssh/id_hostinger"
REMOTE_PATH="/home/u475605112/domains/softy.uz/public_html/tender"
LOCAL_JSON="exports/cooperation_latest.json"
REMOTE_JSON="$REMOTE_PATH/data/cooperation_latest.json"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') cooperation.uz sinxronizatsiyasi boshlandi ==="

echo "1) Mac'dan cooperation.uz scrape qilinmoqda..."
/usr/bin/python3 scrape_cooperation.py "$LOCAL_JSON"

echo "2) JSON serverga yuborilmoqda..."
scp -P "$SSH_PORT" -i "$SSH_KEY" -q "$LOCAL_JSON" "$SSH_HOST:$REMOTE_JSON"

echo "3) Serverdagi bazaga yuklanmoqda..."
ssh -p "$SSH_PORT" -i "$SSH_KEY" "$SSH_HOST" "cd $REMOTE_PATH && /opt/alt/python311/bin/python3 load_coop_remote.py data/cooperation_latest.json"

echo "4) Yangi qatorlarni IT/IT-emas deb tasniflash..."
ssh -p "$SSH_PORT" -i "$SSH_KEY" "$SSH_HOST" "cd $REMOTE_PATH && /opt/alt/python311/bin/python3 classify_it.py 50000"

echo "5) Vaqtinchalik faylni tozalash..."
ssh -p "$SSH_PORT" -i "$SSH_KEY" "$SSH_HOST" "rm -f $REMOTE_JSON"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') yakunlandi ==="
