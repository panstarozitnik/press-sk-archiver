"""
Zistí počet CDX záznamov pre press.sk.

Spustenie:
  python3 cdx_count.py 2008        → prehľad po mesiacoch za rok 2008
  python3 cdx_count.py 200810      → prehľad po dňoch za október 2008
"""
import urllib.request, time, sys, calendar, json

BASE = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=press.sk/*"
    "&output=json"
    "&fl=timestamp"
    "&filter=statuscode:200"
)

def count_range(from_date: str, to_date: str) -> int:
    """
    Stiahne všetky timestamps v rozsahu a vráti počet.
    Efektívne — fl=timestamp je malý payload, limit=100000 na stránku.
    """
    total = 0
    offset = 0
    page_size = 100000
    while True:
        url = f"{BASE}&from={from_date}&to={to_date}&limit={page_size}&offset={offset}"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    data = json.loads(r.read())
                break
            except Exception as e:
                if attempt == 2:
                    return total  # vrátime čo máme
                time.sleep(15)

        rows = [x for x in data if x and x[0] != "timestamp"]
        total += len(rows)
        if len(rows) < page_size:
            break
        offset += page_size
        time.sleep(1)
    return total

def report_by_month(year: int):
    print(f"\n=== CDX snapshotov — {year} (po mesiacoch) ===\n", flush=True)
    print(f"{'Mesiac':<12} {'Počet':>15}", flush=True)
    print("-" * 30, flush=True)
    total = 0
    for month in range(1, 13):
        from_date = f"{year}{month:02d}01"
        to_date   = f"{year}{month:02d}31"
        count = count_range(from_date, to_date)
        label = f"{year}-{month:02d}"
        marker = " ⚠️" if count > 1_000_000 else ""
        print(f"{label:<12} {count:>15,}{marker}", flush=True)
        total += count
        time.sleep(1)
    print("-" * 30, flush=True)
    print(f"{'SPOLU':<12} {total:>15,}", flush=True)

def report_by_day(year: int, month: int):
    days = calendar.monthrange(year, month)[1]
    print(f"\n=== CDX snapshotov — {year}-{month:02d} (po dňoch) ===\n", flush=True)
    print(f"{'Deň':<14} {'Počet':>15}", flush=True)
    print("-" * 32, flush=True)
    total = 0
    for day in range(1, days + 1):
        date = f"{year}{month:02d}{day:02d}"
        count = count_range(date, date)
        label = f"{year}-{month:02d}-{day:02d}"
        marker = " ⚠️" if count > 500_000 else ""
        print(f"{label:<14} {count:>15,}{marker}", flush=True)
        total += count
        time.sleep(1)
    print("-" * 32, flush=True)
    print(f"{'SPOLU':<14} {total:>15,}", flush=True)

# ── Main ──
arg = sys.argv[1] if len(sys.argv) > 1 else "2008"
if len(arg) == 4:
    report_by_month(int(arg))
elif len(arg) == 6:
    report_by_day(int(arg[:4]), int(arg[4:6]))
else:
    print("Použitie: python3 cdx_count.py 2008 alebo 200810")
