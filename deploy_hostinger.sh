#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# SOFTY PLATFORMA — Hostinger Deployment Package Builder
# tender.softy.uz domeni uchun to'liq deployment arxivi
# ─────────────────────────────────────────────────────────────
set -euo pipefail

DIST_DIR="dist_hostinger"
ZIP_NAME="tender-softy.zip"

echo "▶ Hostinger deployment paketi tayyorlanmoqda..."
mkdir -p "$DIST_DIR"
rm -f "$DIST_DIR/$ZIP_NAME"

# Zip packaging (excluding temporary files, pycache, and logs)
zip -r "$DIST_DIR/$ZIP_NAME" \
    app/ \
    data/softy_procurement.db \
    frontend/ \
    nginx/ \
    passenger_wsgi.py \
    .htaccess \
    start_server.sh \
    start_sync.sh \
    -x "*.pyc" -x "*__pycache__*" -x "*DS_Store*" -x "*.log"

PKG_SIZE=$(ls -lh "$DIST_DIR/$ZIP_NAME" | awk '{print $5}')
echo "✅ Tayyor: $DIST_DIR/$ZIP_NAME (Hajmi: $PKG_SIZE)"
