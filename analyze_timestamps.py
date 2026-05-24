"""
analyze_timestamps.py
=====================
Prejde všetky relevant_*.csv a skipped_*.csv a vypíše
počty záznamov po rokoch a mesiacoch.

Spustenie:
  python3 analyze_timestamps.py                    → relevant CSV
  python3 analyze_timestamps.py skipped            → skipped CSV
  python3 analyze_timestamps.py all                → oba typy
  python3 analyze_timestamps.py relevant 2008      → len rok 2008
"""

import csv, glob, sys
from collections import defaultdict

def analyze(pattern: str, year_filter: str = None):
    files = sorted(glob.glob(f"output/{pattern}_*.csv"))
    if not files:
        print(f"Žiadne súbory: output/{pattern}_*.csv")
        return

    print(f"\nSpracúvam {len(files)} súborov ({pattern})...\n", flush=True)

    counts = defaultdict(int)
    total  = 0

    for path in files:
        print(f"  {path}", flush=True)
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ts = row.get("timestamp", "")
                if len(ts) < 6:
                    continue
                year  = ts[:4]
                month = ts[4:6]
                if year_filter and year != year_filter:
                    continue
                counts[f"{year}-{month}"] += 1
                total += 1

    if not counts:
        print("Žiadne záznamy.")
        return

    max_count    = max(counts.values())
    current_year = None

    print(f"\n{'Obdobie':<12} {'Počet':>15}  Graf")
    print("=" * 60)

    for key in sorted(counts):
        year = key[:4]
        if year != current_year:
            if current_year is not None:
                print()
            current_year = year

        count  = counts[key]
        bar    = "█" * max(1, min(25, int(count / max_count * 25)))
        marker = " ⚠️" if count > 1_000_000 else ""
        print(f"{key:<12} {count:>15,}  {bar}{marker}", flush=True)

    print("=" * 60)
    print(f"{'SPOLU':<12} {total:>15,}", flush=True)


args    = sys.argv[1:]
pattern = args[0] if args else "relevant"
year    = args[1] if len(args) > 1 else None

if pattern == "all":
    analyze("relevant", year)
    analyze("skipped",  year)
elif pattern in ("relevant", "skipped"):
    analyze(pattern, year)
else:
    print("Použitie: python3 analyze_timestamps.py [relevant|skipped|all] [rok]")
