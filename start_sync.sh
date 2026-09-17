#!/bin/bash
# Softy Platforma — Anti-Blocking Sinxronizatsiyani ishga tushirish
cd "$(dirname "$0")"
echo "====================================================="
echo "  SOFTY PLATFORMA — Kunlik Sinxronizatsiya (Anti-Blocking)"
echo "  Baza boshlanish sanasi: 2024-09-01"
echo "====================================================="
python3 -u -m app.sync_service
