"""
Zistenie počtu CDX záznamov pre press.sk - hrubý odhad.
"""
import urllib.request, json, time

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
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=45) as r:
                data = json.loads(r.read())
            return len([x for x in data if x and x[0] != "original"]) > 0
        except Exception as e:
            print(f"  Retry {attempt+1}/3 (offset={offset:,}): {e}", flush=True)
            time.sleep(10)
    return False

def find_total(label, collapse=""):
    print(f"\n=== {label} ===", flush=True)
    step = 500000  # Väčší krok — menej requestov
    offset = 0
    while has_record(offset, collapse):
        print(f"  offset={offset:,} → existuje", flush=True)
        offset += step
        time.sleep(2)  # Dlhšia pauza

    high = offset
    low  = max(0, offset - step)
    print(f"  Rozsah: {low:,} – {high:,}", flush=True)

    # Binárne hľadanie
    while high - low > 10000:
        mid = (low + high) // 2
        if has_record(mid, collapse):
            low = mid
        else:
            high = mid
        time.sleep(2)

    print(f"  ODHADOVANÝ POČET: ~{high:,}", flush=True)
    return high

total  = find_total("Všetky snapshoty press.sk")
unique = find_total("Unikátne URL (collapse=urlkey)", collapse="urlkey")

print(f"\n{'='*40}", flush=True)
print(f"Všetky snapshoty:       ~{total:,}", flush=True)
print(f"Unikátnych URL:         ~{unique:,}", flush=True)
if unique > 0:
    print(f"Snapshotov/URL:         ~{total/unique:.1f}x", flush=True)
