# DocuMind AI — Complete Project Handoff

**Date:** 2026-10-26  
**Author:** [Current Session]  
**Project State:** M0/M1/M2/M3A/M4A/M4B Phase 1/M5A complete — **all CI green (315 tests)**

---

## TL;DR

DocuMind AI is a **local-first Document Intelligence platform** built in Python 3.12 with zero external API dependencies. It delivers:

| Pipeline | CLI Command | What it does | Status |
|----------|-------------|--------------|--------|
| **OCR** | `documind-ocr` | PaddleOCR 3.x (PP-OCRv6) → structured JSON (text, confidence, boxes) | ✅ Done (M1) |
| **Invoice Extraction** | `documind-extract` | OCR JSON → structured invoice (deterministic regex + layout rules) | ✅ Done (M2) |
| **Table Recognition** | `documind-table` | Ruled-grid detection (OpenCV) + OCR assignment → JSON/CSV/XLSX | ✅ Done (M3A) |
| **Evaluation** | `documind-eval` | CER/WER (OCR), field accuracy (Invoice), cell agreement (Table) | ✅ Done (M4A) |
| **Dataset Onboarding** | `documind-dataset` | Local real-doc workflow (anonymize → annotate → predict → evaluate) | ✅ Done (M4B Phase 1) |
| **Web UI** | `documind-web` | FastAPI + vanilla JS; upload → OCR/Invoice/Table → editable results | ✅ Done (M5A) |

**Key constraints:** CPU-only, no PDF input yet, ruled tables only, Vietnamese OCR not validated, **real-document accuracy pending labeled data**. All current numbers are synthetic.

---

## 1. Repository Structure

```
documind-ai/
├── .github/workflows/ci.yml        # Mocked + geometry-only tests (no PaddlePaddle, no GPU)
├── .venv/                          # Python 3.12 virtual environment (git-ignored)
├── assets/samples/                 # Small synthetic sample images (committed)
├── data/
│   ├── annotation/templates/       # Ground-truth JSON templates (committed)
│   ├── eval/synthetic/             # Synthetic eval manifests + ground truth (committed)
│   └── eval/real/                  # Real-doc dataset root (git-ignored entirely)
├── docs/                           # Specs, guides, learning notes (Vietnamese + English)
├── outputs/                        # Default CLI output directory (git-ignored)
├── reports/                        # Evaluation results (m3a, m4a baselines)
├── scripts/                        # Dev utilities (sample generators, evaluation)
├── src/documind/                   # Core package
│   ├── cli.py                      # documind-ocr entry point
│   ├── extract_cli.py              # documind-extract entry point
│   ├── table_cli.py                # documind-table entry point
│   ├── dataset.py / dataset_cli.py # Real-doc onboarding
│   ├── evaluation/                 # CER/WER, invoice eval, table eval, manifest, report
│   ├── extraction/                 # M2 pipeline (models, parsing, layout, extractor, validator, lexicon_vi)
│   ├── ocr/                        # M1 pipeline (engine, preprocessing, results, validation)
│   ├── tables/                     # M3A pipeline (geometry, assign, models, exporters, pipeline)
│   └── web/                        # M5A FastAPI app (app.py, service.py, schemas.py, pdf.py)
├── tests/                          # 315 pytest tests (mocked OCR, synthetic fixtures)
│   ├── fixtures/ocr/               # Synthetic OCR JSON fixtures (11 files)
│   └── fixtures/tables/            # Synthetic table ground truth (3 files)
├── AGENTS.md                       # Project-specific agent instructions
├── pyproject.toml                  # Build config, dependencies, entry points
└── requirements.lock.txt           # Exact pinned environment (reproducible)
```

---

## 2. Environment & Setup

**Python:** 3.12.10 (pinned: `>=3.12,<3.13` — Python 3.14 has no compatible wheels)  
**Key dependencies:** `paddlepaddle 3.3.1`, `paddleocr 3.7.0` (PP-OCRv6), `opencv-contrib-python 4.10`, `pillow 13.0`, `openpyxl 3.1`, `fastapi 0.162`, `uvicorn 0.54`, `pypdfium2 5.14`, `pytest 9.1`, `ruff 0.17`

