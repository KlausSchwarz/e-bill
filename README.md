# E-Bill

A small tool to create hybrid ZUGFeRD/Factur-X PDF invoices: a human-readable PDF
page with a machine-readable XML invoice (per the EN 16931 semantic data model)
embedded as an attachment inside the same PDF/A-3 document.

## Stack

- **`factur-x`**: builds and validates the EN 16931 Cross-Industry-Invoice XML
  (against the official XSD, bundled and checked locally, no network access needed)
  and embeds it into the PDF as a proper Factur-X attachment with XMP metadata.
- **`reportlab`**: renders the human-readable invoice page.
- **`pypdf` + `Pillow`**: add a PDF/A-3 `/OutputIntent` (sRGB ICC profile, generated
  in-process) to the base PDF, which the Factur-X/ZUGFeRD standard requires.

## Requirements

- Python 3.11+

## Setup

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

Runs every example function defined in `main.py`. Each function takes no arguments:
it reads its own input JSON from `data/input/` and writes the resulting PDF to
`data/output/` (created on first run, git-ignored).

- `minimal_example()` → `data/input/minimal_example.json`
- `typical_example()` → `data/input/typical_example.json`
- `full_en16931_example()` → `data/input/full_en16931_example.json`
- `pfs()` → `data/input/pfs_example.json`

Call a single example instead of all of them, e.g.:

```bash
python -c "from main import pfs; pfs()"
```

## `create_bill(params)`

The core function lives in `create_bill.py`:

```python
from create_bill import create_bill

pdf_bytes = create_bill(params)
```

`params` is a nested dict whose structure mirrors the business groups of EN 16931
(seller, buyer, payee, delivery, payment, line items, VAT breakdown, totals, ...).
Leaf values are mapped internally to the official EN 16931 business-term IDs
(`BT-1`, `BT-27`, ... ) before handing them to `factur-x`. See the example files
under `data/input/` for the exact shape.

## Language / locale (`language` field, default `"de"`)

`params["language"]` selects `"de"` (German, the default) or `"en"` (English) and
drives the **human-readable side** of the PDF only, via the locale profiles in
`i18n.py`:

| | German (`de`, default) | English (`en`) |
|---|---|---|
| Labels | "Rechnung", "Verkäufer", "USt-IdNr." ... | "Invoice", "Seller", "VAT ID" ... |
| Paper size | A4 | Letter |
| Date format | `24.09.2026` | `09/24/2026` |
| Number format | `1.213,80` | `1,213.80` |
| Address line order | postcode, then city | city, then postcode |
| PDF `/Lang` tag | `de-DE` | `en-US` |

The embedded Factur-X/ZUGFeRD XML (the machine-readable side) is unaffected by
`language`: EN 16931 mandates locale-independent ISO dates and plain decimal amounts
there, so invoices stay interoperable regardless of which language they were
rendered in. Add a profile for another language by extending `LOCALE_PROFILES` in
`i18n.py`.

## Example input files (`data/input/`)

- **`minimal_example.json`** — the smallest invoice that still validates against
  the EN 16931 XSD: only the mandatory fields.
- **`typical_example.json`** — a realistic everyday invoice: full addresses,
  contact details, several line items, payment terms and IBAN, a note.
- **`full_en16931_example.json`** — exercises every EN 16931 business term/group
  the `factur-x` library supports: all reference types, all party roles (seller,
  buyer, payee, tax representative, ship-to), payment means, document- and
  line-level allowances/charges, multiple VAT rates, product classification and
  attributes, rounding and prepaid amounts. Uses `"language": "en"` to demonstrate
  the English locale profile; the other examples use the German default.
- **`pfs_example.json`** — a small real-world-style invoice: Partner für Spandau
  billing Maxes Würstchenbude for a rental hut, power and decoration.

## Project layout

```
create_bill.py             # def create_bill(params: dict) -> bytes
i18n.py                      # language/locale profiles (labels, formats, paper size)
main.py                     # example functions: load JSON from data/input, write PDF to data/output
data/
├── input/
│   ├── minimal_example.json
│   ├── typical_example.json
│   ├── full_en16931_example.json
│   └── pfs_example.json
└── output/                 # created on first run (git-ignored)
```
