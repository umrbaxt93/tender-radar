"""
Softy Platforma — dashboard_data.json ni umid/index.html ga joylashtirish.

generate_dashboard_data.py yozgan JSON'ni o'qiydi va umid/index.html dagi:
  - 5 ta `const X = [...]` JS massivini (RAW_EXPORT_ITEMS, RADAR_ITEMS,
    TOP_CUSTOMERS, IT_COMPETITORS, ALL_COMPETITORS),
  - Radar jadvalining statik <tr> qatorlarini (#radar-table-body),
  - sarlavhadagi qattiq yozilgan raqamlarni (Jami xaridlar, Kompaniyalar,
    Radar/HOT soni, IT xaridlar, IT raqobatchilar)
yangi qiymatlar bilan almashtiradi. Boshqa hech qanday JS/HTML kodga
tegilmaydi — faqat ma'lumot almashtiriladi.

Ishga tushirish: python3 apply_dashboard_data.py [--in FAYL] [--out FAYL]
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def esc(s):
    return html.escape(str(s or ""), quote=True)


def fmt_money(amount):
    return f"{amount:,.0f}".replace(",", " ")


def js_array(name, items):
    """`const NAME = [...]` uchun xavfsiz JS massiv literali."""
    body = json.dumps(items, ensure_ascii=False)
    # <script> ichida "</script" satri paydo bo'lib qolmasligi uchun himoya —
    # JS/JSON uchun \/ har doim / bilan bir xil, ma'noni o'zgartirmaydi.
    body = body.replace("</script", "<\\/script")
    return f"const {name} = {body};"


def replace_js_array(html_text, name, items, count):
    pattern = re.compile(r"const " + re.escape(name) + r" = \[.*?\];\s*\n", re.S)
    matches = pattern.findall(html_text)
    if len(matches) != count:
        raise SystemExit(f"XATO: 'const {name} = [...]' {count} marta emas, "
                         f"{len(matches)} marta topildi")
    # MUHIM: replacement funksiya sifatida berilishi shart, satr sifatida
    # EMAS. re.sub/subn satr argumentidagi backslash-qochish belgilarini
    # (\t, \n, \g<...> va h.k.) o'zicha QAYTA talqin qiladi — bizning JSON
    # ichidagi "\t"/"\n" kabi ekranlangan belgilar shu sababli xom tab/
    # newline belgisiga aylanib, JSON'ni buzib qo'yardi. Lambda bu muammoni
    # butunlay chetlab o'tadi, chunki funksiya natijasi o'zgarishsiz qo'yiladi.
    replacement = js_array(name, items) + "\n"
    new_text, n = pattern.subn(lambda m: replacement, html_text, count=count)
    return new_text


def build_radar_row(idx, item):
    score = item["score"]
    if score >= 80:
        badge_cls, badge_txt = "score-hot", f"{score} 🔥 HOT"
    elif score >= 50:
        badge_cls, badge_txt = "score-warm", f"{score} ⚡ WARM"
    else:
        badge_cls, badge_txt = "score-cool", f"{score} ❄️ COOL"

    title = esc(item["title"])
    customer = esc(item["customer"])
    prev_supplier = esc(item.get("previous_supplier") or "Noma'lum")
    category = esc(item["category"])
    amount = fmt_money(item["amount"])

    return f"""
      <tr class="hover:bg-slate-50/80 transition border-b border-slate-100">
        <td class="py-3 px-3 font-mono font-bold whitespace-nowrap">
          <span class="px-2.5 py-1 rounded-lg text-[11px] {badge_cls}">{badge_txt}</span>
        </td>
        <td class="py-3 px-3 font-semibold text-slate-900">{customer}</td>
        <td class="py-3 px-3 font-mono text-slate-600 whitespace-nowrap">{esc(item['stir'])}</td>
        <td class="py-3 px-3 text-slate-800 max-w-xs truncate" title="{title}">{title}</td>
        <td class="py-3 px-3 whitespace-nowrap"><span class="text-slate-700 font-semibold" title="{prev_supplier}">{prev_supplier}</span></td>
        <td class="py-3 px-3 whitespace-nowrap"><span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-semibold">{category}</span></td>
        <td class="py-3 px-3 text-right font-mono font-bold text-slate-900 whitespace-nowrap">{amount} so'm</td>
        <td class="py-3 px-3 text-center text-slate-500 font-mono whitespace-nowrap">{esc(item['last_purchase'])}</td>
        <td class="py-3 px-3 text-center text-indigo-700 font-mono font-bold whitespace-nowrap">{esc(item['expected_renewal'])}</td>
        <td class="py-3 px-3 text-center whitespace-nowrap space-x-1">
          <button onclick="showAiModal({idx})" class="px-2.5 py-1.5 text-xs font-bold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200 rounded-lg transition shadow-sm">
            🧠 Tahlil
          </button>
          <button id="bx-btn-{idx}" onclick="sendOneToBitrix({idx})" class="px-2.5 py-1.5 text-xs font-bold bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200 rounded-lg transition shadow-sm" title="Umidjonga Bitrix24 topshiriq ochish">
            🚀 Bitrix24
          </button>
        </td>
      </tr>
    """


def replace_radar_tbody(html_text, radar_items):
    rows = "".join(build_radar_row(i, it) for i, it in enumerate(radar_items, start=1))
    pattern = re.compile(
        r'(<tbody id="radar-table-body" class="divide-y divide-slate-100">)(.*?)(</tbody>)',
        re.S)
    matches = pattern.findall(html_text)
    if len(matches) != 1:
        raise SystemExit(f"XATO: radar-table-body {len(matches)} marta topildi (1 kutilgan)")
    new_text, n = pattern.subn(lambda m: m.group(1) + rows + m.group(3), html_text, count=1)
    return new_text


def replace_exact(html_text, old, new, count=1, label=""):
    n = html_text.count(old)
    if n != count:
        raise SystemExit(f"XATO [{label}]: kutilgan {count} marta, topilgani {n} marta:\n  {old!r}")
    return html_text.replace(old, new, count)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", default=str(BASE / "umid" / "index.html"))
    ap.add_argument("--out", dest="outfile", default=str(BASE / "umid" / "index.html"))
    ap.add_argument("--data", dest="datafile", default=str(BASE / "data" / "dashboard_data.json"))
    args = ap.parse_args()

    data = json.loads(Path(args.datafile).read_text(encoding="utf-8"))
    h = data["header"]
    text = Path(args.infile).read_text(encoding="utf-8")

    # ── 1) JS massivlari ──────────────────────────────────────────────────
    text = replace_js_array(text, "RAW_EXPORT_ITEMS", data["RAW_EXPORT_ITEMS"], 1)
    text = replace_js_array(text, "RADAR_ITEMS", data["RADAR_ITEMS"], 1)
    text = replace_js_array(text, "TOP_CUSTOMERS", data["TOP_CUSTOMERS"], 1)
    text = replace_js_array(text, "IT_COMPETITORS", data["IT_COMPETITORS"], 1)
    text = replace_js_array(text, "ALL_COMPETITORS", data["ALL_COMPETITORS"], 1)
    print(f"✅ 5 ta JS massiv yangilandi", file=sys.stderr)

    # ── 2) Radar jadvalining statik qatorlari ───────────────────────────────
    text = replace_radar_tbody(text, data["RADAR_ITEMS"])
    print(f"✅ Radar jadvali qayta yasaldi ({len(data['RADAR_ITEMS'])} qator)", file=sys.stderr)

    # ── 3) Sarlavha raqamlari ────────────────────────────────────────────
    total_fmt = h["total_lots_fmt"]
    comp_fmt = h["companies_fmt"]
    it_fmt = h["it_lots_fmt"]
    radar_n = h["radar_total"]
    hot_n = h["radar_hot"]
    it_comp_n = h["it_competitors"]
    total_k = f"{round(h['total_lots'] / 1000)}k"

    repl = [
        ('UZEX, E-Birja, XT-Xarid va Kooperatsiya portallari bo\'yicha 101k+ xaridlar, STIR tahlili, Bitrix24 integratsiyasi va AI maslahatchi.',
         f'UZEX, E-Birja, XT-Xarid va Kooperatsiya portallari bo\'yicha {total_k}+ xaridlar, STIR tahlili, Bitrix24 integratsiyasi va AI maslahatchi.',
         1, "hero matn"),
        ('<div class="text-2xl font-black mt-1 text-slate-900">101,851</div>',
         f'<div class="text-2xl font-black mt-1 text-slate-900">{total_fmt}</div>', 1, "KPI jami"),
        ('<div class="text-[11px] text-emerald-600 mt-1 font-medium">UZEX: 73,299 | E-Birja: 28,173</div>',
         f'<div class="text-[11px] text-emerald-600 mt-1 font-medium">{esc(h["source_breakdown"])}</div>',
         1, "manba taqsimoti"),
        ('<div class="text-2xl font-black mt-1 text-teal-600">22,625</div>',
         f'<div class="text-2xl font-black mt-1 text-teal-600">{comp_fmt}</div>', 1, "kompaniyalar"),
        ('<div class="text-2xl font-black mt-1 text-amber-600">41</div>',
         f'<div class="text-2xl font-black mt-1 text-amber-600">{radar_n}</div>', 1, "radar KPI"),
        ('<div class="text-[11px] text-rose-600 mt-1 font-bold">🔥 10 ta HOT (Score ≥ 80)</div>',
         f'<div class="text-[11px] text-rose-600 mt-1 font-bold">🔥 {hot_n} ta HOT (Score ≥ 80)</div>',
         1, "HOT KPI"),
        ('<div class="text-2xl font-black mt-1 text-indigo-600">1,997</div>',
         f'<div class="text-2xl font-black mt-1 text-indigo-600">{it_fmt}</div>', 1, "IT xaridlar"),
        ('<div class="text-2xl font-black mt-1 text-blue-600">50</div>',
         f'<div class="text-2xl font-black mt-1 text-blue-600">{it_comp_n}</div>', 1, "IT raqobatchilar"),
        ('<span class="px-2 py-0.5 text-xs rounded-full bg-rose-100 text-rose-700 font-bold">🔥 10 HOT</span>',
         f'<span class="px-2 py-0.5 text-xs rounded-full bg-rose-100 text-rose-700 font-bold">🔥 {hot_n} HOT</span>',
         1, "tab badge HOT"),
        ('<span class="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700 font-bold">101k Baza</span>',
         f'<span class="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700 font-bold">{total_k} Baza</span>',
         1, "tab badge baza"),
        ('Jami bazadagi to\'liq xaridlar soni: <strong>101,851</strong> ta',
         f'Jami bazadagi to\'liq xaridlar soni: <strong>{total_fmt}</strong> ta', 1, "eksport izoh"),
        ('Jami <strong>41</strong> ta imkoniyat aniqlandi — <strong class="text-rose-600">🔥 10 ta HOT</strong> qayta xarid arafasida',
         f'Jami <strong>{radar_n}</strong> ta imkoniyat aniqlandi — <strong class="text-rose-600">🔥 {hot_n} ta HOT</strong> qayta xarid arafasida',
         1, "radar izoh"),
        ('''onclick="filterRadarTable('hot')" class="px-3 py-1 rounded-lg text-xs font-semibold bg-rose-100 text-rose-700 hover:bg-rose-200">🔥 HOT (10)</button>''',
         f'''onclick="filterRadarTable('hot')" class="px-3 py-1 rounded-lg text-xs font-semibold bg-rose-100 text-rose-700 hover:bg-rose-200">🔥 HOT ({hot_n})</button>''',
         1, "HOT filtr tugmasi"),
    ]
    for old, new, count, label in repl:
        text = replace_exact(text, old, new, count, label)
    print(f"✅ sarlavha raqamlari yangilandi: jami={total_fmt}, kompaniya={comp_fmt}, "
          f"IT={it_fmt}, radar={radar_n} (HOT {hot_n})", file=sys.stderr)

    Path(args.outfile).write_text(text, encoding="utf-8")
    print(f"\n✅ Yozildi: {args.outfile}  ({len(text):,} bayt)", file=sys.stderr)
    print(f"   (generated_at: {data['generated_at']})", file=sys.stderr)


if __name__ == "__main__":
    main()
