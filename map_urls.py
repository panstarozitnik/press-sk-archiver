"""
map_urls.py
===========
Stiahne CDX index a roztriedí všetky URL do dvoch CSV:
  output/urls_relevant.csv  — listingy + detaily (budeme scrapovať)
  output/urls_skipped.csv   — zvyšok (homepage, obrázky, JS, atď.)

Každý CSV má stĺpce:
  original_url  — čistá press.sk URL
  wayback_url   — archivovaná URL cez web.archive.org
  timestamp     — čas archivácie (YYYYMMDDHHMMSS)
  type          — LISTING / PRODUCT / skip + dôvod

Spustenie:
  python map_urls.py
  python map_urls.py --cdx-limit 10000
"""

import argparse
import csv
import json
import logging
import os
import time
from pathlib import Path

import requests

from parsers.utils import is_listing_url, is_product_url

# ── Nastavenia ────────────────────────────────
CDX_BASE = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=press.sk/*"
    "&output=json"
    "&fl=original,timestamp,statuscode"
    "&filter=statuscode:200"
    r"&filter=original:.*press\.sk.*/[a-zA-Z]"
)
CDX_PAGE_SIZE  = 5000
CDX_CACHE      = "output/cdx_urls.json"
CDX_PROGRESS   = "output/cdx_urls.json.progress"
OUT_RELEVANT   = "output/urls_relevant.csv"
OUT_SKIPPED    = "output/urls_skipped.csv"
LOG_FILE       = "output/map_urls.log"

RELEVANT_FIELDS = ["original_url", "wayback_url", "timestamp", "type"]
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def wayback_url(original: str, timestamp: str) -> str:
    return f"https://web.archive.org/web/{timestamp}/{original}"


def fetch_cdx(session, cdx_limit=None) -> list[dict]:
    if os.path.exists(CDX_CACHE):
        log.info(f"CDX cache nájdená: {CDX_CACHE}")
        with open(CDX_CACHE, encoding="utf-8") as f:
            return json.load(f)

    all_rows = []
    start_offset = 0

    if os.path.exists(CDX_PROGRESS):
        try:
            with open(CDX_PROGRESS, encoding="utf-8") as f:
                prog = json.load(f)
            all_rows    = prog["rows"]
            start_offset = prog["next_offset"]
            log.info(f"CDX resume od offset={start_offset} ({len(all_rows):,} URL)")
        except Exception:
            all_rows, start_offset = [], 0

    log.info("Sťahujem CDX index...")
    headers_row = None
    offset = start_offset

    while True:
        url = f"{CDX_BASE}&limit={CDX_PAGE_SIZE}&offset={offset}"
        log.info(f"  offset={offset}...")

        for attempt, wait in enumerate([30, 60, 120]):
            try:
                resp = session.get(url, timeout=90)
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt == 2:
                    with open(CDX_PROGRESS, "w", encoding="utf-8") as f:
                        json.dump({"rows": all_rows, "next_offset": offset}, f)
                    raise
                log.warning(f"  Retry {attempt+1}: {e} — čakám {wait}s")
                time.sleep(wait)

        raw = resp.json()
        if not raw:
            break

        if headers_row is None:
            headers_row = raw[0]
            data = raw[1:]
        else:
            data = raw[1:] if raw[0] == headers_row else raw

        if not data:
            break

        rows = [dict(zip(headers_row, r)) for r in data]
        all_rows.extend(rows)
        log.info(f"  Celkom: {len(all_rows):,}")

        with open(CDX_PROGRESS, "w", encoding="utf-8") as f:
            json.dump({"rows": all_rows, "next_offset": offset + CDX_PAGE_SIZE}, f)

        if cdx_limit and len(all_rows) >= cdx_limit:
            all_rows = all_rows[:cdx_limit]
            log.info(f"  --cdx-limit {cdx_limit} dosiahnutý")
            break

        if len(data) < CDX_PAGE_SIZE:
            break

        offset += CDX_PAGE_SIZE
        time.sleep(2)

    log.info(f"CDX hotovo: {len(all_rows):,} URL")

    with open(CDX_CACHE, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False)
    if os.path.exists(CDX_PROGRESS):
        os.remove(CDX_PROGRESS)

    return all_rows


def classify(original: str) -> str:
    if is_listing_url(original):
        return "LISTING"
    if is_product_url(original):
        return "PRODUCT"
    return "skip"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdx-limit", type=int, default=None)
    args = ap.parse_args()

    Path("output").mkdir(exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; press-sk-mapper/1.0; "
        "+https://github.com/panstarozitnik/press-sk-archiver)"
    )

    all_rows = fetch_cdx(session, cdx_limit=args.cdx_limit)

    log.info("Triedidem URL...")

    counts = {"LISTING": 0, "PRODUCT": 0, "skip": 0}

    with open(OUT_RELEVANT, "w", newline="", encoding="utf-8") as f_rel, \
         open(OUT_SKIPPED,  "w", newline="", encoding="utf-8") as f_skip:

        wr = csv.DictWriter(f_rel,  fieldnames=RELEVANT_FIELDS)
        ws = csv.DictWriter(f_skip, fieldnames=RELEVANT_FIELDS)
        wr.writeheader()
        ws.writeheader()

        for row in all_rows:
            original  = row["original"]
            timestamp = row["timestamp"]
            t         = classify(original)
            counts[t] += 1

            rec = {
                "original_url": original,
                "wayback_url":  wayback_url(original, timestamp),
                "timestamp":    timestamp,
                "type":         t,
            }

            if t in ("LISTING", "PRODUCT"):
                wr.writerow(rec)
            else:
                ws.writerow(rec)

    log.info("=" * 50)
    log.info(f"LISTING:  {counts['LISTING']:,}")
    log.info(f"PRODUCT:  {counts['PRODUCT']:,}")
    log.info(f"skip:     {counts['skip']:,}")
    log.info(f"Relevantné → {OUT_RELEVANT}")
    log.info(f"Nerelevantné → {OUT_SKIPPED}")
    log.info("=" * 50)


if __name__ == "__main__":
    main()
