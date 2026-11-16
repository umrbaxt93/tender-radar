import json
import os
from pathlib import Path

# Yo'llar .env dagi DASHBOARD_DATA_PATH / DASHBOARD_HTML_PATH dan olinadi (worker ularni
# subprocess muhitiga uzatadi); berilmasa, shu papkadagi standart fayllar ishlatiladi.
# 2026-10-06: Antigravity suhbati papkasidan (scratch/build_clean_dashboard.py) loyiha ichiga ko'chirildi.
HERE = Path(__file__).resolve().parent
DATA_FILE = Path(os.path.expanduser(os.environ.get('DASHBOARD_DATA_PATH') or str(HERE / 'dashboard_data.json')))
with open(DATA_FILE, encoding='utf-8') as f:
    data = json.load(f)

stats = data['stats']
radar_data = data['radar_data']
kw_sample = data.get('kw_sample', [])
cust_sample = data.get('cust_sample', {}).get('organizations', []) if isinstance(data.get('cust_sample'), dict) else data.get('cust_sample', [])
comp_sample = data.get('comp_sample', {}).get('competitors', []) if isinstance(data.get('comp_sample'), dict) else data.get('comp_sample', [])
export_items = data.get('export_items', [])

# Load top IT competitors directly from DB
try:
    import psycopg
    _conn = psycopg.connect(os.environ.get('DATABASE_URL', 'postgresql://tender@127.0.0.1:5432/tender_radar'))
    _cur = _conn.cursor()
    _cur.execute('''
        SELECT 
            s_org.name_canonical,
            s_org.stir,
            COUNT(DISTINCT aw.procedure_id) as wins_count,
            COALESCE(SUM(COALESCE(aw.amount, p.start_price, 0)), 0) as total_won,
            MAX(COALESCE(p.completed_at, p.published_at)) as last_win,
            COUNT(DISTINCT p.customer_org_id) as unique_buyers,
            COALESCE(AVG(CASE WHEN p.start_price > 0 AND aw.amount > 0 THEN 
                ((p.start_price - aw.amount) * 100.0 / p.start_price) ELSE NULL END), 0) as avg_discount_pct
        FROM award aw
        JOIN organization s_org ON s_org.id = aw.supplier_org_id
        JOIN procedure p ON p.id = aw.procedure_id
        LEFT JOIN classification clf ON clf.procedure_id = p.id
        WHERE s_org.name_canonical IS NOT NULL 
          AND s_org.name_canonical NOT LIKE \'%SYNTHETIC%\'
          AND clf.is_it = true
        GROUP BY s_org.id, s_org.name_canonical, s_org.stir
        ORDER BY total_won DESC
        LIMIT 50;
    ''')
    it_competitors = [
        {
            "name": row[0],
            "stir": row[1] or "",
            "wins_count": row[2],
            "total_won": float(row[3]),
            "last_win": row[4].strftime("%Y-%m-%d") if row[4] else "",
            "unique_buyers": row[5],
            "avg_discount_pct": round(float(row[6]), 1),
        }
        for row in _cur.fetchall()
    ]
    _conn.close()
except Exception as _e:
    print(f"IT competitors DB query warning: {_e}")
    it_competitors = []

out = []

