"""
Zistí počet CDX záznamov pre press.sk po dňoch v danom mesiaci.
Spustenie: python3 cdx_count.py YYYYMM (napr. 200810)
"""
import urllib.request, json, time, sys
import calendar

def count_day(year: int, month: int, day: int) -> int:
    from_date = f"{year}{month:02d}{day:02d}"
    to_date   = f"{year}{month:02d}{day:02d}"
    url = (
        "http://web.archive.org/cdx/search/cdx"
        f"?url=press.sk/*&output=json&fl=original"
        f"&filter=statuscode:200"
        f"&from={from_date}&to={to_date}"
        f"&limit=1&showNumPages=true&pageSize=5000"
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                val = r.read().strip()
                return int(val) * 5000
        except Exception as e:
            if attempt == 2:
                print(f"  CHYBA: {e}", flush=True)
                return -1
            time.sleep(15)
    return -1

# Parameter: YYYYMM
arg = sys.argv[1] if len(sys.argv) > 1 else "200810"
year  = int(arg[:4])
month = int(arg[4:6])
days_in_month = calendar.monthrange(year, month)[1]

print(f"\n=== CDX snapshotov pre press.sk — {year}-{month:02d} (po dňoch) ===\n", flush=True)
print(f"{'Deň':<12} {'Odhadovaný počet':>20}", flush=True)
print("-" * 35, flush=True)

total = 0
for day in range(1, days_in_month + 1):
    count = count_day(year, month, day)
    label = f"{year}-{month:02d}-{day:02d}"
    if count == -1:
        print(f"{label:<12} {'CHYBA':>20}", flush=True)
    else:
        print(f"{label:<12} {count:>20,}", flush=True)
        total += count
    time.sleep(2)

print("-" * 35, flush=True)
print(f"{'SPOLU':<12} {total:>20,}", flush=True)