```powershell
# One-time setup (Windows, Python 3.12)
winget install --id Python.Python.3.12 --scope user
cd documind-ai
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"       # or: pip install -r requirements.lock.txt
```

**First OCR run** downloads PP-OCRv6 models (~tens of MB) to `~/.paddlex` (outside repo).

---

## 3. Core Pipelines — Deep Dive

### 3.1 OCR (`src/documind/ocr/`)
- **Entry:** `cli.py` → `documind-ocr`
- **Engine:** `engine.py` — Thin wrapper around `paddleocr.PaddleOCR`
  - Models explicitly pinned: `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec`
  - Doc orientation/unwarping/classification **disabled** (keep baseline minimal)
  - **MKLDNN/oneDNN disabled** (Windows CPU build crashes with PIR attribute error)
  - Lazy import: `paddleocr` only imported inside `PaddleOcrEngine.__init__`
- **Preprocessing:** `preprocessing.py` — Pillow RGB conversion via temp PNG (context manager)
- **Validation:** `validation.py` — File exists, supported extension (PNG/JPG/BMP/TIFF/WEBP), ≤20 MB, not empty
- **Results:** `results.py` — `OcrResult` with `TextBox` (text, confidence, box); `normalize_result()` converts raw PaddleOCR 3.x output (`rec_texts`, `rec_scores`, `rec_polys`/`dt_polys`)

**Exit codes:** `0` success, `2` invalid input, `1` OCR failure.

---

### 3.2 Invoice Extraction (`src/documind/extraction/`)
- **Entry:** `extract_cli.py` → `documind-extract` (operates on saved OCR JSON, **no model run**)
- **Models:** `models.py` — `Invoice`, `LineItem`, `ExtractionResult`, `Provenance`
  - Financial values: `decimal.Decimal` internally, serialized as strings preserving scale (`"9.57"`)
  - `validation_status`: `ok` | `review_required` | `invalid`
  - Provenance maps every field → OCR region (index, text, box)
- **Parsing:** `parsing.py` — Deterministic money/date parsing
  - **Money rules:** Later separator = decimal; thousands if grouped; currency symbols stripped first; `MONEY_TOKEN_RE` accepts unbounded integers, malformed runs match **nothing** (never substring)
  - **Date formats:** Day-first before month-first (`05/04/2026` → 5 Apr)
- **Layout:** `layout.py` — Groups OCR tokens into visual lines (vertical overlap ≥50% of smaller height), orders within line by `x0`
- **Extractor:** `extractor.py` — 8-stage pipeline (supplier → invoice number → date → currency → line items → summary amounts → validation)
  - Vietnamese labels in `lexicon_vi.py` (diacritic-insensitive via NFD + đ→d + casefold)
  - Line items: header row `QTY...PRICE` / `SỐ LƯỢNG...ĐƠN GIÁ`; region = after header until first summary keyword; amount-free rows = description continuations
  - Summary: rightmost money token on matching row wins; multiple TOTAL rows → keep bottom-most; differing values → `ambiguous:` note
- **Validator:** `validator.py` — Completeness + arithmetic consistency judged **separately**
  - **Sufficiently complete** = monetary anchor (total/subtotal/any line_total) + identification (supplier/invoice_number/date)
  - Checks only when **all operands exist**: qty×price=line_total, sum(line_totals)=subtotal, total=subtotal+tax−discount, change=payment−total
  - Missing values never produce errors; `ok` = complete + no inconsistency; `review_required` = incomplete/ambiguous; `invalid` = demonstrated arithmetic error

---

