# DocuMind AI

Local-first Document Intelligence Platform.

## Overview

DocuMind AI extracts structured information from receipts, invoices, and
document tables and runs entirely on the local machine. It combines an
OCR baseline (PaddleOCR 3.x, PP-OCRv6, CPU), deterministic invoice
extraction, ruled-table recognition, an evaluation framework, real-document
dataset onboarding, and a local FastAPI + vanilla JavaScript web app with
PDF input, batch processing, and human-in-the-loop corrections.

**Current status:** M0/M1 OCR baseline, M2 invoice extraction, M3A ruled
tables, M4A evaluation, M4B Phase 1 dataset onboarding, M5A web app, M5B
PDF/batch/page-level exports (D-18), M5C Vietnamese extraction rules,
and M5D synthetic performance baseline are implemented and integrated on
`main` (post-D18 checkpoint: PR #13,
`130f32207e316330cba15d31c23558c6a2987607`). D-16's short-receipt
line-item recovery is implemented in PR #15 (base checkpoint
`31a8f1b`, PR #14 merge; that base does not contain D-16); check the
live PR and current `main` HEAD for integration status.
Real-document accuracy evaluation is **pending** privacy-cleared,
manually annotated data. There is no LLM, no model training, and no
database.

The CLI tools operate on images and saved artifacts. PDFs are supported
through the local web API, which renders pages and returns page-indexed
results.

## Feature Status

### Implemented

- Image and multi-page PDF input through the local web app (PDF via
  `pypdfium2`; page-indexed results).
- OCR, invoice extraction, ruled-table recognition, and an Auto workflow
  that reuses a single OCR pass.
- Short headerless receipt extraction (D-16; source revision: PR #15 —
  check the live PR and current `main` HEAD for integration status):
  content-aware line-item region selection without a table header,
  merged OCR rows such as `COFFEE 25.000`, metadata/tax-identifier
  exclusion, and payment/summary boundaries that close the item region.
  Heuristic only: real-world OCR accuracy for these layouts remains
  unvalidated.
- Editable invoice fields and table cells with corrections kept separate
  from machine output; corrections are isolated per document and page,
  survive page switches, and reset per page/family.
- JSON, CSV, XLSX, TXT, and ZIP exports: OCR JSON/TXT, invoice JSON/CSV/
  XLSX, table JSON/CSV/XLSX, multi-table ZIP, and batch ZIP.
- Page-local PDF exports with page-specific filenames, duplicate-filename
  identity via opaque document IDs, case-insensitive ZIP name
  deduplication, and an explicit batch failure report.
- CSV formula-injection protection, XLSX-safe worksheet titles, filename
  sanitization, and bounded export payloads.
- CLI tools: `documind-ocr`, `documind-extract`, `documind-table`,
  `documind-eval`, `documind-dataset`.
- Evaluation framework (CER/WER, invoice field accuracy, strict table
  agreement) and synthetic evaluation reports.
- Vietnamese invoice label and money rules at the extraction layer
  (diacritic-insensitive matching, VND symbols).
- Reproducible local performance benchmark tooling
  (`scripts/benchmark.py`, `reports/benchmark-local.md`).
- Privacy controls: local-only binding, git-ignored real datasets,
  anonymization gate, and no document data leaves the machine (model
  weights are downloaded once from Hugging Face on first real OCR use).

### Not yet implemented

- Genuine OCR accuracy evaluation on real documents (M4B Phase 2).
- Malformed evaluation-input hardening (D-22).
- Borderless table recognition (M3B, deferred).
- Vietnamese OCR model/language benchmarking on real data.
- Database, job queue/resume, or multi-user deployment (not planned for
  the current local-first scope).

