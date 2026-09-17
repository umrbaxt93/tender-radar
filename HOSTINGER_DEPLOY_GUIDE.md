# Softy Platforma — Hostinger (tender.softy.uz) Deployment Yo'riqnomasi

Ushbu yo'riqnoma `tender.softy.uz` domenini to'g'ridan-to'g'ri Hostinger hostingiga ulash va ishlab chiqarish (production) rejimida ishga tushirish uchun tayyorlangan.

---

## 1. Hosting va Domen Parametrlari

- **Asosiy Domen:** `softy.uz`
- **Tender Portali:** `tender.softy.uz`
- **Hostinger Hisob:** `u475605112` (Server 1103)
- **Hostinger IP:** `62.72.50.47`
- **VPS IP (zahira):** `93.127.213.246`
- **DNS Boshqaruvi:** Ahost (`clients.ahost.uz`, Zone 98242, NS: `rdns1/2/3.ahost.uz`)

---

## 2. Ahost DNS Sozlamasi (Domen Yo'naltirish)

1. `clients.ahost.uz` shaxsiy kabinetiga kiring (Zone: `98242` - `softy.uz`).
2. Yangi **A record** qo'shing:
   - **Host / Subdomain:** `tender`
   - **Type:** `A`
   - **Points to / IP:** `62.72.50.47` (yoki VPS bo'lsa `93.127.213.246`)
   - **TTL:** `3600`

---

## 3. Hostinger hPanel da Subdomen O'rnatish

1. **Hostinger hPanel** (`hpanel.hostinger.com`) ga kiring.
2. **Websites** -> `softy.uz` boshqaruviga o'ting.
3. **Domains** -> **Subdomains** bo'limini oching:
   - **Subdomain nomi:** `tender` (natijada `tender.softy.uz` bo'ladi).
   - **Custom folder for subdomain:** `public_html/tender` belgilang.
   - **Create** tugmasini bosing.
4. **SSL:** Hostinger avtomatik ravishda `tender.softy.uz` uchun bepul Lifetime SSL sertifikatini o'rnatadi.

---

## 4. Fayllarni Yuklash (1-Bosqichli Deployment)

Loyiha ildizida barcha ma'lumotlar bazasi (1,058 ta lot, 412 ta korxona, 4.99 MB SQLite), frontend va backend modullarini o'z ichiga olgan tayyor arxiv yaratilgan:
👉 **`dist_hostinger/tender-softy.zip`** (hajmi ~978 KB).

1. Hostinger hPanel -> **File Manager** bo'limiga kiring.
2. `/home/u475605112/domains/softy.uz/public_html/tender` papkasiga o'ting.
3. `tender-softy.zip` arxivini yuklang va **Extract** (arxivdan chiqarish) qiling.
4. Chiqarilgandan so'ng, papkada quyidagilar mavjud bo'ladi:
   - `passenger_wsgi.py` (Hostinger Python WSGI startap fayli)
   - `.htaccess` (LiteSpeed/Apache yo'naltiruvchisi)
   - `app/` (qidiruv, filtr, CRM va E-IMZO kodlari)
   - `data/softy_procurement.db` (to'liq 1,058 lot bazasi)
   - `frontend/` (veb interfeys)

---

## 5. Sinov va Tekshirish

Brauzerda quyidagi manzillarni oching:
- Veb interfeys: **`https://tender.softy.uz`**
- Salomatlik tekshiruvi: **`https://tender.softy.uz/api/health`**
- Manbalar monitoringi: **`https://tender.softy.uz/api/sources`**
- Qidiruv API: **`POST https://tender.softy.uz/api/search`**

Agar VPS orqali ishlatilayotgan bo'lsa:
`nginx/tender.softy.uz.conf` fayli to'liq sozlangan bo'lib, `/etc/nginx/sites-available/` ga joylanadi va `certbot --nginx -d tender.softy.uz` bilan SSL faollashtiriladi.
