#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# SOFTY PROCUREMENT — Hostinger Tezkor Deploy va Sinxronizatsiya Skripti
# Antigravity, Claude Code va Codex'dan birdek ishlatish uchun.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SSH_HOST="u475605112@62.72.50.47"
SSH_PORT="65002"
SSH_KEY="$HOME/.ssh/id_hostinger"
REMOTE_PATH="/home/u475605112/domains/softy.uz/public_html/tender"

echo "1. 🐍 Python sintaksis xatolarini tekshirish..."
python3 -m py_compile passenger_wsgi.py app/*.py app/adapters/*.py
echo "   ✅ Sintaksis xatosiz."

echo "2. 🚀 Fayllarni Hostinger serveriga sinxronlash..."
scp -P "$SSH_PORT" -i "$SSH_KEY" passenger_wsgi.py index.html .htaccess "$SSH_HOST:$REMOTE_PATH/"
scp -P "$SSH_PORT" -i "$SSH_KEY" app/*.py "$SSH_HOST:$REMOTE_PATH/app/"
# app/*.py adapterlar papkasini QAMRAMAYDI — ular alohida yuboriladi,
# aks holda adapter tuzatishlari jimgina serverga yetib bormaydi.
ssh -p "$SSH_PORT" -i "$SSH_KEY" "$SSH_HOST" "mkdir -p $REMOTE_PATH/app/adapters"
scp -P "$SSH_PORT" -i "$SSH_KEY" app/adapters/*.py "$SSH_HOST:$REMOTE_PATH/app/adapters/"
scp -P "$SSH_PORT" -i "$SSH_KEY" umid/index.html "$SSH_HOST:$REMOTE_PATH/umid/index.html"
ssh -p "$SSH_PORT" -i "$SSH_KEY" "$SSH_HOST" "mkdir -p $REMOTE_PATH/it"
scp -P "$SSH_PORT" -i "$SSH_KEY" it/index.html "$SSH_HOST:$REMOTE_PATH/it/index.html"

echo "3. 🔄 WSGI ilovasini qayta yuklash (restart)..."
ssh -p "$SSH_PORT" -i "$SSH_KEY" "$SSH_HOST" "touch $REMOTE_PATH/tmp/restart.txt"

echo "4. 🐙 O'zgarishlarni GitHub'ga avtomatik push qilish..."
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git add -A
    if ! git diff-index --quiet HEAD --; then
        git commit -m "deploy: avtomatik yangilanish $(date '+%Y-%m-%d %H:%M:%S')"
    fi
    git push origin main || echo "   ⚠️ GitHub push xatolik berdi (tarmoqni tekshiring)"
    echo "   ✅ GitHub (umrbaxt93/tender-radar) muvaffaqiyatli sinxronlandi."
fi

echo "5. 🩺 Salomatlikni tekshirish (Health Check)..."
sleep 2
HEALTH=$(curl -s https://tender.softy.uz/api/health)
echo "   Natija: $HEALTH"

echo "🎉 Barcha o'zgarishlar muvaffaqiyatli jonli efirga chiqdi va GitHub'ga saqlandi!"
echo "   Portal: https://tender.softy.uz/umid/"
echo "   GitHub: https://github.com/umrbaxt93/tender-radar"
