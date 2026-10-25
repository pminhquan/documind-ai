# DocuMind AI

AI-powered Document Intelligence Platform.

## Overview

An Applied AI project focused on extracting structured
information from receipts, invoices, and document tables.

**Current status (M0 + M1 + M2 + M3A + M4A complete):** a minimal,
CPU-first OCR baseline, deterministic invoice extraction, ruled-table
structure recognition, and a reproducible evaluation framework.
`documind-ocr` runs pretrained PaddleOCR 3.x (PP-OCRv6, pinned in
`engine.py`) on an image and saves text, confidence, and bounding boxes
as JSON. `documind-extract` transforms that OCR JSON into structured
invoice data with regex + layout heuristics. `documind-table` detects
ruled (visible grid line) tables, reconstructs rows/columns/cells,
assigns OCR text geometrically, and exports JSON/CSV/XLSX.
`documind-eval` measures CER/WER, invoice field accuracy, and table
agreement against labeled ground truth from saved prediction files —
no LLM, no model training. No API, database, or frontend yet.

## Planned Features

- Image and PDF upload
- OCR and document preprocessing
- Invoice information extraction
- Table structure recognition
- Editable extraction results
- JSON, CSV, and Excel export
- Model evaluation and benchmarking

## Tech Stack

Current: Python 3.12, PaddleOCR 3.x / PaddlePaddle 3.x (CPU), OpenCV
(geometry), Pillow, openpyxl (XLSX), pytest.
Planned (later milestones): FastAPI, PostgreSQL, Streamlit, Docker.

## Setup (Windows, Python 3.12)

PaddlePaddle 3.x supports Python 3.9–3.13; the project pins **Python 3.12**
(`requires-python = ">=3.12,<3.13"`) because the machine default (3.14) has
no compatible wheels yet. Details: [docs/setup.md](docs/setup.md).

```powershell
# 1. Python 3.12 (per-user, no admin needed)
winget install --id Python.Python.3.12 --scope user
py -3.12 -V    # -> Python 3.12.10

# 2. Virtual environment
cd documind-ai
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -V     # -> 3.12.10 from .venv

# 3. Dependencies
python -m pip install --upgrade pip
pip install -e ".[dev]"
# or reproduce the verified environment exactly - run from the repo root;
# the lock file installs the local project (as `-e .`) plus exact pins:
pip install -r requirements.lock.txt
```

Verified versions in the development environment: `paddlepaddle 3.3.1`,
`paddleocr 3.7.0`, `pillow 13.0.0`, `pytest 9.1.1` (see
`requirements.lock.txt`).

## Usage

### 1. OCR — image to text JSON

Run OCR on an image and save JSON (default output: `outputs/<stem>.json`):

```powershell
documind-ocr assets/samples/sample_receipt.png -o outputs/sample_receipt.json
```

Regenerate the synthetic sample receipt (fictional data only):

```powershell
python scripts/make_sample_receipt.py
```

Example output (excerpt):

```json
{
  "source": "assets/samples/sample_receipt.png",
  "engine": "paddleocr",
  "items": [
    {
      "text": "TOTAL",
      "confidence": 0.9999812245368958,
      "box": [[36.0, 360.0], [129.0, 360.0], [129.0, 388.0], [36.0, 388.0]]
    }
  ],
  "full_text": "MINI MART EXPRESS\n...\nTOTAL\n9.57\n..."
}
```

Exit codes: `0` success, `2` invalid input (missing/unsupported/empty/oversized),
`1` OCR failure (undecodable image or inference error). Messages go to stderr.

### 2. Extraction — OCR JSON to invoice JSON

Transform a saved OCR JSON into structured invoice data (no OCR model run):

```powershell
documind-extract outputs/sample_receipt.json -o outputs/sample_receipt.invoice.json
```

Default output: `outputs/<stem>.invoice.json`. Exit codes: `0` success,
`2` invalid input (missing file, non-JSON, malformed JSON), `1` IO error.

Example output (excerpt, from the synthetic sample):

```json
{
  "invoice": {
    "supplier": "MINI MART EXPRESS",
    "invoice_number": "00001234",
    "invoice_date": "2026-10-25",
    "currency": "USD",
    "line_items": [
      {
        "description": "SOAP",
        "quantity": "2",
        "unit_price": "2.50",
        "line_total": "5.00"
      }
    ],
    "subtotal": "8.70",
    "tax": "0.87",
    "total": "9.57",
    "payment_amount": "10.00",
    "change_amount": "0.43",
    "validation_status": "ok",
    "validation_errors": []
  },
  "provenance": {
    "total": {"ocr_index": 24, "text": "9.57", "box": [[327.0, 494.0], "..."]}
  }
}
```

Financial values are decimal strings (parsed internally as `Decimal`,
never float). Absent values are `null` — nothing is fabricated. Field
rules and arithmetic checks: [docs/extraction-spec.md](docs/extraction-spec.md).

### 3. Tables — ruled grid to JSON/CSV/XLSX

Detect ruled tables (visible grid lines), reconstruct rows/columns/cells,
assign OCR text geometrically, and export:

```powershell
# Full pipeline (runs PaddleOCR once)
documind-table assets/samples/table_products.png -o outputs/table_products.tables.json --csv outputs/table_products.csv --xlsx outputs/table_products.xlsx

# Reuse a saved OCR JSON - geometry + assignment only, no model run
documind-table assets/samples/table_gaps.png --ocr-json outputs/table_gaps.ocr.json
```

