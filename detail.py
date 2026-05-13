"""
Parser pre DETAIL stránky press.sk — individuálny produkt.
Používa schema.org + viacero fallback selektorov.
"""

from bs4 import BeautifulSoup
from parsers.utils import safe_text, clean_price, extract_isbn, fix_image_url, extract_img_src


def parse_detail_page(html: str, wayback_url: str, original_url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    p = {
        "source_url":  original_url,
        "wayback_url": wayback_url,
        "timestamp":   "",
        "title":       "",
        "author":      "",
        "price":       "",
        "isbn":        "",
        "publisher":   "",
        "category":    "",
        "description": "",
        "image_url":   "",
        "image_file":  "",
    }

    # ── Názov ───────────────────────────────────
    for sel in [
        '[itemprop="name"]', "h1.product-title", "h1.nazov",
        ".product-name h1", "h1",
    ]:
        el = soup.select_one(sel)
        if el and safe_text(el):
            p["title"] = safe_text(el)
            break

    # ── Autor ────────────────────────────────────
    for sel in [
        '[itemprop="author"]', ".autor", ".author",
        ".product-author", "span.autor",
    ]:
        el = soup.select_one(sel)
        if el:
            p["author"] = safe_text(el)
            break

    # ── Cena ─────────────────────────────────────
    for sel in [
        '[itemprop="price"]', ".price", ".cena",
        ".product-price", ".our-price", "strong.price",
    ]:
        el = soup.select_one(sel)
        if el:
            p["price"] = clean_price(safe_text(el))
            break

    # ── ISBN ──────────────────────────────────────
    el = soup.find(itemprop="isbn")
    if el:
        p["isbn"] = safe_text(el)
    if not p["isbn"]:
        p["isbn"] = extract_isbn(soup.get_text())
    if not p["isbn"]:
        p["isbn"] = extract_isbn(original_url)

    # ── Vydavateľ ─────────────────────────────────
    for sel in [
        '[itemprop="publisher"]', ".vydavatel", ".publisher", ".nakladatelstvo",
    ]:
        el = soup.select_one(sel)
        if el:
            p["publisher"] = safe_text(el)
            break

    # ── Kategória z breadcrumb ────────────────────
    bc = soup.select(".breadcrumb li, .breadcrumbs li, nav[aria-label='breadcrumb'] li")
    if len(bc) >= 2:
        p["category"] = safe_text(bc[-2])

    # ── Popis ─────────────────────────────────────
    for sel in [
        '[itemprop="description"]', ".product-description",
        ".popis", ".description", "#description",
    ]:
        el = soup.select_one(sel)
        if el:
            p["description"] = safe_text(el)[:500]
            break

    # ── Obrázok ───────────────────────────────────
    for sel in [
        '[itemprop="image"]', ".product-image img",
        ".book-cover img", "#product-image img", "img.cover", ".shop-cat-img img",
    ]:
        el = soup.select_one(sel)
        if el:
            url = extract_img_src(el)
            if url:
                p["image_url"] = url
                break

    return p
