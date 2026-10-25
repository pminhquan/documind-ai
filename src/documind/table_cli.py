"""Command-line entry point for ruled-table recognition (M3A).

    documind-table <image-path> -o <table-json-path> [--csv path] [--xlsx path]

Geometry and cell assignment can be exercised without the OCR model by
passing an existing ``documind-ocr`` JSON via ``--ocr-json``.
"""

import argparse
import sys
from pathlib import Path

from .extraction.extractor import OcrInputError, load_ocr_document
from .ocr.validation import ValidationError, validate_file
from .tables.exporters import export_csv, export_json, export_xlsx
from .tables.pipeline import TableRecognitionError, recognize_tables

SUPPORTED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"})
DEFAULT_MAX_INPUT_BYTES = 20 * 1024 * 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="documind-table",
        description=(
            "Detect ruled (visible grid line) tables in an image, reconstruct "
            "rows/columns/cells, assign OCR text geometrically, and export to "
            "JSON, CSV, and XLSX. Reuses the documind-ocr engine unless an "
            "existing OCR JSON is provided via --ocr-json."
        ),
    )
    parser.add_argument("input", help="Path to the input image")
    parser.add_argument(
        "-o", "--output", default=None,
        help="Table JSON output path. Default: outputs/<stem>.tables.json",
    )
    parser.add_argument("--csv", default=None, help="Optional CSV export path")
    parser.add_argument("--xlsx", default=None, help="Optional XLSX export path")
    parser.add_argument(
        "--ocr-json", default=None,
        help="Reuse a saved documind-ocr JSON instead of running the OCR model",
    )
    parser.add_argument("--lang", default="en", help="OCR language model (default: en)")
    parser.add_argument(
        "--compact", action="store_true", help="Write JSON without indentation"
    )
    return parser


def run_table_recognition(args: argparse.Namespace) -> int:
    validate_file(
        args.input,
        extensions=SUPPORTED_EXTENSIONS,
        max_size_bytes=DEFAULT_MAX_INPUT_BYTES,
    )

    ocr_items = None
    if args.ocr_json:
        ocr_items = load_ocr_document(args.ocr_json)["items"]

    result = recognize_tables(args.input, ocr_items=ocr_items, lang=args.lang)

    output_path = (
        Path(args.output)
        if args.output
        else Path("outputs") / f"{Path(args.input).stem}.tables.json"
    )
    export_json(result, output_path, indent=None if args.compact else 2)

    written = [str(output_path)]
    if args.csv:
        written.extend(str(path) for path in export_csv(result, args.csv))
    if args.xlsx:
        written.append(str(export_xlsx(result, args.xlsx)))

    total_cells = sum(len(table.cells) for table in result.tables)
    print(
        f"Detected {len(result.tables)} table(s), {total_cells} cell(s) "
        f"from {args.input}"
    )
    for table in result.tables:
        print(
            f"  {table.table_id}: {table.rows} rows x {table.columns} columns"
        )
    for warning in result.warnings:
        print(f"  warning: {warning}")
    print("Output written to: " + ", ".join(written))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_table_recognition(args)
    except (ValidationError, OcrInputError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    except (TableRecognitionError, OSError) as exc:
        print(f"Table recognition error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
