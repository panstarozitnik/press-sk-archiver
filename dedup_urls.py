"""
dedup_urls.py
=============
Prejde všetky urls_relevant_*.csv a urls_skipped_*.csv,
odstráni duplicity podľa (original_url, timestamp)
a zapíše čisté výsledky do output/urls_relevant_dedup.csv a urls_skipped_dedup.csv

Spustenie:
  python dedup_urls.py
"""

import csv
import glob
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

FIELDS = ["original_url", "wayback_url", "timestamp", "type"]


def dedup_files(pattern: str, output: str):
    files = sorted(glob.glob(pattern))
    if not files:
        log.info(f"Žiadne súbory pre vzor: {pattern}")
        return 0

    log.info(f"Spracúvam {len(files)} súborov → {output}")
    seen = set()
    written = duplicates = 0

    with open(output, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)
        writer.writeheader()

        for path in files:
            log.info(f"  {path}")
            with open(path, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    key = (row.get("original_url", ""), row.get("timestamp", ""))
                    if key in seen:
                        duplicates += 1
                        continue
                    seen.add(key)
                    writer.writerow({k: row.get(k, "") for k in FIELDS})
                    written += 1

            if written % 500000 == 0 and written > 0:
                log.info(f"  Zapísaných: {written:,}, duplikátov: {duplicates:,}")

    log.info(f"  Hotovo: {written:,} unikátnych, {duplicates:,} duplikátov odstránených")
    return written


Path("output").mkdir(exist_ok=True)

rel = dedup_files("output/urls_relevant_*.csv", "output/urls_relevant_dedup.csv")
skp = dedup_files("output/urls_skipped_*.csv",  "output/urls_skipped_dedup.csv")

log.info("=" * 50)
log.info(f"Relevant unikátnych: {rel:,}")
log.info(f"Skipped unikátnych:  {skp:,}")
log.info("=" * 50)
