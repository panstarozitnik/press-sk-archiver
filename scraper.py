"""
press.sk Wayback Machine Scraper
=================================
Prechádza VŠETKY archivované URL press.sk cez Wayback CDX API,
deteguje typ stránky (zoznam / detail) a extrahuje produkty.

Inštalácia:
    pip install -r requirements.txt

Spustenie (plný beh):
    python scraper.py

Testovací beh (prvých 30 URL):
    python scraper.py --limit 30

Len CDX index (bez parsingu):
    python scraper.py --cdx-only
"""

import argparse
import csv
import hashlib
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from parsers.listing import parse_listing_page
from parsers.detail  import parse_detail_page
from parsers.utils   import is_listing_url, is_product_url, wayback_url

# ─────────────────────────────────────────────
# NASTAVENIA
# ─────────────────────────────────────────────

OUTPUT_CSV = "output/products.csv"
IMAGES_DIR = "output/images"
CDX_CACHE  = "output/cdx_urls.json"
LOG_FILE   = "output/scraper.log"
DELAY      = 1.5   # sekundy medzi requestmi

CDX_BASE = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=press.sk/*"
    "&output=json"
    "&fl=original,timestamp,statuscode"
    "&filter=statuscode:200"
    r"&filter=original:.*press\.sk.*/[a-zA-Z]"  # Vynech homepage
    # Bez collapse — chceme KAŽDÝ snapshot každej URL
)
CDX_PAGE_SIZE = 5000   # Bezpečná veľkosť stránky — CDX zvládne bez timeoutu

CSV_FIELDS = [
    "source_url", "wayback_url", "timestamp",
    "title", "author", "price", "isbn",
    "publisher", "category", "description",
    "image_urls",    # pipe-separated unikátne čisté URL obrázkov
    "page_urls",     # pipe-separated unikátne URL stránok kde sa produkt našiel
]

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

def setup_logging():
    Path("output").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CDX
# ─────────────────────────────────────────────

def fetch_cdx_urls(session, cdx_limit=None):
    import json

    # Cache ukladáme priebežne — ak spadne, ďalší beh pokračuje od miesta pádu
    CDX_PROGRESS = CDX_CACHE + ".progress"

    # Plná cache existuje — hotovo
    if os.path.exists(CDX_CACHE):
        log.info(f"CDX cache nájdená, načítavam z {CDX_CACHE}...")
        with open(CDX_CACHE, encoding="utf-8") as f:
            return json.load(f)

    # Priebežná cache existuje — pokračuj od posledného offsetu
    all_rows = []
    start_offset = 0
    if os.path.exists(CDX_PROGRESS):
        try:
            with open(CDX_PROGRESS, encoding="utf-8") as f:
                progress = json.load(f)
            all_rows = progress["rows"]
            start_offset = progress["next_offset"]
            log.info(f"CDX resume: pokračujem od offset={start_offset} ({len(all_rows):,} URL už stiahnutých)")
        except Exception:
            log.warning("CDX progress súbor poškodený, začínam odznova")
            all_rows = []
            start_offset = 0

    log.info("Sťahujem CDX index po stránkach...")

    headers = None
    offset = start_offset

    while True:
        url = f"{CDX_BASE}&limit={CDX_PAGE_SIZE}&offset={offset}"
        log.info(f"  CDX offset={offset}...")

        # Exponenciálny backoff: 30s, 60s, 120s
        wait_times = [30, 60, 120]
        last_exc = None
        for attempt, wait in enumerate(wait_times):
            try:
                resp = session.get(url, timeout=90)
                resp.raise_for_status()
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                log.warning(f"  Retry {attempt+1}/{len(wait_times)}: {e} — čakám {wait}s")
                time.sleep(wait)

        if last_exc:
            # Ulož progress pred pádom
            with open(CDX_PROGRESS, "w", encoding="utf-8") as f:
                json.dump({"rows": all_rows, "next_offset": offset}, f, ensure_ascii=False)
            log.error(f"CDX zlyhalo po všetkých pokusoch. Progress uložený ({len(all_rows):,} URL). Spusti znova.")
            raise last_exc

        raw = resp.json()
        if not raw:
            break

        if headers is None:
            headers = raw[0]
            data = raw[1:]
        else:
            data = raw[1:] if raw[0] == headers else raw

        if not data:
            break

        rows = [dict(zip(headers, r)) for r in data]
        all_rows.extend(rows)
        log.info(f"  Celkom: {len(all_rows):,} URL")

        # Test mód — zastav po dosiahnutí cdx_limit
        if cdx_limit and len(all_rows) >= cdx_limit:
            log.info(f"  --cdx-limit {cdx_limit} dosiahnutý, zastavujem CDX sťahovanie")
            all_rows = all_rows[:cdx_limit]
            break

        # Priebežne ulož progress po každej stránke
        with open(CDX_PROGRESS, "w", encoding="utf-8") as f:
            json.dump({"rows": all_rows, "next_offset": offset + CDX_PAGE_SIZE}, f, ensure_ascii=False)

        if len(data) < CDX_PAGE_SIZE:
            break

        offset += CDX_PAGE_SIZE
        time.sleep(2)  # Trochu dlhšia pauza — šetri Wayback

    log.info(f"CDX hotovo: {len(all_rows):,} unikátnych URL")

    # Ulož finálnu cache a vymaž progress
    with open(CDX_CACHE, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False)
    if os.path.exists(CDX_PROGRESS):
        os.remove(CDX_PROGRESS)

    return all_rows

