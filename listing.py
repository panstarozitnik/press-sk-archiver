"""
Parser pre LISTING stránky press.sk — stránky so zoznamom produktov.
"""

from bs4 import BeautifulSoup
from parsers.utils import safe_text, clean_price, extract_isbn, fix_image_url, extract_img_src


def parse_listing_page(html: str, wayback_url: str, original_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    products = []

    for parser_fn in [
        _parse_press_sk_modern,
        _parse_virtuemart,
        _parse_table_layout,
        _parse_generic_links,
    ]:
        products = parser_fn(soup)
        if products:
            break

    # Kategória z breadcrumb — spoločná pre celú stránku
    cat = ""
    for sel in ["h1.page-title", "h1.cat-title", "h1", ".breadcrumb li:last-child"]:
        el = soup.select_one(sel)
        if el and safe_text(el):
            cat = safe_text(el)
            break

    for p in products:
        p.setdefault("source_url",  original_url)
        p.setdefault("wayback_url", wayback_url)
        p.setdefault("timestamp",   "")
        p.setdefault("isbn",        "")
        p.setdefault("publisher",   "")
        p.setdefault("description", "")
        p.setdefault("image_file",  "")
        if not p.get("category"):
            p["category"] = cat
        if not p["isbn"] and p.get("title"):
            p["isbn"] = extract_isbn(p["title"])

    return products


# ─────────────────────────────────────────────
# HLAVNÝ DIZAJN press.sk (2015–2023)
# Každý produkt je v: div.shop-category-product
# ─────────────────────────────────────────────

def _parse_press_sk_modern(soup: BeautifulSoup) -> list[dict]:
    products = []

    items = soup.select("div.shop-category-product, div.cs_product_item")
    if not items:
        return []

    for item in items:
        p = _empty_product()

        # Názov
        name_el = item.select_one("h3.product-name a, h2.product-name a, .product-name a")
        if not name_el:
            continue
        p["title"] = safe_text(name_el)

        # Obrázok — z .shop-cat-img img, data-srcset má prioritu
        img = item.select_one(".shop-cat-img img, .browse_top img")
        if img:
            p["image_url"] = extract_img_src(img)

        # Vydavateľ
        mfr = item.select_one("span.manufacturer")
        if mfr:
            p["publisher"] = safe_text(mfr)

        # Cena — prednostne akciová
        for sel in ["span.akcia-cena", "span.productPrice", "span.product-price", "span.price"]:
            el = item.select_one(sel)
            if el:
                p["price"] = clean_price(safe_text(el))
                break

        if p["title"]:
            products.append(p)

    return products


# ─────────────────────────────────────────────
# VirtueMart / starý Joomla (2008–2015)
# ─────────────────────────────────────────────

def _parse_virtuemart(soup: BeautifulSoup) -> list[dict]:
    products = []

    for row in soup.select("table.product-browse tr, .browseProductImage"):
        title_el = row.select_one(".product-name a, .browseProductName a, td.productname a")
        if not title_el:
            continue
        p = _empty_product()
        p["title"] = safe_text(title_el)

        price_el = row.select_one(".productPrice, .pricecolor, td.price")
        if price_el:
            p["price"] = clean_price(safe_text(price_el))

        img = row.select_one("img")
        if img:
            p["image_url"] = extract_img_src(img)

        mfr = row.select_one(".manufacturer, .autor, .browseManufacturer")
        if mfr:
            p["publisher"] = safe_text(mfr)

        if p["title"]:
            products.append(p)

    return products


# ─────────────────────────────────────────────
# Tabuľkový layout
# ─────────────────────────────────────────────

def _parse_table_layout(soup: BeautifulSoup) -> list[dict]:
    products = []
    for row in soup.select("tr"):
        cells = row.select("td")
        if len(cells) < 2:
            continue
        if not any(c.find("img") for c in cells) or not any(c.find("a") for c in cells):
            continue
        p = _empty_product()
        for cell in cells:
            link = cell.find("a")
            if link and safe_text(link) and not p["title"]:
                p["title"] = safe_text(link)
            img = cell.find("img")
            if img and not p["image_url"]:
                p["image_url"] = extract_img_src(img)
        if p["title"] and len(p["title"]) > 3:
            products.append(p)
    return products


# ─────────────────────────────────────────────
# Fallback
# ─────────────────────────────────────────────

def _parse_generic_links(soup: BeautifulSoup) -> list[dict]:
    products = []
    seen = set()
    for a in soup.find_all("a", href=True):
        img = a.find("img")
        text = safe_text(a)
        if not img or not text or len(text) < 5 or text in seen:
            continue
        if any(s in text.lower() for s in ["domov", "kontakt", "košík", "prihlás", "menu"]):
            continue
        p = _empty_product()
        p["title"] = text[:200]
        p["image_url"] = extract_img_src(img)
        seen.add(text)
        products.append(p)
    return products


def _empty_product() -> dict:
    return {
        "title": "", "author": "", "price": "", "isbn": "",
        "publisher": "", "category": "", "description": "",
        "image_url": "", "image_file": "",
    }
