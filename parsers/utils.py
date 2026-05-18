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
    r"97[89]\d{10}",              # ISBN-13 v URL
    r"/\d{4,}-[a-z\-]{3,}",      # číselné ID + slug
    r"page,shop[.]product_details",
    r"press[.]sk/\d{4}[/+]",     # /2010/nazov/ alebo /2012+193/nazov/
    r"press[.]sk/\d{4}$",        # /2010 (bez lomky)
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
