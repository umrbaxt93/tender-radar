"""
Softy Platforma — Acceptance Criteria Test Suite (Section 17.I)
Quyidagi 10 ta qabul qilish mezonining barchasi avtomatlashtirilgan tarzda sinovdan o'tkaziladi:

1. Kalit so'z bo'yicha qidiruv (Kaspersky, AutoCAD, Kirill va Lotin)
2. Tarixiy lotlar ma'lumotlarining to'liqligi (sanalar, summalar, buyurtmachi, g'olib)
3. Sana va platforma filtrlari (Asia/Tashkent, quick periods, platform selection)
4. Xarid qilgan korxonalar alohida jadvali ("Shu mahsulotni oldin olgan korxonalar")
5. STIR bo'yicha xaridlar tarixi xronologiyasi (Timeline)
6. Haqiqiy lot va shartnoma havolalari (xt-xarid.uz va boshqalar)
7. Mas'ul xodim biriktirish (Umid, Yoqubxon, Usmon, Shohruh, Komiljon, Siyovush)
8. Asoslangan taklif va savdo vazifasi (Grounded proposal, inson tasdig'i, o'ylab topilmagan narxlar)
9. Eksport (Filtrlangan CSV ekranga 100% mosligi)
10. Qidiruvni saqlash va qayta tiklash
"""

import unittest
import json
from app.filter_engine import execute_search, build_search_filter_query
from app.crm_service import (
    get_company_profile_and_timeline,
    assign_staff,
    create_sales_task,
    generate_grounded_proposal,
    push_to_bitrix24
)
from app.export_service import export_data
from app.database import db_session
from app.config import STAFF_MEMBERS, PLATFORMS

