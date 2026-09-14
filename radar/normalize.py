"""Product normalization module: brand, product family, model, and licence term."""

from __future__ import annotations

import re
from dataclasses import dataclass

from radar.classify.rules import detect_brand, detect_term_months, normalize


@dataclass(frozen=True)
class NormalizedProduct:
    raw_name: str
    brand: str | None = None
    product_family: str | None = None
    model: str | None = None
    term_months: int | None = None


# Family patterns per brand (case-insensitive)
FAMILY_RULES: list[tuple[str, str, str]] = [
    # (brand, pattern, family_name)
    ("Autodesk", r"\b(autocad\s*lt|автокад\s*лт)\b", "AutoCAD LT"),
    ("Autodesk", r"\b(autocad|автокад)\b", "AutoCAD"),
    ("Autodesk", r"\b(revit|ревит)\b", "Revit"),
    ("Autodesk", r"\b(3ds\s*max|3d\s*max)\b", "3ds Max"),
    ("Autodesk", r"\b(civil\s*3d)\b", "Civil 3D"),
    ("Autodesk", r"\b(inventor)\b", "Inventor"),
    ("Kaspersky", r"\b(total\s*security)\b", "Total Security"),
    ("Kaspersky", r"\b(endpoint\s*security|kes)\b", "Endpoint Security"),
    ("Kaspersky", r"\b(security\s*center|ksc)\b", "Security Center"),
    ("Kaspersky", r"\b(internet\s*security|kis)\b", "Internet Security"),
    ("Kaspersky", r"\b(kaspersky|касперский)\b", "Endpoint Security"),
    ("ESET", r"\b(eset\s*protect|protect)\b", "ESET PROTECT"),
    ("ESET", r"\b(nod32|нод32)\b", "NOD32 Antivirus"),
    ("ESET", r"\b(eset)\b", "ESET PROTECT"),
    ("Microsoft", r"\b(office\s*365|m365|microsoft\s*365)\b", "Microsoft 365"),
    ("Microsoft", r"\b(windows\s*server)\b", "Windows Server"),
    ("Microsoft", r"\b(sql\s*server)\b", "SQL Server"),
    ("Microsoft", r"\b(windows\s*(?:10|11|pro|home))\b", "Windows Client"),
    ("Microsoft", r"\b(office|ms\s*office)\b", "Microsoft Office"),
    ("Microsoft", r"\b(exchange\s*server)\b", "Exchange Server"),
    ("Microsoft", r"\b(visio)\b", "Visio"),
    ("Microsoft", r"\b(project)\b", "Project"),
    ("Zoom", r"\b(webinar|webinars)\b", "Zoom Video Webinars"),
    ("Zoom", r"\b(zoom|meeting|meetings)\b", "Zoom Workplace"),
    ("Fortinet", r"\b(fortigate|fg)\b", "FortiGate"),
    ("Fortinet", r"\b(fortianalyzer)\b", "FortiAnalyzer"),
    ("Fortinet", r"\b(fortimail)\b", "FortiMail"),
    ("Fortinet", r"\b(fortiswitch)\b", "FortiSwitch"),
    ("Check Point", r"\b(quantum|spark)\b", "Quantum Security"),
    ("Oracle", r"\b(database|db)\b", "Oracle Database"),
    ("1C", r"\b(бухгалтер|предприяти|korxona)\b", "1C:Korxona"),
    ("VMware", r"\b(vsphere|esxi)\b", "vSphere ESXi"),
    ("Veeam", r"\b(backup|replication)\b", "Backup & Replication"),
    ("Cisco", r"\b(catalyst|c9\d{3})\b", "Catalyst Switch"),
    ("Cisco", r"\b(nexus)\b", "Nexus Switch"),
    ("Adobe", r"\b(acrobat|pdf)\b", "Acrobat Pro"),
    ("Adobe", r"\b(creative\s*cloud|cc)\b", "Creative Cloud"),
    ("Dell", r"\b(poweredge)\b", "PowerEdge Server"),
    ("Dell", r"\b(powervault)\b", "PowerVault Storage"),
    ("Dell", r"\b(latitude)\b", "Latitude Notebook"),
    ("Dell", r"\b(optiplex)\b", "OptiPlex Desktop"),
    ("HPE", r"\b(proliant)\b", "ProLiant Server"),
    ("Lenovo", r"\b(thinkpad)\b", "ThinkPad Notebook"),
    ("HP", r"\b(laserjet|deskjet|probook|elitebook)\b", "LaserJet"),
]

# Model patterns for common hardware and software editions
MODEL_PATTERNS = [
    re.compile(r"\b([c-z]?\d{2,4}[a-z]?(?:-\d+[a-z]+)?)\b", re.IGNORECASE),
    re.compile(r"\b(dl\d{3}\s*gen\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\b(r\d{3}\b|r\d{3}\s*xs?)\b", re.IGNORECASE),
    re.compile(r"\b(me\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(l1[3-6]|t1[4-6]|x1\s*carbon)\b", re.IGNORECASE),
]


def normalize_product(raw_name: str) -> NormalizedProduct:
    if not raw_name:
        return NormalizedProduct(raw_name="")

    clean = normalize(raw_name)
    brand = detect_brand(clean)
    term = detect_term_months(clean)

    # Fallback brand detection for brands not yet in keywords.yaml
    if not brand:
        low = clean.lower()
        if "autocad" in low or "autodesk" in low:
            brand = "Autodesk"
        elif "zoom" in low:
            brand = "Zoom"
        elif "fortinet" in low or "fortigate" in low:
            brand = "Fortinet"
        elif "eset" in low or "nod32" in low:
            brand = "ESET"
        elif "dell" in low:
            brand = "Dell"
        elif "hpe" in low or "proliant" in low:
            brand = "HPE"
        elif "lenovo" in low:
            brand = "Lenovo"
        elif "cisco" in low:
            brand = "Cisco"
        elif "adobe" in low or "acrobat" in low:
            brand = "Adobe"
        elif "vmware" in low:
            brand = "VMware"
        elif "veeam" in low:
            brand = "Veeam"
        elif "oracle" in low:
            brand = "Oracle"
        elif "1c" in low or "1с" in low:
            brand = "1C"
        elif "hp" in re.findall(r"\b[a-z0-9]+\b", low) or "laserjet" in low or "probook" in low:
            brand = "HP"

    product_family = None
    if brand:
        for b_name, pat, fam in FAMILY_RULES:
            if b_name.lower() == brand.lower():
                if re.search(pat, clean, re.IGNORECASE):
                    product_family = fam
                    break

    model = None
    # Model hint extraction
    for pat in MODEL_PATTERNS:
        match = pat.search(clean)
        if match:
            candidate = match.group(1).upper().strip()
            # Ignore purely numeric or too short codes
            if not candidate.isdigit() and len(candidate) >= 3:
                model = candidate
                break

    return NormalizedProduct(
        raw_name=raw_name.strip(),
        brand=brand,
        product_family=product_family,
        model=model,
        term_months=term,
    )
