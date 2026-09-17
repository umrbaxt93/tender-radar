"""
Softy Platforma — Export Service (17.E)
Ekrandagi filtrlar va saralashga 100% mos ravishda Excel (.xlsx) va PDF (.pdf) formatlarida eksport qilish.
"""

import csv
import io
import json
import zipfile
from datetime import datetime
from typing import Dict, Any, List, Tuple, Union
from app.database import db_session
from app.filter_engine import build_search_filter_query

# ─────────────────────────────────────────────────────────────
# 1. Excel (.xlsx OpenXML) Sof Python Generator
# ─────────────────────────────────────────────────────────────
def generate_xlsx(sheet_title: str, headers: List[str], rows: List[List[Any]]) -> bytes:
    """
    Tashqi kutubxonalarsiz, 100% standart OpenXML .xlsx faylini yaratish.
    UTF-8, Kirill/Lotin belgilari va raqamli formatlarni to'liq qo'llab-quvvatlaydi.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        zf.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>''')

        # _rels/.rels
        zf.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''')

        # xl/_rels/workbook.xml.rels
        zf.writestr('xl/_rels/workbook.xml.rels', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>''')

        # xl/styles.xml (Professional Dark Navy Header & Money formatting)
        zf.writestr('xl/styles.xml', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="1">
    <numFmt numFmtId="164" formatCode="#,##0"/>
  </numFmts>
  <fonts count="2">
    <font><sz val="10"/><color rgb="0F172A"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFF"/><name val="Calibri"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="0F172A"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/></border>
    <border>
      <left style="thin"><color rgb="E2E8F0"/></left>
      <right style="thin"><color rgb="E2E8F0"/></right>
      <top style="thin"><color rgb="E2E8F0"/></top>
      <bottom style="thin"><color rgb="E2E8F0"/></bottom>
    </border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="4">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"/>
  </cellXfs>
</styleSheet>''')

        # xl/workbook.xml
        clean_sheet_title = sheet_title[:30].replace('/', '-').replace('\\', '-')
        zf.writestr('xl/workbook.xml', f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="{clean_sheet_title}" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>''')

        # Column letter generator (A, B ... Z, AA, AB ...)
        def get_col_letter(idx):
            if idx < 26: return chr(65 + idx)
            return chr(64 + idx // 26) + chr(65 + idx % 26)

        sheet_rows = []
        # Header Row
        h_cells = []
        for c_idx, h in enumerate(headers):
            c_let = get_col_letter(c_idx)
            h_clean = str(h).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            h_cells.append(f'<c r="{c_let}1" s="1" t="inlineStr"><is><t>{h_clean}</t></is></c>')
        sheet_rows.append('<row r="1" ht="28" customHeight="1">' + ''.join(h_cells) + '</row>')

        # Data Rows
        for r_idx, row in enumerate(rows, start=2):
            r_cells = []
            for c_idx, val in enumerate(row):
                c_let = get_col_letter(c_idx)
                if isinstance(val, (int, float)) and val != 0:
                    r_cells.append(f'<c r="{c_let}{r_idx}" s="2"><v>{val}</v></c>')
                else:
                    v_str = str(val if val is not None else '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    r_cells.append(f'<c r="{c_let}{r_idx}" s="0" t="inlineStr"><is><t>{v_str}</t></is></c>')
            sheet_rows.append(f'<row r="{r_idx}">' + ''.join(r_cells) + '</row>')

        sheet_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(sheet_rows) + '</sheetData></worksheet>'
        zf.writestr('xl/worksheets/sheet1.xml', sheet_xml.encode('utf-8'))

    return buf.getvalue()

# ─────────────────────────────────────────────────────────────
# 2. PDF (.pdf) Sof Python Generator
# ─────────────────────────────────────────────────────────────
CYR_TO_LAT = {
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo', 'Ж': 'J', 'З': 'Z',
    'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R',
    'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'X', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sh',
    'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya', 'Ў': 'O\'', 'Қ': 'Q', 'Ғ': 'G\'', 'Ҳ': 'H',
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'j', 'з': 'z',
    'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'x', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sh',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya', 'ў': 'o\'', 'қ': 'q', 'ғ': 'g\'', 'ҳ': 'h'
}

def to_latin(text: Any) -> str:
    if not text: return ''
    res = []
    for ch in str(text):
        res.append(CYR_TO_LAT.get(ch, ch))
    return ''.join(res)

def clean_pdf_str(text: Any) -> str:
    t = to_latin(text)
    t = t.replace('\\', '/').replace('(', '[').replace(')', ']')
    return t.encode('latin-1', 'replace').decode('latin-1')

def generate_pdf(title: str, subtitle: str, headers: List[str], rows: List[List[Any]]) -> bytes:
    """
    A4 Landscape (842x595) formatida to'liq sahifalangan PDF hisobot yaratish.
    """
    out = io.BytesIO()
    page_w, page_h = 842, 595
    margin = 35

    # Display at most 7-8 primary columns for readability on PDF
    display_headers = headers[:7]
    display_rows = [[r[i] if i < len(r) else '' for i in range(len(display_headers))] for r in rows]

    num_cols = len(display_headers)
    col_w = (page_w - 2 * margin) / max(1, num_cols)

    rows_per_page = 22
    total_pages = max(1, (len(display_rows) + rows_per_page - 1) // rows_per_page)

    page_obj_ids = []
    next_id = 5
    page_contents = []

    for p_idx in range(total_pages):
        page_id = next_id
        content_id = next_id + 1
        next_id += 2

        page_obj_ids.append(page_id)
        p_rows = display_rows[p_idx * rows_per_page : (p_idx + 1) * rows_per_page]

        ops = []
        # Header banner (Dark Navy #0F172A)
        ops.append('0.06 0.09 0.16 rg')
        ops.append(f'{margin} 530 {page_w - 2 * margin} 40 re f')

        # Title
        ops.append('1 1 1 rg')
        ops.append('BT /F1 13 Tf')
        ops.append(f'{margin + 12} 550 Td')
        ops.append(f'({clean_pdf_str(title)}) Tj ET')

        # Subtitle
        ops.append('0.7 0.8 0.9 rg')
        ops.append('BT /F2 8 Tf')
        ops.append(f'{margin + 12} 538 Td')
        ops.append(f'({clean_pdf_str(subtitle)} | Sahifa {p_idx + 1} / {total_pages}) Tj ET')

        # Table Header (Emerald Blue #0284C7)
        y = 512
        ops.append('0.01 0.52 0.78 rg')
        ops.append(f'{margin} {y - 18} {page_w - 2 * margin} 18 re f')

        ops.append('1 1 1 rg')
        ops.append('BT /F1 8 Tf')
        for c_idx, h in enumerate(display_headers):
            x = margin + c_idx * col_w + 4
            max_chars = int(col_w / 6)
            ops.append(f'{x} {y - 13} Td ({clean_pdf_str(h)[:max_chars]}) Tj')
            ops.append(f'{-x} {-y + 13} Td')
        ops.append('ET')

        y -= 18
        # Table Rows
        for r_idx, row in enumerate(p_rows):
            bg = '0.96 0.97 0.98 rg' if r_idx % 2 == 0 else '1 1 1 rg'
            ops.append(bg)
            ops.append(f'{margin} {y - 16} {page_w - 2 * margin} 16 re f')

            # Thin row border
            ops.append('0.85 0.88 0.92 RG 0.4 w')
            ops.append(f'{margin} {y - 16} {page_w - 2 * margin} 16 re S')

            ops.append('0.1 0.1 0.1 rg')
            ops.append('BT /F2 7 Tf')
            for c_idx, val in enumerate(row):
                x = margin + c_idx * col_w + 4
                max_chars = int(col_w / 4.8)
                v_clean = clean_pdf_str(val)[:max_chars]
                ops.append(f'{x} {y - 12} Td ({v_clean}) Tj')
                ops.append(f'{-x} {-y + 12} Td')
            ops.append('ET')
            y -= 16

        # Footer
        ops.append('0.4 0.4 0.4 rg')
        ops.append('BT /F2 7 Tf')
        ops.append(f'{margin} 18 Td')
        ops.append(f'(SOFTY PLATFORMA -- tender.softy.uz -- Yaratildi: {datetime.now().strftime("%Y-%m-%d %H:%M")}) Tj ET')

        content_stream = '\n'.join(ops).encode('latin-1', 'replace')
        page_contents.append((page_id, content_id, content_stream))

    out.write(b'%PDF-1.4\n')
    xref = {}

    xref[1] = out.tell()
    out.write(b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n')

    kids_str = ' '.join(f'{pid} 0 R' for pid in page_obj_ids)
    xref[2] = out.tell()
    out.write(f'2 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {total_pages} >>\nendobj\n'.encode('latin-1'))

    xref[3] = out.tell()
    out.write(b'3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n')

    xref[4] = out.tell()
    out.write(b'4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n')

    for page_id, content_id, stream_bytes in page_contents:
        xref[page_id] = out.tell()
        out.write(f'{page_id} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w} {page_h}] /Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>\nendobj\n'.encode('latin-1'))

        xref[content_id] = out.tell()
        out.write(f'{content_id} 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n'.encode('latin-1'))
        out.write(stream_bytes)
        out.write(b'\nendstream\nendobj\n')

    xref_start = out.tell()
    out.write(f'xref\n0 {next_id}\n'.encode('latin-1'))
    out.write(b'0000000000 65535 f \n')
    for i in range(1, next_id):
        out.write(f'{xref[i]:010d} 00000 n \n'.encode('latin-1'))

    out.write(f'trailer\n<< /Size {next_id} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n'.encode('latin-1'))
    return out.getvalue()

# ─────────────────────────────────────────────────────────────
# 3. Asosiy Eksport Xizmati
# ─────────────────────────────────────────────────────────────
def export_data(filters: Dict[str, Any], format_type: str = "xlsx") -> Tuple[Union[bytes, str], str, str]:
    """
    Filtrlangan ma'lumotlarni Excel (.xlsx), PDF (.pdf) yoki CSV shaklida eksport qilish.
    Qaytaradi: (fayl_baytlari_yoki_matni, media_type, fayl_nomi)
    """
    view_mode = filters.get("view_mode", "lots")
    fmt = (format_type or filters.get("format") or "xlsx").lower()

    sql, params, _ = build_search_filter_query(
        view_mode=view_mode,
        query_str=filters.get("query"),
        platforms=filters.get("platforms"),
        procurement_type=filters.get("procurement_type"),
        official_status=filters.get("official_status"),
        brand=filters.get("brand"),
        product_family=filters.get("product_family"),
        buyer_inn_or_name=filters.get("buyer"),
        supplier_inn_or_name=filters.get("supplier"),
        region=filters.get("region"),
        min_price=filters.get("min_price"),
        max_price=filters.get("max_price"),
        has_contract=filters.get("has_contract"),
        expiry_known=filters.get("expiry_known"),
        verification_status=filters.get("verification_status"),
        assigned_staff_id=filters.get("assigned_staff_id"),
        crm_status=filters.get("crm_status"),
        date_field=filters.get("date_field", "announcement_date"),
        date_from=filters.get("date_from"),
        date_to=filters.get("date_to"),
        quick_period=filters.get("quick_period"),
        include_missing_dates=filters.get("include_missing_dates", False),
        sort_by=filters.get("sort_by", "announcement_date"),
        sort_desc=filters.get("sort_desc", True),
        limit=10000,
        offset=0
    )

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]

    now_str = datetime.now().strftime('%Y%m%d_%H%M%S')

    if view_mode == "lots":
        headers = [
            "Lot raqami", "Lot nomi", "Platforma", "Xarid turi", "Holati",
            "E'lon sanasi", "Shartnoma sanasi", "Litsenziya tugash sanasi",
            "Summa (so'm)", "Buyurtmachi", "Buyurtmachi STIR", "Buyurtmachi telefoni",
            "Yetkazib beruvchi / G'olib", "Shartnoma havolasi", "Mas'ul xodim", "CRM holati"
        ]
        data_rows = []
        for r in rows:
            data_rows.append([
                r.get("lot_number") or "",
                r.get("title") or "",
                r.get("platform_name") or r.get("platform_id") or "",
                r.get("procurement_type") or "",
                r.get("official_status") or "",
                r.get("announcement_date") or "",
                r.get("contract_date") or "",
                r.get("license_end_date") or "Noma'lum",
                r.get("final_price") or 0.0,
                r.get("buyer_name") or "",
                r.get("buyer_inn") or "",
                r.get("buyer_phone") or "",
                r.get("winner_name") or r.get("supplier_name") or "",
                r.get("contract_url") or r.get("source_url") or "",
                r.get("assigned_staff_name") or "Biriktirilmagan",
                r.get("crm_status") or "Yangi"
            ])
        base_name = f"softy_lotlar_{now_str}"
        sheet_title = "Xarid Lotlari"

    elif view_mode == "companies":
        headers = [
            "STIR", "Korxona nomi", "Telefon", "E-pochta", "Hudud", "Manzil",
            "Dalil holati", "Xaridlar soni", "Tasdiqlangan shartnomalar",
            "Birinchi xarid", "Oxirgi xarid", "Yetkazib beruvchilar",
            "Yaqin litsenziya tugash sanasi", "Mas'ul xodim", "CRM holati", "Keyingi vazifa"
        ]
        data_rows = []
        for r in rows:
            data_rows.append([
                r.get("inn") or "",
                r.get("name") or "",
                r.get("phone") or "",
                r.get("email") or "",
                r.get("region") or "",
                r.get("legal_address") or "",
                "Tasdiqlangan xaridor" if r.get("proof_status") == "VERIFIED_BUYER" else "Xarid e'lon qilgan",
                r.get("distinct_lots_count") or 0,
                r.get("verified_contracts_count") or 0,
                r.get("first_purchase_date") or "",
                r.get("latest_purchase_date") or "",
                r.get("suppliers_list") or "",
                r.get("nearest_license_expiry") or "Noma'lum",
                r.get("assigned_staff_name") or "Biriktirilmagan",
                r.get("crm_status") or "Yangi",
                r.get("next_task_text") or ""
            ])
        base_name = f"softy_korxonalar_{now_str}"
        sheet_title = "Xarid Qilgan Korxonalar"

    else: # contracts
        headers = [
            "Shartnoma raqami", "Mahsulot", "Brend", "Oila", "Miqdor",
            "Birlik narxi", "Jami summa", "Buyurtmachi", "STIR",
            "Yetkazib beruvchi", "Shartnoma sanasi", "Litsenziya muddati", "Havola"
        ]
        data_rows = []
        for r in rows:
            data_rows.append([
                r.get("contract_number") or r.get("lot_number") or "",
                r.get("product_name") or "",
                r.get("brand") or "",
                r.get("product_family") or "",
                r.get("quantity") or 1,
                r.get("unit_price") or 0.0,
                r.get("total_price") or r.get("contract_amount") or 0.0,
                r.get("buyer_name") or "",
                r.get("buyer_inn") or "",
                r.get("supplier_name") or "",
                r.get("contract_date") or "",
                r.get("license_end_date") or "Noma'lum",
                r.get("contract_url") or ""
            ])
        base_name = f"softy_shartnomalar_{now_str}"
        sheet_title = "Shartnomalar va Mahsulotlar"

    # FORMAT BO'YICHA YUKLASH
    if fmt == "xlsx":
        content = generate_xlsx(sheet_title, headers, data_rows)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{base_name}.xlsx"
        return content, media_type, filename

    elif fmt == "pdf":
        title = f"SOFTY PLATFORMA -- {sheet_title.upper()} HISOBOTI"
        subtitle = f"Davr: 2024-01-01 dan hozirgacha | Jami: {len(data_rows)} ta yozuv"
        content = generate_pdf(title, subtitle, headers, data_rows)
        media_type = "application/pdf"
        filename = f"{base_name}.pdf"
        return content, media_type, filename

    else: # CSV format fallback
        output = io.StringIO()
        output.write('\ufeff') # UTF-8 BOM for Excel compatibility
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(data_rows)
        media_type = "text/csv; charset=utf-8"
        filename = f"{base_name}.csv"
        return output.getvalue().encode('utf-8'), media_type, filename
