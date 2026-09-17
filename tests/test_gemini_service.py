import unittest
from app.gemini_service import analyze_lot_with_gemini, get_gemini_api_key, set_gemini_api_key

class TestGeminiService(unittest.TestCase):
    def test_analyze_lot_heuristic(self):
        # Lot 6471358 is AutoCAD LT
        res = analyze_lot_with_gemini("6471358")
        self.assertNotIn("error", res)
        self.assertTrue(res.get("is_it"))
        self.assertIn("CAD", res.get("it_category"))
        self.assertEqual(res.get("verdict"), "QATNASHISH TAVSIYA ETILADI")
        self.assertGreaterEqual(res.get("relevance_score"), 90)
        self.assertIn("pricing_strategy", res)
        self.assertTrue(len(res.get("hidden_risks", [])) >= 1)
        self.assertTrue(len(res.get("technical_tips", [])) >= 1)

    def test_save_and_get_api_key(self):
        ok = set_gemini_api_key("test_dummy_key_12345")
        self.assertTrue(ok)
        key = get_gemini_api_key()
        self.assertEqual(key, "test_dummy_key_12345")
        # cleanup
        set_gemini_api_key("")

if __name__ == "__main__":
    unittest.main()
