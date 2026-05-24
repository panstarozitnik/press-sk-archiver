"""
Zistí počet CDX záznamov pre press.sk (odhad cez binárne hľadanie).

Spustenie:
  python3 cdx_count.py 2008        → po mesiacoch
  python3 cdx_count.py 200810      → po dňoch
"""
import urllib.request, time, sys, calendar, json

BASE = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=press.sk/*"
    "&output=json"
    "&fl=original"
    "&filter=statuscode:200"
)

def has_record_at(from_date: str, to_date: str, offset: int) -> bool:
    url = f"{BASE}&from={from_date}&to={to_date}&limit=1&offset={offset}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=45) as r:
                data = json.loads(r.read())
            rows = [x for x in data if x and x[0] != "original"]
            return len(rows) > 0
        except:
            if attempt == 2:
                return False
            time.sleep(10)
    return False

def estimate_count(from_date: str, to_date: str) -> str:
    """Vráti odhad počtu ako string napr. '~5,000,000'."""
    # Testuj exponenciálne — 1k, 10k, 100k, 1M, 5M, 10M...
    thresholds = [100, 1_000, 10_000, 100_000, 500_000,
                  1_000_000, 2_000_000, 5_000_000, 10_000_000]

    last_true = 0
    for t in thresholds:
        if has_record_at(from_date, to_date, t):
            last_true = t
            time.sleep(0.3)
        else:
            # Medzi last_true a t
            if last_true == 0:
                return f"< {t:,}"
            return f"~{last_true:,} – {t:,}"

    return f"> {thresholds[-1]:,}"

def report_by_month(year: int):
    print(f"\n=== CDX snapshotov — {year} (po mesiacoch) ===\n", flush=True)
    print(f"{'Mesiac':<12} {'Odhad počtu':>25}", flush=True)
    print("-" * 40, flush=True)
    for month in range(1, 13):
        from_date = f"{year}{month:02d}01"
        to_date   = f"{year}{month:02d}31"
        est = estimate_count(from_date, to_date)
        label = f"{year}-{month:02d}"
        print(f"{label:<12} {est:>25}", flush=True)
        time.sleep(1)
    print("-" * 40, flush=True)

def report_by_day(year: int, month: int):
    days = calendar.monthrange(year, month)[1]
    print(f"\n=== CDX snapshotov — {year}-{month:02d} (po dňoch) ===\n", flush=True)
    print(f"{'Deň':<14} {'Odhad počtu':>25}", flush=True)
    print("-" * 42, flush=True)
    for day in range(1, days + 1):
        date = f"{year}{month:02d}{day:02d}"
        est = estimate_count(date, date)
        label = f"{year}-{month:02d}-{day:02d}"
        print(f"{label:<14} {est:>25}", flush=True)
        time.sleep(0.5)
    print("-" * 42, flush=True)

# ── Main ──
arg = sys.argv[1] if len(sys.argv) > 1 else "2008"
if len(arg) == 4:
    report_by_month(int(arg))
elif len(arg) == 6:
    report_by_day(int(arg[:4]), int(arg[4:6]))
else:
    print("Použitie: python3 cdx_count.py 2008 alebo 200810")