### 3.3 Table Recognition (`src/documind/tables/`)
- **Entry:** `table_cli.py` → `documind-table`
- **Geometry (`geometry.py`):** Pure OpenCV, no OCR
  1. Binarize → inverted Otsu
  2. Erosion+dilation with `(w/15,1)` / `(1,h/15)` kernels (min 20px)
  3. H/V masks OR → dilate 3×3×2 → external contours → regions ≥40×40px
  4. Projection profiles inside region: ≥60% extent = line; cluster gap ≤3px; dedupe <5px
  5. Cells = intersections of consecutive row/col edges
- **Assignment (`assign.py`):** Geometric OCR-region → cell matching
  - Box center inside cell wins; fallback = largest box/cell intersection area
  - Unassigned regions → warnings (never dropped silently)
  - Within-cell ordering: top-to-bottom, left-to-right within visual lines (50% vertical center tolerance)
- **Models (`models.py`):** `Rect`, `TableCell`, `Table`, `TableResult`
- **Exporters (`exporters.py`):** JSON, CSV (per table; `_t0` suffixes for multi-table), XLSX (1 sheet/table)
  - CSV formula-injection protection: quote-prefix `'` for `=`, `+`, `@`, leading `-` (numeric `-5.00` kept)
  - XLSX: all values stored as explicit strings (`data_type="s"`), XML-illegal chars stripped
- **Pipeline (`pipeline.py`):** Orchestrates geometry + assignment; accepts `ocr_items` from saved JSON (no model run) or runs OCR lazily

**Limitations:** Complete axis-aligned ruled grids only; borderless/partial/rotated tables not recognized; text outside grid → warnings.

---

### 3.4 Evaluation (`src/documind/evaluation/`)
- **Entry:** `cli.py` → `documind-eval --task ocr|invoice|table --manifest <path>`
- **Manifest:** JSON with `task`, `provenance` (`synthetic|real|unknown`, default `unknown`), `documents[]` (id, prediction path, ground_truth path) — paths relative to manifest
- **OCR eval (`ocr_eval.py`):** CER/WER (Levenshtein), NFKC + casefold + whitespace collapse (configurable), micro-aggregation (total edits / total reference), per-doc operation counts + 5 error examples
- **Invoice eval (`invoice_eval.py`):** Field-level accuracy with null semantics
  - Both null = `true_negative` (excluded from denominator); GT+null = `missing` (never correct); null+pred = `extra`; diff = `incorrect`
  - Money: `Decimal` scale-insensitive; dates: ISO; text: casefold+collapse
  - Line items: **index-matched** (reading order assumed); strict item matching (incorrect matched item = 1 FP + 1 FN)
  - Micro + macro accuracy; item precision/recall/F1; item field accuracy (matched pairs only)