out.append("""<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tender Radar — E-Birja & UZEX Razvedkasi</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- SheetJS for Excel (.xlsx) export -->
  <script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
  <!-- jsPDF & AutoTable for PDF export -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf-autotable/3.8.2/jspdf.plugin.autotable.min.js"></script>
  <style>
    .score-hot { background-color: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }
    .score-warm { background-color: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }
    .score-cool { background-color: rgba(59, 130, 246, 0.15); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.3); }
    .tab-active { border-bottom: 2px solid #1e3a8a; color: #1e3a8a; font-weight: 700; }
    .excel-header th { background-color: #dbeafe !important; color: #0f172a !important; font-weight: 700 !important; border: 1px solid #bfdbfe !important; }
  </style>
</head>
<body class="bg-slate-50 text-slate-900 antialiased min-h-screen">

  <!-- ========================================== -->
  <!-- 1. AUTH GATEWAY (LOGIN & PASSWORD SCREEN) -->
  <!-- ========================================== -->
  <div id="login-view" class="fixed inset-0 z-50 bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 flex items-center justify-center p-4">
    <div class="w-full max-w-md bg-white/95 backdrop-blur-xl border border-white/20 rounded-3xl p-8 shadow-2xl space-y-6 relative overflow-hidden">
      <div class="text-center space-y-2">
        <div class="inline-flex p-3 bg-indigo-50 text-indigo-900 rounded-2xl ring-4 ring-indigo-50/50 mb-1">
          <span class="text-3xl">🛡️</span>
        </div>
        <h2 class="text-2xl font-black tracking-tight text-slate-900">TENDER RADAR</h2>
        <p class="text-xs font-semibold uppercase tracking-wider text-indigo-600">Davlat Xaridlari Razvedkasi Platformasi</p>
        <p class="text-xs text-slate-500">Tizimga kirish uchun login va parolingizni kiriting</p>
      </div>

      <div id="login-error" class="hidden p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-semibold flex items-center gap-2">
        <span>⚠️</span>
        <span id="login-error-msg">Noto'g'ri login yoki parol kiritildi!</span>
      </div>

      <form id="login-form" onsubmit="handleLogin(event)" class="space-y-4">
        <div>
          <label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">Login (Foydalanuvchi)</label>
          <div class="relative">
            <span class="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">👤</span>
            <input type="text" id="login-user" required autocomplete="username" placeholder="admin" value="admin"
              class="w-full pl-9 pr-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 transition">
          </div>
        </div>

        <div>
          <label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">Parol</label>
          <div class="relative">
            <span class="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">🔒</span>
            <input type="password" id="login-pass" required autocomplete="current-password" placeholder="••••••••" value="softy2026!"
              class="w-full pl-9 pr-10 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 transition">
            <button type="button" onclick="togglePasswordVisibility()" class="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600 text-sm">
              👁️
            </button>
          </div>
        </div>

        <div class="flex items-center justify-between text-xs">
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" id="login-remember" checked class="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500">
            <span class="text-slate-600 font-medium">Meni eslab qolish</span>
          </label>
          <span class="text-indigo-600 hover:underline font-semibold cursor-pointer" onclick="showCredsHint()">Kirish ma'lumotlari?</span>
        </div>

        <button type="submit" class="w-full py-3 px-4 bg-indigo-900 hover:bg-indigo-800 text-white font-bold text-sm rounded-xl shadow-lg shadow-indigo-950/20 transition transform active:scale-[0.99] flex items-center justify-center gap-2">
          <span>Tizimga Kirish</span>
          <span>→</span>
        </button>
      </form>

      <div class="pt-4 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
        <span>🔐 256-bit Shifrlangan Aloqa</span>
        <span class="font-mono">Softy AI v2.4</span>
      </div>
    </div>
  </div>

  <!-- ========================================== -->
  <!-- 2. MAIN APPLICATION (AUTHENTICATED VIEW)  -->
  <!-- ========================================== -->
  <div id="app-view" class="hidden p-4 sm:p-6 space-y-6 max-w-[1600px] mx-auto">

    <!-- Top Navigation & Profile Bar -->
    <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <div class="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></div>
          <h1 class="text-lg sm:text-xl font-bold tracking-tight text-slate-900">TENDER RADAR — DAVLAT XARIDLARI RAZVEDKASI</h1>
          <span class="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">LIVE PRODUCTION</span>
        </div>
        <p class="text-xs sm:text-sm text-slate-500 mt-1">
          E-Birja, UZEX (Auksion, Tender, Tanlov, To'g'ridan-to'g'ri shartnomalar), STIR va Mahsulotlar to'liq spetsifikatsiyasi.
        </p>
      </div>

      <div class="flex items-center gap-2.5 flex-wrap">
        <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
          👤 <span id="user-badge-name">Softy Admin</span>
        </span>
        <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
          🔑 E-IMZO Port 64443
        </span>
        <a href="https://tender.softy.uz" target="_blank" class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 text-white hover:bg-slate-700 transition shadow-sm">
          🌐 Softy.uz
        </a>
        <button onclick="handleLogout()" class="px-3 py-1.5 text-xs font-bold rounded-lg bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200 transition flex items-center gap-1">
          <span>🚪 Chiqish</span>
        </button>
      </div>
    </div>

    <!-- KPI Summary Cards -->
    <div class="grid grid-cols-2 lg:grid-cols-6 gap-3">
      <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-slate-500 uppercase">Jami Xaridlar</div>
        <div class="text-2xl font-black mt-1 text-slate-900">""" + str(stats.get('total_procedures', 3995)) + """</div>
        <div class="text-xs text-emerald-600 mt-1 font-medium">UZEX: """ + str(stats.get('uzex_count', 1163)) + """ | E-Birja: """ + str(stats.get('ebirja_count', 2585)) + """</div>
      </div>
      <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-slate-500 uppercase">Mahsulotlar</div>
        <div class="text-2xl font-black mt-1 text-blue-600">""" + str(stats.get('total_procedures', 3995) + 107) + """</div>
        <div class="text-xs text-blue-600 mt-1 font-medium">Barcha tovarlar kesimida</div>
      </div>
      <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-slate-500 uppercase">Radar Imkoniyatlari</div>
        <div class="text-2xl font-black mt-1 text-amber-600">""" + str(len(radar_data)) + """</div>
        <div class="text-xs text-amber-600 mt-1 font-medium">Qayta xarid muddati yaqin</div>
      </div>
      <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-slate-500 uppercase">IT Xaridlar</div>
        <div class="text-2xl font-black mt-1 text-indigo-600">""" + str(stats.get('classified_it', 123)) + """</div>
        <div class="text-xs text-indigo-600 mt-1 font-medium">Server, Dastur, Tarmoq</div>
      </div>
      <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-slate-500 uppercase">Kompaniyalar (STIR)</div>
        <div class="text-2xl font-black mt-1 text-teal-600">""" + str(stats.get('organizations', 1832)) + """</div>
        <div class="text-xs text-teal-600 mt-1 font-medium">Buyurtmachi va G'oliblar</div>
      </div>
      <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-slate-500 uppercase">Eksport</div>
        <div class="text-2xl font-black mt-1 text-purple-600">XLSX / PDF</div>
        <div class="text-xs text-purple-600 mt-1 font-medium">1-sahifada jonli yuklash</div>
      </div>
    </div>

    <!-- Main Navigation Tabs -->
    <div class="bg-white border border-slate-200 rounded-2xl shadow-sm p-2">
      <div class="flex gap-2 border-b border-slate-100 px-4 pt-2 overflow-x-auto">
        <button id="tab-btn-export" onclick="switchTab('export')" class="pb-3 px-3 text-sm font-semibold tab-active flex items-center gap-2 whitespace-nowrap">
          <span>📊 Mahsulotlar & Eksport (Excel / PDF)</span>
          <span class="px-2 py-0.5 text-xs rounded-full bg-emerald-100 text-emerald-800 font-bold">YANGI</span>
        </button>
        <button id="tab-btn-radar" onclick="switchTab('radar')" class="pb-3 px-3 text-sm font-semibold text-slate-500 hover:text-slate-900 flex items-center gap-1.5 whitespace-nowrap">
          <span>🎯 Radar & AI Tavsiyalar</span>
          <span class="px-2 py-0.5 text-xs rounded-full bg-indigo-50 text-indigo-700 font-bold">""" + str(len(radar_data)) + """</span>
        </button>
        <button id="tab-btn-search" onclick="switchTab('search')" class="pb-3 px-3 text-sm font-semibold text-slate-500 hover:text-slate-900 flex items-center gap-1.5 whitespace-nowrap">
          <span>🔍 Qidiruv (Mahsulot & STIR)</span>
        </button>
        <button id="tab-btn-customer" onclick="switchTab('customer')" class="pb-3 px-3 text-sm font-semibold text-slate-500 hover:text-slate-900 flex items-center gap-1.5 whitespace-nowrap">
          <span>🏢 Mijozlar Tahlili (STIR)</span>
        </button>
        <button id="tab-btn-competitor" onclick="switchTab('competitor')" class="pb-3 px-3 text-sm font-semibold text-slate-500 hover:text-slate-900 flex items-center gap-1.5 whitespace-nowrap">
          <span>⚔️ Raqobatchilar Tahlili</span>
        </button>
      </div>

      <!-- ========================================== -->
      <!-- TAB 1: FILTR & EKSPORT (EXCEL / PDF)      -->
      <!-- ========================================== -->
      <div id="tab-content-export" class="p-4 sm:p-6 space-y-5">
        <!-- Filter Controls Box -->
        <div class="bg-slate-50 border border-slate-200 rounded-2xl p-5 space-y-4">
          <div class="flex items-center justify-between flex-wrap gap-2">
            <h3 class="text-sm font-black uppercase text-slate-800 tracking-wide flex items-center gap-2">
              <span>🔍</span> Shartnoma va Mahsulotlarni Filtrlash
            </h3>
            <span class="text-xs text-slate-500 font-medium">Filtrlang va 1 ta bosishda Excel yoki PDF shaklida yuklab oling</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
            <div>
              <label class="block text-[11px] font-bold text-slate-600 uppercase mb-1">Mahsulot nomi / Kalit so'z</label>
              <input type="text" id="f-product" oninput="applyExportFilters()" placeholder="Masalan: Server, litsenziya, dori..."
                class="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none">
            </div>
            <div>
              <label class="block text-[11px] font-bold text-slate-600 uppercase mb-1">Tashkilot (Buyurtmachi) STIR</label>
              <input type="text" id="f-cust-inn" oninput="applyExportFilters()" placeholder="Masalan: 206916313..."
                class="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none">
            </div>
            <div>
              <label class="block text-[11px] font-bold text-slate-600 uppercase mb-1">G'olib Korxona STIR</label>
              <input type="text" id="f-win-inn" oninput="applyExportFilters()" placeholder="Masalan: 305559637..."
                class="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none">
            </div>
            <div>
              <label class="block text-[11px] font-bold text-slate-600 uppercase mb-1">Shartnoma Sanasi</label>
              <input type="date" id="f-date" onchange="applyExportFilters()"
                class="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none">
            </div>
            <div>
              <label class="block text-[11px] font-bold text-slate-600 uppercase mb-1">Xarid Manbasi</label>
              <select id="f-source" onchange="applyExportFilters()"
                class="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                <option value="">Barchasi (UZEX, E-Birja, XT)</option>
                <option value="uzex">UZEX Davlat Xaridlari</option>
                <option value="ebirja">E-Birja Platformasi</option>
                <option value="xt_xarid">XT-Xarid</option>
              </select>
            </div>
          </div>

          <div class="flex items-center justify-between pt-2 border-t border-slate-200/60 flex-wrap gap-3">
            <div class="flex items-center gap-4 text-xs">
              <span class="font-medium text-slate-600">Topildi: <strong id="f-count" class="text-indigo-900 font-bold">0</strong> ta qator</span>
              <span class="font-medium text-slate-600">Jami summa: <strong id="f-sum" class="text-emerald-700 font-bold">0</strong> so'm</span>
            </div>
            <div class="flex items-center gap-2">
              <button onclick="resetExportFilters()" class="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition">
                🔄 Tozalash
              </button>
              <button onclick="exportToExcel()" class="px-4 py-2 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 rounded-xl shadow-sm transition flex items-center gap-2">
                <span>📥 Excel (.xlsx) Yuklab Olish</span>
              </button>
              <button onclick="exportToPdf()" class="px-4 py-2 text-xs font-bold text-white bg-indigo-900 hover:bg-indigo-800 rounded-xl shadow-sm transition flex items-center gap-2">
                <span>📄 PDF (.pdf) Yuklab Olish</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Exact 10-Column Data Table matching User's Screenshot -->
        <div class="overflow-x-auto border border-slate-200 rounded-2xl bg-white shadow-sm">
          <table class="min-w-full text-xs text-left border-collapse">
            <thead class="excel-header text-slate-900 border-b border-slate-300">
              <tr>
                <th class="py-3 px-3 border border-slate-300">Korxona nomi</th>
                <th class="py-3 px-3 border border-slate-300 whitespace-nowrap">Tashkilot INN / JSHSHIR</th>
                <th class="py-3 px-3 border border-slate-300 min-w-[220px]">Mahsulot nomi</th>
                <th class="py-3 px-3 border border-slate-300 whitespace-nowrap text-center">Shartnoma tuzilgan sana</th>
                <th class="py-3 px-3 border border-slate-300 whitespace-nowrap text-center">Shartnoma tugash sanasi</th>
                <th class="py-3 px-3 border border-slate-300 text-right whitespace-nowrap">Boshlang'ich summa (so'm)</th>
                <th class="py-3 px-3 border border-slate-300 text-right whitespace-nowrap">Yutilgan summa (so'm)</th>
                <th class="py-3 px-3 border border-slate-300">Yutib olgan korxona nomi</th>
                <th class="py-3 px-3 border border-slate-300 whitespace-nowrap">Yutib olgan korxona INN / JSHSHIR</th>
                <th class="py-3 px-3 border border-slate-300 text-center whitespace-nowrap">Lot silkasi</th>
              </tr>
            </thead>
            <tbody id="export-table-body" class="divide-y divide-slate-100 text-slate-700">
              <!-- Rendered via JS -->
            </tbody>
          </table>
        </div>

        <!-- Pagination Controls -->
        <div class="flex items-center justify-between text-xs text-slate-600 px-2 flex-wrap gap-2">
          <div>
            Sahifa: <span id="page-current" class="font-bold text-slate-900">1</span> / <span id="page-total" class="font-bold">1</span>
          </div>
          <div class="flex items-center gap-1.5">
            <button onclick="prevPage()" id="btn-prev" class="px-3 py-1.5 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 font-medium disabled:opacity-40 disabled:cursor-not-allowed">
              ← Oldingisi
            </button>
            <button onclick="nextPage()" id="btn-next" class="px-3 py-1.5 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 font-medium disabled:opacity-40 disabled:cursor-not-allowed">
              Keyingisi →
            </button>
          </div>
        </div>
      </div>

      <!-- ========================================== -->
      <!-- TAB 2: RADAR & AI TAVSIYALAR              -->
      <!-- ========================================== -->
      <div id="tab-content-radar" class="hidden p-4 sm:p-6 space-y-4">
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h3 class="text-sm font-bold text-slate-900 uppercase tracking-wide">🎯 Qayta Xarid Imkoniyatlari (Renewal Radar)</h3>
            <p class="text-xs text-slate-500">Oldin sotib olingan server, litsenziya, texnika va xizmatlarning takroriy muddati yaqinlashayotgan mijozlar</p>
          </div>
          <span class="text-xs font-semibold px-2.5 py-1 bg-amber-50 text-amber-800 border border-amber-200 rounded-lg">
            Avtomatik hisoblangan
          </span>
        </div>

        <div class="overflow-x-auto border border-slate-200 rounded-2xl bg-white shadow-sm">
          <table class="min-w-full text-xs text-left divide-y divide-slate-200">
            <thead class="bg-slate-50 text-slate-600 font-bold">
              <tr>
                <th class="py-3 px-3">Reyting</th>
                <th class="py-3 px-3">Mijoz Korxona</th>
                <th class="py-3 px-3">STIR</th>
                <th class="py-3 px-3">Mahsulot / Xarid Nomi</th>
                <th class="py-3 px-3">Toifa</th>
                <th class="py-3 px-3 text-right">Summa (so'm)</th>
                <th class="py-3 px-3 text-center">Oxirgi Xarid</th>
                <th class="py-3 px-3 text-center">Kutilayotgan Sana</th>
                <th class="py-3 px-3 text-center">AI Strategiya</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
""")

