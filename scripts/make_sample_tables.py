"""Generate synthetic ruled-table images with known ground truth.

Creates three fictional ruled tables (visible grid lines, white
background) used for M3A tests and evaluation:

1. table_products - basic product table with headers and numeric columns
   (line totals are internally consistent).
2. table_gaps     - empty cells and multi-word values.
3. table_large    - a larger 6x5 grid.

Images go to assets/samples/, ground-truth matrices to
tests/fixtures/tables/<name>.truth.json. All data is fictional.

Usage:
    python scripts/make_sample_tables.py
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = REPO_ROOT / "assets" / "samples"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "tables"

FONT = "arial.ttf"

TABLES: dict[str, list[list[str]]] = {
    "table_products": [
        ["Item", "Qty", "Price", "Total"],
        ["Coffee", "2", "3.50", "7.00"],
        ["Sugar", "1", "2.25", "2.25"],
        ["Tea", "3", "1.80", "5.40"],
    ],
    "table_gaps": [
        ["Code", "Product Name", "Stock", "Note"],
        ["A-01", "Red Delicious Apple", "12", ""],
        ["B-02", "Whole Milk 1L", "", "chilled section"],
        ["C-07", "", "5", "limited edition batch"],
    ],
    "table_large": [
        ["ID", "Region", "Salesperson", "Units", "Revenue"],
        ["R01", "North", "Anna Lisz", "140", "15400.00"],
        ["R02", "South", "Ben Trovato", "95", "10450.00"],
        ["R03", "East", "Cara Mel", "210", "23100.00"],
        ["R04", "West", "Dinh Quan", "60", "6600.00"],
        ["R05", "Central", "Eva Luator", "175", "19250.00"],
    ],
}


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    import os

    path = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", FONT)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _column_widths(matrix: list[list[str]], font, padding: int) -> list[int]:
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    widths = []
    for col in range(len(matrix[0])):
        widest = max(
            scratch.textbbox((0, 0), row[col], font=font)[2] for row in matrix
        )
        widths.append(widest + padding * 2)
    return widths


def render_table(name: str, matrix: list[list[str]], output_dir: Path,
                 fixtures_dir: Path) -> Path:
    font = _load_font(20)
    row_height = 38
    line_thickness = 2
    padding = 10
    margin = 30

    col_widths = _column_widths(matrix, font, padding)
    table_w = sum(col_widths)
    table_h = row_height * len(matrix)
    image = Image.new("RGB", (table_w + margin * 2, table_h + margin * 2),
                      color="white")
    draw = ImageDraw.Draw(image)
    origin_x, origin_y = margin, margin

    row_edges = [origin_y + row_height * i for i in range(len(matrix) + 1)]
    col_edges = [origin_x + sum(col_widths[:i]) for i in range(len(col_widths) + 1)]

    for y in row_edges:
        draw.line([(col_edges[0], y), (col_edges[-1], y)],
                  fill="black", width=line_thickness)
    for x in col_edges:
        draw.line([(x, row_edges[0]), (x, row_edges[-1])],
                  fill="black", width=line_thickness)

    for row_index, row in enumerate(matrix):
        for col_index, value in enumerate(row):
            if not value:
                continue
            bbox = draw.textbbox((0, 0), value, font=font)
            text_h = bbox[3] - bbox[1]
            x = col_edges[col_index] + padding
            y = row_edges[row_index] + (row_height - text_h) // 2 - bbox[1]
            draw.text((x, y), value, fill="black", font=font)

    output_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"{name}.png"
    image.save(image_path, format="PNG")

    truth = {
        "image": f"assets/samples/{name}.png",
        "rows": len(matrix),
        "columns": len(matrix[0]),
        "cells": matrix,
    }
    (fixtures_dir / f"{name}.truth.json").write_text(
        json.dumps(truth, indent=1), encoding="utf-8"
    )
    return image_path


def main() -> None:
    for name, matrix in TABLES.items():
        path = render_table(name, matrix, SAMPLES_DIR, FIXTURES_DIR)
        print(f"wrote {path} ({path.stat().st_size} bytes) + truth fixture")


if __name__ == "__main__":
    main()
