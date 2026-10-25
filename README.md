# DocuMind AI

AI-powered Document Intelligence Platform.

## Overview

An Applied AI project focused on extracting structured
information from receipts, invoices, and document tables.

**Current status (M0 + M1 complete):** a minimal, CPU-first OCR baseline.
The `documind-ocr` CLI runs pretrained PaddleOCR 3.x (PP-OCRv6 detection +
recognition, pinned explicitly in `engine.py` for reproducibility) on an
image and saves recognized text, confidence scores, and bounding boxes as
structured JSON. No API, database, or frontend yet.

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
  "full_text": "MINI MART EXPRESS\n...\nTOTAL\n8.70\n..."
}
```

Exit codes: `0` success, `2` invalid input (missing/unsupported/empty/oversized),
`1` OCR failure (undecodable image or inference error). Messages go to stderr.

## Tests

```powershell
pytest
```

**Verified result: 20 passed in 0.17s.** All 20 tests run against
**mocked** inference output (validation, result normalization, CLI
help/error paths, and a mocked end-to-end JSON pipeline) — no real model
is loaded or downloaded during tests.

**Verified end-to-end smoke test** (single image, real inference) on
`assets/samples/sample_receipt.png`: 19 text regions recognized; all 15
text lines of the synthetic receipt were read correctly (output kept
locally at `outputs/sample_receipt.json`, not committed). This is a
one-image functional smoke check on a clean synthetic input — it is
**not** a measured accuracy benchmark. No accuracy metrics are claimed:
that requires labeled ground-truth data and a defined metric (planned
for M4). Confidence scores in the output are model self-assessment
scores useful for filtering low-quality lines; they are **not calibrated
probabilities**.

## Project Layout

```
src/documind/        core package (cli.py, ocr/: validation, preprocessing,
                     engine, results)
tests/               pytest suite
scripts/             dev utilities (sample receipt generator)
assets/samples/      small synthetic sample documents
data/                local datasets (ignored)
docs/                setup, architecture, learning notes
reports/             future evaluation results
```

## Known Limitations

- CPU-only; first run downloads PP-OCRv6 models (~tens of MB) from
  Hugging Face to `~/.paddlex` (outside the repo).
- oneDNN (MKLDNN) is disabled in the engine: the PaddlePaddle 3.x CPU
  Windows build crashes with a PIR attribute error when MKLDNN is on.
- Single image per invocation; no PDF input yet.
- No invoice field extraction, table reconstruction, database, or API yet.
- English model by default (`--lang` passes through to PaddleOCR).

## Roadmap

- **M2:** receipt/invoice field extraction (regex + layout heuristics)
- **M3:** table structure recognition
- **M4:** labeled evaluation dataset + accuracy metrics
- **M5:** API service and frontend

## Development Approach

Start with a reproducible OCR baseline, measure its
performance, and progressively improve the pipeline.
