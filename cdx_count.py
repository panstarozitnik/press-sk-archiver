"""
Rýchle zistenie počtu CDX záznamov pre press.sk.
Používa limit=1 na každom offsete — stiahne len 1 riadok namiesto 5000.
"""
import urllib.request, json, time, sys

BASE = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=press.sk/*"
    "&output=json"
    "&fl=original"
    "&filter=statuscode:200"
)

def has_record(offset, collapse=""):
    col = f"&collapse={collapse}" if collapse else ""
    url = f"{BASE}{col}&limit=1&offset={offset}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
        return len([x for x in data if x and x[0] != "original"]) > 0
    except Exception as e:
        print(f"  Chyba: {e}", flush=True)
        return False

def find_total(label, collapse=""):
    print(f"\n=== {label} ===", flush=True)

    # Fáza 1: nájdi hrubý rozsah krokmi po 50k
    step = 50000
    offset = 0
    while has_record(offset, collapse):
        print(f"  offset={offset:,} → existuje", flush=True)
        offset += step
        time.sleep(0.3)

    high = offset
    low  = offset - step
    print(f"  Rozsah: {low:,} – {high:,}", flush=True)

    # Fáza 2: binárne hľadanie presného konca
    while high - low > 1000:
        mid = (low + high) // 2
        if has_record(mid, collapse):
            low = mid
        else:
            high = mid
        time.sleep(0.2)

    # Fáza 3: presný počet na poslednej stránke
    url = f"{BASE}{'&collapse='+collapse if collapse else ''}&limit=1000&offset={low}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read())
    last = len([x for x in data if x and x[0] != "original"])
    total = low + last
    print(f"  CELKOM: {total:,}", flush=True)
    return total

total  = find_total("Všetky snapshoty press.sk")
unique = find_total("Unikátne URL (collapse=urlkey)", collapse="urlkey")

print(f"\n{'='*40}", flush=True)
print(f"Všetky snapshoty:          {total:,}", flush=True)
print(f"Unikátnych URL:            {unique:,}", flush=True)
print(f"Snapshotov/URL priemer:    {total/max(unique,1):.1f}x", flush=True)
