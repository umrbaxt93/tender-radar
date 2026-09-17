# SOFTY PROCUREMENT & TENDER RADAR — LOYIHA QOIDALARI VA ARXITEKTURASI

Ushbu hujjat **Claude Code**, **Codex**, **Antigravity** va boshqa barcha AI agentlar uchun loyihaning yagona haqiqat manbai (Single Source of Truth) hisoblanadi.

---

## 1. LOYIHA MAQSADI VA FUNKSIYALARI
- **Loyiha nomi:** Softy Platforma — Davlat Xaridlari Radari va CRM Integratsiyasi.
- **Asosiy vazifa:** O'zbekiston davlat xaridlari (100,000+ lotlar) bazasini tahlil qilish, IT/litsenziyalar bo'yicha qayta xarid imkoniyatlarini aniqlash, korxonalar va raqobatchilar tahlili, hamda Bitrix24 orqali Umidjonga avtomatik topshiriqlar yaratish.
- **Jonli domen:** `https://tender.softy.uz`
- **Maxfiy kirish portali:** `https://tender.softy.uz/umid/` (Asosiy root `/` sahifasi begonalarga 404 xatolik ko'rsatib niqoblangan).

---

## 2. PRODUCTION SERVER VA DEPLOYMENT
- **Hosting:** Hostinger Web Hosting (LiteSpeed / Passenger WSGI).
- **SSH ulanish:** `ssh -p 65002 -i ~/.ssh/id_hostinger u475605112@62.72.50.47`
- **Serverdagi loyiha yo'li:** `/home/u475605112/domains/softy.uz/public_html/tender/`
- **WSGI Restart buyrug'i:** `touch /home/u475605112/domains/softy.uz/public_html/tender/tmp/restart.txt`
- **Tezkor Deploy skripti:** `./sync_deploy.sh` (lokal o'zgarishlarni serverga nusxalaydi va WSGI'ni qayta yuklaydi).

---

## 3. AUTENTIFIKATSIYA VA XAVFSIZLIK
- **Hisoblar:**
  - Login: `umidjon` | Parol: `softy2026!` (Asosiy admin)
  - Login: `admin` | Parol: `softy2026!`
- **Auth Mexanizmi:** To'g'ridan-to'g'ri 1-bosqichli xavfsiz autentifikatsiya. Login va parol to'g'ri kiritilganda darhol 7 kunlik SHA-256 session token beriladi.
- **Bildirishnoma:** Har safar tizimga kirilganda `umrbaxt93@gmail.com` pochtasiga fonda xavfsizlik bildirishnomasi ketadi (kirishni to'xtatmaydi).
- **Niqoblash:** Asosiy sahifada "404 Not Found" chiqadi. "404" raqamiga 3 marta bosilganda yoki `?umid` qo'shilganda `/umid/` ga yo'naltiradi.

---

## 4. MA'LUMOTLAR BAZASI VA STRUKTURA
- **Baza turi:** SQLite (WAL mode, foreign keys yoqilgan).
- **Baza fayli yo'li:** `data/softy_procurement.db`
- **Asosiy jadvallar:**
  - `lots` — barcha xaridlar va lotlar (101,800+ yozuv).
  - `companies` — buyurtmachi va yetkazib beruvchi tashkilotlar.
  - `contract_items` — shartnoma mahsulot qatorlari.
  - `tasks_and_proposals` — vazifalar va Bitrix24 ga yuborilgan topshiriqlar tarixi.
  - `admin_users` va `admin_sessions` — xodimlar va kirish sessiyalari.

---

## 5. BITRIX24 INTEGRATSIYASI
- **Bitrix24 Webhook:** `https://softytest.bitrix24.uz/rest/22/zc9msevile69qb6l`
- **Mas'ul xodim (Umidjon Fatullaev):** `ID: 22` (Topshiriqlar Umid nomidan Umidga yuklanadi, admin aralashmaydi).
- **Qayta yubormaslik qoidasi:** 1 marta Bitrix24 ga yuborilgan topshiriq bazaga (`tasks_and_proposals`) yoziladi va platformada "✅ Yuborilgan" deb belgilanadi, qayta yuborilmaydi.
- **Topshiriq formati:** AI radar tavsiyasi, imkoniyat balli kabi shovqin so'zlarsiz, aniq va litsenziyani avval kim yetkazib bergani haqidagi qisqa va lo'nda faktlar bilan ochiladi.

---

## 6. RAQOBATCHILAR VA KORXONALAR TAHLILI (TAB 5)
- **Qidiruv rejimi:**
  1. `💻 Faqat IT Korxonalar` (IT bo'yicha saralash)
  2. `🌐 Barcha Korxonalar (Umumiy)` (14,000+ barcha yetkazib beruvchilar bo'yicha)
- **Chuqur tahlil modal oynasi:**
  - Korxona nomi yoki INN si kiritilganda, u birga o'ynagan barcha korxonalar (`organizations_played`), umumiy summalari, o'ynalgan lotlar ro'yxati va 2-varaqli Excel eksporti chiqariladi.

---

## 7. 2-MIYA (OBSIDIAN VAULT) INTEGRATSIYASI
- **Vault yo'li:** `/Users/admin/Documents/Obsidian Vault`
- **Qoida:** Har qanday muhim texnik qaror, yangi integratsiya, tuzatilgan xatolik yoki yangi xususiyat qo'shilganda avtomatik ravishda Obsidian vaultiga qayd yozilishi shart.
- **Foydalaniladigan vosita:** `brain` MCP serveri (`brain_save_note`, `brain_update_profile`).

---

## 8. ISHLASH VA AVTONOMLIK TALABI
- **1 marta buyruq berilganda 100% mustaqil yakunlash:** Oraliq to'xtashlarsiz barcha bosqichlarni to'liq oxirigacha yetkazing.
- **Texnik to'siqlarni mustaqil bartaraf etish:** Muammolar chiqsa, barcha mavjud vositalar orqali mustaqil yechim topib davom eting.
- **Doimo tekshirilgan va ishlaydigan natija taqdim eting.**