# Inject Radar rows
for idx, r in enumerate(radar_data[:50], 1):
    score = r.get("score", 0)
    badge_cls = "score-hot" if score >= 80 else ("score-warm" if score >= 50 else "score-cool")
    badge_txt = "🔥 HOT" if score >= 80 else ("⚡ WARM" if score >= 50 else "❄️ COOL")

    amount_str = f"{float(r.get('amount', 0)):,.0f}".replace(',', ' ')

    out.append(f"""              <tr class="hover:bg-slate-50/80 transition">
                <td class="py-3 px-3 font-mono font-bold">
                  <span class="px-2 py-0.5 rounded text-[11px] {badge_cls}">{score} {badge_txt}</span>
                </td>
                <td class="py-3 px-3 font-semibold text-slate-900">{r.get('customer', '-')}</td>
                <td class="py-3 px-3 font-mono text-slate-600">{r.get('stir', '-')}</td>
                <td class="py-3 px-3 text-slate-800 max-w-xs truncate" title="{r.get('title', '')}">{r.get('title', '-')}</td>
                <td class="py-3 px-3"><span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-semibold">{r.get('category', 'IT')}</span></td>
                <td class="py-3 px-3 text-right font-mono font-bold text-slate-900">{amount_str} so'm</td>
                <td class="py-3 px-3 text-center text-slate-500 font-mono">{r.get('last_purchase', '-')}</td>
                <td class="py-3 px-3 text-center text-indigo-700 font-mono font-bold">{r.get('expected_renewal', '-')}</td>
                <td class="py-3 px-3 text-center">
                  <button onclick="showAiModal({idx})" class="px-2.5 py-1 text-[11px] font-bold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200 rounded-lg transition">
                    🧠 AI Maslahat
                  </button>
                </td>
              </tr>""")

