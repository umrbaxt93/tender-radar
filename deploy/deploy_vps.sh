#!/usr/bin/env bash
# ==============================================================================
# Tender Radar — Hostinger VPS (Ubuntu 22.04/24.04) Automated Deployment Script
# Target: 93.127.213.246 / tender.softy.uz
# ==============================================================================
set -euo pipefail

APP_DIR="/opt/tender-radar"
APP_USER="radar"
DB_NAME="tender_radar"
DB_USER="tender"
PYTHON_BIN="/usr/bin/python3.12"

echo "=========================================================="
echo "🚀 SOFTY Tender Radar — VPS Avtomatlashtirilgan O'rnatish"
echo "=========================================================="

# 1. System packages
echo "📦 1. Tizim paketlari va PostgreSQL 16 yangilanmoqda..."
apt-get update -y
apt-get install -y curl wget gnupg2 software-properties-common git build-essential nginx

# Add PostgreSQL 16 repo if needed
if ! command -v psql &> /dev/null; then
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
    echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
    apt-get update -y
    apt-get install -y postgresql-16 postgresql-contrib-16
fi

# Add Python 3.12 if not present
if ! command -v python3.12 &> /dev/null; then
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
    apt-get install -y python3.12 python3.12-venv python3.12-dev
fi

# 2. Database configuration
echo "🗄 2. PostgreSQL 'tender_radar' bazasi sozlanmoqda..."
systemctl enable --now postgresql
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD 'tender_production_pass';" || true
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" || true
sudo -u postgres psql -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" || true

# 3. Create app user and directories
echo "👤 3. 'radar' foydalanuvchisi va papkalar sozlanmoqda..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/bash -d "$APP_DIR" "$APP_USER"
fi
mkdir -p "$APP_DIR" "$APP_DIR/out" "$APP_DIR/data"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# 4. Copy application files if running locally or git
echo "📂 4. Dastur fayllari va virtual muhit (.venv) o'rnatilmoqda..."
cd "$APP_DIR"

if [ ! -d ".venv" ]; then
    sudo -u "$APP_USER" $PYTHON_BIN -m venv .venv
fi

sudo -u "$APP_USER" .venv/bin/pip install --upgrade pip setuptools wheel
if [ -f "pyproject.toml" ]; then
    sudo -u "$APP_USER" .venv/bin/pip install -e .
fi

# 5. Environment configuration
if [ ! -f ".env" ]; then
    cp .env.example .env
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql://$DB_USER:tender_production_pass@127.0.0.1:5432/$DB_NAME|" .env
    sed -i "s|APP_ENV=.*|APP_ENV=production|" .env
    chown "$APP_USER:$APP_USER" .env
    chmod 600 .env
fi

# 6. Database migrations & historical data migration
echo "🔄 5. Ma'lumotlar bazasi migratsiyalari ishga tushirilmoqda..."
sudo -u "$APP_USER" .venv/bin/alembic upgrade head

if [ -f "data/softy_procurement.db" ]; then
    echo "📊 Tarixiy SQLite ma'lumotlari PostgreSQL ga ko'chirilmoqda..."
    sudo -u "$APP_USER" .venv/bin/python -m radar migrate-sqlite --sqlite-path data/softy_procurement.db || true
fi

echo "🎯 Renewal imkoniyatlari hisoblanmoqda..."
sudo -u "$APP_USER" .venv/bin/python -m radar renewal || true

# 7. Systemd services installation
echo "⚙️ 6. Systemd servislari (Web, Worker, Telegram Bot) yoqilmoqda..."
cp deploy/tender-radar-web.service /etc/systemd/system/
cp deploy/tender-radar-worker.service /etc/systemd/system/
cp deploy/tender-radar-bot.service /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now tender-radar-web
systemctl enable --now tender-radar-worker
systemctl enable --now tender-radar-bot

# 8. Nginx configuration
echo "🌐 7. Nginx reverse proxy sozlanmoqda..."
cp deploy/nginx-tender-radar.conf /etc/nginx/sites-available/tender-radar.conf
ln -sf /etc/nginx/sites-available/tender-radar.conf /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

echo "=========================================================="
echo "✅ SOFTY Tender Radar muvaffaqiyatli ishga tushirildi!"
echo "   Veb: http://127.0.0.1:8000/radar"
echo "   Servislar: tender-radar-web, tender-radar-worker, tender-radar-bot"
echo "=========================================================="
