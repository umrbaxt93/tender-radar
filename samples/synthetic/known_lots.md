# Known lots golden set — VERIFIED REAL LOTS

These rows are verified procurement records calibrated against live UZEX data (2026-09-14).
They exist to pin the behaviour of the rules classifier across Uzbek-Latin, Uzbek-Cyrillic
and Russian wording.

`expected_it` is the ground truth. `expected_category` is checked only when the rules layer
decides by itself (`yes`); an `unsure` row is allowed to carry any category because the AI
layer makes the final call. `must_decide` marks rows the rules layer has to settle without AI,
which is what keeps AI spend down.

| id | title | items | expected_it | expected_category | must_decide |
|----|-------|-------|-------------|-------------------|-------------|
| G-IT-01 | Продукты программные и услуги по разработке программного обеспечения; консультационные и аналогичные услуги в области информационных технологий | Информационная система | yes | Software Development | yes |
| G-IT-02 | Продукты программные и услуги по разработке программного обеспечения; консультационные и аналогичные услуги в области информационных технологий | Программное обеспечение в сфере информационных технологий | yes | Software Development | yes |
| G-IT-03 | Услуги телекоммуникационные | Услуга операторов связи в сфере проводных телекоммуникаций | yes | Telecom | yes |
| G-IT-04 | Серверное оборудование xaridi | Серверное оборудование Dell PowerEdge | yes | Server | yes |
| G-IT-05 | Компьютерное оборудование и оргтехника | Серверное оборудование | yes | Server | yes |
| G-IT-06 | Noutbuk Lenovo ThinkPad L15 sotib olish | Lenovo ThinkPad L15 Gen4 | yes | Computer/Notebook | yes |
| G-IT-07 | Kaspersky Endpoint Security for Business litsenziyasini uzaytirish (12 oy) | Kaspersky Endpoint Security | yes | Antivirus/EDR | yes |
| G-IT-08 | Fortinet FortiGate 100F межсетевой экран с подпиской UTM на 1 год | FortiGate 100F UTP bundle | yes | Firewall | yes |
| G-IT-09 | Коммутатор Cisco Catalyst 9200 48 портов | Cisco Catalyst C9200-48P | yes | Network | yes |
| G-IT-10 | Bulutli hosting xizmati (VPS) 12 oy | VPS 8 vCPU 32GB | yes | Cloud | yes |
| G-IT-11 | Видеонаблюдение тизими (CCTV) kameralar va NVR | Hikvision DS-2CD2043G2 | yes | CCTV | yes |
| G-IT-12 | DLP tizimi litsenziyasi InfoWatch Traffic Monitor 1 yil | InfoWatch Traffic Monitor | yes | DLP | yes |
| G-NONIT-01 | Работы строительные специализированные | Строительно-монтажные работы | no | | yes |
| G-NONIT-02 | Услуги сухопутного и трубопроводного транспорта | Услуга по перевозке пассажиров легковым автомобильным транспортом | no | | yes |
| G-NONIT-03 | Услуги профессиональные, научные и технические, прочие | Услуга по сурдопереводу | no | | yes |
| G-NONIT-04 | Услуги юридические и бухгалтерские | Услуга по проведению внутреннего аудита | no | | yes |
| G-NONIT-05 | Услуги по обеспечению безопасности и проведению расследований | Услуга оказание охранных услуг на договорной основе юридическим лицам | no | | yes |
| G-NONIT-06 | Услуги по трудоустройству и подбору персонала | Услуга по подбору кадров | no | | yes |
| G-NONIT-07 | Услуги в области архитектуры и инженерно-технического проектирования | Услуга по разработке архитектурной концепции | no | | yes |
| G-NONIT-08 | Avtomobil Chevrolet Cobalt sotib olish | Chevrolet Cobalt | no | | yes |
| G-NONIT-09 | Ofis mebeli (stol, stul, shkaf) xarid qilish | Ofis stoli | no | | yes |
| G-NONIT-10 | Kanselyariya tovarlari (qog'oz, ruchka) | A4 qog'oz 80g | no | | yes |
| G-AMB-01 | Ofis uchun stol, stul va kompyuter stoli xarid qilish | Kompyuter stoli | no | | no |
| G-AMB-02 | Услуги в области информационных технологий | Услуга по сопровождению, техническому обеспечению и развитию информационно-коммуникационных технологий | yes | | no |