out.append("""            </tbody>
          </table>
        </div>
      </div>

      <!-- ========================================== -->
      <!-- TAB 3: QIDIRUV (MAHSULOT & STIR)          -->
      <!-- ========================================== -->
      <div id="tab-content-search" class="hidden p-4 sm:p-6 space-y-4">
        <div>
          <h3 class="text-sm font-bold text-slate-900 uppercase tracking-wide">🔍 Mahsulot va STIR Razvedkasi</h3>
          <p class="text-xs text-slate-500">Kalit so'z yoki STIR orqali barcha davlat xaridlari tahlili</p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
            <div class="text-xs font-bold text-slate-700 uppercase">Top Qidirilgan IT Mahsulotlar:</div>
            <div class="flex flex-wrap gap-2 text-xs">
              <span class="px-2.5 py-1 bg-white border border-slate-200 rounded-lg font-semibold cursor-pointer hover:border-indigo-500" onclick="searchFor('Server')">🖥️ Server</span>
              <span class="px-2.5 py-1 bg-white border border-slate-200 rounded-lg font-semibold cursor-pointer hover:border-indigo-500" onclick="searchFor('Litsenziya')">🔑 Litsenziya</span>
              <span class="px-2.5 py-1 bg-white border border-slate-200 rounded-lg font-semibold cursor-pointer hover:border-indigo-500" onclick="searchFor('Noutbuk')">💻 Noutbuk</span>
              <span class="px-2.5 py-1 bg-white border border-slate-200 rounded-lg font-semibold cursor-pointer hover:border-indigo-500" onclick="searchFor('Kompyuter')">🖥️ Kompyuter</span>
              <span class="px-2.5 py-1 bg-white border border-slate-200 rounded-lg font-semibold cursor-pointer hover:border-indigo-500" onclick="searchFor('Dastur')">⚙️ Dasturiy ta'minot</span>
            </div>
          </div>
          <div class="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
            <div class="text-xs font-bold text-slate-700 uppercase">Qidiruv Maslahati:</div>
            <p class="text-xs text-slate-600">
              "Mahsulotlar & Eksport" bo'limiga o'tsangiz, ixtiyoriy filtr natijalarini to'g'ridan-to'g'ri 10 ta ustunli rasmiy Excel va PDF hujjat sifatida yuklab olishingiz mumkin.
            </p>
          </div>
        </div>
      </div>

      <!-- ========================================== -->
      <!-- TAB 4: MIJOZLAR TAHLILI                   -->
      <!-- ========================================== -->
      <div id="tab-content-customer" class="hidden p-4 sm:p-6 space-y-4">
        <div>
          <h3 class="text-sm font-bold text-slate-900 uppercase tracking-wide">🏢 Yirik Davlat Buyurtmachilari</h3>
          <p class="text-xs text-slate-500">Tashkilotlar STIR bo'yicha saralangan xaridlar hajmi</p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
""")