- **Table eval (`table_eval.py`):** Structural + cell agreement
  - Tables matched by index; missed table → all expected cells unmatched (can't score perfect)
  - Legacy: `cell_exact_agreement` = matched / expected reference cells (extra predictions don't enter denominator)
  - **Strict metrics:** `prediction_precision` = matched / (matched+incorrect+extra); `strict_cell_agreement` = matched / (expected+extra)
  - Unexpected cells (out-of-shape, duplicate, non-int coords) = extra with detailed issues
- **Report (`report.py`):** Markdown with per-doc tables, aggregates, worst documents, error examples, conventions, provenance caveat

---

### 3.5 Dataset Onboarding (`src/documind/dataset.py` + `dataset_cli.py`)
- **Root:** `data/eval/real/` (git-ignored); layout: `raw/`, `anonymized/`, `ground_truth/`, `predictions/`, `reports/`, `manifest-<task>.json`
- **Workflow:**
  1. `documind-dataset init` — creates layout + README
  2. `documind-dataset add <image> --id <id> --confirm-anonymized` — copies to `anonymized/`, requires explicit anonymization confirmation
  3. **Manual annotation** in `ground_truth/` using templates (`data/annotation/templates/`)
  4. `documind-dataset validate` — checks structure, placeholders, required keys, table matrix shapes, manifest validity
  5. `documind-dataset predict --task ocr|invoice|table` — runs local pipelines (OCR regenerated fresh every run), writes `predictions/` + `manifest-<task>.json` (provenance: `real`)
  6. `documind-eval --task <task> --manifest ...` — evaluates
- **Privacy:** Real documents never committed; anonymization = blur/replace in image (not just filename); `--confirm-anonymized` mandatory

---

### 3.6 Web App (`src/documind/web/`)
- **Entry:** `app.py` → `documind-web` (FastAPI, binds `127.0.0.1:8000`, no CORS)
- **Service layer (`service.py`):** Reusable orchestration, lazy singleton `PaddleOcrEngine`, **inference serialized** on `_inference_lock` (PaddleOCR not thread-safe)
- **Endpoints:**
  - `GET /api/health` — `{status, engine_loaded, version}`
  - `POST /api/ocr` — image → `OcrResponse`
  - `POST /api/invoice` — image → `InvoiceResponse` (runs OCR internally)
  - `POST /api/table` — image → `TableResponse` (ruled tables only)
  - `POST /api/process` — image **or PDF** + `workflow` (`auto|ocr|invoice|table`) → unified or multi-page result
  - `POST /api/export` — JSON `{kind, data, filename?}` → file download
- **Export kinds:** `ocr-json|txt`, `invoice-json|csv|xlsx`, `table-json|csv|xlsx`, `batch-zip`
- **PDF (M5B):** `pypdfium2` render ~144 DPI; limits: 10 pages, 30 MP/page; per-page results; partial success on failure
- **Security:** 10 MB upload limit, extension allowlist, Pillow decode check, 10k px / 30 MP dimension limit, temp files cleaned on all paths, OCR text never logged, CSV formula-injection policy re-applied on exports
- **Human-in-the-loop:** Corrections collected client-side (`user_corrections` keyed by field path), materialized into fresh copy on CSV/XLSX export; JSON keeps machine + corrections separate; original never mutated

---

## 4. Test Suite — What's Covered

**315 tests, all passing, ~4.5s**

| Test File | Coverage |
|-----------|----------|
| `test_cli.py` | CLI help, error codes, mocked OCR end-to-end |
| `test_extraction.py` | 11 fixture-based extraction tests (normal, missing fields, date formats, validation semantics, provenance, monetary regressions, EU separators, missing boxes, validation, ambiguity, edge cases) |
| `test_table_*.py` | Geometry detection, assignment, pipeline, exporters (CSV/XLSX read-back) |
| `test_evaluation_*.py` | Manifest loading, CLI, OCR/invoice/table eval metrics, report rendering, provenance handling |
| `test_dataset.py` | Init/add/validate/predict/manifest workflow, input validation, duplicate IDs, stale OCR prevention |
| `test_web_api.py` | All endpoints, validation (413/415/400/422), export kinds, correction materialization, inference serialization, temp cleanup |
| `test_web_pdf_batch.py` | PDF processing, preflight, batch zip, invoice exports, formula safety |

**CI (`.github/workflows/ci.yml`):** Runs ruff + pytest on Python 3.12 with **mocked/geometry-only tests** — never downloads PaddlePaddle or model weights, no GPU.

---

## 5. Key Design Principles

1. **Layer separation:** CLI ≠ logic; OCR engine not imported by extraction/tables/eval; enables unit testing with mocks
2. **Lazy imports:** `paddleocr` only loaded when `PaddleOcrEngine` instantiated — fast imports, fast test collection
3. **CPU-first, no training:** Pretrained PP-OCRv6 only; deterministic rules for extraction/tables
4. **Decimal for money:** Never float; preserves printed scale; arithmetic validation exact
5. **Provenance everywhere:** Every extracted field links to source OCR region (index, text, box)
6. **Explicit null semantics:** Missing ≠ empty; evaluation treats them differently
7. **Strict manifests:** Unknown task/provenance, empty docs, missing fields, duplicate IDs → fail loudly
8. **Provenance metadata:** Every evaluation summary carries `dataset.provenance`; reports render caveats; nothing auto-classified as "real"
9. **Local-first privacy:** Real data git-ignored; anonymization confirmation required; no cloud calls

---

## 6. Current Limitations (Do Not Claim Otherwise)

| Limitation | Details |
|------------|---------|
| **CPU-only** | First OCR run downloads models to `~/.paddlex` |
| **MKLDNN disabled** | Windows PaddlePaddle 3.x CPU build crashes with it enabled |
| **Single image per invocation** | No PDF input yet (except `/api/process` which renders PDF pages) |
| **Ruled tables only (M3A)** | Borderless, partial rules, rotated/skewed not supported |
| **Vietnamese OCR unvalidated** | Extraction has Vietnamese label lexicon but PP-OCRv6 `lang="en"`; recognition accuracy unknown |
| **Single currency, single page** | No multi-page invoice understanding |
| **No real-world accuracy** | All eval numbers synthetic; real-data evaluation **pending labeled data** |
| **No database/API** | Local file I/O only |
| **Index-based line item matching** | Content-based matching is future work |

---

## 7. Roadmap (from README)

| Milestone | Status | Notes |
|-----------|--------|-------|
| **M0/M1** | ✅ Done | OCR baseline (PaddleOCR 3.x, PP-OCRv6) |
| **M2** | ✅ Done | Receipt/invoice extraction (regex + layout) |
| **M3A** | ✅ Done | Ruled table recognition (OpenCV geometry) |
| **M4A** | ✅ Done | Evaluation framework (CER/WER, field accuracy, table agreement) |
| **M4B Phase 1** | ✅ Done | Real-doc dataset onboarding tooling |
| **M5A** | ✅ Done | Local FastAPI + web frontend |
| **M4B Phase 2** | 🔲 Pending | Evaluate on labeled real documents |
| **M5B** | 🔲 Pending | PDF input, batch processing, richer exports |
| **M5C** | 🔲 Pending | Extraction robustness + Vietnamese labels/i18n |
| **M3B** | 🔲 Planned | Borderless table recognition (model-based) |

---

## 8. Critical Files for a New Maintainer

| File | Why it matters |
|------|----------------|
| `README.md` | User-facing overview, usage, roadmap, limitations |
| `AGENTS.md` | Project-specific agent instructions (architecture, commands, security, git workflow) |
| `docs/extraction-spec.md` | Complete M2 rule tables, monetary parsing, validation semantics |
| `docs/evaluation-spec.md` | Metric definitions, null handling, aggregation conventions |
| `docs/table-recognition-spec.md` | M3A geometry pipeline, assignment rules, export formats |
| `docs/dataset-annotation-guide.md` | Real-doc workflow, privacy, templates, labeling guidelines |
| `docs/web-api.md` | Endpoint contracts, security, export kinds, limits |
| `src/documind/ocr/engine.py` | Pinned PP-OCRv6 models, MKLDNN disable rationale |
| `src/documind/extraction/extractor.py` | 8-stage pipeline, provenance recording |
| `src/documind/extraction/validator.py` | Completeness vs arithmetic consistency separation |
| `src/documind/extraction/lexicon_vi.py` | Vietnamese diacritic-insensitive label matching |
| `src/documind/tables/geometry.py` | Deterministic grid detection (OpenCV only) |
| `src/documind/tables/assign.py` | Geometric OCR→cell assignment, warnings for unassigned |
| `src/documind/evaluation/*.py` | Three task evaluators with strict conventions |
| `src/documind/web/service.py` | Shared engine, inference lock, unified processing |
| `pyproject.toml` | Dependencies, entry points, pytest/ruff config |
| `requirements.lock.txt` | Exact reproducible environment |

---

## 9. Verification Commands

```powershell
# Lint + tests (pre-push gate)
cd documind-ai
.\.venv\Scripts\Activate.ps1
python scripts/verify.py      # ruff + frontend-gate + pytest

# Individual
ruff check src tests scripts
pytest -q                     # 315 tests, ~4.5s

# Smoke test (real inference)
documind-ocr assets/samples/sample_receipt.png -o outputs/sample_receipt.json
documind-extract outputs/sample_receipt.json -o outputs/sample_receipt.invoice.json
documind-table assets/samples/table_products.png -o outputs/table_products.tables.json --csv outputs/table_products.csv --xlsx outputs/table_products.xlsx

# Evaluation (synthetic)
documind-eval --task ocr --manifest data/eval/synthetic/ocr/manifest.json
documind-eval --task invoice --manifest data/eval/synthetic/invoice/manifest.json
documind-eval --task table --manifest data/eval/synthetic/table/manifest.json

# Web app
pip install -e ".[web]"
documind-web   # http://127.0.0.1:8000
```

---

## 10. Known Issues / Gotchas

1. **Verify script path sensitivity:** `python scripts/verify.py` must run from repo root (uses relative paths `src`, `tests`, `scripts`)
2. **Windows MKLDNN crash:** Do not enable `enable_mkldnn=True` in `PaddleOcrEngine` — it crashes
3. **Provenance in manifests:** Always declare `provenance: "synthetic"` or `"real"`; default `"unknown"` renders "do not treat as real-world accuracy"
4. **Dataset directory git-ignored:** `data/eval/real/` never committed by default; committing anonymized GT is explicit decision
5. **No ground truth from predictions:** `documind-dataset` never generates labels from model output — manual annotation only
6. **Line item matching by index:** Evaluation assumes reading order preserved; content-based matching would change denominators (versioned metric change)
7. **PDF multipage processing:** Single-page extractor per page; no cross-page relationship inference
8. **Export limits:** ≤50 tables, ≤500 rows/cols, ≤20k cells — enforced at export endpoint with 422

---

## 11. What's Needed to Move Forward

| Next Step | What's Required |
|-----------|-----------------|
| **M4B Phase 2 (Real eval)** | Licensed, privacy-cleared real documents; manual annotation per `docs/dataset-annotation-guide.md`; commit manifests + GT to `data/eval/real/` (git-ignored) or new dataset dir |
| **M5B (PDF)** | Extend `/api/process` batch; add CLI `documind-pdf`; improve cross-page invoice logic |
| **M5C (VN extraction)** | Validate PP-OCRv6 on Vietnamese text; add `lang="vi"` support; extend lexicon; add diacritic-aware amount parsing |
| **M3B (Borderless tables)** | Model-based table structure recognition (TableFormer, PubTables, etc.); fallback to ruled geometry |
| **Database/API** | Design schema (PostgreSQL); add persistence layer; consider auth if ever deployed |

---

## 12. Git History Context

- **Main branch:** All work merged via PRs targeting `main`
- **Current PR:** #2 (M2 review fixes) — merged, CI green
- **Branch naming:** `feat/<milestone>-<slug>` (e.g., `feat/m3a-table-recognition`)
- **Never force-push;** PRs stay open for review unless explicitly authorized

---

## 13. Memory & Context Files (Persistent)

Agent-session memory files live OUTSIDE the repository (in the ZCode CLI
memory directory for this project) and are never committed. They track
milestone status and maintainer preferences across sessions; consult them
via the agent tooling, not git.

---

## 14. Quick Mental Model for New Contributors

> **DocuMind = deterministic pipelines on saved artifacts, not a training framework.**
>
> - OCR runs once → saves JSON
> - Extraction/tables/eval **never re-run OCR** — they transform saved JSON
> - Web service reuses OCR items across workflows (single inference per request)
> - Evaluation runs on **predictions vs ground truth** — no model inference
> - All "accuracy" numbers are **synthetic**; real-world = pending labeled data

This architecture makes everything testable, reproducible, and debuggable — the price is manual pipeline orchestration (CLI per step) and no end-to-end learned optimization. That's intentional for a baseline.

---

*End of handoff. This document reflects the exact state as of 2026-10-26 with all 315 tests passing and CI green.*