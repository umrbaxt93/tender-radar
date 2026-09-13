# Known lots golden set — SYNTHETIC

These rows are hand-written test cases, **not real procurement records**. No verified public
lot was available when they were written (docs/SOURCE_API.md is still UNVERIFIED). They exist
to pin the behaviour of the rules classifier across Uzbek-Latin, Uzbek-Cyrillic and Russian
wording. Replace them with verified real lots once the source contract is confirmed; keep the
table shape so `tests/test_rules.py` keeps working.

`expected_it` is the ground truth. `expected_category` is checked only when the rules layer
decides by itself (`yes`); an `unsure` row is allowed to carry any category because the AI
layer makes the final call. `must_decide` marks rows the rules layer has to settle without AI,
which is what keeps AI spend down.

| id | title | items | expected_it | expected_category | must_decide |
|----|-------|-------|-------------|-------------------|-------------|
| G-IT-01 | Kaspersky Endpoint Security for Business litsenziyasini uzaytirish (12 oy) | Kaspersky Endpoint Security | yes | Antivirus/EDR | yes |
| G-IT-02 | Приобретение лицензий Microsoft Windows Server 2022 Standard | Microsoft Windows Server 2022 | yes | Microsoft | yes |
| G-IT-03 | Fortinet FortiGate 100F межсетевой экран с подпиской UTM на 1 год | FortiGate 100F UTP bundle | yes | Firewall | yes |
| G-IT-04 | Server HPE ProLiant DL380 Gen11 xarid qilish | HPE ProLiant DL380 Gen11 | yes | Server | yes |
| G-IT-05 | Коммутатор Cisco Catalyst 9200 48 портов | Cisco Catalyst C9200-48P | yes | Network | yes |
| G-IT-06 | Noutbuk Lenovo ThinkPad L15 sotib olish | Lenovo ThinkPad L15 Gen4 | yes | Computer/Notebook | yes |
| G-IT-07 | Видеонаблюдение тизими (CCTV) kameralar va NVR | Hikvision DS-2CD2043G2 | yes | CCTV | yes |
| G-IT-08 | ИБП APC Smart-UPS 3000VA | APC SMT3000RMI2UC | yes | UPS | yes |
| G-IT-09 | Bulutli hosting xizmati (VPS) 12 oy | VPS 8 vCPU 32GB | yes | Cloud | yes |
| G-IT-10 | Принтер МФУ HP LaserJet Pro MFP | HP LaserJet Pro MFP 4103 | yes | Printer/MFP | yes |
| G-IT-11 | DLP tizimi litsenziyasi InfoWatch Traffic Monitor 1 yil | InfoWatch Traffic Monitor | yes | DLP | yes |
| G-IT-12 | Система хранения данных Dell PowerVault ME5024 | Dell PowerVault ME5024 | yes | Storage | yes |
| G-NONIT-01 | Ofis mebeli (stol, stul, shkaf) xarid qilish | Ofis stoli | no | | yes |
| G-NONIT-02 | Приобретение продуктов питания для столовой | Мука высший сорт | no | | yes |
| G-NONIT-03 | Avtomobil Chevrolet Cobalt sotib olish | Chevrolet Cobalt | no | | yes |
| G-NONIT-04 | Kanselyariya tovarlari (qog'oz, ruchka) | A4 qog'oz 80g | no | | yes |
| G-NONIT-05 | Ремонт кровли административного здания | Кровельные работы | no | | yes |
| G-NONIT-06 | Dori vositalari va tibbiy sarf materiallari | Paratsetamol 500mg | no | | yes |
| G-NONIT-07 | Yoqilg'i-moylash materiallari (AI-92 benzin) | AI-92 | no | | yes |
| G-NONIT-08 | Kommunal xizmatlar: elektr energiyasi | Elektr energiyasi | no | | yes |
| G-NONIT-09 | Приобретение спецодежды и СИЗ | Спецодежда летняя | no | | yes |
| G-NONIT-10 | Qurilish materiallari (sement, g'isht) | Sement M400 | no | | yes |
| G-AMB-01 | Ofis uchun stol, stul va kompyuter stoli xarid qilish | Kompyuter stoli | no | | no |
| G-AMB-02 | Оказание услуг по сопровождению информационной системы | Сопровождение ИС | yes | | no |
