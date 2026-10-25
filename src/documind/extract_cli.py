"""Command-line entry point for receipt/invoice extraction (M2).

Operates on a saved OCR JSON document (the output of ``documind-ocr``)
without re-running the OCR model:

    documind-extract <ocr-json-path> -o <output-json-path>
"""

import argparse
import json
import sys
from pathlib import Path

from .extraction.extractor import OcrInputError, extract, load_ocr_document
from .ocr.validation import ValidationError, validate_file

DEFAULT_MAX_INPUT_BYTES = 50 * 1024 * 1024
SUPPORTED_EXTENSIONS = frozenset({".json"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="documind-extract",
        description=(
            "Extract structured invoice data (supplier, date, line items, "
            "totals) from a saved documind-ocr JSON file using deterministic, "
            "layout-aware rules. Does not run the OCR model."
        ),
    )
    parser.add_argument("input", help="Path to an OCR JSON file from documind-ocr")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "Path of the invoice JSON output file. "
            "Default: outputs/<input-stem>.invoice.json"
        ),
    )
    parser.add_argument(
        "--compact", action="store_true", help="Write JSON without indentation"
    )
    return parser


def run_extract(input_path: str, output_path: Path, compact: bool) -> int:
    validate_file(input_path, extensions=SUPPORTED_EXTENSIONS,
                  max_size_bytes=DEFAULT_MAX_INPUT_BYTES)

    document = load_ocr_document(input_path)
    result = extract(document, source=str(input_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    indent = None if compact else 2
    output_path.write_text(result.to_json(indent=indent), encoding="utf-8")

    invoice = result.invoice
    print(
        f"Extracted invoice: supplier={invoice.supplier!r}, "
        f"date={invoice.invoice_date}, line_items={len(invoice.line_items)}, "
        f"total={invoice.total}, status={invoice.validation_status}"
    )
    if invoice.validation_errors:
        for error in invoice.validation_errors:
            print(f"  - {error}")
    print(f"Invoice JSON saved to: {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    output_path = (
        Path(args.output)
        if args.output
        else Path("outputs") / f"{Path(args.input).stem}.invoice.json"
    )

    try:
        return run_extract(args.input, output_path, args.compact)
    except (ValidationError, OcrInputError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"IO error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
