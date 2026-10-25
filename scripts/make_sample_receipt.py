"""Generate a small synthetic receipt image for OCR demos.

The image contains only fictional data - no real personal or financial
information. Output format is PNG (RGB).

Usage:
    python scripts/make_sample_receipt.py [-o assets/samples/sample_receipt.png]
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "assets" / "samples" / "sample_receipt.png"

# (text, font_size, bold)
#
# Financial layout (all values internally consistent):
#   line total  = quantity x unit price
#   subtotal    = sum of line totals                 = 12.30
#   tax         = 10% of subtotal                    =  1.23
#   total       = subtotal + tax                     = 13.53
#   change      = cash paid - total                  =  1.47
RECEIPT_LINES: list[tuple[str, int, bool]] = [
    ("MINI MART EXPRESS", 34, True),
    ("123 Demo Street, Sample City", 22, False),
    ("Receipt #: 00001234", 22, False),
    ("Date: 2026-10-25   Time: 10:30", 22, False),
    ("Currency: USD", 22, False),
    ("--------------------------------", 20, False),
    ("ITEM            QTY x PRICE   LINE TOTAL", 20, False),
    ("SOAP            2 x 2.50          5.00", 24, False),
    ("MILK 1L         1 x 2.50          2.50", 24, False),
    ("BREAD           1 x 1.20          1.20", 24, False),
    ("EGGS X12        1 x 3.60          3.60", 24, False),
    ("--------------------------------", 20, False),
    ("SUBTOTAL                          12.30", 26, False),
    ("TAX 10%                            1.23", 24, False),
    ("TOTAL                             13.53", 26, True),
    ("CASH                              15.00", 24, False),
    ("CHANGE                             1.47", 24, False),
    ("--------------------------------", 20, False),
    ("THANK YOU - SEE YOU AGAIN", 22, False),
]

FONT_CANDIDATES_BOLD = ["arialbd.ttf", "ARIALBD.TTF", "consolab.ttf"]
FONT_CANDIDATES_REGULAR = ["arial.ttf", "ARIAL.TTF", "consola.ttf", "DejaVuSans.ttf"]


def _find_font(size: int, bold: bool) -> ImageFont.FreeTypeFont:
    import os

    candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR
    for name in candidates:
        for font_dir in (
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
        ):
            font_path = os.path.join(font_dir, name)
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
    return ImageFont.load_default(size)


def render_receipt(output_path: Path) -> Path:
    width = 720
    padding = 40
    line_gap = 16

    # First pass on a scratch canvas to measure total height.
    scratch = Image.new("RGB", (width, 100))
    draw = ImageDraw.Draw(scratch)
    line_heights = []
    for text, size, bold in RECEIPT_LINES:
        font = _find_font(size, bold)
        bbox = draw.textbbox((0, 0), text, font=font)
        line_heights.append(bbox[3] - bbox[1])
    height = padding * 2 + sum(line_heights) + line_gap * (len(RECEIPT_LINES) - 1)

    image = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(image)

    y = padding
    for (text, size, bold), line_height in zip(RECEIPT_LINES, line_heights, strict=True):
        font = _find_font(size, bold)
        draw.text((padding, y), text, fill="black", font=font)
        y += line_height + line_gap

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = render_receipt(args.output)
    print(f"Sample receipt written to: {output} (size: {output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
