"""
Zistí počet CDX záznamov pre press.sk.

Spustenie:
  python3 cdx_count.py 2008        → prehľad po mesiacoch za rok 2008
  python3 cdx_count.py 200810      → prehľad po dňoch za október 2008
"""
import urllib.request, time, sys, calendar

def count_range(from_date: str, to_date: str) -> int:
    """Počet záznamov v rozsahu — stiahne limit=0 a číta x-archive-total."""
    url = (
        "http://web.archive.org/cdx/search/cdx"
        "?url=press.sk/*"
        "&output=json"
        "&fl=original"
        "&filter=statuscode:200"
        f"&from={from_date}"
        f"&to={to_date}"
        "&limit=1"
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read().decode()
            # Počítame riadky — odpočítame header
            lines = [l for l in data.strip().split('\n') if l and l != '["original"]' and l != '[null]']
            # Ak vráti 1 riadok = existuje aspoň 1 záznam, ale nevieme celkový počet
            # Použijeme offset trick — hľadáme kde prestane vracať záznamy
            return _binary_count(from_date, to_date)
        except Exception as e:
            if attempt == 2:
                return -1
            time.sleep(10)
    return -1

def _has_record(from_date: str, to_date: str, offset: int) -> bool:
    url = (
        "http://web.archive.org/cdx/search/cdx"
        "?url=press.sk/*"
        "&output=json"
        "&fl=original"
        "&filter=statuscode:200"
        f"&from={from_date}"
        f"&to={to_date}"
        f"&limit=1&offset={offset}"
    )
    try:
        with urllib.request.urlopen(url, timeout=45) as r:
            data = r.read().decode().strip()
        lines = [l for l in data.split('\n') if l and 'original' not in l and 'null' not in l]
        return len(lines) > 0
    except:
        return False

def _binary_count(from_date: str, to_date: str) -> int:
    """Nájde celkový počet cez binárne hľadanie."""
    # Krok 1: nájdi hrubý rozsah
    step = 10000
    offset = 0
    while _has_record(from_date, to_date, offset):
        offset += step
        time.sleep(0.3)
        if offset > 10_000_000:
            return offset  # príliš veľa, vrátime odhad

    high = offset
    low  = max(0, offset - step)

    # Krok 2: binárne hľadanie
    while high - low > 1000:
        mid = (low + high) // 2
        if _has_record(from_date, to_date, mid):
            low = mid
        else:
            high = mid
        time.sleep(0.2)

    return high

def report_by_month(year: int):
    print(f"\n=== CDX snapshotov — {year} (po mesiacoch) ===\n", flush=True)
    print(f"{'Mesiac':<12} {'Odhadovaný počet':>20}", flush=True)
    print("-" * 35, flush=True)
    total = 0
    for month in range(1, 13):
        from_date = f"{year}{month:02d}01"
        to_date   = f"{year}{month:02d}31"
        count = _binary_count(from_date, to_date)
        label = f"{year}-{month:02d}"
        marker = " ⚠️" if count > 1_000_000 else ""
        print(f"{label:<12} {count:>20,}{marker}", flush=True)
        total += count
        time.sleep(1)
    print("-" * 35, flush=True)
    print(f"{'SPOLU':<12} {total:>20,}", flush=True)

def report_by_day(year: int, month: int):
    days = calendar.monthrange(year, month)[1]
    print(f"\n=== CDX snapshotov — {year}-{month:02d} (po dňoch) ===\n", flush=True)
    print(f"{'Deň':<12} {'Odhadovaný počet':>20}", flush=True)
    print("-" * 35, flush=True)
    total = 0
    for day in range(1, days + 1):
        from_date = f"{year}{month:02d}{day:02d}"
        to_date   = f"{year}{month:02d}{day:02d}"
        count = _binary_count(from_date, to_date)
        label = f"{year}-{month:02d}-{day:02d}"
        marker = " ⚠️" if count > 500_000 else ""
        print(f"{label:<12} {count:>20,}{marker}", flush=True)
        total += count
        time.sleep(1)
    print("-" * 35, flush=True)
    print(f"{'SPOLU':<12} {total:>20,}", flush=True)

# ── Main ──────────────────────────────────
arg = sys.argv[1] if len(sys.argv) > 1 else "2008"

if len(arg) == 4:
    report_by_month(int(arg))
elif len(arg) == 6:
    report_by_day(int(arg[:4]), int(arg[4:6]))
else:
    print("Použitie: python3 cdx_count.py 2008 (rok) alebo 200810 (mesiac)")
