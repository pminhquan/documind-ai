# DocuMind AI — Complete Project Handoff

**Date:** 2026-10-29

**Dated main checkpoints:** `130f32207e316330cba15d31c23558c6a2987607` (PR #13 merge, post-D18), `31a8f1bde0328402cb976b7e0f257871ebc2848b` (PR #14 merge; PR #15 base — does not contain D-16), and `231cd909924f75b4d46816ca028bbdca5b6107ef` (PR #15 merge, D-16 integrated; 519 tests; CI run [40843248171](https://github.com/pminhquan/documind-ai/actions/runs/40843248171)). Inspect live `origin/main` for the current HEAD.

**Project state:** M0/M1, M2, M3A, M4A, M4B Phase 1, M5A, M5B (including D-18), M5C extraction rules, and M5D synthetic performance baseline are complete and integrated on `main`. M4B Phase 2 remains pending real labeled data.

**2026-10-31 P3 integration release.** Starting from verified `origin/main` @ `4d01e78ec95d58f3b7ca2113da08489e8ec1092d` (PR #16 merge; 643 tests), the seven engineering PRs below were **merged into `main` on 2026-10-31** in the reviewed order (#17 → #18 → #19 → #20 → #21 → #22 → #23), each through a regular two-parent merge commit of its exact reviewed head, each confirmed by a green CI run on the resulting main SHA, with per-stage pytest totals matching the additive cross-check. The combined baseline on main after PR #23 is **715 passing tests** (ruff and the frontend gate green). This documentation PR #24 is the final step of the release. The table also preserves the pre-merge heads as a dated historical snapshot.

PR branches were based on `4d01e78` (independent, non-stacked); the per-PR test count is that PR's own CI total on its branch — the **integrated** total after each merge is listed separately:

| PR | Branch @ reviewed head | Defect | Merge commit (main) | Post-merge CI | Tests after merge |
|----|------------------------|--------|---------------------|---------------|-------------------|
| #17 | `fix/d23-d24-dataset-lifecycle` @ `defee19` | D-23, D-24 | `3f4bab3` | [41192946913](https://github.com/pminhquan/documind-ai/actions/runs/41192946913) | 648 |
| #18 | `fix/d29-d30-d20-signed-amounts-dates` @ `17bee92` | D-29, D-30, D-20 | `0df8a68` | [41193058369](https://github.com/pminhquan/documind-ai/actions/runs/41193058369) | 696 |
| #19 | `fix/d31-word-level-qty-price` @ `9236b23` | D-31 | `418ac5c` | [41193148990](https://github.com/pminhquan/documind-ai/actions/runs/41193148990) | 702 |
| #20 | `fix/d32-header-provenance` @ `6bf7e12` | D-32 | `e9bcbb0` | [41193231289](https://github.com/pminhquan/documind-ai/actions/runs/41193231289) | 706 |
| #21 | `fix/d34-assign-line-tolerance` @ `42c0d07` | D-34 | `1f10ab9` | [41193801548](https://github.com/pminhquan/documind-ai/actions/runs/41193801548) | 712 |
| #22 | `fix/d33-temp-cleanup` @ `57a0cd1` | D-33 | `b727bbd` | [41193870275](https://github.com/pminhquan/documind-ai/actions/runs/41193870275) | 713 |
| #23 | `fix/d28-ocr-json-byte-guard` @ `469879c` | D-28 | `c1528ab` | [41193945173](https://github.com/pminhquan/documind-ai/actions/runs/41193945173) | 715 |

A cumulative dry-run on a throwaway worktree (never pushed, removed afterwards) had predicted these totals before the real merges; every real post-merge CI run matched the prediction exactly. Post-merge synthetic acceptance on an isolated checkout of `c1528ab` passed for D-16 receipts, D-22 rejection, D-23/D-24 lifecycle, signed/tight-label totals, dates and textual months, word-level quantity rows, header provenance, tiny-leading-token table assignment, temp-PNG cleanup and the OCR JSON size guard; `git diff 4d01e78..main -- src/documind/evaluation/` is empty — no metric definition or denominator changed.

Closed as already-resolved or documented without code changes: **D-27** (correction keys use per-File sequential doc ids — no name collisions), **D-25** and **D-26** (documented in `docs/evaluation-spec.md` / `pdf.py` docstring), **D-21** (UTF-8-without-BOM documented as existing compatibility behavior with a **pending product decision** in `docs/web-api.md`), and the evaluation `rows × columns` allocation risk (documented in `docs/evaluation-spec.md`: the table evaluator allocates its expected-shape grid from the GROUND-TRUTH side's declared dimensions — sparse ground truth with enormous declared dimensions passes validation and can exhaust memory, so file size alone does not bound memory; accepted local-tool risk, with resource budgeting recorded as an unresolved backlog item). None of these PRs are merged; the owner reviews and merges. The recovery session also rebuilt the Windows environment: Python 3.12.10 via winget, repaired `.venv` (packages preserved), Node.js LTS for the frontend gate, and fixed post-reinstall file-ownership (old-SID ACLs) that blocked git/pip writes.

**Dated release checkpoint:** at the post-D18 release checkpoint, main SHA `130f322` had **392 passing pytest tests**; CI run [40439790177](https://github.com/pminhquan/documind-ai/actions/runs/40439790177) completed successfully. This is a historical verified snapshot, not a promise that future HEADs always have 392 tests.

**D-16 / PR #15:** merged into `main` via PR #15 (merge commit `231cd909924f75b4d46816ca028bbdca5b6107ef`, 2026-10-29; 519 tests, CI run [40843248171](https://github.com/pminhquan/documind-ai/actions/runs/40843248171)). The base `31a8f1bde0328402cb976b7e0f257871ebc2848b` (PR #14 merge) did **not** contain D-16. **D-22 / PR #16:** evaluation-input validation is merged on `main` (merge commit `4d01e78ec95d58f3b7ca2113da08489e8ec1092d`); do not reimplement it. The P3 audit follow-ups were merged via PRs #17–#23 on 2026-10-31 (release record below).

> For a new agent: read this file together with `AGENTS.md`, then inspect Git and the code. Do not use a stale local `main` as the base; fetch and branch from `origin/main`. This document covers the post-D18 state, the PR #14 integration base, D-16 and D-22 on `main`, and the 2026-10-31 P3 release (PRs #17–#23 merged); if HEAD has moved, `git log` and CI are authoritative.

---

## TL;DR

DocuMind AI is a **local-first Document Intelligence platform** built in Python 3.12. It delivers:

| Pipeline | Entry point | What it does | Status |
|----------|-------------|--------------|--------|
| **OCR** | `documind-ocr` | PaddleOCR 3.x (PP-OCRv6) → structured JSON (text, confidence, boxes) | ✅ M1 |
| **Invoice Extraction** | `documind-extract` | OCR JSON → structured invoice (deterministic regex + layout rules) | ✅ M2 |
| **Table Recognition** | `documind-table` | Ruled-grid detection (OpenCV) + OCR assignment → JSON/CSV/XLSX | ✅ M3A |
| **Evaluation** | `documind-eval` | CER/WER (OCR), field accuracy (invoice), cell agreement (table) | ✅ M4A |
| **Dataset Onboarding** | `documind-dataset` | Local real-doc workflow (anonymize → annotate → predict → evaluate) | ✅ M4B Phase 1 |
| **Web UI / API** | `documind-web` | FastAPI + vanilla JS; image or PDF → OCR/Invoice/Table/Auto → editable, exportable results | ✅ M5A/M5B (D-18) |

**Key constraints:** CPU-first; no database; no LLM or model training; the CLI is image-oriented while PDF input is web-only; ruled tables only; no cross-page invoice aggregation; Vietnamese **extraction rules** exist but Vietnamese **OCR recognition** is not validated; all automated tests and the recorded benchmark use synthetic/mocked inputs, so **real-document accuracy remains unvalidated**.

---

## 1. Repository Structure

```
documind-ai/
├── .agents/skills/                  # Focused agent skills (Markdown, read on demand)
├── .github/workflows/ci.yml         # Ruff + Node gate + pytest (mocked; no PaddlePaddle/GPU)
├── assets/samples/                  # Small synthetic sample images (committed)
├── data/
│   ├── annotation/templates/        # Ground-truth JSON templates (committed)
│   ├── eval/synthetic/              # Synthetic eval manifests + ground truth (committed)
│   └── eval/real/                   # Real-doc dataset root (git-ignored entirely)
├── docs/                            # Specs, guides, web API, product plan, notes
├── outputs/                         # Default CLI output directory (git-ignored)
├── reports/                         # m3a/m4a evaluations, benchmark, audit
├── scripts/                         # verify, browser gate, samples, eval, benchmark
├── src/documind/                    # Core package
│   ├── cli.py                       # documind-ocr
│   ├── extract_cli.py               # documind-extract
│   ├── table_cli.py                 # documind-table
│   ├── dataset.py / dataset_cli.py  # Real-doc onboarding
│   ├── ocr/                         # M1 pipeline
│   ├── extraction/                  # M2 + M5C (lexicon_vi.py)
│   ├── tables/                      # M3A pipeline + exports
│   ├── evaluation/                  # M4A metrics, manifests, reports
│   └── web/                         # M5A/M5B/D-18 (app.py, service.py, schemas.py, pdf.py, static/)
├── tests/                           # pytest suite + fixtures
│   ├── fixtures/ocr/                # Synthetic OCR JSON fixtures
│   ├── fixtures/tables/             # Synthetic table ground truth
│   └── fixtures/frontend/           # Node DOM harness scenarios (pdf_page_harness.js)
├── AGENTS.md                        # Agent instructions
├── HANDOFF.md                       # This file
├── pyproject.toml                   # Build config, deps, entry points
└── requirements.lock.txt            # Historical env snapshot (pins an older commit)
```

`docs/product-expansion-plan.md` is the milestone/backlog roadmap. `docs/web-api.md` is the normative wire contract for the web app.

---

## 2. Environment & Setup

- **Python:** 3.12.10 (pinned: `>=3.12,<3.13`; Python 3.14 has no compatible wheels)
- **Key dependencies:** `paddlepaddle 3.3.1`, `paddleocr 3.7.0` (PP-OCRv6), `opencv-contrib-python 4.10`, `pillow 13.0`, `openpyxl 3.1`, `fastapi 0.162`, `uvicorn 0.54`, `pypdfium2 5.14`, `pytest 9.1`, `ruff 0.17`
- **Node.js:** required for the frontend gate and `tests/test_frontend_pdf_pages.py` (CI uses Node 20; a recent Node 24 also works).

```powershell
# One-time setup (Windows, Python 3.12)
winget install --id Python.Python.3.12 --scope user
cd documind-ai
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pip install -e ".[web]"       # only needed to run the web app
```

`requirements.lock.txt` is a historical environment snapshot, not an
installer: it pins the project itself to an earlier commit
(`ab62d749`, pre-M5A). Use the editable installs above.

**First OCR run** downloads PP-OCRv6 models (~tens of MB) to `~/.paddlex` (outside repo). Tests never download models.

---

## 3. Core Pipelines — Deep Dive

### 3.1 OCR (`src/documind/ocr/`)
- **Entry:** `cli.py` → `documind-ocr`
- **Engine:** `engine.py` — thin wrapper around `paddleocr.PaddleOCR`
  - Models explicitly pinned: `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec`
  - Doc orientation/unwarping/classification **disabled** (keep the baseline minimal)
  - **MKLDNN/oneDNN disabled** (Windows CPU build crashes with a PIR attribute error)
  - Lazy import: `paddleocr` only imported inside `PaddleOcrEngine.__init__`
- **Preprocessing:** `preprocessing.py` — Pillow RGB conversion via temp PNG (context manager)
- **Validation:** `validation.py` — file exists, supported extension (PNG/JPG/BMP/TIFF/WEBP), ≤20 MB, not empty
- **Results:** `results.py` — `OcrResult` with `TextBox` (text, confidence, box); `normalize_result()` converts raw PaddleOCR 3.x output (`rec_texts`, `rec_scores`, `rec_polys`/`dt_polys`)

**Exit codes:** `0` success, `2` invalid input, `1` OCR failure.

---

### 3.2 Invoice Extraction (`src/documind/extraction/`)
- **Entry:** `extract_cli.py` → `documind-extract` (operates on saved OCR JSON, **no model run**)
- **Models:** `models.py` — `Invoice`, `LineItem`, `ExtractionResult`, `Provenance`
  - Financial values: `decimal.Decimal` internally, serialized as strings preserving scale (`"9.57"`)
  - `validation_status`: `ok` | `review_required` | `invalid`
  - Provenance maps every field → OCR region (index, text, box)
- **Parsing:** `parsing.py` — deterministic money/date parsing
  - **Money rules:** later separator = decimal; thousands if grouped; currency symbols stripped first; `MONEY_TOKEN_RE` accepts unbounded integers, malformed runs match **nothing** (never substring)
  - **Date formats:** day-first before month-first (`05/04/2026` → 5 Apr)
- **Layout:** `layout.py` — groups OCR tokens into visual lines (vertical overlap ≥50% of smaller height), orders within line by `x0`
- **Extractor:** `extractor.py` — 8-stage pipeline (supplier → invoice number → date → currency → line items → summary amounts → validation)
  - Vietnamese labels in `lexicon_vi.py` (diacritic-insensitive via NFD + đ→d + casefold); VND money symbols/formats at the extraction layer
  - Line items: header row `QTY...PRICE` / `SỐ LƯỢNG...ĐƠN GIÁ`; region = after header until first summary keyword; amount-free rows = description continuations
  - Summary: rightmost money token on matching row wins; multiple TOTAL rows → keep bottom-most; differing values → `ambiguous:` note
- **Validator:** `validator.py` — completeness + arithmetic consistency judged **separately**
  - **Sufficiently complete** = monetary anchor (total/subtotal/any line_total) + identification (supplier/invoice_number/date)
  - Checks only when **all operands exist**: qty×price=line_total, sum(line_totals)=subtotal, total=subtotal+tax−discount, change=payment−total
  - Missing values never produce errors; `ok` = complete + no inconsistency; `review_required` = incomplete/ambiguous; `invalid` = demonstrated arithmetic error

M5C delivered **extraction rules**, not OCR accuracy: the default OCR model remains English, and Vietnamese recognition quality is unmeasured.

---

### 3.3 Table Recognition (`src/documind/tables/`)
- **Entry:** `table_cli.py` → `documind-table`
- **Geometry (`geometry.py`):** pure OpenCV, no OCR
  1. Binarize → inverted Otsu
  2. Erosion+dilation with `(w/15,1)` / `(1,h/15)` kernels (min 20px)
  3. H/V masks OR → dilate 3×3×2 → external contours → regions ≥40×40px
  4. Projection profiles inside region: ≥60% extent = line; cluster gap ≤3px; dedupe <5px
  5. Cells = intersections of consecutive row/col edges
- **Assignment (`assign.py`):** geometric OCR-region → cell matching
  - Box center inside cell wins; fallback = largest box/cell intersection area
  - Unassigned regions → warnings (never dropped silently)
  - Within-cell ordering: top-to-bottom, left-to-right within visual lines (50% vertical center tolerance)
- **Models (`models.py`):** `Rect`, `TableCell`, `Table`, `TableResult`
- **Exporters (`exporters.py`):** JSON, CSV (per table; `_t0` suffixes for multi-table), XLSX (1 sheet/table)
  - CSV formula-injection protection: quote-prefix `'` for `=`, `+`, `@`, leading `-` (numeric `-5.00` kept)
  - CSV encoding is UTF-8 **without BOM** (known D-21 limitation; Excel on Windows may mojibake Vietnamese)
  - XLSX: all values stored as explicit strings (`data_type="s"`), XML-illegal chars stripped, worksheet titles sanitized/capped/deduplicated
- **Pipeline (`pipeline.py`):** orchestrates geometry + assignment; accepts `ocr_items` from saved JSON (no model run) or runs OCR lazily

**Limitations:** complete axis-aligned ruled grids only; borderless/partial/rotated tables not recognized; text outside grid → warnings.

---

### 3.4 Evaluation (`src/documind/evaluation/`)
- **Entry:** `cli.py` → `documind-eval --task ocr|invoice|table --manifest <path>`
- **Manifest:** JSON with `task`, `provenance` (`synthetic|real|unknown`, default `unknown`), `documents[]` (id, prediction path, ground_truth path) — paths relative to manifest
- **OCR eval (`ocr_eval.py`):** CER/WER (Levenshtein), NFKC + casefold + whitespace collapse (configurable), micro-aggregation (total edits / total reference), per-doc operation counts + 5 error examples
- **Invoice eval (`invoice_eval.py`):** field-level accuracy with null semantics
  - Both null = `true_negative` (excluded from denominator); GT+null = `missing` (never correct); null+pred = `extra`; diff = `incorrect`
  - Money: `Decimal` scale-insensitive; dates: ISO; text: casefold+collapse
  - Line items: **index-matched** (reading order assumed); strict item matching (incorrect matched item = 1 FP + 1 FN)
  - Micro + macro accuracy; item precision/recall/F1; item field accuracy (matched pairs only)
- **Table eval (`table_eval.py`):** structural + cell agreement
  - Tables matched by index; missed table → all expected cells unmatched (can't score perfect)
  - Legacy: `cell_exact_agreement` = matched / expected reference cells (extra predictions don't enter denominator)
  - **Strict metrics:** `prediction_precision` = matched / (matched+incorrect+extra); `strict_cell_agreement` = matched / (expected+extra)
  - Unexpected cells (out-of-shape, duplicate, non-int coords) = extra with detailed issues
- **Report (`report.py`):** Markdown with per-doc tables, aggregates, worst documents, error examples, conventions, provenance caveat

Malformed evaluation inputs (D-22): the pre-D-22 behavior let non-dict line items/cells or missing structural keys surface as tracebacks instead of clean CLI errors. D-22 input validation is merged on `main` (PR #16, merge commit `4d01e78`).

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
- **Privacy:** real documents never committed; anonymization = blur/replace in the image (not just filename); `--confirm-anonymized` mandatory

Known lifecycle gaps (D-23/D-24): `add` can run before `init`, and `validate` does not yet flag manifest/annotation drift. Revalidate these against current code before starting that work.

---

### 3.6 Web App (`src/documind/web/`) — M5A/M5B/D-18

- **Entry:** `app.py` → `documind-web` (FastAPI, binds `127.0.0.1:8000`, no CORS, no auth)
- **Service layer (`service.py`):** reusable orchestration, lazy singleton `PaddleOcrEngine`, **inference serialized** on `_inference_lock` (PaddleOCR is not thread-safe)
- **Frontend:** `static/index.html`, `static/app.js`, `static/style.css` — vanilla JS, no build step

**Endpoints:**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | `{status, engine_loaded, version}` |
| POST | `/api/ocr` | image → `OcrResponse` |
| POST | `/api/invoice` | image → `InvoiceResponse` (runs OCR internally) |
| POST | `/api/table` | image → `TableResponse` (ruled tables only) |
| POST | `/api/process` | image **or PDF** + `workflow` (`auto/ocr/invoice/table`) → unified or multi-page result |
| POST | `/api/export` | JSON `{kind, data, filename?}` → file download |

**Export kinds:** `ocr-json|txt`, `invoice-json|csv|xlsx`, `table-json|csv|xlsx`, `batch-zip`. Multi-table `table-csv` returns a ZIP when there are ≥2 tables. Unknown kinds and malformed payloads → 422 (D-17); JSON exports pass through untouched; CSV/XLSX materialize corrections into fresh copies.

**PDF (M5B):** `pypdfium2` renders pages at ~144 DPI. Limits: **10 pages**, **30 MP per page**, **60 MP cumulative**, **15,000 PDF points per side** — violations return 400. Results are page-indexed (`{kind: "pdf", page_count, pages: [{page_index, ocr, invoice, tables}], errors}`); a failing page is recorded while other pages still process. Page images live in a temp directory removed afterwards. Single-page extractor per page; no cross-page relationship inference.

**D-18 page-level exports and identity:**
- The active PDF page is tracked by `page_index`, not array position.
- A PDF export reads only the selected page, with names `<stem>-page-<N>-<artifact>.<ext>` (N = `page_index + 1`); missing page artifacts produce an explicit UI error, never an empty financial export.
- Each selected **file instance** gets an opaque run-local document id; correction keys are `<document-id>#<page_index>`. Filenames are display/export labels only, so two files with the same name keep separate corrections and batch entries.
- Corrections survive page switches and repeated exports in a run; a new selection or processing run clears them. Reset removes one correction family for the active page only. Machine output is never mutated.

**Batch (M5B/D-18):**
- The UI processes up to **10 files sequentially**, one document in memory at a time, with per-file status, error isolation, partial success, and Stop.
- A new run replaces the previous results **and** corrections; a cancelled run exports only completed documents.
- `batch-zip` has ≤10 entries including the failure report. Sanitized names are unique case-insensitively (first case preserved; later collisions get `_2`, `_3`, ...); the 80-character cap budgets the extension; entries are never overwritten.
- Each successful PDF contributes one complete JSON entry (`kind: "ocr-json"`) with all pages, per-page OCR/invoice/tables, page-local `user_corrections`, and failed pages as `{page_index, error}`.
- Image Auto contributes one full snapshot `{workflow: "auto", ocr, invoice, tables, user_corrections}`; per-workflow image entries keep their pre-D-18 shapes.
- In mixed batches the failure report is written **first** as `batch-errors.json`; a successful document whose derived name collides keeps its artifact as `batch-errors_2.json`. Success-only batches are unchanged. No fabricated OCR/invoice/table records for failures.

**Security:** 10 MB upload limit, extension allowlist, Pillow decode check, 10k px / 30 MP dimension limit, temp files cleaned on all paths, OCR text never logged, stable `upload` / `upload#pageN` source labels (no absolute temp paths, D-19), CSV formula-injection policy re-applied on exports, XLSX-safe worksheet titles, bounded export payloads.

**Known export edge case:** a single-file export with a very long source stem can lose its extension because the download-header filename is capped at 100 characters; batch ZIP names budget the extension and are unaffected. This is a recorded follow-up (P3), not silent data loss.

Full wire contracts: `docs/web-api.md`.

---

## 4. Test Suite — What's Covered

### 4.1 Dated release checkpoint

At the post-D18 release checkpoint (2026-10-27), main SHA `130f32207e316330cba15d31c23558c6a2987607` had **392 passing pytest tests**, ruff clean, and the frontend gate green. Evidence: [CI run 40439790177](https://github.com/pminhquan/documind-ai/actions/runs/40439790177) (1 warning: a pre-existing Starlette/httpx deprecation). This is a historical snapshot; do not hardcode 392 as a permanent total. Run the suite for the current count.

### 4.2 What the tests actually prove

| Class | Location | Real OCR model? | What it validates |
|---|---|---|---|
| **A. Pytest unit/regression** | `tests/` | No — mocked OCR, synthetic JSON, geometry-only images | Application logic, contracts, error paths, export read-back |
| **B. Node DOM frontend** | `tests/test_frontend_pdf_pages.py` + `tests/fixtures/frontend/pdf_page_harness.js` | No | Real `static/app.js` behavior in a Node VM: page switching, correction restoration, resets, export payloads, batch ZIP; payloads are posted to the real FastAPI endpoints and artifacts read back |
| **C. Browser smoke (manual)** | Release acceptance, not committed as a test | No — mocked backend | Real Chromium UI navigation, edits, resets, downloads, mixed batch ZIP; **not** recognition quality |
| **D. Historical real-inference smoke** | `reports/benchmark-local.md`, `reports/m3a-synthetic-evaluation.md` | Yes, at the recorded time | Single-image pipeline wiring and synthetic cell agreement; not re-run in CI |
| **E. Genuine real-document accuracy** | — | — | **Pending** privacy-cleared, manually annotated documents (M4B Phase 2) |

**No test, benchmark, or browser smoke run establishes real-world OCR accuracy.** Confidence scores are model self-assessment, not calibrated probabilities.

### 4.3 Test files

| Test file | Coverage |
|-----------|----------|
| `test_cli.py`, `test_results.py`, `test_validation.py` | CLI behavior, exit codes, result normalization, input validation |
| `test_extraction.py`, `test_extraction_vi.py` | M2 field rules, monetary/date regressions, validation semantics, provenance, Vietnamese labels/VND |
| `test_tables_*.py` | Geometry, assignment, pipeline, JSON/CSV/XLSX read-back, formula-injection safety |
| `test_evaluation_*.py`, `test_text_metrics.py` | Manifest loading, CLI, OCR/invoice/table metrics, report rendering, provenance |
| `test_dataset.py` | Init/add/validate/predict/manifest workflow, privacy gate, duplicate IDs, stale OCR prevention |
| `test_web_api.py` | Endpoints, upload validation (413/415/400/422), export kinds, D-17 malformed payloads, D-19 source labels, XLSX titles, correction materialization, inference serialization, temp cleanup |
| `test_web_pdf_batch.py` | PDF preflight/processing, page limits, batch ZIP naming (case-insensitive, long names, sanitization), invoice exports, formula safety |
| `test_frontend_pdf_pages.py` | D-18 frontend behavior via Node harness + FastAPI read-back (scenarios A–V) |
| `test_frontend_gate.py` | Executes the real `app.js` under Node so a top-level load error cannot ship |

**CI (`.github/workflows/ci.yml`):** ruff + browser-script gate + pytest on Python 3.12 with Node 20, installing only lightweight test dependencies — no PaddlePaddle, no model weights, no GPU. A green CI validates application logic only.

---

## 5. Key Design Principles

1. **Layer separation:** CLI ≠ logic; OCR engine not imported by extraction/tables/eval; web/service calls service functions, never CLI subprocesses.
2. **Lazy imports:** `paddleocr` only loaded when `PaddleOcrEngine` is instantiated — fast imports and test collection.
3. **CPU-first, no training:** pretrained PP-OCRv6 only; deterministic rules for extraction/tables.
4. **Decimal for money:** never float; preserves printed scale; exact arithmetic validation.
5. **Provenance everywhere:** every extracted field links to its source OCR region.
6. **Explicit null semantics:** missing ≠ empty; evaluation treats them differently.
7. **Human corrections are separate state:** machine output is immutable; corrections are keyed by opaque document id + page, never by filename.
8. **Export safety is contract:** formula-injection protection, filename/ZIP sanitization, worksheet-title safety, and read-back tests are mandatory.
9. **Local-first privacy:** real data git-ignored; anonymization confirmation required; document data never leaves the machine (model weights download once from Hugging Face); no public binding.
10. **Honest evidence:** mocked/synthetic tests are never described as real OCR accuracy; benchmark numbers are runtime, not quality.

---

## 6. Current Limitations (Do Not Claim Otherwise)

| Limitation | Details |
|------------|---------|
| **CPU-only** | First OCR run downloads models to `~/.paddlex` |
| **MKLDNN disabled** | Windows PaddlePaddle 3.x CPU build crashes with it enabled |
| **CLI is image-oriented** | PDF input exists through `/api/process` (web API), not the CLI |
| **No cross-page invoice understanding** | Each PDF page is extracted independently; no aggregation |
| **Ruled tables only (M3A)** | Borderless, partial rules, rotated/skewed not supported; M3B deferred |
| **Vietnamese OCR unvalidated** | M5C added extraction labels/VND rules; PP-OCRv6 `lang="en"` recognition of diacritics is unmeasured |
| **Single currency, single page** | No multi-page/multi-currency invoice model |
| **No real-world accuracy** | All eval numbers are synthetic; real-document evaluation **pending labeled data** |
| **No database/job queue** | Stateless web app; batch is sequential in the browser; no resume or multi-user deployment |
| **Batch UI shows the last document** | There is no full batch navigator in the results panel |
| **CSV UTF-8 without BOM** | Excel on Windows may display Vietnamese text incorrectly (D-21) |
| **Long single-export filenames** | A very long stem can lose its extension at the 100-character download-header cap; batch ZIP is safe |
| **Remaining audit defects** | None open from the 2026-10-26 audit: D-16 (PR #15), D-22 (PR #16) and the P3 batch (PRs #17–#23) are integrated on `main` @ `346d1c5` (715 tests); D-21 stays a pending product decision |
| **Local-only** | 127.0.0.1, no CORS, no auth; do not expose |

---

## 7. Milestone Status

| Milestone | Status | Notes |
|-----------|--------|-------|
| **M0/M1** | ✅ Done | OCR baseline (PaddleOCR 3.x, PP-OCRv6) |
| **M2** | ✅ Done | Receipt/invoice extraction (regex + layout, Decimal money) |
| **M3A** | ✅ Done | Ruled table recognition (OpenCV geometry) |
| **M4A** | ✅ Done | Evaluation framework (CER/WER, field accuracy, strict table agreement) |
| **M4B Phase 1** | ✅ Done | Real-doc dataset onboarding tooling |
| **M5A** | ✅ Done | Local FastAPI + vanilla JS web app |
| **M5B (including D-18)** | ✅ Done | PDF page-indexed processing, page-level exports, batch ZIP, identity/correction isolation, ZIP naming hardening |
| **M5C** | ✅ Extraction rules done | Vietnamese labels/VND money at the extraction layer; **OCR accuracy not validated** |
| **M5D** | ✅ Done | Synthetic/local performance baseline (`reports/benchmark-local.md`) |
| **Post-audit fixes** | ✅ Integrated | P1/P2 audit regressions; D-17 export 422 contract; D-19 stable source labels; XLSX worksheet-title hardening |
| **M4B Phase 2** | 🔲 Pending | Needs privacy-cleared, manually annotated real documents |
| **D-16** | ✅ Merged | PR #15 merge commit `231cd9`; short-receipt line-item extraction integrated and tested |
| **D-22** | ✅ Merged | PR #16 merge commit `4d01e78`; structural validation for malformed evaluation payloads integrated and tested |
| **P3 audit batch** | ✅ Merged | PRs #17–#23 merge commits `3f4bab3`…`c1528ab`; D-20, D-23/D-24 and D-28–D-34 integrated (release record above) |
| **M3B** | 🔲 Deferred | Borderless table recognition (model-based) |

---

## 8. Critical Files for a New Maintainer

| File | Why it matters |
|------|----------------|
| `README.md` | User-facing overview, usage, feature status, limitations, roadmap |
| `AGENTS.md` | Project-specific agent instructions (architecture, commands, security, git workflow) |
| `docs/product-expansion-plan.md` | Current milestone status and next-task order |
| `docs/web-api.md` | Endpoint contracts, PDF limits, D-18 exports, batch ZIP, corrections |
| `docs/extraction-spec.md` | Complete M2/M5C rule tables, monetary parsing, validation semantics |
| `docs/evaluation-spec.md` | Metric definitions, null handling, aggregation conventions |
| `docs/table-recognition-spec.md` | M3A geometry pipeline, assignment rules, export formats |
| `docs/dataset-annotation-guide.md` | Real-doc workflow, privacy, templates, labeling |
| `reports/audits/2026-10-26-baseline-audit.md` | Historical audit; open P3 backlog context |
| `src/documind/ocr/engine.py` | Pinned PP-OCRv6 models, MKLDNN disable rationale |
| `src/documind/extraction/extractor.py` | 8-stage pipeline, provenance |
| `src/documind/extraction/lexicon_vi.py` | Vietnamese diacritic-insensitive labels |
| `src/documind/tables/geometry.py` | Deterministic ruled-grid detection |
| `src/documind/evaluation/*.py` | Three task evaluators with strict conventions |
| `src/documind/web/service.py` | Shared engine, inference lock, unified processing |
| `src/documind/web/pdf.py` | PDF rendering limits (pages, pixels, points) |
| `src/documind/web/app.py` | Endpoints, export validation, batch ZIP allocator |
| `src/documind/web/static/app.js` | Frontend: page state, corrections, exports, batch |
| `tests/fixtures/frontend/pdf_page_harness.js` | D-18 behavioral scenarios |
| `pyproject.toml` / `requirements.lock.txt` | Dependencies and entry points; the lock file is a historical environment snapshot |

---

## 9. Verification Commands

```powershell
# Lint + frontend gate + tests (pre-push gate; run from repo root)
cd documind-ai
.\.venv\Scripts\Activate.ps1
python scripts/verify.py      # ruff + frontend-gate + pytest

# Individual
ruff check src tests scripts
python scripts/check_browser_js.py   # Node required
pytest -q                            # current test count; do not hardcode

# Historical real-inference smoke (downloads models; not CI)
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

Documentation changes must still keep `python scripts/verify.py` green.

---

## 10. Known Issues / Gotchas

1. **Verify path sensitivity:** `python scripts/verify.py` must run from the repo root (relative `src`, `tests`, `scripts`).
2. **Windows MKLDNN crash:** do not enable `enable_mkldnn=True` in `PaddleOcrEngine`.
3. **Provenance in manifests:** declare `provenance: "synthetic"` or `"real"`; default `"unknown"` renders "do not treat as real-world accuracy".
4. **Dataset directory git-ignored:** `data/eval/real/` is never committed by default; committing anonymized ground truth is an explicit decision.
5. **No ground truth from predictions:** `documind-dataset` never generates labels from model output.
6. **Line-item matching by index:** evaluation assumes reading order; content-based matching would change denominators (versioned metric change).
7. **PDF per-page extraction:** no cross-page relationship inference; page limits are 10 pages / 30 MP per page / 60 MP cumulative / 15k points per side.
8. **Export limits:** ≤50 tables, ≤500 rows/columns per table, ≤20k cells — 422; batch ZIP ≤10 entries including the failure report.
9. **ZIP identity/naming:** opaque document ids, case-insensitive name allocation, `_2`/`_3` suffixes, extensions preserved; `batch-errors.json` is first when failures exist and colliding success entries are suffixed.
10. **Stale local `main`:** existing developer clones may have an old `7e7621f` local main. Fetch `origin/main` and branch from it; do not reset/overwrite local main as part of normal work.
11. **Long single-export filename:** the 100-character download-header cap can truncate the stem and lose the extension; prefer batch ZIP for long names until fixed.
12. **CSV BOM (D-21):** UTF-8 without BOM; import explicitly in Excel on Windows.
13. **Browser smoke ≠ accuracy:** mocked inference in Chromium proves UI wiring only.
14. **Open defects:** none from the 2026-10-26 audit — D-16 (PR #15), D-22 (PR #16) and the P3 batch (PRs #17–#23) are merged and tested on `main` @ `346d1c5`. D-21 remains a pending product decision and evaluation rows×columns resource budgeting an unresolved backlog. Do not mark anything fixed on `main` without tests and a merge.

---

## 11. Next Engineering Work

The 2026-10-26 audit is fully integrated: D-16 (PR #15), D-22 (PR #16) and the P3 batch (PRs #17–#23 — D-20, D-23/D-24, D-28–D-34; D-27 was already resolved) are merged on `main` @ `346d1c5` with a 715-test baseline. Remaining backlog, in recommended order:

1. ~~Merge review of PRs #17–#23~~ — **done 2026-10-31**: all seven merged with verified per-stage CI; combined baseline **715 tests** on `main`.
2. **M4B Phase 2 — real-document evaluation (current next task, blocked):** collect privacy-cleared, manually annotated documents (10–20 pilot: Vietnamese receipts, invoice-style pages, ruled-table pages), onboard via `documind-dataset`, evaluate with provenance `real`, and publish the first honest accuracy report. Blocked until legitimate, privacy-cleared, manually annotated data exists — data collection/annotation can start any time that data becomes available.
3. **Vietnamese OCR model/language benchmarking:** compare `lang="vi"` vs `lang="en"` on the real set after M4B Phase 2 evidence; record a model-selection decision before tuning.
4. **M3B — borderless tables:** deferred; requires a model-based structure recognizer and should follow real-data evidence.

Do not start a new milestone before its prerequisite data/decision exists. Do not present mock/synthetic results as accuracy.

---

## 12. Git State and Agent Workflow

- **Post-D18 release checkpoint (historical):** `origin/main` @ `130f32207e316330cba15d31c23558c6a2987607` (PR #13 merged on 2026-10-27; merge commit; three D-18 commits reachable).
- **D-16 merge checkpoint:** `origin/main` @ `231cd909924f75b4d46816ca028bbdca5b6107ef` (PR #15 merged on 2026-10-29; 519 tests; CI run [40843248171](https://github.com/pminhquan/documind-ai/actions/runs/40843248171)).
- **PR #15 base (historical):** `31a8f1bde0328402cb976b7e0f257871ebc2848b` (PR #14 merge). That base does **not** contain D-16; D-16 was implemented in PR #15 and is now merged at `231cd9`.
- **PR #13:** merged; the `fix/m5b-pdf-page-level-exports` branch is retained (not deleted).
- **D-22 merge checkpoint:** `origin/main` @ `4d01e78ec95d58f3b7ca2113da08489e8ec1092d` (PR #16 merged; 643 tests at that SHA).
- **2026-10-31 pre-release snapshot (historical):** at that checkpoint there were seven Draft PRs (#17–#23); all were merged the same day after review — merge commits and CI in the release table above. After the release no feature PRs are open. Inspect `gh pr list` / `git log origin/main` before starting: history may have moved since this document was written.
- **Branch naming:** `feat/<milestone>-<slug>` for features, `docs/<slug>` for documentation; create focused commits; never force-push; PRs target `main` and stay Draft/open until the owner authorizes merge.
- **Never** rewrite history, reset a stale local main, or delete someone else's branch.
- **Durable context lives in the repository and GitHub** (README, HANDOFF, docs, issues/PRs, CI). Do not rely on agent-private memory directories; if a harness has extra memory, treat it as non-authoritative.

---

## 13. Quick Mental Model for New Contributors

> **DocuMind = deterministic pipelines on saved artifacts, plus a local UI for human-in-the-loop review.**
>
> - OCR runs once per request → results reused across workflows.
> - Extraction/tables/eval never re-run OCR; they transform saved results.
> - Web app: images or PDFs; PDFs are processed page by page and exported page by page.
> - Corrections are client-side, keyed by opaque document id + page; machine output is immutable.
> - Evaluation compares saved predictions vs ground truth; no inference.
> - All current "accuracy" evidence is synthetic or unvalidated; real-world numbers are pending labeled data.

This architecture keeps everything testable, reproducible, and debuggable. The price is manual pipeline orchestration for CLI workflows, per-page PDF semantics, and no learned end-to-end optimization — intentional for a baseline.

---

*End of handoff. Release checkpoint 2026-10-31: main `c1528ab` — PRs #17–#23 merged with per-stage CI verified and a **715-test** combined baseline; documentation PR #24 (this document) completes the release. Check live `origin/main` before acting. This document is not a substitute for Git.*
