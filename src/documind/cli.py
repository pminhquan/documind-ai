"""Command-line entry point for the DocuMind OCR baseline."""

import argparse
import json
import logging
import sys
from pathlib import Path

from .ocr.engine import OcrEngineError, PaddleOcrEngine
from .ocr.preprocessing import PreprocessingError, prepare_image
from .ocr.results import normalize_result
from .ocr.validation import ValidationError, validate_image

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("outputs")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="documind-ocr",
        description=(
            "Run pretrained PaddleOCR 3.x inference on an image and save "
            "recognized text with bounding boxes as structured JSON."
        ),
    )
    parser.add_argument("input", help="Path to the input image (PNG/JPG/BMP/TIFF/WEBP)")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "Path of the JSON output file. "
            "Default: outputs/<input-stem>.json relative to the working directory."
        ),
    )
    parser.add_argument(
        "--lang", default="en", help="OCR language model (default: en)"
    )
    parser.add_argument(
        "--compact", action="store_true", help="Write JSON without indentation"
    )
    return parser


def run_ocr(input_path: str, output_path: Path, lang: str, compact: bool) -> int:
    validated = validate_image(input_path)

    with prepare_image(validated.path) as prepared_path:
        engine = PaddleOcrEngine(lang=lang)
        raw_results = engine.predict(prepared_path)

    raw_page = raw_results[0] if raw_results else {}
    result = normalize_result(raw_page, source=str(validated.path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    indent = None if compact else 2
    output_path.write_text(result.to_json(indent=indent), encoding="utf-8")

    print(f"Recognized {len(result.items)} text region(s) from {validated.path}")
    print(f"JSON result saved to: {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)

    output_path = (
        Path(args.output)
        if args.output
        else DEFAULT_OUTPUT_DIR / f"{Path(args.input).stem}.json"
    )

    try:
        return run_ocr(args.input, output_path, args.lang, args.compact)
    except ValidationError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 2
    except (PreprocessingError, OcrEngineError) as exc:
        print(f"OCR error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
