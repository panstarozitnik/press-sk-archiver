"""
Parser pre LISTING stránky press.sk.
"""

from bs4 import BeautifulSoup
from parsers.utils import safe_text, clean_price, extract_isbn, extract_img_src, strip_wayback_prefix


def parse_listing_page(html: str, wayback_url: str, original_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    products = []

    for parser_fn in [
        _parse_wrapped,       # div.shop-category-product wrapper
        _parse_unwrapped,     # browse_top + h3.product-name bez wrappera
        _parse_virtuemart,
        _parse_generic_links,
    ]:
        products = parser_fn(soup)
        if products:
            break

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
        if not p.get("category"):
            p["category"] = cat
        if not p["isbn"] and p.get("title"):
            p["isbn"] = extract_isbn(p["title"])

    return products


def _img_url(img) -> str:
    """Vytiahne čistú URL obrázku bez Wayback prefixu."""
    raw = extract_img_src(img)
    return strip_wayback_prefix(raw) if raw else ""


def _extract_product_data(name_el, container) -> dict:
    """
    Spoločná extrakcia dát produktu.
    name_el  = <h3 class="product-name"> element
    container = rodičovský alebo susedný blok s obrázkom/cenou
    """
    p = _empty_product()
    link = name_el.select_one("a") if name_el else None
    if not link:
        return p
    p["title"] = safe_text(link)

    # Obrázok — hľadaj v kontajneri
    if container:
        img = container.select_one(".shop-cat-img img, .browse_top img, img")
        if img:
            p["image_urls"] = _img_url(img)

    # Vydavateľ a cena — hľadaj za name_el v siblings
    for sib in name_el.next_siblings:
        if not hasattr(sib, "get"):
            continue
        classes = sib.get("class") or []
        if "manufacturer" in classes and not p["publisher"]:
            p["publisher"] = safe_text(sib)
        if ("akcia-cena" in classes or "productPrice" in classes or "price" in classes) and not p["price"]:
            p["price"] = clean_price(safe_text(sib))

    return p


# ── VARIANT 1: div.shop-category-product wrapper ──────────────────────────────

def _parse_wrapped(soup: BeautifulSoup) -> list[dict]:
    items = soup.select("div.shop-category-product, div.cs_product_item")
    if not items:
        return []

    products = []
    for item in items:
        name_el = item.select_one("h3.product-name, h2.product-name, .product-name")
        if not name_el:
            continue
        p = _extract_product_data(name_el, item)
        if p["title"]:
            products.append(p)
    return products


# ── VARIANT 2: browse_top bez wrappera ────────────────────────────────────────
# Štruktúra:
#   <div class="browse_top">...</div>      ← obrázok
#   <h3 class="product-name">...</h3>     ← názov
#   <span class="manufacturer">...</span>
#   <span class="akcia-cena">...</span>
#
# browse_top a h3 sú siblings na rovnakej úrovni

def _parse_unwrapped(soup: BeautifulSoup) -> list[dict]:
    # Nájdi všetky h3.product-name na stránke
    name_els = soup.select("h3.product-name, h2.product-name")
    if not name_els:
        return []

    products = []
    for name_el in name_els:
        # Hľadaj najbližší predchádzajúci browse_top sibling
        browse_top = None
        for sib in name_el.previous_siblings:
            if not hasattr(sib, "get"):
                continue
            classes = sib.get("class") or []
            if "browse_top" in classes:
                browse_top = sib
                break
            # Niekedy je browse_top vnorený o úroveň vyššie
            found = sib.select_one(".browse_top")
            if found:
                browse_top = found
                break

        p = _extract_product_data(name_el, browse_top)
        if p["title"]:
            products.append(p)

    return products


# ── VARIANT 3: VirtueMart ─────────────────────────────────────────────────────

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
            p["image_urls"] = _img_url(img)
        mfr = row.select_one(".manufacturer, .autor, .browseManufacturer")
        if mfr:
            p["publisher"] = safe_text(mfr)
        if p["title"]:
            products.append(p)
    return products


# ── VARIANT 4: Fallback ───────────────────────────────────────────────────────

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
        p["image_urls"] = _img_url(img)
        seen.add(text)
        products.append(p)
    return products


def _empty_product() -> dict:
    return {
        "title": "", "author": "", "price": "", "isbn": "",
        "publisher": "", "category": "", "description": "",
        "image_urls": "",
    }
