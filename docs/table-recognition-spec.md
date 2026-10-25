# Table Recognition Specification (M3A)

Ruled-table structure recognition baseline: images of tables with
**visible, complete grid lines** → structured cells → JSON / CSV / XLSX.
Command: `documind-table <image> -o <json> [--csv path] [--xlsx path] [--ocr-json path]`.

## Architecture

```
documind.tables/
├── geometry.py    # OpenCV only: lines -> regions -> grid edges -> cells
├── assign.py      # geometric OCR-region -> cell matching
├── models.py      # Rect / TableCell / Table / TableResult
├── exporters.py   # JSON, CSV (per table), XLSX (sheet per table)
└── pipeline.py    # orchestration; lazy PaddleOCR reuse
```

Geometry detection never imports the OCR engine — grids and assignment
are unit tested without the model. OCR runs lazily (or is supplied from
a saved `documind-ocr` JSON via `--ocr-json`) and reuses the M1 engine
(PP-OCRv6, CPU, pinned models) and result schema.

## Geometry pipeline (deterministic)

1. **Binarize** — grayscale → inverted Otsu threshold (dark strokes white).
2. **Line extraction** — erosion + dilation with a `(w/15, 1)` kernel keeps
   horizontal runs ≥ ~w/15 px (min 20 px); `(1, h/15)` for vertical. Text
   strokes are shorter than the kernel and vanish.
3. **Table regions** — h/v masks OR-combined, dilated 3×3 ×2, external
   contours; regions < 40×40 px discarded; sorted top-to-bottom (multi-table
   support).
4. **Grid edges** — projection profile of each line mask inside the region:
   rows/columns where ≥ 60 % of the region extent is ink; consecutive pixel
   positions clustered (gap ≤ 3 px) into line centers; edges closer than
   5 px dropped (degenerate slivers).
5. **Cells** — intersections of consecutive row/col edges; zero-based
   row-major (reading) order.

## Cell assignment

For each OCR region: the cell containing the **box center** wins; if the
center misses every cell (e.g. a box overshooting a rule), the cell with
the **largest box/cell intersection area** takes it. Regions matching no
cell are reported in `warnings` ("N OCR region(s) outside the detected
grid") — never dropped silently, never forced into a cell. Multiple
regions per cell join with a space in reading order (y then x). Empty
cells keep `text: ""`, empty `source_ocr_indices`, `confidence: null` —
no text is ever invented.

## Output schema

```jsonc
{
  "source_image": "assets/samples/table_products.png",
  "tables": [{
    "table_id": "table_0",          // zero-based, reading order
    "source_image": "...",
    "rows": 4, "columns": 4,        // counts; indices are zero-based
    "cells": [{
      "row_index": 0, "column_index": 0,
      "text": "Item",
      "bounding_box": [[x,y],[x2,y],[x2,y2],[x,y2]],
      "source_ocr_indices": [0],
      "confidence": 0.99             // mean of assigned regions; null if none
    }],
    "warnings": []
  }],
  "warnings": []
}
```

## Exports

- **JSON** — full schema above (default: `outputs/<stem>.tables.json`).
- **CSV** — one file per table; a single table uses the exact `--csv`
  path, multiple tables get `_t0`, `_t1` suffixes. Empty cells are empty
  fields.
- **XLSX** — one workbook, one sheet per table (`table_0`, ...), plain
  editable values at `(row+1, col+1)`.

Exit codes: `0` success (including "no table detected" — reported via
warnings), `2` invalid input (missing/unsupported/empty file, bad OCR
JSON), `1` processing error (undecodable image, IO failure).

## Known limitations

- Requires **complete, axis-aligned ruled grids**; borderless tables
  (M3B), partial rules, rotated/skewed tables are not recognized.
- Grid edges come from long-run projections: a column line that does not
  span the full table height, or a row line that does not span the full
  width, may be missed (cells then merge across the gap).
- Text outside the grid (titles, footers) is reported as unassigned
  warnings, not attached to cells.
- Text inside cells is OCR output as-is; no per-cell type inference.
- Synthetic evaluation numbers (`reports/m3a-synthetic-evaluation.md`)
  describe clean rendered inputs and must not be read as real-world
  accuracy.
