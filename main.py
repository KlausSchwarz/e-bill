"""Entry point to create hybrid ZUGFeRD/Factur-X PDF invoices from the example JSON
files under data/input/.

Usage:
    python main.py

Each example function below takes no arguments: it reads its input JSON from
data/input/, builds the PDF via create_bill(), and writes it to data/output/.
"""

import json
from pathlib import Path

from create_bill import create_bill

INPUT_DIR = Path(__file__).parent / "data" / "input"
OUTPUT_DIR = Path(__file__).parent / "data" / "output"


def _build(name: str) -> Path:
    params = json.loads((INPUT_DIR / f"{name}.json").read_text(encoding="utf-8"))
    pdf_bytes = create_bill(params)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{name}.pdf"
    output_path.write_bytes(pdf_bytes)
    print(f"Wrote {output_path} ({len(pdf_bytes)} bytes)")
    return output_path


def minimal_example():
    """Smallest invoice that still validates against the EN 16931 XSD."""
    return _build("minimal_example")


def typical_example():
    """A realistic everyday invoice: addresses, contact details, several line
    items, payment terms and IBAN, a note."""
    return _build("typical_example")


def full_en16931_example():
    """Exercises every EN 16931 business term/group the factur-x library
    supports."""
    return _build("full_en16931_example")


def pfs():
    """Party rental invoice: Partner für Spandau billing Maxes Würstchenbude for
    a rental hut, power and decoration."""
    return _build("pfs_example")


def main():
    minimal_example()
    typical_example()
    full_en16931_example()
    pfs()


if __name__ == "__main__":
    main()
