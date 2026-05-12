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
    r"97[89]\d{10}",             # ISBN-13 v URL
    r"/\d{4,}-[a-z\-]{3,}",     # číselné ID + slug
    r"page,shop\.product_details",
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
    url_lower = url.lower()
    return any(re.search(p, url_lower) for p in patterns)


def is_listing_url(url: str) -> bool:
    if _matches_any(url, _SKIP_PATTERNS):
        return False
    return _matches_any(url, _LISTING_PATTERNS)


def is_product_url(url: str) -> bool:
    if _matches_any(url, _SKIP_PATTERNS):
        return False
    return _matches_any(url, _PRODUCT_PATTERNS)


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
