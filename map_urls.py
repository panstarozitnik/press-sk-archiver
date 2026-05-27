"""
map_urls.py — CDX text streaming s resumeKey pagination
Každý riadok sa parsuje hneď — žiadny JSON overhead, žiadne duplikáty.
"""

import argparse
import csv
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import requests

from parsers.utils import is_listing_url, is_product_url

CDX_URL = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=press.sk/*"
    "&output=text"           # text streaming — jeden riadok = jeden záznam
    "&fl=original,timestamp"
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


def fetch_page(session, base_url, resume_key=None):
    """
    Stiahne jednu stránku CDX ako text.
    Vráti (riadky, next_resume_key).
    """
    if resume_key:
        url = f"{base_url}&limit={CDX_PAGE_SIZE}&resumeKey={urllib.parse.quote(resume_key)}"
    else:
        url = f"{base_url}&limit={CDX_PAGE_SIZE}"

    for attempt, wait in enumerate([180, 360, 900]):
        try:
            resp = session.get(url, timeout=300, stream=True)
            resp.raise_for_status()
            break
        except Exception as e:
            if attempt == 2:
                raise
            logging.getLogger(__name__).warning(f"  Retry {attempt+1}: {e} — čakám {wait}s")
            time.sleep(wait)

    lines      = []
    resume_key = None

    for raw_line in resp.iter_lines(decode_unicode=True):
        line = raw_line.strip()
        if not line:
            continue

        # resumeKey je base64 encoded — neobsahuje medzery ako normálne URL
        # CDX text formát: "original timestamp" — dva polia oddelené medzerou
        parts = line.split(" ")
        if len(parts) == 2:
            lines.append((parts[0], parts[1]))   # (original, timestamp)
        elif len(parts) == 1:
            # Pravdepodobne resumeKey
            resume_key = parts[0]

    return lines, resume_key


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

    base_url = f"{CDX_URL}&from={args.from_date}&to={args.to_date}"

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
            log.info(f"Resume: rel={total_rel:,} skp={total_skp:,}")
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
    seen          = set()   # Dedup v rámci jedného behu

    log.info("Sťahujem CDX (text streaming + resumeKey)...")

    while True:
        try:
            lines, next_resume_key = fetch_page(session, base_url, resume_key)
        except Exception as e:
            log.error(f"CDX zlyhalo: {e}")
            save_progress(progress_path, resume_key, rel, skp, total_rel, total_skp)
            rel.close(); skp.close()
            raise

        if not lines:
            log.info("Prázdna stránka — koniec CDX")
            break

        page_num      += 1
        total_fetched += len(lines)

        for original, timestamp in lines:
            # Dedup
            key = (original, timestamp)
            if key in seen:
                continue
            seen.add(key)

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

        log.info(f"strana={page_num} | +{len(lines)} riadkov | spolu={total_fetched:,} | rel={total_rel:,} skp={total_skp:,} | resumeKey={'áno' if next_resume_key else 'nie'}")
        if page_num % 10 == 0 or total_fetched % 50_000 == 0:
            save_progress(progress_path, next_resume_key,
                          rel, skp, total_rel, total_skp)

        if not next_resume_key:
            log.info("Žiadny ďalší resumeKey — koniec CDX")
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