See [Known Limitations](#known-limitations) and [Roadmap](#roadmap).

## Tech Stack

Current: Python 3.12, PaddleOCR 3.x / PaddlePaddle 3.x (CPU), OpenCV
(geometry), Pillow, openpyxl (XLSX), pypdfium2 (PDF rendering), FastAPI +
vanilla JS/HTML/CSS (no build step), pytest, ruff, and a Node.js DOM
harness for frontend regression tests. The application is local-only and
does not require a database.

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
pip install -e ".[web]"        # only needed to run the web app
```

`requirements.lock.txt` is a historical environment snapshot that pins the
project itself at an earlier commit (`ab62d749`); it is not a current
installer for this checkout. Use the editable installs above so the
current `src/` tree is what runs.

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
      "confidence": 0.9999762773513794,
      "box": [[37.0, 498.0], [128.0, 498.0], [128.0, 523.0], [37.0, 523.0]]
    }
  ],
  "full_text": "MINI MART EXPRESS\n...\nSUBTOTAL\n12.30\nTAX 10%\n1.23\nTOTAL\n13.53\n..."
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
    "subtotal": "12.30",
    "tax": "1.23",
    "total": "13.53",
    "payment_amount": "15.00",
    "change_amount": "1.47",
    "validation_status": "ok",
    "validation_errors": []
  },
  "provenance": {
    "total": {"ocr_index": 24, "text": "13.53", "box": [[327.0, 494.0], "..."]}
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

### 5. Datasets — onboard local real documents (M4B Phase 1)

```powershell
documind-dataset init
documind-dataset add path\to\anonymized-receipt.jpg --id receipt-001 --confirm-anonymized
# annotate ground_truth/receipt-001.<ocr|invoice|table>.json by hand
documind-dataset validate
documind-dataset predict --task ocr     # local inference (not CI)
documind-eval    --task ocr --manifest data/eval/real/manifest-ocr.json
```

`data/eval/real/` is git-ignored entirely: raw documents, anonymized
images, predictions, and reports stay local. Ground truth is annotated
manually — never generated from predictions. Real-document metrics are
**pending** until authentic, verified labels exist.

### 6. Web app — local Document Intelligence UI (M5A/M5B)

```powershell
pip install -e ".[web]"
documind-web        # http://127.0.0.1:8000 (local only, no CORS, no auth)
```

The web app accepts images and PDFs (10 MB upload limit; PDFs up to 10
pages, 30 MP per page, 60 MP cumulative) and offers OCR only, Invoice
extraction, Table recognition, or Auto (one OCR pass shared across
workflows). PDF results are page-indexed; page tabs switch between them.

Invoice fields and table cells are editable. Corrections are isolated per
document and page, survive page switches within a run, and are exported
**alongside** the untouched machine output. **Reset Invoice** / **Reset
Tables** remove only the active page's corrections of that family.
Starting a new selection or processing run clears previous corrections
rather than re-applying them to fresh output.

Single-file PDF exports cover the selected page only, with page-specific
filenames (`<stem>-page-<N>-...`), and include OCR JSON/TXT, invoice
JSON/CSV/XLSX, table JSON/CSV/XLSX, and a multi-table ZIP where needed.
Multi-file runs process up to 10 documents sequentially and offer an
**Export batch ZIP** that includes one complete JSON entry per successful
PDF (all pages, not just the active one), image Auto artifacts,
page-local corrections, and an explicit `batch-errors.json` report when
any document fails. ZIP names are sanitized, case-insensitively
deduplicated, and keep their extensions.

Full endpoint and payload contracts: [docs/web-api.md](docs/web-api.md).

## Tests

```powershell
python scripts/verify.py   # ruff check + frontend gate + pytest
pytest                     # tests only
```

The suite is verified by the current CI workflow; check the Actions tab
for the exact count, which grows with every milestone. CI
(`.github/workflows/ci.yml`) runs ruff, the Node browser-script gate, and
pytest on Python 3.12 with Node 20, installing only lightweight test
dependencies (`pytest`, `pillow`, `openpyxl`, `opencv-python-headless`,
`fastapi`, `httpx`, `python-multipart`, `pypdfium2`, `ruff`) — no
PaddlePaddle, no model weights, no GPU.

All automated tests run against **mocked** OCR output, synthetic JSON
fixtures, or geometry-only synthetic images; no real model is loaded or
downloaded during tests, so a green suite validates application logic
only, **not OCR model accuracy**. Frontend behavior is exercised by a
Node DOM harness that runs the real `static/app.js` (page switching,
corrections, resets, exports, batch ZIP payloads) and feeds payloads to
the real FastAPI endpoints.

**Historical smoke tests** (single image, real inference):
`documind-ocr` on `assets/samples/sample_receipt.png` (30 text regions)
feeds `documind-extract` (all invoice fields, `validation_status: ok`),
and `documind-table` on three synthetic ruled tables reaches **62/62
exact cell-text agreement** with committed ground truth
([reports/m3a-synthetic-evaluation.md](reports/m3a-synthetic-evaluation.md)).
These are functional smoke checks on clean synthetic inputs — they are
**not** real-world accuracy benchmarks, and a browser smoke test with
mocked inference is not evidence of recognition quality. No accuracy
metrics are claimed for real documents: that requires labeled
ground-truth data and a defined metric (M4B Phase 2). Confidence scores
in OCR output are model self-assessment scores useful for filtering
low-quality lines; they are **not calibrated probabilities**.

## Project Layout

```
src/documind/        core package
  cli.py               documind-ocr entry point
  extract_cli.py       documind-extract entry point
  table_cli.py         documind-table entry point
  ocr/                 validation, preprocessing, engine, results (M1)
  extraction/          models, parsing, layout, extractor, validator,
                       lexicon_vi (M2/M5C)
  tables/              geometry, assign, models, exporters, pipeline (M3A)
  evaluation/          text_metrics, ocr/invoice/table eval, manifest,
                       report, CLI (M4A)
  dataset.py           real-data onboarding/validation (M4B Phase 1)
  dataset_cli.py       documind-dataset entry point
  web/                 FastAPI app, service layer, schemas, pdf.py,
                       static UI (M5A/M5B/D-18)
tests/               pytest suite + fixtures (synthetic OCR JSONs, table
                     truth, frontend DOM harness scenarios)
scripts/             verify, browser gate, sample generators, evaluation,
                     benchmark
assets/samples/      small synthetic sample documents
data/                annotation templates + synthetic eval ground truth
                     (raw datasets git-ignored)
docs/                setup, architecture, specs, web API, annotation
                     guide, notes, product expansion plan
reports/             evaluation results, benchmark, audits (m3a, m4a,
                     m5d, 2026-10-26 audit)
.github/workflows/   CI (mock/geometry tests + frontend gate, Python 3.12,
                     Node 20)
```

## Known Limitations

- CPU-only; the first real OCR run downloads PP-OCRv6 models (~tens of
  MB) from Hugging Face to `~/.paddlex` (outside the repo).
- oneDNN (MKLDNN) is disabled in the engine: the PaddlePaddle 3.x CPU
  Windows build crashes with a PIR attribute error when MKLDNN is on.
- The CLI processes one image per invocation. PDF input is available
  through the web API only (page-by-page results, no cross-page
  invoice aggregation).
- Extraction is strictly extractive (never derives a line total from
  qty × price); single-page, single-currency documents.
- Invoice extraction understands Vietnamese labels and money formats,
  but OCR recognition of Vietnamese text is **not validated**; the
  default model is English (`--lang` passes through to PaddleOCR).
- Table recognition needs **complete, axis-aligned ruled grids** —
  borderless tables (M3B), partial rules, and rotated/skewed tables are
  not recognized; text outside the grid is reported as warnings.
- No database, job queue, resume, or multi-user deployment. Batch runs
  are sequential in the browser (up to 10 files); the results panel shows
  the last processed document rather than a full batch navigator.
- All automated tests and the recorded benchmark use synthetic inputs.
  Real-document accuracy is unvalidated; the M5D numbers measure local
  runtime, not recognition quality.
- CSV exports are UTF-8 without BOM, so Excel on Windows may display
  Vietnamese text mojibaked unless imported explicitly.
- Single-file export filenames are sanitized and length-capped; a very
  long source stem can lose its extension in the download header.
  Batch ZIP names budget the extension inside the cap and are not
  affected.
- Hand-crafted API export payloads with names consisting only of dots
  (`"."`, `".."`) can produce odd (non-traversing) ZIP entry names;
  extractors drop them and the UI cannot generate them.
- Local-only, no CORS, no authentication; do not expose the server.
- Headerless receipt recovery is heuristic: metadata classification is
  pattern-based, a first item's description above its amount is not
  reconstructed, merged bare integers stay ambiguous, and a VAT token on
  a metadata row can still be read as a monetary tax. Real-world OCR
  accuracy for these layouts is unvalidated.
- Remaining P3 audit items (D-22 and other small defects) are tracked in
  [HANDOFF.md](HANDOFF.md) and the [baseline audit](reports/audits/2026-10-26-baseline-audit.md).
  D-16's extraction fix is implemented in PR #15; check the live PR and
  current `main` HEAD for integration status.

## Roadmap

- ~~**M0/M1:** OCR baseline (PaddleOCR 3.x, PP-OCRv6)~~ ✓
- ~~**M2:** receipt/invoice field extraction (regex + layout heuristics)~~ ✓
- ~~**M3A:** ruled table structure recognition (OpenCV geometry)~~ ✓
- ~~**M4A:** evaluation framework (CER/WER, field accuracy, table
  agreement)~~ ✓ — real-data evaluation **pending** labeled data
- ~~**M4B Phase 1:** real-document dataset onboarding tooling~~ ✓ —
  real-document metrics **pending** authentic annotated data
- ~~**M5A:** local FastAPI backend + web frontend~~ ✓
- ~~**M5B:** PDF input, batch processing, page-level exports, ZIP
  hardening (D-18)~~ ✓
- ~~**M5C:** Vietnamese extraction rules (labels, VND money formats)~~ ✓
  — OCR recognition accuracy not validated
- ~~**M5D:** synthetic/local performance baseline and benchmark tooling~~ ✓
- **D-16:** short-receipt line-item extraction — implemented in PR #15;
  check the live PR and current `main` HEAD for integration status
- **D-22:** malformed evaluation-input handling (pending; next
  prioritized engineering defect after D-16 integration)
- **Remaining P3 audit items** (pending, prioritized in HANDOFF)
- **M4B Phase 2:** evaluate on privacy-cleared, manually annotated real
  documents (pending data)
- **Vietnamese OCR benchmarking:** compare `lang="vi"` vs `lang="en"` on
  real data (pending data)
- **M3B:** borderless table recognition (model-based, deferred)

## Development Approach

Start with a reproducible OCR baseline, measure its performance, and
progressively improve the pipeline. Documentation must match implemented
behavior; synthetic evidence is never presented as real-world accuracy.
