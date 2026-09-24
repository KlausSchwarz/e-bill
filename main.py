"""CLI entry point to create a hybrid ZUGFeRD/Factur-X PDF invoice from a JSON file.

Usage:
    python main.py data/input/typical_example.json
    python main.py data/input/typical_example.json --output out.pdf
    python main.py data/input/typical_example.json --language en
"""

import argparse
import json
from pathlib import Path

from create_bill import create_bill
from i18n import LOCALE_PROFILES

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "data" / "output"


def main():
    parser = argparse.ArgumentParser(description="Create a hybrid ZUGFeRD/Factur-X PDF invoice.")
    parser.add_argument("input_json", type=Path, help="Path to a JSON file with invoice params")
    parser.add_argument("-o", "--output", type=Path, help="Output PDF path (default: data/output/<input>.pdf)")
    parser.add_argument(
        "-l", "--language",
        choices=sorted(LOCALE_PROFILES),
        help="Override the 'language' field from the input JSON (de or en)",
    )
    args = parser.parse_args()

    params = json.loads(args.input_json.read_text(encoding="utf-8"))
    if args.language:
        params["language"] = args.language

    if args.output:
        output_path = args.output
    else:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = DEFAULT_OUTPUT_DIR / f"{args.input_json.stem}.pdf"

    pdf_bytes = create_bill(params)
    output_path.write_bytes(pdf_bytes)
    print(f"Wrote {output_path} ({len(pdf_bytes)} bytes)")


if __name__ == "__main__":
    main()