Default JSON output: `outputs/<stem>.tables.json`. Supported table types:
complete, axis-aligned ruled grids; one or more tables per image
(multi-table: CSV gets `_t<i>` suffixes, XLSX gets one sheet per table).
Exit codes: `0` success (including "no table detected", reported via
warnings), `2` invalid input, `1` processing error.

Example output (excerpt):

```json
{
  "source_image": "assets/samples/table_products.png",
  "tables": [{
    "table_id": "table_0", "rows": 4, "columns": 4,
    "cells": [
      {"row_index": 0, "column_index": 0, "text": "Item",
       "bounding_box": [[30, 30], [116, 30], [116, 68], [30, 68]],
       "source_ocr_indices": [0], "confidence": 0.99},
      {"row_index": 2, "column_index": 3, "text": "",
       "bounding_box": ["..."], "source_ocr_indices": [], "confidence": null}
    ],
    "warnings": []
  }],
  "warnings": []
}
```

Spec and limitations: [docs/table-recognition-spec.md](docs/table-recognition-spec.md).

### 4. Evaluation — saved predictions vs labeled ground truth

Evaluate saved prediction files against labeled ground truth using a
manifest (no OCR inference; confidence is never an accuracy metric):

```powershell
documind-eval --task ocr     --manifest data/eval/synthetic/ocr/manifest.json     --output outputs/eval/ocr
documind-eval --task invoice --manifest data/eval/synthetic/invoice/manifest.json --output outputs/eval/invoice
documind-eval --task table   --manifest data/eval/synthetic/table/manifest.json   --output outputs/eval/table
```

Each run writes `summary.json` + `report.md`. Metrics: CER/WER with
error examples (OCR), field-level accuracy with null semantics and
canonical date/money comparison (invoice), structural + cell agreement
with missed-table penalization (table). Spec:
[docs/evaluation-spec.md](docs/evaluation-spec.md); annotation guide:
[docs/dataset-annotation-guide.md](docs/dataset-annotation-guide.md).

## Tests

```powershell
pytest
```

**Verified result: 189 passed** (20 M1 + 46 M2 + 41 M3A + 82 M4A) — see
Verification below for the exact run. All tests run against **mocked**
OCR output, synthetic JSON fixtures, or geometry-only synthetic images;
no real model is loaded or downloaded during tests, so a green suite
validates application logic only, **not OCR model accuracy**.
CI (`.github/workflows/ci.yml`) runs this same mocked/geometry-only
suite on every pull request with Python 3.12, installing only `pytest`,
`pillow`, `openpyxl`, `opencv-python-headless` — no PaddlePaddle, no
model weights, no GPU.

**Verified end-to-end smoke tests** (single image, real inference):
`documind-ocr` on `assets/samples/sample_receipt.png` (30 text regions)
feeds `documind-extract` (all invoice fields, `validation_status: ok`),
and `documind-table` on three synthetic ruled tables reaches **62/62
exact cell-text agreement** with committed ground truth
([reports/m3a-synthetic-evaluation.md](reports/m3a-synthetic-evaluation.md)).
These are functional smoke checks on clean synthetic inputs — they are
**not** real-world accuracy benchmarks. No accuracy metrics are claimed
for real documents: that requires labeled ground-truth data and a
defined metric (planned for M4). Confidence scores in the OCR output
are model self-assessment scores useful for filtering low-quality
lines; they are **not calibrated probabilities**.

## Project Layout

```
src/documind/        core package
  cli.py               documind-ocr entry point
  extract_cli.py       documind-extract entry point
  table_cli.py         documind-table entry point
  ocr/                 validation, preprocessing, engine, results (M1)
  extraction/          models, parsing, layout, extractor, validator (M2)
  tables/              geometry, assign, models, exporters, pipeline (M3A)
  evaluation/          text_metrics, ocr/invoice/table eval, manifest,
                       report, CLI (M4A)
tests/               pytest suite + fixtures (synthetic OCR JSONs, table truth)
scripts/             dev utilities (sample generators, table evaluation)
assets/samples/      small synthetic sample documents
data/                annotation templates + synthetic eval ground truth
                     (raw datasets git-ignored)
docs/                setup, architecture, specs, annotation guide, notes
reports/             evaluation results (m3a, m4a baselines)
.github/workflows/   CI (mocked + geometry-only tests, Python 3.12)
```

## Known Limitations

- CPU-only; first run downloads PP-OCRv6 models (~tens of MB) from
  Hugging Face to `~/.paddlex` (outside the repo).
- oneDNN (MKLDNN) is disabled in the engine: the PaddlePaddle 3.x CPU
  Windows build crashes with a PIR attribute error when MKLDNN is on.
- Single image per invocation; no PDF input yet.
- Extraction keywords are English-only (`TOTAL`, `CASH`, ...); strictly
  extractive (never derives a line total from qty × price); single-page,
  single-currency documents.
- Table recognition needs **complete, axis-aligned ruled grids** —
  borderless tables (M3B), partial rules, and rotated/skewed tables are
  not recognized; text outside the grid is reported as warnings.
- No database or API yet.
- English OCR model by default (`--lang` passes through to PaddleOCR).

## Roadmap

- ~~**M2:** receipt/invoice field extraction (regex + layout heuristics)~~ ✓
- ~~**M3A:** ruled table structure recognition (OpenCV geometry)~~ ✓
- ~~**M4A:** evaluation framework (CER/WER, field accuracy, table
  agreement)~~ ✓ — real-data evaluation **pending** labeled data
- **M3B:** borderless table recognition (model-based)
- **M4B:** evaluation on labeled real documents
- **M5:** API service and frontend

## Development Approach

Start with a reproducible OCR baseline, measure its
performance, and progressively improve the pipeline.
