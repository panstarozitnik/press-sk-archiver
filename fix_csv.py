"""
fix_csv.py - Oprav CSV kde URL obsahujú čiarky (bez quotovania)
Použitie: python fix_csv.py input.csv [output.csv]
"""
import sys, re

WB_RE   = re.compile(r'https?://web\.archive\.org/web/(\d{14})/https?://\S+')
TYPE_RE = re.compile(r'\b(LISTING|PRODUCT|SKIP)\b', re.I)
TS_RE   = re.compile(r'\b(\d{14})\b')

def fix_line(line):
    """Oprav jeden CSV riadok s potenciálne rozsekanými URL."""
    line = line.rstrip('\r\n')
    if not line.strip():
        return None
    
    # Nájdi Wayback URL — začína na https://web.archive.org/web/TIMESTAMP/
    wb_m = WB_RE.search(line)
    if not wb_m:
        return line  # bez Wayback URL — nechaj tak
    
    # original_url je všetko pred Wayback URL (bez trailing čiarky)
    orig_url = line[:wb_m.start()].rstrip(',').strip().strip('"')
    
    # Nájdi type — LISTING/PRODUCT/SKIP — hľadaj odzadu
    type_m = list(TYPE_RE.finditer(line))
    url_type = type_m[-1].group(1).upper() if type_m else "LISTING"
    type_end = type_m[-1].end() if type_m else len(line)
    type_start = type_m[-1].start() if type_m else len(line)
    
    # Nájdi timestamp — 14-ciferné číslo tesne pred TYPE
    before_type = line[:type_start]
    ts_m = list(TS_RE.finditer(before_type))
    ts = ts_m[-1].group(1) if ts_m else wb_m.group(1)
    ts_start = ts_m[-1].start() if ts_m else type_start
    
    # wb_url = všetko medzi orig_url a timestampom (bez trailing čiarky)
    wb_url = line[wb_m.start():ts_start].rstrip(',').strip()
    
    # products_found ak existuje za TYPE
    pf = line[type_end:].strip().strip(',').strip()
    
    # Quotuj polia s čiarkami
    def q(v):
        v = str(v)
        if ',' in v or '"' in v:
            return '"' + v.replace('"', '""') + '"'
        return v
    
    row = [q(orig_url), q(wb_url), q(ts), q(url_type)]
    if pf and pf.isdigit():
        row.append(q(pf))
    
    return ','.join(row)


def fix_csv_urls(input_path, output_path=None):
    if not output_path:
        output_path = input_path
    
    with open(input_path, encoding='utf-8') as f:
        lines = f.read().splitlines()
    
    header = lines[0]
    fixed_lines = [header]
    fixed = skipped = 0
    
    for line in lines[1:]:
        result = fix_line(line)
        if result is None:
            continue
        fixed_lines.append(result)
        if result != line:
            fixed += 1
        else:
            skipped += 1
    
    with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(fixed_lines) + '\n')
    
    print(f"Opravených: {fixed}, nezmenených: {skipped}, celkom: {fixed+skipped}")
    return fixed


if __name__ == '__main__':
    inp = sys.argv[1] if len(sys.argv) > 1 else 'output/relevant.csv'
    out = sys.argv[2] if len(sys.argv) > 2 else inp
    fix_csv_urls(inp, out)
