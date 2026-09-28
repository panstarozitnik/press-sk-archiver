"""
Pomocné funkcie pre klasifikáciu URL a iné utility.
"""

import re


# ─────────────────────────────────────────────
# URL klasifikácia
# ─────────────────────────────────────────────

# Vzory pre LISTING stránky (kategórie, zoznamy)
_LISTING_PATTERNS = [
    r"/kategori",
    r"/category",
    r"/browse",
    r"/shop\.browse",
    r"/technika",
    r"/knihy",
    r"/casopisy",
    r"/beletria",
    r"/detske",
    r"/nauka",
    r"/hobby",
    r"/biznis",
    r"/zdravie",
    r"/sport",
    r"/pc",
    r"/auto",
    r"/historia",
    r"/veda",
    r"/umenie",
    r"/cestovanie",
    r"/kuchyne",
    r"/zahrada",
    r"/option,com_virtuemart",   # starý VirtueMart e-shop
    r"/page,shop",
    r"/c,[a-z],\d",              # /c,d,16,48 typ URL
    r"press[.]sk/[a-z0-9][a-z0-9.-]*/[a-z],[a-z],\d",  # /cd/n,a,30,0/ a /chovatelstvo-124/o,a,30,30/ typ URL
    r"page=shop\.browse",  # ?page=shop.browse&category_id=... - stary com_phpshop listing
    r"press[.]sk/[a-z0-9][a-z0-9.-]+/?$",  # genericka kategoria /audio/ /chovatelstvo-124/ /1.-a-2.svetova-vojna/
    r"press[.]sk/\d{4}/?$",     # /2011/ alebo /2011 - listing roka
    r"press[.]sk/\d{4}[+]\d+/?$",  # /2011+389/ - listing rok+kategoria
    r"\?start=\d",               # stránkovanie
    r"Itemid=\d",
]

# Vzory pre DETAIL stránky (individuálny produkt)
_PRODUCT_PATTERNS = [
    r"/produkt/",
    r"/product/",
    r"/kniha/",
    r"/casopis/",
    r"/detail/",
    r"/p/\d",
    r"97[89]\d{10}",              # ISBN-13 v URL
    r"/\d{4,}-[a-z\-]{3,}",      # číselné ID + slug
    r"page,shop[.]product_details",
    r"press[.]sk/\d{4}[+]\d+/[a-z]",  # /2012+193/nazov/ - rok+id+slug (produkt)
    r"press[.]sk/\d{4}/[a-z]",        # /2010/nazov/ - rok/slug (produkt)
    r"press[.]sk/[a-z][a-z-]+/[a-z][a-z-]+/?$",  # /kategoria/nazov-produktu/ - slug produkt
    r"page=shop\.flypage",  # ?page=shop.flypage&product_id=... - stary com_phpshop produkt
    r"press[.]sk/[a-z][a-z0-9-]+/[a-z][a-z0-9-]+/?$",  # /kategoria/produkt/ - slug/slug
]

# URL ktoré určite nie sú produkty/listy
_SKIP_PATTERNS = [
    r"/wp-content/",
    r"/wp-admin/",
    r"\.css($|\?)",
    r"\.js($|\?)",
    r"\.xml($|\?)",
    r"/feed",
    r"/rss",
    r"/sitemap",
    r"/login",
    r"/register",
    r"/cart",
    r"/checkout",
    r"/account",
    r"/contact",
    r"/about",
    r"/mapa-stranky",
    r"/ochrana-osobnych",
    r"/obchodne-podmienky",
]


def _matches_any(url: str, patterns: list) -> bool:
    # Normalizuj URL - odstran port (:80, :443 atd) aby patterny fungovali
    url_norm = re.sub(r":\d+/", "/", url).lower()
    return any(re.search(p, url_norm) for p in patterns)


def is_product_url(url: str) -> bool:
    """Produkt má prioritu — ak URL sedí product vzoru, je to produkt."""
    if _matches_any(url, _SKIP_PATTERNS):
        return False
    return _matches_any(url, _PRODUCT_PATTERNS)


def is_listing_url(url: str) -> bool:
    """Listing len ak nie je produkt."""
    if _matches_any(url, _SKIP_PATTERNS):
        return False
    if _matches_any(url, _PRODUCT_PATTERNS):
        return False  # produkt má prioritu
    return _matches_any(url, _LISTING_PATTERNS)


def wayback_url(original: str, timestamp: str) -> str:
    """Poskladá Wayback Machine URL."""
    return f"https://web.archive.org/web/{timestamp}/{original}"


# ─────────────────────────────────────────────
# Text utilities
# ─────────────────────────────────────────────

def safe_text(el) -> str:
    if el is None:
        return ""
    return el.get_text(separator=" ", strip=True)


def clean_price(text: str) -> str:
    """Vytiahne cenu z textu. Napr. '12,99 €' alebo '299 Sk'."""
    m = re.search(r"[\d\s]+[,.]?\d*\s*(?:€|EUR|Sk|SKK|Kč|CZK)", text)
    return m.group(0).strip() if m else text.strip()


def extract_isbn(text: str) -> str:
    """Nájde ISBN-13 alebo ISBN-10 v texte."""
    clean = text.replace("-", "").replace(" ", "")
    m = re.search(r"97[89]\d{10}", clean)
    if m:
        return m.group(0)
    m = re.search(r"\b\d{9}[\dX]\b", clean)
    return m.group(0) if m else ""