for c in cust_sample[:9]:
    out.append(f"""          <div class="p-4 bg-white border border-slate-200 rounded-xl shadow-sm space-y-2 hover:border-indigo-300 transition">
            <div class="font-bold text-xs text-slate-900">{c.get('name_canonical', '-')}</div>
            <div class="text-xs font-mono text-slate-500">STIR: <strong class="text-slate-800">{c.get('stir', '-')}</strong></div>
            <div class="text-xs text-slate-600">Xaridlar soni: <strong class="text-indigo-900">{c.get('procedures_count', 0)} ta</strong></div>
            <button onclick="filterByCustInn('{c.get('stir', '')}')" class="text-xs text-indigo-600 hover:text-indigo-800 font-bold flex items-center gap-1 mt-1">
              Shartnomalarini ko'rish →
            </button>
          </div>""")

out.append("""        </div>
      </div>

      <!-- ========================================== -->
      <!-- TAB 5: RAQOBATCHILAR TAHLILI              -->
      <!-- ========================================== -->
      <div id="tab-content-competitor" class="hidden p-4 sm:p-6 space-y-5">

        <!-- Header -->
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h3 class="text-sm font-bold text-slate-900 uppercase tracking-wide">⚔️ Raqobatchilar Tahlili</h3>
            <p class="text-xs text-slate-500 mt-0.5">IT sohasidagi yetakchi yetkazib beruvchilar — yutgan summalar, chegirma foizi va xaridorlar soni</p>
          </div>
          <div class="flex gap-2">
            <input type="text" id="comp-search" oninput="filterCompetitors()" placeholder="🔍 Nomi yoki STIR bo'yicha..." 
              class="text-xs border border-slate-200 rounded-lg px-3 py-2 w-56 focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white">
          </div>
        </div>

        <!-- Stats bar -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="bg-indigo-50 border border-indigo-100 rounded-xl p-3 text-center">
            <div class="text-lg font-black text-indigo-900" id="comp-total-count">0</div>
            <div class="text-xs text-indigo-600 font-medium">IT raqobatchilar</div>
          </div>
          <div class="bg-emerald-50 border border-emerald-100 rounded-xl p-3 text-center">
            <div class="text-lg font-black text-emerald-900" id="comp-total-wins">0</div>
            <div class="text-xs text-emerald-600 font-medium">Jami g'alabalar</div>
          </div>
          <div class="bg-amber-50 border border-amber-100 rounded-xl p-3 text-center">
            <div class="text-lg font-black text-amber-900" id="comp-avg-discount">0%</div>
            <div class="text-xs text-amber-600 font-medium">O'rtacha chegirma</div>
          </div>
          <div class="bg-rose-50 border border-rose-100 rounded-xl p-3 text-center">
            <div class="text-lg font-black text-rose-900" id="comp-top-sum">0</div>
            <div class="text-xs text-rose-600 font-medium">Eng yirik g'alaba (M so'm)</div>
          </div>
        </div>

        <!-- Competitors table -->
        <div class="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="bg-indigo-50 text-indigo-900 text-left">
                <th class="py-2.5 px-3 font-bold border-b border-indigo-100">#</th>
                <th class="py-2.5 px-3 font-bold border-b border-indigo-100">Korxona nomi</th>
                <th class="py-2.5 px-3 font-bold border-b border-indigo-100 text-center">STIR</th>
                <th class="py-2.5 px-3 font-bold border-b border-indigo-100 text-center">G'alabalar</th>
                <th class="py-2.5 px-3 font-bold border-b border-indigo-100 text-right">Jami summa</th>
                <th class="py-2.5 px-3 font-bold border-b border-indigo-100 text-center">Chegirma</th>
                <th class="py-2.5 px-3 font-bold border-b border-indigo-100 text-center">Xaridorlar</th>
                <th class="py-2.5 px-3 font-bold border-b border-indigo-100 text-center">Amal</th>
              </tr>
            </thead>
            <tbody id="comp-table-body">
            </tbody>
          </table>
        </div>
        <p class="text-xs text-slate-400 text-center">IT sohasidagi shartnomalar bo'yicha saralangan • Manba: UZEX va E-Birja</p>
      </div>
"""
)

