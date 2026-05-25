"""
map_urls.py
===========
Stiahne CDX index pre press.sk v danom časovom rozsahu a roztriedí URL.

Výstup (príklad pre --from-date 20100101 --to-date 20151231):
  output/relevant_2010-2015_001.csv
  output/relevant_2010-2015_002.csv
  output/skipped_2010-2015_001.csv
  ...

Stĺpce: original_url, wayback_url, timestamp, type (LISTING/PRODUCT/skip)

Spustenie:
  python map_urls.py --from-date 20100101 --to-date 20151231
  python map_urls.py --from-date 20160101 --to-date 20201231
  python map_urls.py --from-date 20210101 --to-date 20261231
  python map_urls.py --from-date 20100101 --to-date 20151231 --chunk-size 500000
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
)
CDX_PAGE_SIZE = 10000
CHUNK_SIZE    = 500_000
FIELDS        = ["original_url", "wayback_url", "timestamp", "type"]
# ─────────────────────────────────────────────


def setup_logging(period: str):
    Path("output").mkdir(exist_ok=True)
    log_file = f"output/map_{period}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)


def wayback_url(original: str, timestamp: str) -> str:
    return f"https://web.archive.org/web/{timestamp}/{original}"


# Prípony ktoré úplne ignorujeme — ani do skipped
_IGNORE_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico",
    ".txt",
}

def classify(url: str) -> str:
    # Ignoruj URL podľa prípony
    path = url.split("?")[0].lower()
    ext  = "." + path.rsplit(".", 1)[-1] if "." in path.rsplit("/", 1)[-1] else ""
    if ext in _IGNORE_EXTS:
        return "ignore"
    if is_listing_url(url):  return "LISTING"
    if is_product_url(url):  return "PRODUCT"
    return "skip"


def chunk_path(prefix: str, period: str, n: int) -> str:
    return f"output/{prefix}_{period}_{n:03d}.csv"


class ChunkWriter:
    def __init__(self, prefix: str, period: str, chunk_size: int,
                 start_chunk: int = 1, start_count: int = 0):
        self.prefix     = prefix
        self.period     = period
        self.chunk_size = chunk_size
        self.chunk_n    = start_chunk
        self.count      = start_count
        self.total      = 0
        self._file      = None
        self._writer    = None
        self._open()

    def _open(self):
        if self._file:
            self._file.close()
        path   = chunk_path(self.prefix, self.period, self.chunk_n)
        is_new = not os.path.exists(path)
        self._file   = open(path, "a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=FIELDS)
        if is_new:
            self._writer.writeheader()
        logging.getLogger(__name__).info(f"  → {path}")

    def write(self, row: dict):
        if self.count >= self.chunk_size:
            self._file.close()
            self.chunk_n += 1
            self.count    = 0
            self._open()
        self._writer.writerow(row)
        self.count += 1
        self.total += 1
        if self.total % 50_000 == 0:
            self._file.flush()

    def close(self):
        if self._file:
            self._file.close()


def save_progress(path: str, offset: int, rel: ChunkWriter,
                  skp: ChunkWriter, total_rel: int, total_skp: int):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "next_offset": offset,
            "rel_chunk":   rel.chunk_n,
            "rel_count":   rel.count,
            "skp_chunk":   skp.chunk_n,
            "skp_count":   skp.count,
            "total_rel":   total_rel,
            "total_skp":   total_skp,
        }, f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-date",  required=True,
                    help="Začiatok obdobia YYYYMMDD (napr. 20100101)")
    ap.add_argument("--to-date",    required=True,
                    help="Koniec obdobia YYYYMMDD (napr. 20151231)")
    ap.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    ap.add_argument("--from-offset",type=int, default=None,
                    help="Override: začni od tohto CDX offsetu")
    args = ap.parse_args()

    # Obdobie ako string pre názvy súborov: 2010-2015
    period = f"{args.from_date}-{args.to_date}"
    progress_path = f"output/map_progress_{period}.json"

    log = setup_logging(period)
    log.info(f"Obdobie: {args.from_date} → {args.to_date}  (súbory: *_{period}_*.csv)")

    # CDX query s časovým rozsahom
    cdx_url_base = (
        f"{CDX_BASE}"
        f"&from={args.from_date}"
        f"&to={args.to_date}"
    )

    # ── Resume ────────────────────────────────
    start_offset = 0
    rel_chunk, rel_count = 1, 0
    skp_chunk, skp_count = 1, 0
    total_rel = total_skp = 0

    if args.from_offset is not None:
        start_offset = args.from_offset
        log.info(f"--from-offset={start_offset:,}")
    elif os.path.exists(progress_path):
        try:
            with open(progress_path, encoding="utf-8") as f:
                prog = json.load(f)
            start_offset = prog.get("next_offset", 0)
            rel_chunk    = prog.get("rel_chunk", 1)
            rel_count    = prog.get("rel_count", 0)
            skp_chunk    = prog.get("skp_chunk", 1)
            skp_count    = prog.get("skp_count", 0)
            total_rel    = prog.get("total_rel", 0)
            total_skp    = prog.get("total_skp", 0)
            log.info(f"Resume od offset={start_offset:,} | rel={total_rel:,} skp={total_skp:,}")
        except Exception:
            log.warning("Progress poškodený, začínam odznova")

    rel = ChunkWriter("relevant", period, args.chunk_size, rel_chunk, rel_count)
    skp = ChunkWriter("skipped",  period, args.chunk_size, skp_chunk, skp_count)

    # ── CDX sťahovanie ────────────────────────
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; press-sk-mapper/1.0; "
        "+https://github.com/panstarozitnik/press-sk-archiver)"
    )

    offset       = start_offset
    headers_row  = None
    total_fetched = 0

    log.info("Sťahujem CDX a triedim...")

    while True:
        url = f"{cdx_url_base}&limit={CDX_PAGE_SIZE}&offset={offset}"

        for attempt, wait in enumerate([180, 360, 900]):
            try:
                resp = session.get(url, timeout=300)
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt == 2:
                    log.error(f"CDX zlyhalo po 3 pokusoch: {e}")
                    save_progress(progress_path, offset, rel, skp, total_rel, total_skp)
                    rel.close(); skp.close()
                    raise
                log.warning(f"  Retry {attempt+1}: {e} — čakám {wait}s")
                time.sleep(wait)

        if not resp.text.strip():
            log.warning(f"  Prázdna odpoveď pri offset={offset}, preskakujem")
            offset += CDX_PAGE_SIZE
            time.sleep(3)
            continue

        try:
            raw = resp.json()
        except Exception as e:
            log.warning(f"  JSON chyba pri offset={offset}: {e}, preskakujem")
            offset += CDX_PAGE_SIZE
            time.sleep(3)
            continue

        if not raw:
            break

        if headers_row is None:
            headers_row = raw[0]
            data = raw[1:]
        else:
            data = raw[1:] if raw[0] == headers_row else raw

        if not data:
            log.info("Posledná stránka — koniec CDX pre toto obdobie")
            break

        for record in data:
            row_dict  = dict(zip(headers_row, record))
            original  = row_dict.get("original", "")
            timestamp = row_dict.get("timestamp", "")
            t         = classify(original)
            rec = {
                "original_url": original,
                "wayback_url":  wayback_url(original, timestamp),
                "timestamp":    timestamp,
                "type":         t,
            }
            if t == "ignore":
                continue
            elif t in ("LISTING", "PRODUCT"):
                rel.write(rec)
                total_rel += 1
            else:
                skp.write(rec)
                total_skp += 1

        total_fetched += len(data)

        if total_fetched % 50_000 == 0:
            log.info(f"CDX offset={offset:,} | rel={total_rel:,} skp={total_skp:,}")
            save_progress(progress_path, offset + CDX_PAGE_SIZE,
                          rel, skp, total_rel, total_skp)

        if len(data) < CDX_PAGE_SIZE:
            log.info("Posledná stránka CDX — hotovo")
            break

        offset += CDX_PAGE_SIZE
        time.sleep(3)

    rel.close()
    skp.close()

    if os.path.exists(progress_path):
        os.remove(progress_path)

    log.info("=" * 50)
    log.info(f"Obdobie:  {period}")
    log.info(f"RELEVANT: {total_rel:,}  ({rel.chunk_n} súborov)")
    log.info(f"SKIPPED:  {total_skp:,}  ({skp.chunk_n} súborov)")
    log.info("=" * 50)


if __name__ == "__main__":
    main()
