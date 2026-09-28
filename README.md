# press-sk-archiver

Scraper ktorý prechádza historické záznamy e-shopu **press.sk** cez [Wayback Machine](https://web.archive.org) a extrahuje zoznam kníh a časopisov do CSV súboru vrátane obrázkov obálok.

## Čo zbiera

- Názov knihy / časopisu
- Autor
- Cena (historická — z obdobia archivácie)
- ISBN
- Vydavateľ
- Kategória
- Krátky popis
- URL obrázku + stiahnutý súbor obálky

## Inštalácia

```bash
git clone https://github.com/panstarozitnik/press-sk-archiver.git
cd press-sk-archiver
pip install -r requirements.txt
```

> Python 3.10+ odporúčaný.

## Spustenie

### Testovací beh (prvých 30 URL)
```bash
python scraper.py --limit 30
```
Skontroluj `output/products.csv` — ak sú polia správne vyplnené, spusti plný beh.

### Plný beh
```bash
python scraper.py
```

### Len stiahni CDX index (bez parsingu)
```bash
python scraper.py --cdx-only
```

### Bez obrázkov (rýchlejšie)
```bash
python scraper.py --no-images
```

## Výstup

```
output/
  products.csv      ← hlavný výstup
  images/           ← obálky kníh (pomenované podľa ISBN)
  scraper.log       ← log behu
  cdx_urls.json     ← cache CDX indexu (nezmazávaj, šetrí čas)
```

## Ako funguje

1. **CDX API** — Wayback Machine má API ktoré vráti zoznam všetkých archivovaných URL pre danú doménu bez toho aby sme museli navštíviť každú stránku. Stiahne sa raz a cachuje.
2. **Klasifikácia** — URL sa roztriedí na *listing* (zoznam produktov) a *detail* (jednotlivý produkt).
3. **Parsovanie** — pre každú URL sa stiahne archivovaná HTML stránka a extrahujú sa dáta. Skript zvláda viacero dizajnov press.sk (VirtueMart 2008–2015, moderný 2016+).
4. **Resume** — ak skript prerušíš, pri ďalšom spustení pokračuje kde skončil.

## Úprava parserov

Ak niektoré polia zostávajú prázdne, otvor príslušnú archivovanú URL v prehliadači, pozri zdrojový kód (Ctrl+U) a uprav selektory v:

- `parsers/listing.py` — pre zoznamové stránky
- `parsers/detail.py` — pre detailné stránky produktov
- `parsers/utils.py` — URL klasifikácia a pomocné funkcie

## Poznámky

- Skript používa 1.5s pauzu medzi requestmi aby nezaťažoval Wayback Machine.
- Wayback Machine môže byť pomalá — plný beh tisícov URL môže trvať niekoľko hodín.
- Spúšťaj cez noc alebo nechaj bežať na pozadí.
