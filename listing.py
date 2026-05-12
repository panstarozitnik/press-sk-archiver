"""
Parser pre LISTING stránky press.sk — stránky so zoznamom produktov.

press.sk prešla niekoľkými dizajnmi:
  - ~2008–2015: VirtueMart (Joomla) — tabuľky produktov
  - ~2015–2020: vlastný dizajn — card grid
  - ~2020+:     moderný e-shop — Bootstrap grid

Parser skúša všetky varianty a vráti zoznam produktov.
"""

from bs4 import BeautifulSoup
from parsers.utils import safe_text, clean_price, extract_isbn, fix_image_url


def parse_listing_page(html: str, wayback_url: str, original_url: str) -> list[dict]:
    """
    Vyparsuje zoznamovú stránku. Vracia list dict-ov s info o produktoch.
    Každý dict má kľúče kompatibilné s CSV_FIELDS v scraper.py.
    """
    soup = BeautifulSoup(html, "lxml")
    products = []

    # Skús každý parser variant — použije prvý ktorý nájde produkty
    for parser_fn in [
        _parse_virtuemart,
        _parse_modern_cards,
        _parse_table_layout,
        _parse_generic_links,
    ]:
        products = parser_fn(soup)
        if products:
            break

    # Doplň spoločné polia
    for p in products:
        p.setdefault("source_url",  original_url)
        p.setdefault("wayback_url", wayback_url)
        p.setdefault("timestamp",   "")
        p.setdefault("isbn",        "")
        p.setdefault("publisher",   "")
        p.setdefault("description", "")
        p.setdefault("image_file",  "")
        # Pokús sa extrahovať ISBN z názvu/URL
        if not p["isbn"] and p.get("title"):
            p["isbn"] = extract_isbn(p["title"])

    return products


# ─────────────────────────────────────────────
# VARIANT 1: VirtueMart / starý Joomla dizajn (2008–2015)
# ─────────────────────────────────────────────

def _parse_virtuemart(soup: BeautifulSoup) -> list[dict]:
    """
    VirtueMart zobrazoval produkty v <table class="product-browse"> alebo
    vnorených divoch s triedou 'product'.
    """
    products = []

    # Varianta A: tabuľka
    for row in soup.select("table.product-browse tr, .browseProductImage"):
        title_el = row.select_one(".product-name a, .browseProductName a, td.productname a")
        if not title_el:
            continue

        p = _empty_product()
        p["title"] = safe_text(title_el)

        price_el = row.select_one(".productPrice, .pricecolor, td.price")
        if price_el:
            p["price"] = clean_price(safe_text(price_el))

        img_el = row.select_one("img")
        if img_el:
            p["image_url"] = fix_image_url(img_el.get("src") or img_el.get("data-src", ""))

        # Autor môže byť v extra riadku alebo atribúte
        mfr = row.select_one(".manufacturer, .autor, .browseManufacturer")
        if mfr:
            p["author"] = safe_text(mfr)

        if p["title"]:
            products.append(p)

    return products


# ─────────────────────────────────────────────
# VARIANT 2: Moderný card grid (~2016–2023)
# ─────────────────────────────────────────────

def _parse_modern_cards(soup: BeautifulSoup) -> list[dict]:
    """
    Moderný dizajn používa Bootstrap karty alebo vlastné product-card divy.
    """
    products = []

    card_selectors = [
        ".product-card",
        ".product-item",
        ".item-product",
        ".book-card",
        ".product",
        "article.product",
        ".produkt",
        "[class*='product-']",
    ]

    cards = []
    for sel in card_selectors:
        cards = soup.select(sel)
        if len(cards) > 1:
            break

    for card in cards:
        p = _empty_product()

        # Názov
        for sel in ["h2 a", "h3 a", "h4 a", ".product-name a", ".title a", ".nazov a", "a.name"]:
            el = card.select_one(sel)
            if el and safe_text(el):
                p["title"] = safe_text(el)
                break

        if not p["title"]:
            # Fallback: akýkoľvek heading
            for sel in ["h2", "h3", "h4", ".product-name", ".title", ".nazov"]:
                el = card.select_one(sel)
                if el and safe_text(el):
                    p["title"] = safe_text(el)
                    break

        # Autor
        for sel in [".author", ".autor", ".author-name", "[class*='author']"]:
            el = card.select_one(sel)
            if el:
                p["author"] = safe_text(el)
                break

        # Cena
        for sel in [".price", ".cena", "[class*='price']", ".product-price"]:
            el = card.select_one(sel)
            if el:
                p["price"] = clean_price(safe_text(el))
                break

        # Obrázok
        img = card.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
            p["image_url"] = fix_image_url(src)

        # Kategória z nadriadeného elementu
        cat_el = soup.select_one("h1, .category-title, .page-title")
        if cat_el:
            p["category"] = safe_text(cat_el)

        if p["title"]:
            products.append(p)

    return products


# ─────────────────────────────────────────────
# VARIANT 3: Tabuľkový layout (medziobdobie)
# ─────────────────────────────────────────────

def _parse_table_layout(soup: BeautifulSoup) -> list[dict]:
    products = []

    for row in soup.select("tr"):
        cells = row.select("td")
        if len(cells) < 2:
            continue

        # Hľadáme riadok kde je obrázok a text vedľa seba
        has_img  = any(c.find("img") for c in cells)
        has_link = any(c.find("a") for c in cells)
        if not (has_img and has_link):
            continue

        p = _empty_product()
        for cell in cells:
            link = cell.find("a")
            if link and safe_text(link) and not p["title"]:
                p["title"] = safe_text(link)
            img = cell.find("img")
            if img and not p["image_url"]:
                p["image_url"] = fix_image_url(img.get("src", ""))

        if p["title"] and len(p["title"]) > 3:
            products.append(p)

    return products


# ─────────────────────────────────────────────
# VARIANT 4: Generický fallback — nájdi všetky linky s obrázkom
# ─────────────────────────────────────────────

def _parse_generic_links(soup: BeautifulSoup) -> list[dict]:
    """
    Posledná možnosť: hľadá <a> tagy ktoré obsahujú obrázok + text.
    Funguje pre väčšinu e-shopov aj bez znalosti štruktúry.
    """
    products = []
    seen_titles = set()

    for a in soup.find_all("a", href=True):
        img = a.find("img")
        text = safe_text(a)

        if not img or not text or len(text) < 5:
            continue
        if text in seen_titles:
            continue
        # Filtruj navigáciu, menu, atď.
        if any(skip in text.lower() for skip in ["domov", "kontakt", "košík", "prihlás"]):
            continue

        p = _empty_product()
        p["title"] = text[:200]
        p["image_url"] = fix_image_url(img.get("src") or img.get("data-src", ""))
        seen_titles.add(text)
        products.append(p)

    return products


# ─────────────────────────────────────────────

def _empty_product() -> dict:
    return {
        "title":     "",
        "author":    "",
        "price":     "",
        "isbn":      "",
        "publisher": "",
        "category":  "",
        "description": "",
        "image_url": "",
        "image_file": "",
    }
