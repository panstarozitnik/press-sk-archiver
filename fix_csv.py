"""
fix_csv.py - Oprav CSV s rôznymi oddeľovačmi (tab, ;, ,)
Výstup je vždy správne quotovaný CSV s čiarkovým oddeľovačom.
"""
import sys, re

WB_RE   = re.compile(r'(https?://web\.archive\.org/web/(\d{14})/https?://\S+)')
TYPE_RE = re.compile(r'\b(LISTING|PRODUCT|SKIP)\b', re.I)


def detect_sep(header):
    if '\t' in header: return '\t'
    if ';'  in header: return ';'
    return ','


def q(v):
    v = str(v)
    if ',' in v or '"' in v:
        return '"' + v.replace('"', '""') + '"'
    return v


def fix_csv_urls(input_path, output_path=None):
    if not output_path:
        output_path = input_path

    with open(input_path, encoding='utf-8') as f:
        lines = f.read().splitlines()

    if not lines:
        return 0

    header = lines[0]
    sep    = detect_sep(header)
    print(f"Oddeľovač: {'TAB' if sep == chr(9) else repr(sep)}")

    out = ['original_url,wayback_url,timestamp,type']
    fixed = skipped = 0

    for line in lines[1:]:
        if not line.strip():
            continue

        parts = line.split(sep)

        # Spoj všetky časti do jedného stringu a hľadaj regexom
        joined = ' '.join(parts)

        wb_m = WB_RE.search(joined)
        if not wb_m:
            skipped += 1
            continue

        wb_url   = wb_m.group(1)
        ts       = wb_m.group(2)  # vždy z wb_url - spoľahlivé

        # original_url — prvý stĺpec
        orig_url = parts[0].strip().strip('"')

        # type — hľadaj v posledných stĺpcoch
        url_type = "LISTING"
        for p in reversed(parts):
            m = TYPE_RE.match(p.strip())
            if m:
                url_type = m.group(1).upper()
                break

        out.append(','.join([q(orig_url), q(wb_url), q(ts), q(url_type)]))
        fixed += 1

    with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + '\n')

    print(f"Opravených: {fixed}, preskočených: {skipped}")
    return fixed


if __name__ == '__main__':
    inp = sys.argv[1] if len(sys.argv) > 1 else 'output/relevant.csv'
    out = sys.argv[2] if len(sys.argv) > 2 else inp
    fix_csv_urls(inp, out)
