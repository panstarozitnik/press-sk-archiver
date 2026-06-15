"""
Parser pre DETAIL stránky press.sk — individuálny produkt.
Používa schema.org + viacero fallback selektorov.
"""

from bs4 import BeautifulSoup
from parsers.utils import safe_text, clean_price, extract_isbn, extract_all_image_urls


def parse_detail_page(html: str, wayback_url: str, original_url: str) -> dict:
    soup = BeautifulSoup(html, "xml")
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
        "image_urls":  "",
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

    # ── Popis — aj flypage-longdesc ───────────────
    for sel in [
        '[itemprop="description"]', ".product-description",
        ".popis", ".description", "#description",
        ".flypage-longdesc-txt",
    ]:
        el = soup.select_one(sel)
        if el:
            text = safe_text(el)
            # Odstran prefix "Popis titulu:"
            if text.startswith("Popis titulu:"):
                text = text[len("Popis titulu:"):].strip()
            p["description"] = text[:500]
            break

    # ── Vydavateľ — aj z flypage textu ───────────
    if not p["publisher"]:
        for sel in [
            '[itemprop="publisher"]', ".vydavatel", ".publisher",
            ".nakladatelstvo", ".browse-publish",
        ]:
            el = soup.select_one(sel)
            if el:
                pub = safe_text(el)
                for prefix in ["Vydáva: ", "Vydáva:", "Vydava: "]:
                    if pub.startswith(prefix):
                        pub = pub[len(prefix):]
                p["publisher"] = pub.strip()
                break

    # ── Obrázky — všetky grafické URL v HTML ─────
    # Priorita: product_images_history (obálky starších čísiel) + bežné obrázky
    history_imgs = []
    for a in soup.select(".product_images_history_image a[href]"):
        href = a.get("href", "")
        if href and any(ext in href.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
            from parsers.utils import strip_wayback_prefix
            clean = strip_wayback_prefix(href)
            if "press.sk" in clean and "thumb_" not in clean:
                history_imgs.append(clean)

    imgs = extract_all_image_urls(html)
    # Spoj: history obrázky prvé (sú kvalitnejšie — full size), potom ostatné
    all_imgs = list(dict.fromkeys(history_imgs + imgs))  # dedup zachovajúc poradie
    p["image_urls"] = "|".join(all_imgs)

    return p
