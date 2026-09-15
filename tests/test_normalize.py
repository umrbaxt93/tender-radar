"""Tests for product normalization (brand, product_family, model, term_months)."""

from __future__ import annotations

from radar.normalize import normalize_product


def test_autodesk_autocad_normalization():
    p = normalize_product("AutoCAD LT 2026; 1 yil")
    assert p.brand == "Autodesk"
    assert p.product_family == "AutoCAD LT"
    assert p.term_months == 12

    p2 = normalize_product("AutoCAD Commercial New Single-user ELD 1-Year Subscription")
    assert p2.brand == "Autodesk"
    assert p2.product_family == "AutoCAD"
    assert p2.term_months == 12


def test_kaspersky_normalization():
    p = normalize_product(
        "Kaspersky Endpoint Security for Business litsenziyasini uzaytirish (12 oy)"
    )
    assert p.brand == "Kaspersky"
    assert p.product_family == "Endpoint Security"
    assert p.term_months == 12

    p2 = normalize_product("Kaspersky Total Security 24 oy")
    assert p2.brand == "Kaspersky"
    assert p2.product_family == "Total Security"
    assert p2.term_months == 24


def test_fortinet_hardware_and_model_normalization():
    p = normalize_product("Fortinet FortiGate 100F межсетевой экран с подпиской UTM на 1 год")
    assert p.brand == "Fortinet"
    assert p.product_family == "FortiGate"
    assert p.model == "100F"
    assert p.term_months == 12


def test_microsoft_normalization():
    p = normalize_product("Microsoft 365 Business Standard 1 yil")
    assert p.brand == "Microsoft"
    assert p.product_family == "Microsoft 365"
    assert p.term_months == 12

    p2 = normalize_product("Microsoft SQL Server 2022 Standard")
    assert p2.brand == "Microsoft"
    assert p2.product_family == "SQL Server"


def test_zoom_normalization():
    p = normalize_product("Zoom Video Webinars 1000 Attendees 1 year")
    assert p.brand == "Zoom"
    assert p.product_family == "Zoom Video Webinars"
    assert p.term_months == 12
