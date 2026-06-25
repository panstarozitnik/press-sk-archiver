import argparse
import csv
import sys
import logging
import os
import time
from pathlib import Path

import requests

from parsers.listing import parse_listing_page
from parsers.detail  import parse_detail_page
from parsers.utils   import is_listing_url, is_product_url

csv.field_size_limit(sys.maxsize)

PRODUCTS_CSV     = "output/products.csv"
SPRACOVANE_CSV   = "output/spracovane.csv"
NESPRACOVANE_CSV = "output/nespracovane.csv"
LOG_FILE         = "output/scraper.log"
DELAY            = 1.5

PRODUCT_FIELDS = [
    "source_url", "wayback_url", "timestamp",
    "title", "author", "price", "isbn",
    "publisher", "category", "description",
    "image_urls", "page_urls",
]
INPUT_FIELDS = ["original_url", "wayback_url", "timestamp", "type", "products_found"]


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
    return logging.getLogger(__name__)


def flush_csv(products):
    with open(PRODUCTS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PRODUCT_FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in products.values():
            w.writerow(row)


def dedup_images_by_filename(urls: set) -> list:
    """
    Z množiny Wayback im_ URL zachová len jeden URL per filename.
    Preferuje najstarší timestamp (najbližší k originálu).
    """
    import re, os
    by_name = {}
    for url in urls:
        if not url.strip():
            continue
        m = re.match(r"https?://web\.archive\.org/web/(\d+)im_/https?://.+/([^/?]+\.\w+)", url)
        if m:
            ts   = m.group(1)
            name = m.group(2).lower()
        else:
            name = os.path.basename(url.split("?")[0]).lower()
            ts   = "99999999999999"
        if name not in by_name or ts < by_name[name][0]:
            by_name[name] = (ts, url)
    return [v[1] for v in sorted(by_name.values(), key=lambda x: x[1])]


def load_products():
    products = {}
    if not os.path.exists(PRODUCTS_CSV):
        return products
    with open(PRODUCTS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            title  = row.get("title", "").lower().strip()
            author = row.get("author", "").lower().strip()
            if title:
                products[(title, author)] = dict(row)
    return products


def append_csv(path, row, fields):
    is_new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if is_new:
            w.writeheader()
        w.writerow(row)


def remove_rows_from_csv(path, processed_urls):
    if not os.path.exists(path):
        return 0
    tmp = path + ".tmp"
    kept = 0
    with open(path, encoding="utf-8") as fin, \
         open(tmp, "w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=reader.fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            if row.get("wayback_url") not in processed_urls:
                writer.writerow(row)
                kept += 1
    os.replace(tmp, path)
    return kept


def scrape_url(wb_url, original_url, session, log):
    try:
        resp = session.get(wb_url, timeout=25)
        if resp.status_code != 200:
            log.warning(f"  HTTP {resp.status_code}")
            return None
        # Oprav enkodovanie - stare stranky su casto windows-1250
        # requests automaticky detekuje ale casto chybuje
        if resp.encoding and resp.encoding.lower() in ("iso-8859-1", "latin-1"):
            # Skus windows-1250 ak je v HTML meta charset
            import re
            meta = re.search(rb'charset=["\']?([\w-]+)', resp.content[:2000], re.I)
            if meta:
                enc = meta.group(1).decode("ascii", errors="ignore")
                resp.encoding = enc
            else:
                resp.encoding = "windows-1250"
        if is_listing_url(original_url):
            products = parse_listing_page(resp.text, wb_url, original_url)
            log.info(f"  -> listing, {len(products)} produktov")
            # Fallback 1: ak listing nenasiel nic, skus detail parser (napr. flypage)
            if not products:
                p = parse_detail_page(resp.text, wb_url, original_url)
                if p and p.get("title"):
                    products = [p]
                    log.info(f"  -> listing fallback na detail, 1 produktov")
            # Fallback 2: ak stale nic a URL ma % enkodovanie, skus decoded URL
            if not products and "%" in wb_url:
                from urllib.parse import unquote
                wb_url_decoded = unquote(wb_url)
                if wb_url_decoded != wb_url:
                    try:
                        resp2 = session.get(wb_url_decoded, timeout=25)
                        if resp2.status_code == 200:
                            products = parse_listing_page(resp2.text, wb_url_decoded, original_url)
                            if not products:
                                p = parse_detail_page(resp2.text, wb_url_decoded, original_url)
                                if p and p.get("title"):
                                    products = [p]
                            if products:
                                log.info(f"  -> decoded URL fallback, {len(products)} produktov")
                    except Exception:
                        pass
        else:
            p = parse_detail_page(resp.text, wb_url, original_url)
            products = [p] if p and p.get("title") else []
            log.info(f"  -> detail, {len(products)} produktov")
        return products
    except requests.exceptions.Timeout:
        log.warning("  Timeout")
        return None
    except Exception as e:
        log.error(f"  Chyba: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",     required=True,
                    help="Vstupny relevant CSV (napr. output/relevant_20020101-20101231_001.csv)")
    ap.add_argument("--limit",     type=int, default=100,
                    help="Pocet URL na spracovanie v tomto behu")
    ap.add_argument("--no-images", action="store_true")
    args = ap.parse_args()

    log = setup_logging()

    if not os.path.exists(args.input):
        log.error(f"Vstupny subor neexistuje: {args.input}")
        return

    products      = load_products()
    seen_products = {k: set(v.get("image_urls","").split("|")) for k, v in products.items()}
    seen_pages    = {k: set(v.get("page_urls","").split("|"))  for k, v in products.items()}
    log.info(f"Nacitanych produktov: {len(products):,}")

    with open(args.input, encoding="utf-8") as f:
        total_remaining = sum(1 for _ in f) - 1
    log.info(f"Zostatok v {args.input}: {total_remaining:,} zaznamov")
    log.info(f"Spracujem: {args.limit} zaznamov")

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; press-sk-scraper/1.0; "
        "+https://github.com/panstarozitnik/press-sk-archiver)"
    )

    processed_urls = set()
    saved = errors = sprac = nesprac = 0

    with open(args.input, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= args.limit:
                break

            wb_url       = row.get("wayback_url", "")
            original_url = row.get("original_url", "")
            timestamp    = row.get("timestamp", "")

            log.info(f"[{i+1}/{args.limit}] {wb_url[-70:]}")
            time.sleep(DELAY)

            found = scrape_url(wb_url, original_url, session, log)
            processed_urls.add(wb_url)

            if found is None:
                row["products_found"] = 0
                append_csv(NESPRACOVANE_CSV, row, INPUT_FIELDS)
                nesprac += 1
                errors  += 1
                continue

            if not found:
                row["products_found"] = 0
                append_csv(NESPRACOVANE_CSV, row, INPUT_FIELDS)
                nesprac += 1
                continue

            for p in found:
                dedup_key = (
                    p.get("title", "").lower().strip(),
                    p.get("author", "").lower().strip(),
                )
                if not dedup_key[0]:
                    continue

                new_imgs  = {u for u in p.get("image_urls","").split("|") if u.strip()}
                new_pages = {original_url} if original_url else set()

                if dedup_key in seen_products:
                    seen_products[dedup_key].update(new_imgs)
                    seen_pages[dedup_key].update(new_pages)
                    products[dedup_key]["image_urls"] = "|".join(dedup_images_by_filename(seen_products[dedup_key]))
                    products[dedup_key]["page_urls"]  = "|".join(sorted(seen_pages[dedup_key]))
                else:
                    seen_products[dedup_key] = new_imgs
                    seen_pages[dedup_key]    = new_pages
                    p["source_url"]  = original_url
                    p["wayback_url"] = wb_url
                    p["timestamp"]   = timestamp
                    p["image_urls"]  = "|".join(dedup_images_by_filename(new_imgs))
                    p["page_urls"]   = "|".join(sorted(new_pages))
                    products[dedup_key] = p
                    saved += 1

            row["products_found"] = len([p for p in found if p.get("title")])
            append_csv(SPRACOVANE_CSV, row, INPUT_FIELDS)
            sprac += 1

    flush_csv(products)
    kept = remove_rows_from_csv(args.input, processed_urls)

    log.info("=" * 55)
    log.info(f"Spracovanych URL:     {sprac + nesprac}")
    log.info(f"  -> uspesne:         {sprac}")
    log.info(f"  -> bez produktu:    {nesprac}")
    log.info(f"Novych produktov:     {saved}")
    log.info(f"Produktov celkom:     {len(products):,}")
    log.info(f"Zostatok v inpute:    {kept:,}")
    log.info("=" * 55)


if __name__ == "__main__":
    main()