# ─────────────────────────────────────────────
# OBRÁZKY
# ─────────────────────────────────────────────

def download_image(img_url, key, session):
    ext = os.path.splitext(urlparse(img_url).path)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        ext = ".jpg"
    filename = f"{key}{ext}"
    path = os.path.join(IMAGES_DIR, filename)
    if os.path.exists(path):
        return filename
    try:
        r = session.get(img_url, timeout=15, stream=True)
        if r.status_code == 200 and "image" in r.headers.get("Content-Type", ""):
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return filename
    except Exception as e:
        log.debug(f"Obrázok zlyhal ({img_url}): {e}")
    return ""

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    setup_logging()
    Path(IMAGES_DIR).mkdir(parents=True, exist_ok=True)

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit",     type=int, default=None, help="Max počet relevantných URL na parsovanie")
    ap.add_argument("--cdx-limit", type=int, default=None, help="Max počet URL stiahnutých z CDX (pre test, napr. 10000)")
    ap.add_argument("--cdx-only",  action="store_true")
    ap.add_argument("--no-images", action="store_true")
    args = ap.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; press-sk-archiver/1.0; "
        "+https://github.com/panstarozitnik/press-sk-archiver)"
    )

    all_urls = fetch_cdx_urls(session, cdx_limit=args.cdx_limit)
    if args.cdx_only:
        log.info("--cdx-only hotovo.")
        return

    # Diagnostika — ukaž prvých 20 URL zo CDX bez ohľadu na filter
    log.info("=== Prvých 20 URL z CDX (pre diagnostiku filtrov) ===")
    for r in all_urls[:20]:
        listing = is_listing_url(r["original"])
        product = is_product_url(r["original"])
        tag = "LISTING" if listing else ("PRODUCT" if product else "skip")
        log.info(f"  [{tag}] {r['original']}")
    log.info("=" * 50)

    relevant = [
        r for r in all_urls
        if is_listing_url(r["original"]) or is_product_url(r["original"])
    ]
    log.info(f"Relevantných URL: {len(relevant):,} z {len(all_urls):,}")
    log.info("Ukážka relevantných (prvých 10):")
    for r in relevant[:10]:
        log.info(f"  [{r['timestamp']}] {r['original']}")

    if args.limit:
        relevant = relevant[:args.limit]

    # Deduplikácia — rovnaká kniha môže byť na viacerých snapshotoch
    seen_products  = {}   # dedup_key → set of image URLs
    seen_page_urls = {}   # dedup_key → set of page URLs
    product_rows   = {}   # dedup_key → product dict (pre merge)

    # Načítaj existujúce produkty pre resume + merge obrázkov
    done = set()
    if os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add(row.get("source_url", ""))
                title = row.get("title", "").lower().strip()
                author = row.get("author", "").lower().strip()
                if title:
                    key = (title, author)
                    product_rows[key] = dict(row)
                    img_urls = row.get("image_urls", "")
                    seen_products[key] = set(u for u in img_urls.split("|") if u)
                    page_urls_str = row.get("page_urls", "")
                    seen_page_urls[key] = set(u for u in page_urls_str.split("|") if u)
        log.info(f"Resume: {len(done)} URL preskočených, {len(product_rows)} produktov načítaných")

    def flush_csv():
        """Prepíše celý CSV súbor aktuálnym stavom product_rows."""
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            w.writeheader()
            for r in product_rows.values():
                w.writerow(r)

    # Úvodný zápis — existujúce produkty (pri resume)
    flush_csv()

    total = len(relevant)
    saved = errors = 0

    for i, row in enumerate(relevant, 1):
        original  = row["original"]
        timestamp = row["timestamp"]
        wb        = wayback_url(original, timestamp)

        if original in done:
            continue

        log.info(f"[{i}/{total}] {wb}")

        try:
            time.sleep(DELAY)
            resp = session.get(wb, timeout=25)
            if resp.status_code != 200:
                log.warning(f"  HTTP {resp.status_code}")
                errors += 1
                continue

            if is_listing_url(original):
                products = parse_listing_page(resp.text, wb, original)
                with_img = sum(1 for p in products if p.get("image_urls"))
                log.info(f"  → listing, {len(products)} produktov, {with_img} s obrázkom")
                # Detail každého produktu
                for p in products:
                    log.info(f"    [{'+' if p.get('image_urls') else '!'}] {p.get('title','?')[:50]} | img: {p.get('image_urls','')[:60] or 'CHÝBA'}")
            else:
                p = parse_detail_page(resp.text, wb, original)
                products = [p] if p and p.get("title") else []

            for p in products:
                dedup_key = (
                    p.get("title", "").lower().strip(),
                    p.get("author", "").lower().strip(),
                )
                if not dedup_key[0]:
                    continue

                # Rozdeľ pipe-separated URL na individuálne — filtruj prázdne
                new_imgs = {u for u in p.get("image_urls", "").split("|") if u.strip()}

                if dedup_key in seen_products:
                    changed = False
                    # Merge obrázkov
                    before = len(seen_products[dedup_key])
                    seen_products[dedup_key].update(new_imgs)
                    if len(seen_products[dedup_key]) > before:
                        product_rows[dedup_key]["image_urls"] = "|".join(
                            sorted(seen_products[dedup_key])
                        )
                        changed = True
                    # Merge page_urls
                    if original not in seen_page_urls[dedup_key]:
                        seen_page_urls[dedup_key].add(original)
                        product_rows[dedup_key]["page_urls"] = "|".join(
                            sorted(seen_page_urls[dedup_key])
                        )
                        changed = True
                    continue

                # Nový produkt
                seen_products[dedup_key] = set(new_imgs)
                seen_page_urls[dedup_key] = {original}
                p.setdefault("source_url",  original)
                p.setdefault("wayback_url", wb)
                p.setdefault("timestamp",   timestamp)
                p["image_urls"] = "|".join(sorted(new_imgs))
                p["page_urls"]  = original
                product_rows[dedup_key] = p
                saved += 1

            # Prepíš CSV s aktuálnym stavom
            flush_csv()

        except requests.exceptions.Timeout:
            log.warning("  Timeout")
            errors += 1
        except Exception as e:
            log.error(f"  Chyba: {e}")
            errors += 1

    log.info("=" * 50)
    log.info(f"HOTOVO — {saved} produktov, {errors} chýb")
    log.info(f"CSV: {OUTPUT_CSV} | Obrázky: {IMAGES_DIR}/")
    log.info("=" * 50)


if __name__ == "__main__":
    main()
