"""
fix_csv.py - Oprav CSV s rôznymi oddeľovačmi (tab, ;, ,)
Výstup je vždy správne quotovaný CSV s čiarkovým oddeľovačom.

Kľúčové: štruktúra riadku je vždy original_url, wayback_url, timestamp, type
(presne 4 logické polia). Wayback_url môže obsahovať interné čiarky (napr.
/cd/n,a,30,0/), preto sa rekonštruuje ako "všetko medzi prvým a posledné 2
poľami" namiesto spoliehania sa na regex hranice.
"""
import sys, re

TYPE_RE = re.compile(r'^(LISTING|PRODUCT|SKIP)$', re.I)
TS14_RE = re.compile(r'(\d{14})')


def detect_sep(header):
    if '\t' in header: return '\t'
    if ';'  in header: return ';'
    return ','


def fix_line(line, sep):
    """
    Oprav jeden riadok. Predpoklad: presne 4 logické polia
    original_url, wayback_url, timestamp, type - kde wayback_url
    môže obsahovať interné oddeľovače (čiarky).
    """
    line = line.rstrip('\r\n')
    if not line.strip():
        return None

    parts = line.split(sep)
    if len(parts) < 4:
        return None

    orig_url = parts[0].strip().strip('"')
    url_type_raw = parts[-1].strip().strip('"')
    ts_raw = parts[-2].strip().strip('"')
    # Všetko medzi original_url a (timestamp, type) - rekonštruuj wb_url
    wb_url = sep.join(parts[1:-2]).strip().strip('"')

    if "web.archive.org" not in wb_url:
        return None

    # type - normalizuj, fallback na hľadanie v celom riadku
    m = TYPE_RE.match(url_type_raw)
    url_type = m.group(1).upper() if m else "LISTING"
    if not m:
        for p in reversed(parts):
            m2 = TYPE_RE.match(p.strip().strip('"'))
            if m2:
                url_type = m2.group(1).upper()
                break

    # timestamp - vždy preferuj 14-ciferný z wb_url (spoľahlivejšie ako CSV pole)
    ts_m = TS14_RE.search(wb_url)
    if ts_m:
        ts = ts_m.group(1)
    elif TS14_RE.match(ts_raw):
        ts = ts_raw
    else:
        ts = ts_raw  # necháme čo je, nech to nie je prázdne

    def q(v):
        v = str(v)
        if ',' in v or '"' in v:
            return '"' + v.replace('"', '""') + '"'
        return v

    return ','.join([q(orig_url), q(wb_url), q(ts), q(url_type)])


def fix_csv_urls(input_path, output_path=None):
    if not output_path:
        output_path = input_path

    with open(input_path, encoding='utf-8') as f:
        lines = f.read().splitlines()

    if not lines:
        print("Prázdny súbor.")
        return 0

    header = lines[0]
    sep    = detect_sep(header)
    print(f"Oddeľovač: {'TAB' if sep == chr(9) else repr(sep)}")

    out = ['original_url,wayback_url,timestamp,type']
    fixed = skipped = 0

    for line in lines[1:]:
        if not line.strip():
            continue
        result = fix_line(line, sep)
        if result is None:
            skipped += 1
            continue
        out.append(result)
        fixed += 1

    with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + '\n')

    print(f"Opravených: {fixed}, preskočených: {skipped}")
    return fixed


if __name__ == '__main__':
    inp = sys.argv[1] if len(sys.argv) > 1 else 'output/relevant.csv'
    out = sys.argv[2] if len(sys.argv) > 2 else inp
    fix_csv_urls(inp, out)
