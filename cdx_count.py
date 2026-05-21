import urllib.request, json, time

BASE = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=press.sk/*"
    "&output=json"
    "&fl=original"
    "&filter=statuscode:200"
)

def count_at_offset(offset, collapse=""):
    col = f"&collapse={collapse}" if collapse else ""
    url = f"{BASE}{col}&limit=5000&offset={offset}"
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read())
    return len([x for x in data if x and x[0] != "original"])

def find_total(label, collapse=""):
    print(f"\n=== {label} ===")
    offset = 0
    while True:
        try:
            n = count_at_offset(offset, collapse)
            print(f"  offset={offset:,} → {n} riadkov")
            if n < 5000:
                total = offset + n
                print(f"  CELKOM: ~{total:,}")
                return total
            offset += 100000
            time.sleep(1)
        except Exception as e:
            print(f"  Chyba pri offset={offset}: {e}")
            return offset

total  = find_total("Všetky snapshoty press.sk")
unique = find_total("Unikátne URL (collapse=urlkey)", collapse="urlkey")

print(f"\n{'='*40}")
print(f"Všetky snapshoty:          {total:,}")
print(f"Unikátnych URL:            {unique:,}")
print(f"Snapshotov na URL priemer: {total/max(unique,1):.1f}x")
