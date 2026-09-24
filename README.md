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
python main.py data/input/typical_example.json
```

Writes the generated PDF to `data/output/typical_example.pdf` (created on first run,
git-ignored). Pass an explicit output path as a second argument to override this.

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

## Example input files (`data/input/`)

- **`minimal_example.json`** — the smallest invoice that still validates against
  the EN 16931 XSD: only the mandatory fields.
- **`typical_example.json`** — a realistic everyday invoice: full addresses,
  contact details, several line items, payment terms and IBAN, a note.
- **`full_en16931_example.json`** — exercises every EN 16931 business term/group
  the `factur-x` library supports: all reference types, all party roles (seller,
  buyer, payee, tax representative, ship-to), payment means, document- and
  line-level allowances/charges, multiple VAT rates, product classification and
  attributes, rounding and prepaid amounts.

## Project layout

```
create_bill.py             # def create_bill(params: dict) -> bytes
main.py                     # CLI: load JSON from data/input, write PDF to data/output
data/
├── input/
│   ├── minimal_example.json
│   ├── typical_example.json
│   └── full_en16931_example.json
└── output/                 # created on first run (git-ignored)
```
