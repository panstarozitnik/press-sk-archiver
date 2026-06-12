"""
apply_blacklist.py
==================
Aplikuje image_blacklist.txt spätne na existujúci products.csv.
Odstráni blacklistované URL z image_urls stĺpca.

Spustenie:
  python apply_blacklist.py
  python apply_blacklist.py --products output/products.csv --blacklist image_blacklist.txt
"""
import argparse
import csv
import os
import sys

csv.field_size_limit(sys.maxsize)

def load_blacklist(path):
    blacklist = []
    if not os.path.exists(path):
        print(f"Blacklist nenajdeny: {path}")
        return blacklist
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            blacklist.append(line.lower())
    return blacklist

def is_blacklisted(url, blacklist):
    url_lower = url.lower()
    for pattern in blacklist:
        if "*" in pattern:
            # Wildcard podpora: */M_images/* -> hladaj cast
            parts = [p for p in pattern.split("*") if p]
            if all(p in url_lower for p in parts):
                return True
        else:
            if url_lower == pattern or url_lower.endswith(pattern.lstrip("https://www.press.sk")):
                return True
    return False

def apply(products_path, blacklist_path, dry_run=False):
    blacklist = load_blacklist(blacklist_path)
    if not blacklist:
        print("Prazdny blacklist, konec.")
        return

    print(f"Blacklist: {len(blacklist)} vzory")

    tmp_path = products_path + ".tmp"
    changed = total = removed_total = 0

    with open(products_path, encoding="utf-8") as fin, \
         open(tmp_path, "w", newline="", encoding="utf-8") as fout:

        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=reader.fieldnames, extrasaction="ignore")
        writer.writeheader()

        for row in reader:
            total += 1
            orig_urls = [u.strip() for u in row.get("image_urls", "").split("|") if u.strip()]
            clean_urls = [u for u in orig_urls if not is_blacklisted(u, blacklist)]
            removed = len(orig_urls) - len(clean_urls)

            if removed > 0:
                changed += 1
                removed_total += removed
                if not dry_run:
                    row["image_urls"] = "|".join(clean_urls)
                else:
                    print(f"  [{row.get('title','?')[:50]}] odstrani {removed} URL:")
                    for u in orig_urls:
                        if is_blacklisted(u, blacklist):
                            print(f"    - {u}")

            writer.writerow(row)

    if not dry_run:
        os.replace(tmp_path, products_path)
        print(f"Hotovo: {total} produktov, {changed} upravených, {removed_total} URL odstranených")
    else:
        os.remove(tmp_path)
        print(f"DRY RUN: {changed} produktov by sa zmenilo, {removed_total} URL by sa odstranilo")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--products",  default="output/products.csv")
    ap.add_argument("--blacklist", default="image_blacklist.txt")
    ap.add_argument("--dry-run",   action="store_true", help="Len zobraz co by sa zmenilo")
    args = ap.parse_args()

    if not os.path.exists(args.products):
        print(f"products.csv nenajdeny: {args.products}")
        return

    apply(args.products, args.blacklist, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
