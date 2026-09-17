# SOFTY PLATFORMA — Davlat Xaridlari Qidiruvi va Yagona Mijozlar Bazasi

Davlat xaridlari platformalari (`xt-xarid.uz`, `xarid.uzex.uz`, `xarid.ebirja.uz`, `new.cooperation.uz`) bo'yicha tarixiy IT va dasturiy ta'minot xaridlari qidiruvi, ko'p o'lchamli filtrlar, korxonalar xaridlar tarixi xronologiyasi (Timeline), mas'ul xodimlarni biriktirish, asoslangan tijorat takliflari va Bitrix24 integratsiyasiga ega to'liq ishchi tizim.

---

## 🚀 Tizim hozirda faol ishlamoqda!

Server fonda ishga tushirilgan:
👉 **Brauzerda kiring:** [http://127.0.0.1:8080](http://127.0.0.1:8080)

Serverni qayta ishga tushirish uchun:
```bash
./start_server.sh
# yoki
python3 -u -m app.server
```

---

## 🛠 Asosiy Imkoniyatlar va Arxitektura

### 1. Rasmiy manbalar va tekshirilgan domenlar (17.A)
- **`xt-xarid.uz`** — Hayot Birja / XT-Xarid platformasi.
- **`xarid.uzex.uz`** — O'zRTXB davlat xaridlari portali.
- **`xarid.ebirja.uz`** — Toshkent tovar xomashyo birjasi AJ (ТТСБ / TTXB).
- **`new.cooperation.uz`** — Yangi Elektron kooperatsiya portali (O'zRTXB AJ).
- Barcha platformalar uchun kengaytiriluvchi adapterlar mavjud (`app/adapters/`). Ishlab chiqilayotgan yangi manbalar uchun `"Adapter ishlab chiqilishi kerak"` fallback holati ta'minlangan.

### 2. Ko'p tilli qidiruv tizimi (17.C, 17.D)
- O'zbek lotin, o'zbek kirill va rus tillaridagi so'rovlarni avtomatik normalizatsiya qilish (`Kaspersky` = `Касперский`, `AutoCAD` = `Автокад`).
- Aniq ibora (`"..."`), istisnolar (`-word`), apostrof turlarini avtomatik to'g'rilash.
- Natijalarni `<mark>` bilan yoritish va moslik sababi bo'yicha nishonlar:
  - 🎯 **"Xarid mahsuloti sifatida aniqlandi"** (yashil nishon)
  - 🔍 **"Matnda uchradi"** (ko'k nishon)

### 3. 14 parametrli filtrlar va 3 xil ko'rinish (17.E)
- **3 ta tab ko'rinishi:**
  1. `Xarid lotlari`
  2. `Xarid qilgan korxonalar` ("Shu mahsulotni oldin olgan korxonalar")
  3. `Shartnomalar va mahsulot qatorlari`
- **Sana tanlovi ("Qaysi sana bo'yicha?"):** E'lon sanasi, Shartnoma sanasi, Litsenziya tugashi va h.k. + Asia/Tashkent bo'yicha tezkor davrlar (`Shu oy`, `O'tgan oy`, `Shu yil`, `O'tgan yil`, `Oxirgi 12 oy`).
- **URL bilan sinxronizatsiya:** Sahifa yangilanganda filtrlar o'chib ketmaydi.
- **CSV eksport:** Ekrandagi natijalarga 100% mos ravishda yuklab olish.

### 4. Korxona xaridlar tarixi (Timeline) va CRM (17.F, 17.G)
- **Xaridorlik dalili:** Shartnomasi borlar — `Tasdiqlangan Xaridor`, faqat tender e'lon qilganlar — `Xarid e'lon qilgan (shartnomasiz)`.
- **Timeline:** Sanalar bo'yicha eng yangi xariddan boshlab xronologik ko'rinish, lot va shartnomalarning to'g'ridan-to'g'ri havolalari.
- **Mas'ul xodim biriktirish:** Umidjon Fatullayev, Yoqubxon, Usmon, Shohruh, Komiljon, Siyovush.
- **Asoslangan tijorat taklifi (Grounded Proposal):** Faqat korxona avval sotib olgan rasmiy litsenziyalar asosida shakllanadi, to'qima narxlar yo'q. "Men rasmiy distribyutor narxlarini tekshirdim va taklifni tasdiqlayman" inson tasdig'i nazorati (approval gate) o'rnatilgan.
- **Bitrix24:** Yangi bitim va vazifa yaratish.

---

## 🧪 Avtomatlashtirilgan Testlar (17.I)

10 ta qabul qilish mezonining barchasi avtomatlashtirilgan testlar bilan tekshirilgan:
```bash
python3 -m unittest tests/test_acceptance_criteria.py
```
**Natija:** 10/10 OK.
