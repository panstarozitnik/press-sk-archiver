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

CDX_ENDPOINT = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=press.sk/*"
    "&output=json"
    "&fl=original,timestamp,statuscode"
    "&filter=statuscode:200"
    "&collapse=urlkey"
    "&limit=100000"
)

CSV_FIELDS = [
    "source_url", "wayback_url", "timestamp",
    "title", "author", "price", "isbn",
    "publisher", "category", "description",
    "image_url", "image_file",
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

def fetch_cdx_urls(session):
    import json

    if os.path.exists(CDX_CACHE):
        log.info(f"CDX cache nájdená, načítavam z {CDX_CACHE}...")
        with open(CDX_CACHE, encoding="utf-8") as f:
            return json.load(f)

    log.info("Sťahujem CDX index z Wayback Machine (môže trvať minútu)...")
    resp = session.get(CDX_ENDPOINT, timeout=120)
    resp.raise_for_status()
    raw = resp.json()

    if len(raw) < 2:
        return []

    headers = raw[0]
    rows = [dict(zip(headers, r)) for r in raw[1:]]
    log.info(f"CDX: {len(rows):,} unikátnych URL")

    with open(CDX_CACHE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)

    return rows

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
    ap.add_argument("--limit",     type=int, default=None)
    ap.add_argument("--cdx-only",  action="store_true")
    ap.add_argument("--no-images", action="store_true")
    args = ap.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; press-sk-archiver/1.0; "
        "+https://github.com/panstarozitnik/press-sk-archiver)"
    )

    all_urls = fetch_cdx_urls(session)
    if args.cdx_only:
        log.info("--cdx-only hotovo.")
        return

    relevant = [
        r for r in all_urls
        if is_listing_url(r["original"]) or is_product_url(r["original"])
    ]
    log.info(f"Relevantných URL: {len(relevant):,} z {len(all_urls):,}")
    log.info("Ukážka (prvých 10):")
    for r in relevant[:10]:
        log.info(f"  [{r['timestamp']}] {r['original']}")

    if args.limit:
        relevant = relevant[:args.limit]

    # Resume — preskočí už spracované
    done = set()
    if os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add(row.get("source_url", ""))
        log.info(f"Resume: {len(done)} URL preskočených")

    csv_file = open(OUTPUT_CSV, "a", newline="", encoding="utf-8")
    writer   = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, extrasaction="ignore")
    if not done:
        writer.writeheader()

    total = len(relevant)
    saved = errors = 0

    for i, row in enumerate(relevant, 1):
        original  = row["original"]
        timestamp = row["timestamp"]
        wb        = wayback_url(original, timestamp)

        if original in done:
            continue

        log.info(f"[{i}/{total}] {original}")

        try:
            time.sleep(DELAY)
            resp = session.get(wb, timeout=25)
            if resp.status_code != 200:
                log.warning(f"  HTTP {resp.status_code}")
                errors += 1
                continue

            if is_listing_url(original):
                products = parse_listing_page(resp.text, wb, original)
                log.info(f"  → listing, {len(products)} produktov")
            else:
                p = parse_detail_page(resp.text, wb, original)
                products = [p] if p and p.get("title") else []

            for p in products:
                if not args.no_images and p.get("image_url"):
                    key = p.get("isbn") or hashlib.md5(p["image_url"].encode()).hexdigest()[:10]
                    p["image_file"] = download_image(p["image_url"], key, session)

                p.setdefault("source_url",  original)
                p.setdefault("wayback_url", wb)
                p.setdefault("timestamp",   timestamp)
                writer.writerow(p)
                saved += 1

            csv_file.flush()

        except requests.exceptions.Timeout:
            log.warning("  Timeout")
            errors += 1
        except Exception as e:
            log.error(f"  Chyba: {e}")
            errors += 1

    csv_file.close()
    log.info("=" * 50)
    log.info(f"HOTOVO — {saved} produktov, {errors} chýb")
    log.info(f"CSV: {OUTPUT_CSV} | Obrázky: {IMAGES_DIR}/")
    log.info("=" * 50)


if __name__ == "__main__":
    main()
