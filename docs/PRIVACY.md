# Shaxsga Doir Ma'lumotlar va Maxfiylik Siyosati (Privacy Policy)

> **OGOHLANTIRISH**: Ushbu hujjat yurist ko'rib chiqishi uchun qoralama (draft) hisoblanadi va yuridik maslahat o'rnini bosmaydi. Loyiha ishlab chiqarishga to'liq kiritilishidan avval professional yurist (huquqshunos) ekspertizasidan o'tkazilishi shart.

---

## 1. Umumiy Qoidalar va Qonuniy Asoslar

"Tender Radar" axborot tizimi "Softy" MChJning ichki tahliliy vositasi hisoblanadi. Mazkur siyosat tizimda ma'lumotlarni to'plash, qayta ishlash, saqlash va himoya qilish tartibini belgilaydi.

Tizim o'z faoliyatida O'zbekiston Respublikasining quyidagi qonunchilik hujjatlariga qat'iy amal qiladi:
1. **O'zbekiston Respublikasining 2019-yil 2-iyuldagi O'RQ-547-son "Shaxsga doir ma'lumotlar to'g'risida"gi Qonuni**.
2. **O'RQ-547-son Qonunning 27-1-moddasi**: O'zbekiston Respublikasi fuqarolarining shaxsga doir ma'lumotlariga ishlov berishda O'zbekiston Respublikasi hududida joylashgan texnik vositalardan (serverlar va ma'lumotlar bazalaridan) foydalanish majburiyati.
3. **O'zbekiston Respublikasining 2021-yil 22-apreldagi O'RQ-684-son "Davlat xaridlari to'g'risida"gi Qonuni** (ochiqlik va shaffoflik prinsiplari).

---

## 2. Ma'lumot Manbalari va Toifalari

Tender Radar tizimi faqat qonuniy va ommaviy ochiq manbalardan ma'lumot to'playdi:
- **xarid.uzex.uz / etender.uzex.uz** — O'zbekiston Respublika tovar-xom ashyo birjasi davlat xaridlari portali;
- **e-birja.uz** — Elektron savdo maydonchasi;
- **xt-xarid.uz** — Maxsus savdo portali.

### Qayta ishlanadigan ma'lumotlar turlari:
1. **Ochiq korporativ ma'lumotlar:**
   - Yuridik shaxslarning 9 xonali soliq to'lovchining identifikatsiya raqami (STIR / INN);
   - Tashkilotning to'liq va qisqartirilgan nomi;
   - Lot, tender va to'g'ridan-to'g'ri shartnomalar bo'yicha e'lonlar, xarid summalari, tovar/xizmat nomlari va muddatlari.
   - *Ushbu ma'lumotlar davlat xaridlari qonunchiligiga ko'ra ochiq hisoblanadi va to'liq ko'rinishda namoyish etiladi.*

2. **Shaxsga doir ma'lumotlar (PII):**
   - Jismoniy shaxslar va YaTT (Yakka tartibdagi tadbirkorlar) ning 14 xonali Jismoniy shaxsning shaxsiy identifikatsiya raqami (JSHSHIR / PINFL);
   - Aloqa ma'lumotlari (telefon raqamlari, elektron pochta manzillari).

---

## 3. JSHSHIR (PINFL) ni Maskalash va Himoyalash Qoidalari

Shaxsiy daxlsizlikni va O'RQ-547 talablarini ta'minlash maqsadida Tender Radar tizimida quyidagi texnik cheklovlar o'rnatilgan:

1. **Avtomatik aniqlash va farqlash:**
   - 9 xonali raqamlar — Yuridik shaxs STIRi sifatida baholanadi va ochiq ko'rsatiladi.
   - 14 xonali raqamlar — Jismoniy shaxs / YaTT JSHSHIRi sifatida tan olinadi va zudlik bilan maskalanadi.
2. **Maskalash standarti:**
   - Foydalanuvchi interfeysi (UI) va Excel (XLSX) eksportlarida 14 xonali JSHSHIR doimiy ravishda quyidagi formatda ko'rsatiladi:
     `*********12345` (dastlabki 9 raqam yulduzcha `*` bilan yashiriladi, faqat oxirgi 5 raqam ko'rinadi).
3. **Ochish (Unmasking) faqat Admin huquqi bilan:**
   - Oddiy sotuv xodimlari (`sales`) va kuzatuvchilar (`viewer`) hech qachon to'liq JSHSHIRni ko'ra olmaydilar.
   - Faqat `admin` roliga ega vakolatli xodimlar asosli zarurat tug'ilganda JSHSHIRni ochishlari mumkin.
4. **Qat'iy Audit Nazorati (`audit_log`):**
   - Har bir JSHSHIRni ochish (unmask) hodisasi yoki to'liq JSHSHIR bilan Excel faylni yuklab olish harakati `audit_log` jadvaliga yoziladi.
   - Qayd quyidagilarni o'z ichiga oladi: `user_id`, `action` ("unmask_pinfl" yoki "export_unmasked_pinfl"), maqsadli JSHSHIR identifikatori, IP-manzil va UTC vaqt tamg'asi.

---

## 4. Sun'iy Intellekt (LLM / Gemini) Uchun Ma'lumotlarni Sanitarizatsiya Qilish

Tizimda tavsiyalar va tijoriy takliflar yaratishda tashqi AI modellari (masalan, Google Gemini API) qo'llaniladi. Shaxsiy ma'lumotlarning tashqi serverlarga chiqib ketishini oldini olish maqsadida:

- AI modeliga yuboriladigan har qanday matn (lot nomi, texnik talablar, xarid tavsifi) oldindan avtomatik ravishda **sanitarizatsiya filtridan** o'tkaziladi (`sanitize_for_ai`).
- Matndagi barcha:
  - 14 xonali JSHSHIRlar `[PINFL]` belgisi bilan;
  - 9 xonali STIRlar `[STIR]` belgisi bilan;
  - Telefon raqamlari `[PHONE]` belgisi bilan;
  - Elektron pochta manzillari `[EMAIL]` belgisi bilan almashtiriladi.
- Tashqi AI provayderiga faqat tozalangan, anonimlashtirilgan xarid parametrlari uzatiladi.

---

## 5. Ma'lumotlarni Saqlash Muddati va Tozalash (Retention & Minimization)

Ma'lumotlarni minimallashtirish (Data Minimization) tamoyiliga binoan:
1. **Birlamchi tarmoq suratlari (`raw_snapshot`):**
   - Manbalardan olingan asl HTML/JSON javoblari operatsion tekshirish uchun ko'pi bilan **12 oy (365 kun)** saqlanadi.
   - Belgilangan muddatdan oshgan barcha xom yozuvlar `python -m radar cleanup --older-than 365d` buyrug'i orqali muntazam ravishda to'liq o'chiriladi.
   - Har bir tozalash jarayoni `audit_log` da qayd etiladi.
2. **Qayta ishlangan tahliliy ma'lumotlar:**
   - Tasniflangan IT-lotlar va shartnoma tarixi litsenziyalarni qayta yangilash (Renewal Radar) davri uchun zarur bo'lgan muddatda xavfsiz saqlanadi.

---

## 6. Serverlar va Xavfsizlik (O'RQ-547 27-1-moddasi)

1. **Mahalliy joylashuv:**
   - Barcha tizim ma'lumotlar bazalari (PostgreSQL 16) va ilova serverlari O'zbekiston Respublikasi hududida jismonan joylashgan server infratuzilmasida yuritiladi.
2. **Xavfsizlik choralari:**
   - Barcha parollar argon2id (yoki bcrypt) xesh algoritmlari yordamida himoyalangan.
   - Tizim sessiyalari xavfsiz HTTP cookie va JWT tokenlar orqali boshqariladi.
   - API so'rovlari tezlik chegarasi (Rate Limiting) va xavfsizlik sarlavhalari (CSP, HSTS, X-Frame-Options, X-Content-Type-Options) bilan himoyalangan.

---

## 7. Mas'ul Shaxslar va Aloqa

Shaxsga doir ma'lumotlarni qayta ishlash yoki maxfiylik siyosati bo'yicha taklif va e'tirozlar bo'yicha:
- **Mas'ul tashkilot:** "Softy" MChJ
- **Ichki xavfsizlik va muvofiqlik:** AppSec & Legal Team
