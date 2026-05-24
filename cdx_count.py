"""
Zistí počet CDX záznamov pre press.sk.
Sťahuje po 5000 a počíta kým nedostane prázdnu odpoveď.

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

def count_range(from_date: str, to_date: str) -> int:
    """Počíta záznamy po 5000 kým CDX nevráti prázdnu odpoveď."""
    total  = 0
    offset = 0
    while True:
        url = (f"{BASE}&from={from_date}&to={to_date}"
               f"&limit=5000&offset={offset}")
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    data = json.loads(r.read())
                break
            except Exception as e:
                if attempt == 2:
                    return total
                time.sleep(15)

        rows = [x for x in data if x and x[0] != "original"]
        total += len(rows)
        print(f"    offset={offset:,} +{len(rows)} = {total:,}", flush=True)

        if len(rows) < 5000:
            break
        offset += 5000
        time.sleep(2)
    return total

def report_by_month(year: int):
    print(f"\n=== CDX snapshotov — {year} (po mesiacoch) ===\n", flush=True)
    print(f"{'Mesiac':<12} {'Počet':>15}", flush=True)
    print("-" * 30, flush=True)
    total = 0
    for month in range(1, 13):
        from_date = f"{year}{month:02d}01"
        to_date   = f"{year}{month:02d}31"
        print(f"\n{year}-{month:02d}:", flush=True)
        count = count_range(from_date, to_date)
        print(f"{'→':>4} {year}-{month:02d}: {count:,}", flush=True)
        total += count
        time.sleep(1)
    print(f"\nSPOLU: {total:,}", flush=True)

def report_by_day(year: int, month: int):
    days = calendar.monthrange(year, month)[1]
    print(f"\n=== CDX snapshotov — {year}-{month:02d} (po dňoch) ===\n", flush=True)
    total = 0
    for day in range(1, days + 1):
        date = f"{year}{month:02d}{day:02d}"
        print(f"\n{year}-{month:02d}-{day:02d}:", flush=True)
        count = count_range(date, date)
        print(f"{'→':>4} {year}-{month:02d}-{day:02d}: {count:,}", flush=True)
        total += count
        time.sleep(1)
    print(f"\nSPOLU: {total:,}", flush=True)

arg = sys.argv[1] if len(sys.argv) > 1 else "2008"
if len(arg) == 4:
    report_by_month(int(arg))
elif len(arg) == 6:
    report_by_day(int(arg[:4]), int(arg[4:6]))
else:
    print("Použitie: python3 cdx_count.py 2008 alebo 200810")
