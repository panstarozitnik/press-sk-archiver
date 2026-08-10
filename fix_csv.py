"""
fix_csv.py - Oprav CSV s rôznymi oddeľovačmi (tab, ;, ,)
Výstup je vždy správny RFC-4180 CSV s čiarkovým oddeľovačom.

Použitie: python fix_csv.py input.csv [output.csv]

Poznámka: používa Pythonov csv modul aj na čítanie aj na zápis (nie manuálne
stringové skladanie s .strip('"')), takže je bezpečný pri opakovanom spustení
na už opravenom súbore aj pri poliach ktoré obsahujú úvodzovky.
"""
import sys, csv, re

TYPE_RE = re.compile(r'^(LISTING|PRODUCT|SKIP)$', re.I)
TS14_RE = re.compile(r'(\d{14})')


def detect_sep(header_line):
    if '\t' in header_line: return '\t'
    if ';'  in header_line: return ';'
    return ','


def fix_csv_urls(input_path, output_path=None):
    if not output_path:
        output_path = input_path

    with open(input_path, encoding='utf-8', newline='') as f:
        first_line = f.readline()
        sep = detect_sep(first_line)
        f.seek(0)
        print(f"Oddeľovač: {'TAB' if sep == chr(9) else repr(sep)}")

        reader = csv.reader(f, delimiter=sep)
        rows = list(reader)

    if not rows:
        print("Prázdny súbor.")
        return 0

    header = rows[0]
    data_rows = rows[1:]

    out_rows = []
    fixed = skipped = 0

    for raw in data_rows:
        if not raw or all(not c.strip() for c in raw):
            continue

        # Odfiltruj prázdne stĺpce na konci (niekedy vznikajú pri split)
        parts = [c for c in raw]
        if len(parts) < 4:
            skipped += 1
            continue

        orig_url = parts[0].strip()
        url_type_raw = parts[-1].strip()
        ts_raw = parts[-2].strip()
        # Všetko medzi original_url a (timestamp, type) je wayback_url,
        # aj keď obsahuje interné čiarky rozdelené oddeľovačom.
        wb_url = sep.join(parts[1:-2]).strip()

        if "web.archive.org" not in wb_url:
            skipped += 1
            continue

        m = TYPE_RE.match(url_type_raw)
        url_type = m.group(1).upper() if m else "LISTING"
        if not m:
            for p in reversed(parts):
                m2 = TYPE_RE.match(p.strip())
                if m2:
                    url_type = m2.group(1).upper()
                    break

        ts_m = TS14_RE.search(wb_url)
        ts = ts_m.group(1) if ts_m else ts_raw

        out_rows.append([orig_url, wb_url, ts, url_type])
        fixed += 1

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['original_url', 'wayback_url', 'timestamp', 'type'])
        writer.writerows(out_rows)

    print(f"Opravených: {fixed}, preskočených: {skipped}")
    return fixed


if __name__ == '__main__':
    inp = sys.argv[1] if len(sys.argv) > 1 else 'output/relevant.csv'
    out = sys.argv[2] if len(sys.argv) > 2 else inp
    fix_csv_urls(inp, out)
