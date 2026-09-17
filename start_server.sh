#!/bin/bash
# Softy Platforma — Serverni ishga tushirish skripti
cd "$(dirname "$0")"
echo "====================================================="
echo "  SOFTY PLATFORMA — Davlat Xaridlari & CRM Tizimi"
echo "  Manzil: http://127.0.0.1:8080"
echo "====================================================="
python3 -u -m app.server
