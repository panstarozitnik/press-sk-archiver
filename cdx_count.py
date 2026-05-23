"""
Zistí počet CDX záznamov pre press.sk po mesiacoch v danom roku.
Spustenie cez GitHub Actions workflow cdx_count.yml
"""
import urllib.request, json, time, sys

def count_month(year: int, month: int) -> int:
    """Vráti počet záznamov pre daný mesiac."""
    from_date = f"{year}{month:02d}01"
    # Posledný deň mesiaca
    if month == 12:
        to_date = f"{year}1231"
    else:
        to_date = f"{year}{month+1:02d}01"
        # Odčítame 1 deň — stačí dať posledný deň predchádzajúceho mesiaca
        to_date = f"{year}{month:02d}31"  # CDX akceptuje aj neexistujúce dni

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
                return -1
            time.sleep(10)
    return -1

# Rok z argumentu alebo default
year = int(sys.argv[1]) if len(sys.argv) > 1 else 2008

print(f"\n=== Počet CDX snapshotov pre press.sk — rok {year} ===\n", flush=True)
print(f"{'Mesiac':<12} {'Odhadovaný počet':>20}", flush=True)
print("-" * 35, flush=True)

total = 0
for month in range(1, 13):
    count = count_month(year, month)
    month_name = f"{year}-{month:02d}"
    if count == -1:
        print(f"{month_name:<12} {'CHYBA':>20}", flush=True)
    else:
        print(f"{month_name:<12} {count:>20,}", flush=True)
        total += count
    time.sleep(2)

print("-" * 35, flush=True)
print(f"{'SPOLU':<12} {total:>20,}", flush=True)
