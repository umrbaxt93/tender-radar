import sqlite3
from pathlib import Path
db = Path(__file__).resolve().parent / "data" / "softy_procurement.db"
c = sqlite3.connect(str(db))
# Boyitilmagan = placeholder sarlavha (monoton belgi; supplier/buyer bo'shligiga
# qaralmaydi, chunki ba'zi shartnomalarda ular tabiiy bo'sh)
print(c.execute(
    "SELECT COUNT(*) FROM lots WHERE platform_id='ebirja' "
    "AND id LIKE 'ebirja_ebirja_c_%' "
    "AND title LIKE 'E-Birja shartnoma%'").fetchone()[0])