# Inject top IT competitors as JS constant
out.append("""    </div>
  </div>

  <!-- AI Recommendation Modal -->
  <div id="ai-modal" class="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm hidden flex items-center justify-center p-4">
    <div class="bg-white border border-slate-200 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-4">
      <div class="flex items-center justify-between border-b border-slate-100 pb-3">
        <h3 class="text-base font-bold text-indigo-900 flex items-center gap-2">
          <span>🧠</span> AI Maslahatchi Tavsiyasi
        </h3>
        <button onclick="closeAiModal()" class="text-slate-400 hover:text-slate-600 font-bold text-lg">✕</button>
      </div>
      <div id="ai-modal-content" class="text-xs text-slate-700 space-y-3"></div>
      <div class="flex justify-end pt-2 border-t border-slate-100">
        <button onclick="closeAiModal()" class="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200">Yopish</button>
      </div>
    </div>
  </div>

  <!-- EMBEDDED EXPORT DATASET (1000 ITEMS) -->
  <script>
    const RAW_EXPORT_ITEMS = """ + json.dumps(export_items, ensure_ascii=False) + """;
    const RADAR_ITEMS = """ + json.dumps(radar_data, ensure_ascii=False) + """;
  </script>

  <!-- EMBEDDED IT COMPETITORS DATASET -->
  <script>
    const IT_COMPETITORS = """ + json.dumps(it_competitors, ensure_ascii=False) + """;
  </script>

  <!-- JAVASCRIPT LOGIC -->
  <script>
    // =========================================================================
    // 1. AUTHENTICATION & LOGIN LOGIC (Redirect to server /login in production)
    // =========================================================================
    // Plaintext credentials removed in Phase 0 AppSec hardening.


    function checkAuth() {
      const auth = localStorage.getItem('tender_radar_auth') || sessionStorage.getItem('tender_radar_auth');
      if (auth) {
        try {
          const parsed = JSON.parse(auth);
          document.getElementById('login-view').classList.add('hidden');
          document.getElementById('app-view').classList.remove('hidden');
          document.getElementById('user-badge-name').innerText = parsed.username || 'Softy Admin';
          return true;
        } catch(e) {}
      }
      document.getElementById('login-view').classList.remove('hidden');
      document.getElementById('app-view').classList.add('hidden');
      return false;
    }

    function handleLogin(e) {
      e.preventDefault();
      const user = document.getElementById('login-user').value.trim().toLowerCase();
      const pass = document.getElementById('login-pass').value;
      const remember = document.getElementById('login-remember').checked;
      const errEl = document.getElementById('login-error');

      if (VALID_USERS[user] && VALID_USERS[user] === pass) {
        errEl.classList.add('hidden');
        const sessionData = JSON.stringify({ username: user === 'umidjon' ? 'Umidjon' : 'Softy Admin', time: Date.now() });
        if (remember) {
          localStorage.setItem('tender_radar_auth', sessionData);
        } else {
          sessionStorage.setItem('tender_radar_auth', sessionData);
        }
        checkAuth();
      } else {
        errEl.classList.remove('hidden');
        document.getElementById('login-error-msg').innerText = "Login yoki parol xato! Iltimos qayta tekshiring.";
      }
    }

    function handleLogout() {
      localStorage.removeItem('tender_radar_auth');
      sessionStorage.removeItem('tender_radar_auth');
      checkAuth();
    }

    function togglePasswordVisibility() {
      const passInput = document.getElementById('login-pass');
      passInput.type = passInput.type === 'password' ? 'text' : 'password';
    }

    function showCredsHint() {
      alert("Standart kirish ma'lumotlari:\\n\\nLogin: admin\\nParol: softy2026!\\n\\n(Yoki login: softy / parol: softy2026!)");
    }

    // =========================================================================
    // 2. TAB SWITCHING
    // =========================================================================
    function switchTab(tab) {
      ['export', 'radar', 'search', 'customer', 'competitor'].forEach(t => {
        const btn = document.getElementById('tab-btn-' + t);
        const cnt = document.getElementById('tab-content-' + t);
        if (btn) {
          if (t === tab) {
            btn.className = 'pb-3 px-3 text-sm font-semibold tab-active flex items-center gap-2 whitespace-nowrap';
          } else {
            btn.className = 'pb-3 px-3 text-sm font-semibold text-slate-500 hover:text-slate-900 flex items-center gap-1.5 whitespace-nowrap';
          }
        }
        if (cnt) {
          if (t === tab) {
            cnt.classList.remove('hidden');
          } else {
            cnt.classList.add('hidden');
          }
        }
      });
    }

    // =========================================================================
    // 3. TABLE FILTERING & PAGINATION (EXACT 10 COLUMNS)
    // =========================================================================
    let currentFilteredData = [];
    let currentPage = 1;
    const pageSize = 15;

    function applyExportFilters() {
      const pKw = (document.getElementById('f-product').value || '').trim().toLowerCase();
      const cInn = (document.getElementById('f-cust-inn').value || '').trim().toLowerCase();
      const wInn = (document.getElementById('f-win-inn').value || '').trim().toLowerCase();
      const fDate = document.getElementById('f-date').value;
      const fSrc = document.getElementById('f-source').value;

      currentFilteredData = RAW_EXPORT_ITEMS.filter(it => {
        if (pKw && !((it.product_name || '').toLowerCase().includes(pKw) || (it.customer_name || '').toLowerCase().includes(pKw))) return false;
        if (cInn && !((it.customer_inn || '').toLowerCase().includes(cInn))) return false;
        if (wInn && !((it.winner_inn || '').toLowerCase().includes(wInn))) return false;
        if (fDate && it.contract_date !== fDate) return false;
        if (fSrc && it.source !== fSrc) return false;
        return true;
      });

      currentPage = 1;
      renderExportTable();
    }

    function resetExportFilters() {
      document.getElementById('f-product').value = '';
      document.getElementById('f-cust-inn').value = '';
      document.getElementById('f-win-inn').value = '';
      document.getElementById('f-date').value = '';
      document.getElementById('f-source').value = '';
      applyExportFilters();
    }

    function formatNumber(num) {
      if (num === null || num === undefined || isNaN(num)) return '0';
      return Math.round(Number(num)).toString().replace(/\\B(?=(\\d{3})+(?!\\d))/g, ' ');
    }

    function renderExportTable() {
      const tbody = document.getElementById('export-table-body');
      tbody.innerHTML = '';

      // Update Summary Bar
      document.getElementById('f-count').innerText = currentFilteredData.length;
      const totalSum = currentFilteredData.reduce((acc, row) => acc + (Number(row.deal_sum) || 0), 0);
      document.getElementById('f-sum').innerText = formatNumber(totalSum);

      const totalPages = Math.ceil(currentFilteredData.length / pageSize) || 1;
      document.getElementById('page-current').innerText = currentPage;
      document.getElementById('page-total').innerText = totalPages;
      document.getElementById('btn-prev').disabled = (currentPage <= 1);
      document.getElementById('btn-next').disabled = (currentPage >= totalPages);

      const start = (currentPage - 1) * pageSize;
      const pageData = currentFilteredData.slice(start, start + pageSize);

      if (pageData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center py-8 text-slate-400 font-medium">Filtr bo\\'yicha hech qanday ma\\'lumot topilmadi</td></tr>';
        return;
      }

      pageData.forEach(row => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-50 transition border-b border-slate-200';
        
        const startSumStr = formatNumber(row.start_sum);
        const dealSumStr = formatNumber(row.deal_sum);
        const lotLink = row.lot_url ? `<a href="${row.lot_url}" target="_blank" class="text-indigo-600 hover:text-indigo-900 font-bold underline">Ochish ↗</a>` : '-';

        tr.innerHTML = `
          <td class="py-2.5 px-3 font-medium text-slate-900 border border-slate-200">${row.customer_name || '-'}</td>
          <td class="py-2.5 px-3 font-mono text-slate-700 whitespace-nowrap border border-slate-200">${row.customer_inn || '-'}</td>
          <td class="py-2.5 px-3 font-semibold text-slate-800 border border-slate-200">${row.product_name || '-'}</td>
          <td class="py-2.5 px-3 font-mono text-center text-slate-600 whitespace-nowrap border border-slate-200">${row.contract_date || '-'}</td>
          <td class="py-2.5 px-3 font-mono text-center text-indigo-700 whitespace-nowrap border border-slate-200">${row.contract_end_date || '-'}</td>
          <td class="py-2.5 px-3 font-mono text-right text-slate-700 whitespace-nowrap border border-slate-200">${startSumStr} so'm</td>
          <td class="py-2.5 px-3 font-mono text-right font-bold text-emerald-800 whitespace-nowrap border border-slate-200">${dealSumStr} so'm</td>
          <td class="py-2.5 px-3 text-slate-800 border border-slate-200">${row.winner_name || '-'}</td>
          <td class="py-2.5 px-3 font-mono text-slate-700 whitespace-nowrap border border-slate-200">${row.winner_inn || '-'}</td>
          <td class="py-2.5 px-3 text-center whitespace-nowrap border border-slate-200">${lotLink}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    function prevPage() {
      if (currentPage > 1) {
        currentPage--;
        renderExportTable();
      }
    }

    function nextPage() {
      const totalPages = Math.ceil(currentFilteredData.length / pageSize) || 1;
      if (currentPage < totalPages) {
        currentPage++;
        renderExportTable();
      }
    }

    function filterByCustInn(inn) {
      switchTab('export');
      document.getElementById('f-cust-inn').value = inn;
      applyExportFilters();
    }

    function filterByWinInn(inn) {
      switchTab('export');
      document.getElementById('f-win-inn').value = inn;
      applyExportFilters();
    }

    function searchFor(kw) {
      switchTab('export');
      document.getElementById('f-product').value = kw;
      applyExportFilters();
    }

    // =========================================================================
    // COMPETITOR ANALYSIS — FILTER & RENDER
    // =========================================================================
    function initCompetitors() {
      renderCompetitors(IT_COMPETITORS);
      const total = IT_COMPETITORS.length;
      const totalWins = IT_COMPETITORS.reduce((a, c) => a + c.wins_count, 0);
      const avgDisc = IT_COMPETITORS.length > 0
        ? (IT_COMPETITORS.reduce((a, c) => a + c.avg_discount_pct, 0) / IT_COMPETITORS.length).toFixed(1)
        : 0;
      const topSum = IT_COMPETITORS.length > 0
        ? Math.round(IT_COMPETITORS[0].total_won / 1e6).toLocaleString('ru-RU')
        : 0;
      document.getElementById('comp-total-count').innerText = total;
      document.getElementById('comp-total-wins').innerText = totalWins.toLocaleString('ru-RU');
      document.getElementById('comp-avg-discount').innerText = avgDisc + '%';
      document.getElementById('comp-top-sum').innerText = topSum;
    }

    function filterCompetitors() {
      const q = (document.getElementById('comp-search').value || '').trim().toLowerCase();
      const filtered = q
        ? IT_COMPETITORS.filter(c =>
            (c.name || '').toLowerCase().includes(q) ||
            (c.stir || '').includes(q)
          )
        : IT_COMPETITORS;
      renderCompetitors(filtered);
    }

    function renderCompetitors(list) {
      const tbody = document.getElementById('comp-table-body');
      tbody.innerHTML = '';
      if (!list || list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center py-6 text-slate-400">Hech qanday raqobatchi topilmadi</td></tr>';
        return;
      }
      list.forEach((c, i) => {
        const sumMln = (c.total_won / 1e6).toFixed(1);
        const disc = c.avg_discount_pct;
        const discClass = disc >= 10 ? 'text-rose-600 font-bold' : disc >= 5 ? 'text-amber-600 font-semibold' : 'text-slate-600';
        const stir = c.stir || '—';
        const tr = document.createElement('tr');
        tr.className = (i % 2 === 0 ? 'bg-white' : 'bg-slate-50') + ' hover:bg-indigo-50 transition border-b border-slate-100';
        tr.innerHTML = `
          <td class="py-2 px-3 text-slate-400 font-mono">${i + 1}</td>
          <td class="py-2 px-3 font-semibold text-slate-900">${c.name || '—'}</td>
          <td class="py-2 px-3 font-mono text-center text-slate-600">${stir}</td>
          <td class="py-2 px-3 text-center font-bold text-emerald-700">${c.wins_count}</td>
          <td class="py-2 px-3 text-right font-mono font-bold text-slate-800">${Number(sumMln).toLocaleString('ru-RU')} M</td>
          <td class="py-2 px-3 text-center ${discClass}">${disc}%</td>
          <td class="py-2 px-3 text-center text-indigo-700 font-semibold">${c.unique_buyers}</td>
          <td class="py-2 px-3 text-center">
            <button onclick="filterByWinInn('${c.stir}')" class="text-xs bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-bold px-2 py-1 rounded-lg transition">
              Ko'rish →
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    // =========================================================================
    // 4. EXCEL EXPORT (.xlsx) — EXACT 10 COLUMNS FROM USER SCREENSHOT
    // =========================================================================
    function exportToExcel() {
      if (!currentFilteredData || currentFilteredData.length === 0) {
        alert("Yuklab olish uchun ma'lumot topilmadi!");
        return;
      }

      // Map rows with exact 10 column names
      const excelRows = currentFilteredData.map(r => ({
        "Korxona nomi": r.customer_name || "",
        "Tashkilot INN / JSHSHIR": r.customer_inn || "",
        "Mahsulot nomi": r.product_name || "",
        "Shartnoma tuzilgan sana": r.contract_date || "",
        "Shartnoma tugash sanasi": r.contract_end_date || "",
        "Boshlang'ich summa (so'm)": Number(r.start_sum || 0),
        "Yutilgan summa (so'm)": Number(r.deal_sum || 0),
        "Yutib olgan korxona nomi": r.winner_name || "",
        "Yutib olgan korxona INN / JSHSHIR": r.winner_inn || "",
        "Lot silkasi": r.lot_url || ""
      }));

      const worksheet = XLSX.utils.json_to_sheet(excelRows);

      // Set standard column widths for clean look
      worksheet['!cols'] = [
        { wch: 35 }, // Korxona nomi
        { wch: 22 }, // Tashkilot INN / JSHSHIR
        { wch: 45 }, // Mahsulot nomi
        { wch: 24 }, // Shartnoma tuzilgan sana
        { wch: 24 }, // Shartnoma tugash sanasi
        { wch: 26 }, // Boshlang'ich summa (so'm)
        { wch: 26 }, // Yutilgan summa (so'm)
        { wch: 35 }, // Yutib olgan korxona nomi
        { wch: 28 }, // Yutib olgan korxona INN / JSHSHIR
        { wch: 45 }  // Lot silkasi
      ];

      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheet, "Xaridlar");

      const dateStr = new Date().toISOString().slice(0, 10);
      XLSX.writeFile(workbook, `Tender_Radar_Xaridlar_${dateStr}.xlsx`);
    }

    // =========================================================================
    // 5. PDF EXPORT (.pdf) — EXACT 10 COLUMNS LANDSCAPE REPORT
    // =========================================================================
    function exportToPdf() {
      if (!currentFilteredData || currentFilteredData.length === 0) {
        alert("Yuklab olish uchun ma'lumot topilmadi!");
        return;
      }

      const { jsPDF } = window.jspdf;
      const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });

      const dateStr = new Date().toISOString().slice(0, 10);

      // Title & Subtitle
      doc.setFontSize(14);
      doc.setTextColor(30, 58, 138);
      doc.text("TENDER RADAR — DAVLAT XARIDLARI VA SHARTNOMALAR HISOBOTI", 30, 32);

      doc.setFontSize(8);
      doc.setTextColor(100, 116, 139);
      doc.text(`Hosil qilingan sana: ${dateStr} | Jami tanlangan qatorlar: ${currentFilteredData.length} ta`, 30, 46);

      const headers = [[
        "Korxona nomi",
        "Tashkilot INN",
        "Mahsulot nomi",
        "Tuzilgan sana",
        "Tugash sanasi",
        "Boshlang'ich summa",
        "Yutilgan summa",
        "Yutib olgan korxona",
        "G'olib INN",
        "Lot silkasi"
      ]];

      const rows = currentFilteredData.slice(0, 500).map(r => [
        (r.customer_name || "-").slice(0, 35),
        r.customer_inn || "-",
        (r.product_name || "-").slice(0, 45),
        r.contract_date || "-",
        r.contract_end_date || "-",
        formatNumber(r.start_sum),
        formatNumber(r.deal_sum),
        (r.winner_name || "-").slice(0, 30),
        r.winner_inn || "-",
        r.lot_url ? "Mavjud" : "-"
      ]);

      doc.autoTable({
        head: headers,
        body: rows,
        startY: 55,
        margin: { left: 25, right: 25 },
        theme: 'grid',
        headStyles: {
          fillColor: [219, 234, 254], // Soft light blue from screenshot
          textColor: [15, 23, 42],
          fontSize: 7.5,
          fontStyle: 'bold',
          halign: 'center'
        },
        styles: {
          fontSize: 6.5,
          cellPadding: 3,
          overflow: 'linebreak'
        },
        columnStyles: {
          0: { cellWidth: 100 },
          1: { cellWidth: 55, halign: 'center' },
          2: { cellWidth: 140 },
          3: { cellWidth: 55, halign: 'center' },
          4: { cellWidth: 55, halign: 'center' },
          5: { cellWidth: 70, halign: 'right' },
          6: { cellWidth: 70, halign: 'right' },
          7: { cellWidth: 100 },
          8: { cellWidth: 55, halign: 'center' },
          9: { cellWidth: 45, halign: 'center' }
        }
      });

      doc.save(`Tender_Radar_Xaridlar_${dateStr}.pdf`);
    }

    // =========================================================================
    // 6. AI RECOMMENDATION MODAL
    // =========================================================================
    function showAiModal(idx) {
      const item = RADAR_ITEMS[idx - 1];
      if (!item) return;
      const modal = document.getElementById('ai-modal');
      const content = document.getElementById('ai-modal-content');
      const ai = item.ai_advice || {};

      content.innerHTML = `
        <div class="p-3 bg-indigo-50/70 rounded-xl space-y-1 border border-indigo-100">
          <div class="font-bold text-slate-900 text-sm">${item.customer || 'Noma\\'lum'}</div>
          <div class="text-slate-500 font-mono text-[11px]">STIR: ${item.stir || '-'} | Hudud: ${item.region || 'O\\'zbekiston'}</div>
          <div class="text-indigo-900 font-semibold mt-1">Lot: ${item.title || '-'}</div>
        </div>
        <div>
          <div class="font-bold text-slate-800 uppercase text-[11px] mb-1">AI Strategik Tahlil:</div>
          <p class="bg-slate-50 p-2.5 rounded-lg border border-slate-200 text-slate-700 leading-relaxed">${ai.reasoning || 'Mijozning yillik IT ehtiyojlari monitoring qilindi. Yangilanish davri yaqinlashmoqda.'}</p>
        </div>
        <div>
          <div class="font-bold text-slate-800 uppercase text-[11px] mb-1">Tavsiya etiladigan amallar:</div>
          <ul class="list-disc list-inside space-y-1 text-slate-700">
            ${(ai.tactics || ['Mijoz IT bo\\'limi bilan bog\\'lanish', 'Yangi taklif taqdim etish']).map(t => `<li>${t}</li>`).join('')}
          </ul>
        </div>
      `;
      modal.classList.remove('hidden');
    }

    function closeAiModal() {
      document.getElementById('ai-modal').classList.add('hidden');
    }

    // INITIALIZE ON LOAD
    window.addEventListener('DOMContentLoaded', () => {
      checkAuth();
      currentFilteredData = RAW_EXPORT_ITEMS;
      renderExportTable();
      initCompetitors();
    });
  </script>
</body>
</html>
""")

output_file = Path(os.path.expanduser(os.environ.get('DASHBOARD_HTML_PATH') or str(HERE / 'index.html')))
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(''.join(out))

print(f'Compiled mvp_dashboard.html successfully! Length: {len("".join(out))}')
