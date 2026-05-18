"""
Parser pre LISTING stránky press.sk.
"""

import sys
from bs4 import BeautifulSoup
from parsers.utils import safe_text, clean_price, extract_isbn, extract_img_src, strip_wayback_prefix, extract_all_image_urls


def parse_listing_page(html: str, wayback_url: str, original_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")

    wrapped   = _parse_wrapped(soup)
    unwrapped = _parse_unwrapped(soup)

    seen_titles = {p["title"].lower() for p in wrapped}
    extra = [p for p in unwrapped if p["title"].lower() not in seen_titles]
    products = wrapped + extra

    if not products:
        products = _parse_virtuemart(soup)
    if not products:
        products = _parse_generic_links(soup)

    # DEBUG — vždy vypíš prvých 5 img tagov
    all_imgs = soup.find_all("img")
    print(f"[IMG-DEBUG] URL={original_url[-50:]}", flush=True)
    print(f"[IMG-DEBUG] img tagov={len(all_imgs)}, produktov={len(products)}", flush=True)
    for i, img in enumerate(all_imgs[:5]):
        print(f"[IMG-DEBUG] img[{i}] src={repr(img.get('src',''))[:70]}", flush=True)
        print(f"[IMG-DEBUG] img[{i}] data-srcset={repr(img.get('data-srcset',''))[:70]}", flush=True)
    sys.stdout.flush()

    # Fallback: ak produkt nemá obrázok, skús regex cez celé HTML jeho kontajnera
    for p in products:
        if not p.get("image_urls"):
            # Nájdi div tohto produktu v soup a extrahuj z neho obrázky
            title = p.get("title", "")
            container = None
            for el in soup.find_all(["h3","h2"], class_="product-name"):
                if title.lower() in safe_text(el).lower():
                    # Vezmi surrounding HTML — parent alebo predchádzajúci sibling
                    parent = el.parent
                    container = str(parent) if parent else ""
                    break
            if container:
                imgs = extract_all_image_urls(container)
                if imgs:
                    p["image_urls"] = "|".join(imgs)

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
    raw = extract_img_src(img)
    return strip_wayback_prefix(raw) if raw else ""


def _parse_wrapped(soup: BeautifulSoup) -> list[dict]:
    items = soup.select("div.shop-category-product, div.cs_product_item")
    if not items:
        return []
    products = []
    for item in items:
        name_el = item.select_one("h3.product-name, h2.product-name, .product-name")
        if not name_el:
            continue
        p = _empty_product()
        link = name_el.select_one("a")
        if not link:
            continue
        p["title"] = safe_text(link)
        img = item.select_one(".shop-cat-img img, .browse_top img")
        if img:
            p["image_urls"] = _img_url(img)
        mfr = item.select_one("span.manufacturer")
        if mfr:
            p["publisher"] = safe_text(mfr)
        for sel in ["span.akcia-cena", "span.productPrice", "span.product-price", "span.price"]:
            el = item.select_one(sel)
            if el:
                p["price"] = clean_price(safe_text(el))
                break
        if p["title"]:
            products.append(p)
    return products


def _parse_unwrapped(soup: BeautifulSoup) -> list[dict]:
    name_els = soup.select("h3.product-name, h2.product-name")
    if not name_els:
        return []
    products = []
    for name_el in name_els:
        link = name_el.select_one("a")
        if not link:
            continue
        p = _empty_product()
        p["title"] = safe_text(link)
        for sib in name_el.previous_siblings:
            if not hasattr(sib, "get"):
                continue
            img = sib.select_one("img") if hasattr(sib, "select_one") else None
            if img:
                p["image_urls"] = _img_url(img)
                break
        for sib in name_el.next_siblings:
            if not hasattr(sib, "get"):
                continue
            classes = sib.get("class") or []
            if "manufacturer" in classes and not p["publisher"]:
                p["publisher"] = safe_text(sib)
            if any(c in classes for c in ["akcia-cena", "productPrice", "price"]) and not p["price"]:
                p["price"] = clean_price(safe_text(sib))
        if p["title"]:
            products.append(p)
    return products


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
