"""
fix_encoding_csv.py - Oprav mojibake encoding v products.csv
Pouzitie: python fix_encoding_csv.py [--products output/products.csv] [--dry-run]
"""
import argparse, csv, sys, os

csv.field_size_limit(sys.maxsize)
TEXT_FIELDS = ["title", "author", "publisher", "description", "category"]

def fix_text(text):
    if not text:
        return text
    try:
        import ftfy
        return ftfy.fix_text(text)
    except ImportError:
        return text

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--products",  default="output/products.csv")
    ap.add_argument("--dry-run",   action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.products):
        print(f"Subor nenajdeny: {args.products}")
        return

    tmp = args.products + ".tmp"
    changed = total = 0

    with open(args.products, encoding="utf-8") as fin, \
         open(tmp, "w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=reader.fieldnames,
                                extrasaction="ignore", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in reader:
            total += 1
            modified = False
            for field in TEXT_FIELDS:
                if row.get(field):
                    fixed = fix_text(row[field])
                    if fixed != row[field]:
                        if args.dry_run:
                            print(f"  [{field}] {repr(row[field][:60])} -> {repr(fixed[:60])}")
                        row[field] = fixed
                        modified = True
            if modified:
                changed += 1
            writer.writerow(row)

    if not args.dry_run:
        os.replace(tmp, args.products)
        print(f"Hotovo: {total} produktov, {changed} opravených")
    else:
        os.remove(tmp)
        print(f"DRY RUN: {changed} produktov by sa zmenilo z {total}")

if __name__ == "__main__":
    main()
