"""CLI entry point to create a hybrid ZUGFeRD/Factur-X PDF invoice from a JSON file.

Usage:
    python main.py data/input/typical_example.json [output.pdf]
"""

import json
import sys
from pathlib import Path

from create_bill import create_bill

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "data" / "output"


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {Path(__file__).name} <input.json> [output.pdf]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    params = json.loads(input_path.read_text(encoding="utf-8"))

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
    else:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = DEFAULT_OUTPUT_DIR / f"{input_path.stem}.pdf"

    pdf_bytes = create_bill(params)
    output_path.write_bytes(pdf_bytes)
    print(f"Wrote {output_path} ({len(pdf_bytes)} bytes)")


if __name__ == "__main__":
    main()
