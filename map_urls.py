"""
map_urls.py
===========
Stiahne CDX index a roztriedí URL do CSV súborov po 500 000 záznamoch:
  output/urls_relevant_001.csv, urls_relevant_002.csv, ...
  output/urls_skipped_001.csv,  urls_skipped_002.csv, ...

Každý CSV má stĺpce:
  original_url, wayback_url, timestamp, type (LISTING/PRODUCT/skip)

Spustenie:
  python map_urls.py
  python map_urls.py --cdx-limit 10000
  python map_urls.py --chunk-size 100000
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
CDX_PAGE_SIZE  = 5000
CDX_PROGRESS   = "output/map_progress.json"
LOG_FILE       = "output/map_urls.log"
FIELDS         = ["original_url", "wayback_url", "timestamp", "type"]
CHUNK_SIZE     = 500_000  # záznamy na jeden súbor
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


def classify(url: str) -> str:
    if is_listing_url(url):  return "LISTING"
    if is_product_url(url):  return "PRODUCT"
    return "skip"


def chunk_path(prefix: str, n: int) -> str:
    return f"output/{prefix}_{n:03d}.csv"


class ChunkWriter:
    """Zapisuje do CSV súborov po CHUNK_SIZE riadkoch."""
    def __init__(self, prefix: str, chunk_size: int, start_chunk: int = 1, start_count: int = 0):
        self.prefix     = prefix
        self.chunk_size = chunk_size
        self.chunk_n    = start_chunk
        self.count      = start_count  # riadky v aktuálnom chunku
        self.total      = 0
        self._file      = None
        self._writer    = None
        self._open()

    def _open(self):
        if self._file:
            self._file.close()
        path = chunk_path(self.prefix, self.chunk_n)
        is_new = not os.path.exists(path)
        self._file   = open(path, "a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=FIELDS)
        if is_new:
            self._writer.writeheader()
        log.info(f"  → {path}")

    def write(self, row: dict):
        if self.count >= self.chunk_size:
            self._file.close()
            self.chunk_n += 1
            self.count    = 0
            self._open()
        self._writer.writerow(row)
        self.count += 1
        self.total += 1
        if self.total % 50000 == 0:
            self._file.flush()
            log.info(f"  {self.prefix}: {self.total:,} záznamov ({self.chunk_n} súborov)")

    def close(self):
        if self._file:
            self._file.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdx-limit",  type=int, default=None)
    ap.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    ap.add_argument("--from-offset", type=int, default=None, help="Začni od tohto CDX offsetu")
    ap.add_argument("--end-offset",  type=int, default=None, help="Zastav pri tomto CDX offsete")
    args = ap.parse_args()

    Path("output").mkdir(exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; press-sk-mapper/1.0; "
        "+https://github.com/panstarozitnik/press-sk-archiver)"
    )

    # ── Resume stav ───────────────────────────
    start_offset        = 0
    rel_chunk, rel_count = 1, 0
    skp_chunk, skp_count = 1, 0
    total_rel = total_skp = 0

    if os.path.exists(CDX_PROGRESS):
        try:
            with open(CDX_PROGRESS, encoding="utf-8") as f:
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
            log.warning("Progress súbor poškodený, začínam odznova")

    # --from-offset prepíše resume offset (ale zachová čísla chunkov)
    if args.from_offset is not None:
        log.info(f"--from-offset={args.from_offset:,} (prepíše resume offset)")
        start_offset = args.from_offset

    rel = ChunkWriter("urls_relevant", args.chunk_size, rel_chunk, rel_count)
    skp = ChunkWriter("urls_skipped",  args.chunk_size, skp_chunk, skp_count)

    # ── CDX sťahovanie ────────────────────────
    offset       = start_offset
    headers_row  = None
    total_fetched = 0

    log.info("Sťahujem CDX a triedim...")

    while True:
        url = f"{CDX_BASE}&limit={CDX_PAGE_SIZE}&offset={offset}"

        for attempt, wait in enumerate([60, 120, 300]):
            try:
                resp = session.get(url, timeout=90)
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt == 2:
                    log.error(f"CDX zlyhalo po 3 pokusoch: {e}")
                    # Ulož progress a skonči
                    _save_progress(offset, rel, skp, total_rel, total_skp)
                    rel.close(); skp.close()
                    raise
                log.warning(f"  Retry {attempt+1}: {e} — čakám {wait}s")
                time.sleep(wait)

        # Prázdna odpoveď — Wayback niekedy vráti 200 s prázdnym telom
        if not resp.text.strip():
            log.warning(f"  Prázdna odpoveď pri offset={offset}, preskakujem")
            offset += CDX_PAGE_SIZE
            time.sleep(5)
            continue

        try:
            raw = resp.json()
        except Exception as e:
            log.warning(f"  JSON chyba pri offset={offset}: {e}, preskakujem")
            offset += CDX_PAGE_SIZE
            time.sleep(5)
            continue

        if not raw:
            break

        if headers_row is None:
            headers_row = raw[0]
            data = raw[1:]
        else:
            data = raw[1:] if raw and raw[0] == headers_row else raw

        if not data:
            break

        for record in data:
            row_dict = dict(zip(headers_row, record))
            original  = row_dict.get("original", "")
            timestamp = row_dict.get("timestamp", "")
            t         = classify(original)

            rec = {
                "original_url": original,
                "wayback_url":  wayback_url(original, timestamp),
                "timestamp":    timestamp,
                "type":         t,
            }

            if t in ("LISTING", "PRODUCT"):
                rel.write(rec)
                total_rel += 1
            else:
                skp.write(rec)
                total_skp += 1

        total_fetched += len(data)

        if total_fetched % 50000 == 0:
            log.info(f"CDX offset={offset:,} | rel={total_rel:,} skp={total_skp:,}")
            _save_progress(offset + CDX_PAGE_SIZE, rel, skp, total_rel, total_skp)

        if args.cdx_limit and total_fetched >= args.cdx_limit:
            log.info(f"--cdx-limit {args.cdx_limit} dosiahnutý")
            break

        if args.end_offset and offset >= args.end_offset:
            log.info(f"--end-offset {args.end_offset:,} dosiahnutý, zastavujem")
            _save_progress(offset, rel, skp, total_rel, total_skp)
            break

        if len(data) < CDX_PAGE_SIZE:
            log.info("Posledná stránka CDX — hotovo")
            break

        offset += CDX_PAGE_SIZE
        time.sleep(3)

    rel.close()
    skp.close()

    # Vymaž progress po úspešnom dokončení
    if os.path.exists(CDX_PROGRESS):
        os.remove(CDX_PROGRESS)

    log.info("=" * 50)
    log.info(f"LISTING + PRODUCT: {total_rel:,}")
    log.info(f"skip:              {total_skp:,}")
    log.info(f"Súborov relevant:  {rel.chunk_n}")
    log.info(f"Súborov skipped:   {skp.chunk_n}")
    log.info("=" * 50)


def _save_progress(next_offset, rel, skp, total_rel, total_skp):
    with open(CDX_PROGRESS, "w", encoding="utf-8") as f:
        json.dump({
            "next_offset": next_offset,
            "rel_chunk":   rel.chunk_n,
            "rel_count":   rel.count,
            "skp_chunk":   skp.chunk_n,
            "skp_count":   skp.count,
            "total_rel":   total_rel,
            "total_skp":   total_skp,
        }, f)


if __name__ == "__main__":
    main()
