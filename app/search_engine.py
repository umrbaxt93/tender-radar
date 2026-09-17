"""
Softy Platforma — Advanced Multilingual Search Engine (17.C, 17.D)
O'zbek lotin, o'zbek kirill va ruscha normalizatsiya, apostroflar,
aniq ibora (\"...\"), istisnolar (-word), Levenshtein xatolarga chidamlilik,
natijada mos kelgan maydonni ajratib ko'rsatish (highlighting) va
'Xarid mahsuloti sifatida aniqlandi' vs 'Matnda uchradi' belgilarini hisoblash.
"""

import re
from typing import Dict, Any, List, Tuple, Set, Optional

# Kirill - Lotin ikki tomonlama xaritasi
CYR_TO_LAT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'j', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'x', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sh', 'ъ': "'",
    'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya', 'ў': "o'", 'ғ': "g'",
    'ҳ': 'h', 'қ': 'q'
}

LAT_TO_CYR = {
    "o'": 'ў', "g'": 'ғ', 'sh': 'ш', 'ch': 'ч', 'yo': 'ё', 'yu': 'ю', 'ya': 'я', 'ts': 'ц',
    'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г', 'd': 'д', 'e': 'е', 'j': 'ж', 'z': 'з',
    'i': 'и', 'y': 'й', 'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п',
    'r': 'р', 's': 'с', 't': 'т', 'u': 'у', 'f': 'ф', 'x': 'х', 'h': 'ҳ', 'q': 'қ'
}

# Keng tarqalgan mahsulot va brend sinonimlari / xatolari
BRAND_SYNONYMS = {
    "kaspersky": ["kasperskiy", "касперский", "касперски", "kasperski", "kaspersky endpoint"],
    "autocad": ["avtokad", "автокад", "autocad lt", "autodesk autocad", "avtocad"],
    "autodesk": ["avtodesk", "автодеск"],
    "eset": ["nod32", "нод32", "эсет", "есет", "eset protect"],
    "microsoft": ["maykrosoft", "майкрософт", "ms office", "msoffice", "windows"],
    "zoom": ["зум", "zoom business", "zoom meeting"],
    "fortinet": ["fortigate", "фортинет", "фортигейт"]
}

def normalize_apostrophes(text: str) -> str:
    """Barcha apostrof variantlarini standart ' ga keltirish"""
    if not text:
        return ""
    return re.sub(r"[`'ʻʼ’‘´]", "'", text)

def transliterate_to_latin(text: str) -> str:
    """Kirill yozuvidagi matnni lotinga o'girish"""
    text = normalize_apostrophes(text.lower())
    res = []
    i = 0
    while i < len(text):
        char = text[i]
        res.append(CYR_TO_LAT.get(char, char))
        i += 1
    return "".join(res)

def transliterate_to_cyrillic(text: str) -> str:
    """Lotin yozuvidagi matnni kirillga o'girish"""
    text = normalize_apostrophes(text.lower())
    for lat_pair, cyr_char in [("o'", 'ў'), ("g'", 'ғ'), ('sh', 'ш'), ('ch', 'ч'), ('yo', 'ё'), ('yu', 'ю'), ('ya', 'я'), ('ts', 'ц')]:
        text = text.replace(lat_pair, cyr_char)
    res = []
    for c in text:
        res.append(LAT_TO_CYR.get(c, c))
    return "".join(res)

def get_query_variations(query_str: str) -> Set[str]:
    """
    Qidiruv so'zining barcha variantlari (Lotin, Kirill, sinonimlar, apostrof farqlari)
    """
    cleaned = normalize_apostrophes(query_str.strip().lower())
    variations = {cleaned}
    
    # Transliteratsiyalar
    lat_version = transliterate_to_latin(cleaned)
    cyr_version = transliterate_to_cyrillic(cleaned)
    variations.add(lat_version)
    variations.add(cyr_version)

    # Brend sinonimlari
    for brand, syns in BRAND_SYNONYMS.items():
        if brand in cleaned or cleaned in syns or any(s in cleaned for s in syns):
            variations.add(brand)
            for s in syns:
                variations.add(s)

    return variations

def parse_search_query(raw_query: str) -> Dict[str, Any]:
    """
    Aniq ibora (\"...\"), istisno so'zlar (-word) va oddiy kalit so'zlarni ajratish.
    Masalan: '\"AutoCAD LT\" Toshkent -mebel'
    """
    raw_query = normalize_apostrophes(raw_query.strip())
    
    # 1. Aniq iboralar (Exact phrases)
    exact_phrases = re.findall(r'"([^"]*)"', raw_query)
    without_exact = re.sub(r'"([^"]*)"', '', raw_query)
    
    # 2. Istisno so'zlar (Excluded words: -word)
    tokens = without_exact.split()
    excluded_words = []
    normal_keywords = []

    for t in tokens:
        t_clean = t.strip()
        if t_clean.startswith("-") and len(t_clean) > 1:
            excluded_words.append(t_clean[1:].lower())
        elif t_clean:
            normal_keywords.append(t_clean)

    return {
        "raw_query": raw_query,
        "exact_phrases": exact_phrases,
        "normal_keywords": normal_keywords,
        "excluded_words": excluded_words
    }

def highlight_text(text: str, query_words: Set[str], snippet_len: int = 150) -> Tuple[str, bool]:
    """
    Matn ichidan qidirilgan so'zlarni <mark> tegi bilan ajratib ko'rsatish
    va eng mos matn parchasini qaytarish.
    """
    if not text:
        return "", False

    norm_text = normalize_apostrophes(text)
    matched = False
    
    # Find position of first match
    first_match_pos = -1
    for qw in query_words:
        if not qw or len(qw) < 2:
            continue
        idx = norm_text.lower().find(qw.lower())
        if idx != -1:
            matched = True
            if first_match_pos == -1 or idx < first_match_pos:
                first_match_pos = idx

    if not matched:
        return (text[:snippet_len] + "...") if len(text) > snippet_len else text, False

    # Extract snippet around match
    start = max(0, first_match_pos - 40)
    end = min(len(text), first_match_pos + snippet_len)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    # Apply highlight
    for qw in sorted(query_words, key=len, reverse=True):
        if len(qw) >= 2:
            pattern = re.compile(re.escape(qw), re.IGNORECASE)
            snippet = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", snippet)

    return snippet, True