def strip_wayback_prefix(url: str) -> str:
    """
    Odstráni Wayback Machine prefix z URL obrázku.
    Formáty ktoré Wayback používa:
      https://web.archive.org/web/20230311055300im_/https://www.press.sk/...
      /web/20230311055300im_/https://www.press.sk/...   (relatívna)
      /web/20230311055300im_/http://www.press.sk/...
    → https://www.press.sk/...
    """
    import re
    if not url:
        return ""
    # Absolútna Wayback URL
    m = re.search(r'https?://web[.]archive[.]org/web/\d+[^/]*/(.+)', url)
    if m:
        result = m.group(1)
        if not result.startswith("http"):
            result = "https://" + result
        return result
    # Relatívna Wayback URL: /web/TIMESTAMP.../https://...
    m = re.search(r'^/web/\d+[^/]*/(.+)', url)
    if m:
        result = m.group(1)
        if not result.startswith("http"):
            result = "https://" + result
        return result
    return url


def extract_img_src(img_tag) -> str:
    """
    Vytiahne URL obrázku aj z lazy-load tagov.
    press.sk používa:
      - data-srcset="https://web.archive.org/web/20230311055300im_/https://www.press.sk/...jpg"
      - data-src="..."
      - src="..."  (fallback, ale môže byť 1px gif)
    Vždy preferuje data-srcset/data-src pred src.
    """
    if img_tag is None:
        return ""

    # 1. data-srcset — Wayback lazy-load (najspoľahlivejší)
    srcset = img_tag.get("data-srcset", "")
    if srcset:
        # Môže obsahovať viacero URL oddelených čiarkou: "url1 1x, url2 2x"
        # Berieme prvú
        first = srcset.split(",")[0].strip().split(" ")[0]
        if first and "1px" not in first and "trans" not in first:
            return fix_image_url(first)

    # 2. data-src
    data_src = img_tag.get("data-src", "")
    if data_src and "1px" not in data_src and "trans" not in data_src:
        return fix_image_url(data_src)

    # 3. data-lazy-src
    lazy = img_tag.get("data-lazy-src", "")
    if lazy and "1px" not in lazy and "trans" not in lazy:
        return fix_image_url(lazy)

    # 4. src — fallback, ale filtruj 1px transparent gify
    src = img_tag.get("src", "")
    if src and "1px" not in src and "trans" not in src:
        return fix_image_url(src)

    return ""


def fix_image_url(src: str, base_domain: str = "https://www.press.sk") -> str:
    """Opraví relatívne a protocol-relative URL obrázkov."""
    if not src:
        return ""
    src = src.strip()
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return base_domain + src
    return src


def load_image_blacklist(path: str = "image_blacklist.txt") -> list:
    """Načíta blacklist URL obrázkov zo súboru. Podporuje wildcard *."""
    import os
    blacklist = []
    # Hľadaj súbor: 1) zadaná cesta, 2) vedľa tohto modulu, 3) root projektu
    candidates = [
        path,
        os.path.join(os.path.dirname(__file__), "..", path),
        os.path.join(os.path.dirname(__file__), "..", "..", path),
    ]
    found_path = None
    for candidate in candidates:
        if os.path.exists(candidate):
            found_path = candidate
            break
    if not found_path:
        return blacklist
    with open(found_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                blacklist.append(line.lower())
    return blacklist


def _is_blacklisted(url: str, blacklist: list) -> bool:
    url_l = url.lower()
    for pattern in blacklist:
        if "*" in pattern:
            parts = [p for p in pattern.split("*") if p]
            if all(p in url_l for p in parts):
                return True
        else:
            if url_l == pattern or url_l.endswith(pattern.lstrip("https://www.press.sk")):
                return True
    return False


# Načítaj blacklist raz pri štarte
_BLACKLIST = load_image_blacklist()


def extract_all_image_urls(html: str) -> list[str]:
    """
    Nájde VŠETKY URL obrázkov v HTML pomocou regex — bez ohľadu na tag/atribút.
    Odstráni Wayback prefix, deduplikuje, vráti len press.sk URL.
    """
    import re
    IMG_EXTS = r'\.(?:jpe?g|png|gif|webp|bmp|svg)(?:\?[^\s"\'<>]*)?'

    patterns = [
        r'https?://web[.]archive[.]org/web/\d+[^/]*/https?://[^\s"\'<>]+' + IMG_EXTS,
        r'/web/\d+[^/]*/https?://[^\s"\'<>]+' + IMG_EXTS,
        r'https?://(?:www[.])?press[.]sk/[^\s"\'<>]+' + IMG_EXTS,
    ]

    found = set()
    for pattern in patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            url = match.group(0)
            # Odstráň Wayback prefix
            m = re.search(r'https?://web[.]archive[.]org/web/\d+[^/]*/(.+)', url)
            if m:
                url = m.group(1)
            else:
                m = re.search(r'^/web/\d+[^/]*/(.+)', url)
                if m:
                    url = m.group(1)
            if 'press.sk' not in url:
                continue
            if any(s in url.lower() for s in ['1px', 'trans.gif', 'spacer', 'pixel', 'favicon']):
                continue
            if not url.startswith('http'):
                url = 'https://' + url
            found.add(url)

    # Filtruj blacklist
    found = {u for u in found if not _is_blacklisted(u, _BLACKLIST)}
    return sorted(found)