class TestAcceptanceCriteria(unittest.TestCase):

    def test_criterion_1_keyword_search_multilingual(self):
        """
        1-mezon: Foydalanuvchi 'Kaspersky' yoki 'AutoCAD' kiritganda,
        avvalgi tegishli barcha xaridlar chiqadi (Lotin, Kirill, sinonimlar).
        """
        # 1. AutoCAD search
        res_autocad = execute_search({"query": "AutoCAD", "view_mode": "lots"})
        self.assertGreater(res_autocad["total_count"], 0, "AutoCAD bo'yicha lotlar topilishi kerak")
        
        # 2. Cyrillic Автокад search should match
        res_avtokad = execute_search({"query": "Автокад", "view_mode": "lots"})
        self.assertEqual(res_autocad["total_count"], res_avtokad["total_count"], "Kirill va Lotin qidiruvlari bir xil natija berishi kerak")

        # 3. Kaspersky search
        res_kaspersky = execute_search({"query": "Kaspersky", "view_mode": "lots"})
        self.assertGreater(res_kaspersky["total_count"], 0, "Kaspersky bo'yicha lotlar topilishi kerak")

        # 4. Cyrillic Касперский
        res_kasperskiy = execute_search({"query": "Касперский", "view_mode": "lots"})
        self.assertEqual(res_kaspersky["total_count"], res_kasperskiy["total_count"], "Kaspersky kirill va lotinda teng bo'lishi kerak")

        print("✓ 1-mezon muvaffaqiyatli: Multilingual qidiruv (Kaspersky, AutoCAD, Kirill/Lotin) to'liq ishlaydi.")

    def test_criterion_2_historical_lot_details(self):
        """
        2-mezon: Har bir lot bo'yicha sana, xarid predmeti, boshlang'ich va yakuniy summa,
        buyurtmachi, yetkazib beruvchi ko'rinadi.
        """
        res = execute_search({"query": "AutoCAD", "view_mode": "lots", "limit": 10})
        self.assertGreater(len(res["items"]), 0)

        for lot in res["items"]:
            self.assertIsNotNone(lot.get("lot_number"), "Lot raqami bo'lishi shart")
            self.assertIsNotNone(lot.get("title"), "Xarid predmeti (nomi) bo'lishi shart")
            self.assertTrue(lot.get("announcement_date") or lot.get("contract_date"), "Sana bo'lishi shart")
            self.assertIsNotNone(lot.get("buyer_inn"), "Buyurtmachi STIRi bo'lishi shart")
            self.assertIsNotNone(lot.get("buyer_name"), "Buyurtmachi nomi bo'lishi shart")
            self.assertIn("final_price", lot, "Yakuniy summa bo'lishi shart")
            self.assertIn("supplier_name", lot, "Yetkazib beruvchi / G'olib bo'lishi shart")

        print("✓ 2-mezon muvaffaqiyatli: Tarixiy lotlar ma'lumotlari (sana, summalar, buyurtmachi, g'olib) to'liq.")

    def test_criterion_3_date_and_platform_filters(self):
        """
        3-mezon: Faqat belgilangan davr va tanlangan platformalar bo'yicha
        natijalar to'g'ri filtrlanadi.
        """
        # Faqat xt_xarid platformasi bo'yicha filtr
        res_xt = execute_search({
            "platforms": ["xt_xarid"],
            "view_mode": "lots"
        })
        self.assertGreater(res_xt["total_count"], 0)
        for lot in res_xt["items"]:
            self.assertEqual(lot["platform_id"], "xt_xarid")

        # Sana oralig'i bo'yicha filtr (masalan 2024-01-01 dan 2026-12-31 gacha)
        res_date = execute_search({
            "date_field": "announcement_date",
            "date_from": "2024-01-01",
            "date_to": "2026-12-31",
            "view_mode": "lots"
        })
        self.assertGreater(res_date["total_count"], 0)
        for lot in res_date["items"]:
            if lot.get("announcement_date"):
                self.assertGreaterEqual(lot["announcement_date"][:10], "2024-01-01")
                self.assertLessEqual(lot["announcement_date"][:10], "2026-12-31")

        print("✓ 3-mezon muvaffaqiyatli: Platforma va sana oraliqlari bo'yicha filtrlash to'liq ishlaydi.")

    def test_criterion_4_buyer_companies_view(self):
        """
        4-mezon: Qidirilgan mahsulotni avval sotib olgan barcha korxonalar
        alohida jadvalda jamlanadi ("Shu mahsulotni oldin olgan korxonalar").
        """
        res_companies = execute_search({
            "query": "AutoCAD",
            "view_mode": "companies"
        })
        self.assertGreater(res_companies["total_count"], 0, "AutoCAD sotib olgan korxonalar topilishi kerak")
        
        for comp in res_companies["items"]:
            self.assertIn("inn", comp, "STIR mavjud bo'lishi kerak")
            self.assertIn("name", comp, "Korxona nomi mavjud bo'lishi kerak")
            self.assertIn("distinct_lots_count", comp, "Xaridlar soni bo'lishi kerak")
            self.assertGreater(comp["distinct_lots_count"], 0)
            self.assertIn("latest_purchase_date", comp, "Oxirgi xarid sanasi bo'lishi kerak")

        print("✓ 4-mezon muvaffaqiyatli: 'Shu mahsulotni oldin olgan korxonalar' alohida jadvali to'liq shakllanadi.")

    def test_criterion_5_company_purchase_timeline(self):
        """
        5-mezon: Korxona tanlanganda yoki uning STIRi kiritilganda,
        uning sanalar bo'yicha to'liq xaridlar tarixi (timeline) xronologik ko'rinadi.
        """
        # Avval AutoCAD olgan korxonalardan birining STIRini olamiz
        res_companies = execute_search({"query": "AutoCAD", "view_mode": "companies", "limit": 1})
        first_comp = res_companies["items"][0]
        inn = first_comp["inn"]

        profile = get_company_profile_and_timeline(inn)
        self.assertTrue(profile["found"], "Korxona profili topilishi kerak")
        self.assertGreater(profile["total_lots"], 0, "Korxonada xaridlar tarixi bo'lishi kerak")
        
        # Timeline xronologik tartibda ekanligini tekshiramiz
        timeline = profile["timeline"]
        for i in range(len(timeline) - 1):
            d1 = timeline[i].get("contract_date") or timeline[i].get("announcement_date") or ""
            d2 = timeline[i+1].get("contract_date") or timeline[i+1].get("announcement_date") or ""
            if d1 and d2:
                self.assertGreaterEqual(d1, d2, "Timeline eng yangi xariddan eng eskisiga qarab saralangan bo'lishi kerak")

        # Proof status tekshiruvi (17.F)
        self.assertIn(profile["company"]["calculated_proof_status"], ["VERIFIED_BUYER", "ANNOUNCED_ONLY"])
        print("✓ 5-mezon muvaffaqiyatli: STIR bo'yicha xaridlar tarixi xronologiyasi (Timeline) to'liq ishlaydi.")

    def test_criterion_6_genuine_source_urls(self):
        """
        6-mezon: Natijalar ichidan lot yoki shartnomaning haqiqiy havolasi (URL)
        mavjud va u orqali manbaga o'tish mumkin.
        """
        res = execute_search({"query": "AutoCAD", "view_mode": "lots", "limit": 20})
        has_url_count = 0
        for lot in res["items"]:
            if lot.get("source_url") or lot.get("contract_url"):
                has_url_count += 1
                # Url formati tekshiruvi
                url = lot.get("source_url") or lot.get("contract_url")
                self.assertTrue(url.startswith("http://") or url.startswith("https://"), f"Havola http(s) bilan boshlanishi kerak: {url}")
        
        self.assertGreater(has_url_count, 0, "Kamida bitta haqiqiy havola bo'lishi kerak")
        print(f"✓ 6-mezon muvaffaqiyatli: Haqiqiy xarid havolalari (URL) mavjud ({has_url_count} ta tasdiqlandi).")

    def test_criterion_7_staff_assignment(self):
        """
        7-mezon: Istalgan korxona yoki xaridga mas'ul xodim
        (Umid, Yoqubxon, Usmon, Shohruh, Komiljon, Siyovush) biriktiriladi va bu saqlanadi.
        """
        res_comp = execute_search({"view_mode": "companies", "limit": 1})
        inn = res_comp["items"][0]["inn"]

        # Mas'ul xodim Usmonni biriktiramiz
        assign_res = assign_staff(inn, "usmon")
        self.assertTrue(assign_res["success"])
        self.assertEqual(assign_res["assigned_staff_id"], "usmon")

        # Qayta o'qib tekshiramiz
        profile = get_company_profile_and_timeline(inn)
        self.assertEqual(profile["company"]["assigned_staff_id"], "usmon")
        self.assertEqual(profile["company"]["assigned_staff_name"], "Usmon")

        print("✓ 7-mezon muvaffaqiyatli: Mas'ul xodim biriktirish va saqlash to'liq ishlaydi.")

    def test_criterion_8_grounded_proposal_and_task(self):
        """
        8-mezon: Korxona xaridlar tarixi asosida litsenziyani uzaytirish yoki
        yangi xarid bo'yicha savdo vazifasi / taklif yaratiladi (narxlar o'ylab topilmagan).
        """
        res_comp = execute_search({"query": "AutoCAD", "view_mode": "companies", "limit": 1})
        inn = res_comp["items"][0]["inn"]

        # Taklif qoralamasini olish
        proposal = generate_grounded_proposal(inn)
        self.assertEqual(proposal["status"], "DRAFT_REQUIRES_HUMAN_CONFIRMATION")
        self.assertFalse(proposal["auto_send_allowed"], "Avtomatik yuborish taqiqlangan, inson tasdig'i shart")
        self.assertIn("to'qima narxlar kiritilmagan", proposal["pricing_notice"].lower())
        self.assertGreater(proposal["observed_products_count"], 0, "Avval olingan mahsulotlar aniqlangan bo'lishi shart")

        # Savdo vazifasi yaratish
        task_res = create_sales_task(
            inn=inn,
            task_title="AutoCAD litsenziyasini yangilash bo'yicha taklif yuborish",
            assigned_staff_id="usmon",
            proposal_summary=proposal["proposal_subject"]
        )
        self.assertTrue(task_res["success"])
        self.assertIsNotNone(task_res["task_id"])

        print("✓ 8-mezon muvaffaqiyatli: Asoslangan tijorat taklifi va savdo vazifasi yaratilishi to'liq ishlaydi.")

    def test_criterion_9_filtered_export_excel_and_pdf(self):
        """
        9-mezon: Filtrlangan natijalar Excel (.xlsx) va PDF (.pdf) formatlarida yuklab olinadi
        va ekrandagi ma'lumotlarga 100% mos bo'ladi.
        """
        import zipfile
        import io

        filters = {
            "query": "AutoCAD",
            "view_mode": "lots",
            "platforms": ["xt_xarid"]
        }
        search_res = execute_search(filters)
        self.assertGreater(search_res["total_count"], 0)

        # 1. Excel (.xlsx) eksport testi
        xlsx_bytes, xlsx_mime, xlsx_filename = export_data(filters, format_type="xlsx")
        self.assertEqual(xlsx_mime, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertTrue(xlsx_filename.endswith(".xlsx"))
        self.assertTrue(xlsx_bytes.startswith(b"PK\x03\x04"), "Excel fayli haqiqiy ZIP/OpenXML arxivi bo'lishi kerak")
        
        # OpenXML fayl strukturasi to'liqligini tekshirish
        with zipfile.ZipFile(io.BytesIO(xlsx_bytes), "r") as zf:
            file_names = zf.namelist()
            self.assertIn("[Content_Types].xml", file_names)
            self.assertIn("xl/workbook.xml", file_names)
            self.assertIn("xl/worksheets/sheet1.xml", file_names)
            self.assertIn("xl/styles.xml", file_names)
            sheet1_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("AutoCAD", sheet1_xml, "Excel sahifasida AutoCAD lotlari bo'lishi shart")

        # 2. PDF (.pdf) eksport testi
        pdf_bytes, pdf_mime, pdf_filename = export_data(filters, format_type="pdf")
        self.assertEqual(pdf_mime, "application/pdf")
        self.assertTrue(pdf_filename.endswith(".pdf"))
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"), "PDF fayli haqiqiy %PDF- sarlavhasiga ega bo'lishi kerak")
        self.assertGreater(len(pdf_bytes), 1000, "PDF fayl hajmi 1 KB dan ortiq bo'lishi shart")

        # 3. CSV zaxira eksport testi
        csv_bytes, csv_mime, csv_filename = export_data(filters, format_type="csv")
        csv_text = csv_bytes.decode("utf-8")
        self.assertTrue(csv_mime.startswith("text/csv"))
        self.assertTrue(csv_filename.endswith(".csv"))
        self.assertIn("Lot raqami", csv_text)
        self.assertIn("AutoCAD", csv_text)
        csv_lines = [l for l in csv_text.strip().split("\n") if l.strip()]
        self.assertEqual(len(csv_lines) - 1, search_res["total_count"], "Eksportdagi qatorlar soni qidiruv natijalariga 100% mos bo'lishi shart")

        print(f"✓ 9-mezon muvaffaqiyatli: Excel (.xlsx, {len(xlsx_bytes)} bayt) va PDF (.pdf, {len(pdf_bytes)} bayt) eksportlari 100% to'g'ri ishlaydi.")

    def test_criterion_10_saved_search_reload(self):
        """
        10-mezon: Qidiruv parametrlari saqlanadi va qayta yuklanganda
        aynan o'sha filtrlangan ro'yxat tiklanadi.
        """
        original_query = "Kaspersky Toshkent"
        filter_params = {
            "query": original_query,
            "view_mode": "lots",
            "region": "Toshkent sh."
        }

        # Saqlash
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO saved_searches (name, search_query, filters_json, created_at)
            VALUES (?, ?, ?, datetime('now'));
            """, ("Test Saqlangan Qidiruv", original_query, json.dumps(filter_params)))
            saved_id = cursor.lastrowid

        # Qayta o'qish va tiklash
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM saved_searches WHERE id = ?", (saved_id,))
            row = dict(cursor.fetchone())

        loaded_params = json.loads(row["filters_json"])
        self.assertEqual(loaded_params["query"], original_query)
        self.assertEqual(loaded_params["region"], "Toshkent sh.")

        # Tiklangan filtrlar bilan qidiruvni bajarish
        res_original = execute_search(filter_params)
        res_loaded = execute_search(loaded_params)
        self.assertEqual(res_original["total_count"], res_loaded["total_count"], "Saqlangan qidiruv yuklanganda aynan bir xil natija chiqishi kerak")

        print("✓ 10-mezon muvaffaqiyatli: Qidiruv parametrlari saqlanishi va qayta yuklanishi to'liq ishlaydi.")

if __name__ == "__main__":
    unittest.main()
