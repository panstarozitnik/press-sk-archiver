"""
Parser pre LISTING stránky press.sk — stránky so zoznamom produktov.

press.sk prešla niekoľkými dizajnmi:
  - ~2008–2015: VirtueMart (Joomla) — tabuľky produktov
  - ~2015–2023: vlastný dizajn — .browse_top karty s lazy-load obrázkami

Parser skúša všetky varianty a vráti zoznam produktov.
"""

from bs4 import BeautifulSoup
from parsers.utils import safe_text, clean_price, extract_isbn, fix_image_url, extract_img_src


def parse_listing_page(html: str, wayback_url: str, original_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    products = []

    for parser_fn in [
        _parse_press_sk_modern,   # hlavný dizajn 2015–2023
        _parse_virtuemart,        # starý Joomla dizajn
        _parse_table_layout,
        _parse_generic_links,
    ]:
        products = parser_fn(soup)
        if products:
            break

    for p in products:
        p.setdefault("source_url",  original_url)
        p.setdefault("wayback_url", wayback_url)
        p.setdefault("timestamp",   "")
        p.setdefault("isbn",        "")
        p.setdefault("publisher",   "")
        p.setdefault("description", "")
        p.setdefault("image_file",  "")
        if not p["isbn"] and p.get("title"):
            p["isbn"] = extract_isbn(p["title"])

    return products


# ─────────────────────────────────────────────
# HLAVNÝ DIZAJN press.sk (2015–2023)
# Štruktúra:
#   <div class="browse_top">
#     <div class="shop-cat-img">
#       <a href="..."><img data-srcset="...wayback...jpg" class="lazyload"/></a>
#     </div>
#   </div>
#   <h3 class="product-name"><a href="...">Názov</a></h3>
#   <span class="manufacturer">Vydavateľ</span>
#   <span class="old-price">11,60 €</span>
#   <span class="akcia-cena ...">7,70 €</span>
# ─────────────────────────────────────────────

def _parse_press_sk_modern(soup: BeautifulSoup) -> list[dict]:
    products = []

    # Každý produkt je obalený v kontajneri — hľadáme product-name ako kotvu
    # keďže browse_top je sibling, nie parent
    for name_el in soup.select("h3.product-name, h2.product-name, .product-name"):
        link = name_el.select_one("a")
        if not link:
            continue

        p = _empty_product()
        p["title"] = safe_text(link)

        # Nájdi predchádzajúci .browse_top sibling
        browse_top = None
        for sib in name_el.previous_siblings:
            if hasattr(sib, "select") and "browse_top" in sib.get("class", []):
                browse_top = sib
                break
            # Niekedy je browse_top obalený ďalším divom
            if hasattr(sib, "select"):
                found = sib.select_one(".browse_top, .shop-cat-img")
                if found:
                    browse_top = sib
                    break

        if browse_top:
            img = browse_top.select_one("img")
            if img:
                p["image_url"] = extract_img_src(img)

        # Vydavateľ — nasledujúci sibling za product-name
        mfr = _next_sibling_with_class(name_el, "manufacturer")
        if mfr:
            p["publisher"] = safe_text(mfr)

        # Cena — prednostne akciová, fallback normálna
        akcia = _next_sibling_with_class(name_el, "akcia-cena")
        normal = _next_sibling_with_class(name_el, "productPrice") or                  _next_sibling_with_class(name_el, "old-price")
        price_el = akcia or normal
        if price_el:
            p["price"] = clean_price(safe_text(price_el))

        # Kategória z breadcrumb alebo page title
        cat = soup.select_one(".breadcrumb li:last-child, h1.page-title, h1.cat-title")
        if cat:
            p["category"] = safe_text(cat)

        if p["title"]:
            products.append(p)

    return products


def _next_sibling_with_class(el, cls):
    """Nájde najbližší nasledujúci sibling s danou CSS triedou."""
    for sib in el.next_siblings:
        if hasattr(sib, "get") and cls in (sib.get("class") or []):
            return sib
    return None


# ─────────────────────────────────────────────
# VARIANT: VirtueMart / starý Joomla (2008–2015)
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
# VARIANT: Tabuľkový layout
# ─────────────────────────────────────────────

def _parse_table_layout(soup: BeautifulSoup) -> list[dict]:
    products = []

    for row in soup.select("tr"):
        cells = row.select("td")
        if len(cells) < 2:
            continue
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
                p["image_url"] = extract_img_src(img)

        if p["title"] and len(p["title"]) > 3:
            products.append(p)

    return products


# ─────────────────────────────────────────────
# FALLBACK: generické linky s obrázkom
# ─────────────────────────────────────────────

def _parse_generic_links(soup: BeautifulSoup) -> list[dict]:
    products = []
    seen = set()

    for a in soup.find_all("a", href=True):
        img = a.find("img")
        text = safe_text(a)
        if not img or not text or len(text) < 5:
            continue
        if text in seen:
            continue
        if any(skip in text.lower() for skip in ["domov", "kontakt", "košík", "prihlás", "menu"]):
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
