"""
map_urls.py — CDX resume key pagination (stabilnejšie než offset)
"""

import argparse
import csv
import json
import logging
import os
import time
import urllib.parse
from pathlib import Path

import requests

from parsers.utils import is_listing_url, is_product_url

CDX_BASE = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=press.sk/*"
    "&output=json"
    "&fl=original,timestamp,statuscode"
    "&filter=statuscode:200"
    "&showResumeKey=true"
)
CDX_PAGE_SIZE = 5000
CHUNK_SIZE    = 500_000
FIELDS        = ["original_url", "wayback_url", "timestamp", "type"]

_IGNORE_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico", ".txt",
}


def setup_logging(period: str):
    Path("output").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(f"output/map_{period}.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)


def wayback_url(original: str, timestamp: str) -> str:
    return f"https://web.archive.org/web/{timestamp}/{original}"


def classify(url: str) -> str:
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
    def __init__(self, prefix, period, chunk_size, start_chunk=1, start_count=0):
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

    def write(self, row):
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


def save_progress(path, resume_key, rel, skp, total_rel, total_skp):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "resume_key": resume_key,
            "rel_chunk":  rel.chunk_n,
            "rel_count":  rel.count,
            "skp_chunk":  skp.chunk_n,
            "skp_count":  skp.count,
            "total_rel":  total_rel,
            "total_skp":  total_skp,
        }, f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-date",   required=True)
    ap.add_argument("--to-date",     required=True)
    ap.add_argument("--chunk-size",  type=int, default=CHUNK_SIZE)
    ap.add_argument("--from-offset", type=int, default=None,
                    help="Ignorované — zachované pre kompatibilitu")
    args = ap.parse_args()

    period        = f"{args.from_date}-{args.to_date}"
    progress_path = f"output/map_progress_{period}.json"

    log = setup_logging(period)
    log.info(f"Obdobie: {args.from_date} → {args.to_date}")

    cdx_url_base = f"{CDX_BASE}&from={args.from_date}&to={args.to_date}"

    # ── Resume ────────────────────────────────
    resume_key   = None
    rel_chunk, rel_count = 1, 0
    skp_chunk, skp_count = 1, 0
    total_rel = total_skp = 0

    if os.path.exists(progress_path):
        try:
            with open(progress_path, encoding="utf-8") as f:
                prog = json.load(f)
            resume_key = prog.get("resume_key")
            rel_chunk  = prog.get("rel_chunk", 1)
            rel_count  = prog.get("rel_count", 0)
            skp_chunk  = prog.get("skp_chunk", 1)
            skp_count  = prog.get("skp_count", 0)
            total_rel  = prog.get("total_rel", 0)
            total_skp  = prog.get("total_skp", 0)
            log.info(f"Resume: rel={total_rel:,} skp={total_skp:,} key={str(resume_key)[:40]}")
        except Exception:
            log.warning("Progress poškodený, začínam odznova")

    rel = ChunkWriter("relevant", period, args.chunk_size, rel_chunk, rel_count)
    skp = ChunkWriter("skipped",  period, args.chunk_size, skp_chunk, skp_count)

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; press-sk-mapper/1.0; "
        "+https://github.com/panstarozitnik/press-sk-archiver)"
    )

    total_fetched = 0
    page_num      = 0

    log.info("Sťahujem CDX (resume key pagination)...")

    while True:
        if resume_key:
            url = f"{cdx_url_base}&limit={CDX_PAGE_SIZE}&resumeKey={urllib.parse.quote(resume_key)}"
        else:
            url = f"{cdx_url_base}&limit={CDX_PAGE_SIZE}"

        for attempt, wait in enumerate([180, 360, 900]):
            try:
                resp = session.get(url, timeout=300)
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt == 2:
                    log.error(f"CDX zlyhalo: {e}")
                    save_progress(progress_path, resume_key, rel, skp, total_rel, total_skp)
                    rel.close(); skp.close()
                    raise
                log.warning(f"  Retry {attempt+1}: {e} — čakám {wait}s")
                time.sleep(wait)

        if not resp.text.strip():
            log.warning("  Prázdna odpoveď, preskakujem")
            time.sleep(10)
            continue

        try:
            raw = resp.json()
        except Exception as e:
            log.warning(f"  JSON chyba: {e}")
            time.sleep(10)
            continue

        if not raw:
            break

        # DEBUG — pozri posledné 3 riadky odpovede
        log.info(f"  raw[-3:] = {raw[-3:]}")

        # showResumeKey=true pridá na koniec: [["resumeKey"], ["hodnota"]]
        next_resume_key = None
        if len(raw) >= 2 and raw[-2] == ["resumeKey"]:
            next_resume_key = raw[-1][0] if raw[-1] else None
            rows = raw[:-2]
        else:
            rows = raw

        # Odstráň header riadok
        if rows and rows[0] in (["original", "timestamp", "statuscode"], ["original"]):
            rows = rows[1:]

        if not rows:
            log.info("Prázdna stránka — koniec")
            break

        page_num      += 1
        total_fetched += len(rows)

        for record in rows:
            if len(record) < 2:
                continue
            original  = record[0]
            timestamp = record[1]
            t = classify(original)
            if t == "ignore":
                continue
            rec = {
                "original_url": original,
                "wayback_url":  wayback_url(original, timestamp),
                "timestamp":    timestamp,
                "type":         t,
            }
            if t in ("LISTING", "PRODUCT"):
                rel.write(rec); total_rel += 1
            else:
                skp.write(rec); total_skp += 1

        if page_num % 10 == 0 or total_fetched % 50_000 == 0:
            log.info(f"CDX strana={page_num} fetched={total_fetched:,} | rel={total_rel:,} skp={total_skp:,}")
            save_progress(progress_path, next_resume_key, rel, skp, total_rel, total_skp)

        if not next_resume_key:
            log.info("Žiadny ďalší resume key — koniec CDX")
            break

        resume_key = next_resume_key
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
