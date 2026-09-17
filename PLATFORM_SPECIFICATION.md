# SOFTY PLATFORMA UZ — TO'LIQ TEXNIK SPETSIFIKATSIYA VA TALABLAR REYESTRI

> **Loyiha nomi:** Softy Platforma uz (Davlat va Korporativ Xaridlar Agregatori, Tarixiy Tahlil va B2G CRM Tizimi)  
> **Versiya:** 2.0 (17-bo'lim bilan kengaytirilgan)  
> **Muallif va buyurtmachi:** SOFTY (Umidjon Fatullayev)  
> **Sana:** 2026-09-12  

---

## 1. Loyiha Missiyasi va Maqsadi
O'zbekiston davlat va korporativ xaridlari (UZEX, XT-Xarid, E-Birja, Yangi Kooperatsiya portali) bo'yicha barcha faol va tarixiy tenderlar, auksionlar, elektron do'kon bitimlari hamda shartnomalarni yagona bazaga jamlash. B2B/B2G IT-integratori (Softy) uchun kalit so'zlar (Kaspersky, AutoCAD, Microsoft, ESET, Zoom va b.) orqali avvalgi xaridorlarni aniqlash, ularning litsenziya va shartnoma muddatlarini tahlil qilish hamda sotuv bo'limi uchun aniq taklif va Bitrix24 lidlarini generatsiya qilish.

---

## 2. Asosiy Bozor Yo'nalishlari va Mahsulotlar Katalogi
Platforma birinchi navbatda SOFTY kompaniyasining asosiy IT litsenziyalash va kiberxavfsizlik yo'nalishlarini qamrab oladi:
- **Antivirus va Xavfsizlik:** Kaspersky (Endpoint, Total Security), ESET (NOD32, Protect Entry, Complete), Fortinet (FortiGate), Palo Alto, Bitdefender.
- **Dasturiy Ta'minot va Loyihalash:** Autodesk (AutoCAD, AutoCAD LT, 3ds Max), JetBrains, CorelDRAW, Adobe Creative Cloud.
- **Ofis va Bulut Xizmatlari:** Microsoft 365 (Business, E3, E5, Copilot), Google Workspace, Zoom (Business, Enterprise).
- **Infratuzilma va Zaxira:** Veeam Backup, GFI/Kerio Control, Qlik Sense, Atlassian Jira/Confluence.

---

## 3. Qamrab Olinadigan Platformalar va Rasmiy Manbalar
Platforma quyidagi rasmiy davlat va korporativ platformalar bilan ishlaydi:
1. **xarid.uzex.uz / etender.uzex.uz:** O'zRTXB AJ davlat xaridlari portali.
2. **xt-xarid.uz:** "XT-Xarid Texnologiyalari" / "Hayot Birja" AJ axborot portali.
3. **xarid.ebirja.uz (ebirja.uz):** "Toshkent tovar xomashyo birjasi" AJ (ТТСБ / TTXB) davlat xaridlari portali.
4. **new.cooperation.uz (cooperation.uz):** O'zRTXB AJ "O'zbekiston Respublikasi Yangi Elektron kooperatsiya portali".
5. **CSV/XLSX Ma'lumotlar Importi:** Mahalliy arxivlar, viloyatlar kesimidagi hisobotlar va brokerlik reestrlari.

---

## 4–16. Arxitektura, Xavfsizlik, CRM va Ma'lumotlar Modeli
- **Arxitektura:** FastAPI (Python) backend + SQLAlchemy 2.0 ORM + High-performance Search & Filter dvigateli + Glassmorphism Web UI.
- **Vaqt va Sanalar:** Barcha vaqtlar `Asia/Tashkent` vaqt mintaqasi asosida hisoblanadi.
- **Xavfsizlik:** Faqat tasdiqlangan rasmiy domenlarga ulanish, soxta yoki taxminiy domenlar bilan integratsiya yaratmaslik.
- **CRM Integratsiyasi:** Bitrix24 REST API va mahalliy Bitrix24 MCP orqali xarid qilgan korxonalarga bitim va vazifalar biriktirish.
- **Mas'ullar Ro'yxati:** Umid (CEO), Yoqubxon (E-shop rahbari), Usmon (Litsenziya yangilash), Shohruh (Vendor narxlash / Bitrix24 admin), Komiljon (Tender saralash), Siyovush (Presale).

---

## 17. Majburiy qo‘shimcha: tarixiy xaridlar qidiruvi va yagona mijozlar bazasi

Quyidagi talablar loyiha doirasining majburiy qismi. Ularni avvalgi talablar bilan birlashtirib amalga oshir.

### A. Qamrab olinadigan platformalar

Birinchi navbatdagi manbalar:
1. xarid.uzex.uz
2. xt-xarid.uz
3. Foydalanuvchi “ebirja” deb atagan platforma — `https://xarid.ebirja.uz` (Operator: Toshkent tovar xomashyo birjasi AJ).
4. Foydalanuvchi “new.corporation” deb atagan platforma — `https://new.cooperation.uz` (Operator: O'zRTXB AJ).

Bir xil ma’lumot turli portallarda uchrasa, takroriy xarid sifatida sanama (deduplikatsiya nazorati).

### B. Tarixiy ma’lumotlarni to‘liq yig‘ish
Maqsad faqat oxirgi 24 oy emas: har bir manbada ruxsat etilgan usulda olinadigan barcha mavjud tarixiy davrni bosqichma-bosqich bazaga kiritish.
Har bir manbada quyidagilar ko‘rinsin:
- Manbada mavjud tarix boshlanishi.
- Bazaga yuklangan davr.
- Tekshirilgan va hali tekshirilmagan davrlar.
- Yuklangan yozuvlar soni.
- Olinmagan hujjatlar soni.
- Oxirgi muvaffaqiyatli yangilanish.
- Yig‘ish jarayonining holati.
Yakunlangan, bekor qilingan, g‘olibi aniqlangan, shartnoma tuzilgan va bajarilgan xaridlarni alohida holatlarda saqla.

### C. Kalit so‘zdan xarid tarixiga o‘tish
Asosiy ekranda katta qidiruv maydoni: “Mahsulot, kalit so‘z, korxona yoki STIR kiriting”.
Natijalar:
1. Topilgan tarixiy va faol lotlar.
2. Xarid qilgan korxonalar.
3. Tashkilotlar kesimida sanalar bo‘yicha xaridlar tarixi.
4. G‘olib va yetkazib beruvchilar.
5. Shartnoma va mahsulot qiymatlari.
6. Asl lot havolasi.
7. Shartnoma sahifasi va asl hujjat havolasi.
8. Mahsulot muddati va tasdiqlangan tugash sanasi.
9. Mas’ul xodim va keyingi savdo vazifasi.

Qidiruv natijalari 3 ta ko‘rinishda bo‘ladi:
- Lotlar.
- Xarid qilgan korxonalar.
- Shartnomalar va mahsulot qatorlari.

### D. Qidiruv qanday ishlashi kerak
Qidiruv quyidagilarni tekshiradi:
- Lot nomi va tavsifi, mahsulot qatorlari, brend, mahsulot oilasi va SKU.
- Ajratib olingan hujjat matni, buyurtmachi va yetkazib beruvchi nomi, STIR, lot va shartnoma raqami.
- O‘zbek lotin, o‘zbek kirill va ruscha variantlar, apostrof farqlari, katta-kichik harflar va yozuv xatolarini hisobga olish.
- Aniq ibora (`"..."`), istalgan kalit so‘z va istisno (`-...`) so‘zlar bilan qidirish.
- Natijada qaysi maydon mos kelganini ajratib ko‘rsatish (Highlighting).
- “Matnda uchradi” va “Xarid mahsuloti sifatida aniqlandi” belgilarini ajratish.

### E. To‘liq ishlaydigan filtrlar
- Kalit so‘z va aniq ibora.
- Platforma: bitta yoki bir nechta.
- Xarid turi va rasmiy holati.
- Brend, mahsulot oilasi va mahsulot.
- Buyurtmachi / Yetkazib beruvchi nomi va STIR.
- Hudud (14 ta viloyat).
- Summa oralig‘i, valyuta.
- Shartnomasi mavjud / mavjud emas.
- Tugash sanasi ma’lum / noma’lum.
- Tekshirish holati, mas’ul xodim, ichki savdo holati.

Sana filtri: “Qaysi sana bo‘yicha?” tanlovi (E’lon sanasi, Muddat, Natija, Shartnoma, Yetkazib berish, Litsenziya tugash, Qo‘shilgan sana) + “Dan” va “Gacha” (Asia/Tashkent). Tezkor davrlar: shu oy, o‘tgan oy, shu yil, o‘tgan yil, oxirgi 12 oy, ixtiyoriy davr.
Filtrlar butun baza bo‘yicha serverda ishlaydi. Qidiruv holati URLda saqlanadi. Eksport ekrandagi filtrga mos bo‘ladi.

### F. Korxonaning sanalar bo‘yicha xarid tarixi
- Vaqt ketma-ketligida (Timeline) xaridlar: Sana, mahsulot, miqdor, yetkazib beruvchi, summa, lot/shartnoma havolasi, litsenziya muddati, dalil holati.
- “Shu mahsulotni oldin olgan korxonalar” jadvali.
- Sotib olganlik dalili bo‘lmagan tashkilotlar “Xarid e’lon qilgan” deb ajratiladi.

### G. Yagona baza va mijozlarga taklif tayyorlash
- Doimiy ma'lumotlar bazasi (SQLite/PostgreSQL).
- Guruhli amallar: Potensial mijozlar ro‘yxatiga qo‘shish, Mas’ul biriktirish, Vazifa yaratish, Taklif tayyorlash, Bitrixga yuborish, Eksport qilish.
- Taklif tayyorlash faqat tekshirilgan xarid tarixi va mahsulotdan foydalanadi (noma'lum narx to‘qilmaydi).
- Yangi tegishli lot paydo bo‘lganda saqlangan qidiruv egasiga tizim ichida bildirishnoma chiqadi.

### H. Keyinchalik yangi platforma qo‘shish
- Manba adapterlari uchun umumiy `BasePlatformAdapter` interfeysi.
- Administrator yangi manba qo‘shishi, sozlamalarni sinashi va jadval belgilashi mumkin.
- Tayyor adapter bo‘lmaganda manba “Adapter ishlab chiqilishi kerak” holatida ko‘rinadi.
- CSV/XLSX importida ustunlarni moslash, oldindan ko‘rish, format tekshiruvi va dublikat nazorati.

### I. Ushbu qo‘shimchaning qabul mezonlari
10 ta asosiy jarayon haqiqiy ma’lumotda sinovdan o'tkaziladi:
1. Mahsulot nomini kiritish.
2. Tegishli tarixiy lotlarni ko‘rish.
3. Muayyan sana oralig‘i va platformalarni tanlash.
4. Natijadan xarid qilgan korxonalarni ochish.
5. Korxonaning STIRi va xarid tarixini ko‘rish.
6. Asl lot va mavjud shartnomani ochish.
7. Korxonani xodimga biriktirish.
8. Taklif tayyorlash vazifasini yaratish.
9. Filtrlangan ro‘yxatni eksport qilish.
10. Saqlangan qidiruvni qayta ochish.

Nol natija chiqqanda 3 ta holat ajratiladi: “Mos yozuv topilmadi”, “Bu davr hali yuklanmagan”, “Manba bilan aloqa xatosi”.
