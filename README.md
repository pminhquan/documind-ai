# DocuMind AI

AI-powered Document Intelligence Platform.

## Overview

An Applied AI project focused on extracting structured
information from receipts, invoices, and document tables.

**Current status (M0 + M1 + M2 complete):** a minimal, CPU-first OCR
baseline plus a deterministic, layout-aware invoice extraction stage.
The `documind-ocr` CLI runs pretrained PaddleOCR 3.x (PP-OCRv6 detection +
recognition, pinned explicitly in `engine.py` for reproducibility) on an
image and saves recognized text, confidence scores, and bounding boxes as
structured JSON. The `documind-extract` CLI transforms that OCR JSON into
structured invoice data (supplier, date, line items, totals) using regex
and layout heuristics — no LLM, no model training. No API, database, or
frontend yet.

## Planned Features

- Image and PDF upload
- OCR and document preprocessing
- Invoice information extraction
- Table structure recognition
- Editable extraction results
- JSON, CSV, and Excel export
- Model evaluation and benchmarking

## Tech Stack

Current: Python 3.12, PaddleOCR 3.x / PaddlePaddle 3.x (CPU), Pillow, pytest.
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

## Tests

```powershell
pytest
```

**Verified result: 59 passed** (20 M1 + 39 M2) — see Verification below for
the exact run. All tests run against **mocked** OCR output and synthetic
JSON fixtures; no real model is loaded or downloaded during tests, so a
green suite validates application logic only, **not OCR model accuracy**.
CI (`.github/workflows/ci.yml`) runs this same mocked suite on every pull
request with Python 3.12, installing only `pytest` + `pillow` — no
PaddlePaddle, no model weights, no GPU.

**Verified end-to-end smoke test** (single image, real inference) on
`assets/samples/sample_receipt.png`: 30 text regions recognized from the
corrected synthetic receipt, followed by extraction of all invoice fields
with `validation_status: ok` (see Verification below). This is a
one-image functional smoke check on a clean synthetic input — it is
**not** a measured accuracy benchmark. No extraction accuracy metrics are
claimed: that requires labeled ground-truth data and a defined metric
(planned for M4). Confidence scores in the OCR output are model
self-assessment scores useful for filtering low-quality lines; they are
**not calibrated probabilities**.

## Project Layout

```
src/documind/        core package
  cli.py               documind-ocr entry point
  extract_cli.py       documind-extract entry point
  ocr/                 validation, preprocessing, engine, results (M1)
  extraction/          models, parsing, layout, extractor, validator (M2)
tests/               pytest suite + fixtures/ocr/ synthetic OCR JSONs
scripts/             dev utilities (sample receipt generator)
assets/samples/      small synthetic sample documents
data/                local datasets (ignored)
docs/                setup, architecture, extraction spec, learning notes
reports/             future evaluation results
.github/workflows/   CI (mocked unit tests, Python 3.12)
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
- No table structure recognition, database, or API yet.
- English OCR model by default (`--lang` passes through to PaddleOCR).

## Roadmap

- ~~**M2:** receipt/invoice field extraction (regex + layout heuristics)~~ ✓
- **M3:** table structure recognition
- **M4:** labeled evaluation dataset + accuracy metrics
- **M5:** API service and frontend

## Development Approach

Start with a reproducible OCR baseline, measure its
performance, and progressively improve the pipeline.
