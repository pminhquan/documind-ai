# AGENTS.md — DocuMind AI

Instructions for AI coding agents working in this repository.

## What this project is

DocuMind AI is a local-first Document Intelligence platform: OCR
(PaddleOCR 3.x, PP-OCRv6 CPU), deterministic invoice extraction,
ruled-table recognition, an evaluation framework, and dataset
onboarding tooling. Python **3.12 only** (`requires-python = ">=3.12,<3.13"`).

## Architecture and module boundaries

```
src/documind/
├── ocr/            image validation, preprocessing, PaddleOCR engine, result model
├── extraction/     OCR JSON -> invoice (deterministic rules; Decimal money)
├── tables/         OpenCV ruled-grid detection, cell assignment, exports
├── evaluation/     CER/WER + invoice/table metrics, manifests, reports
├── dataset.py      real-document onboarding/validation (CLI: dataset_cli)
├── cli.py          documind-ocr          ├── extract_cli.py  documind-extract
├── table_cli.py    documind-table        └── evaluation/cli.py  documind-eval
```

Boundaries that must not blur:
- OCR inference lives only in `ocr/engine.py` (lazy PaddleOCR import).
- Extraction/tables/evaluation never run inference; they transform saved
  results. Web/service layers must call service functions, never CLI
  subprocesses.
- Geometry (`tables/geometry.py`) is independent of OCR so it can be
  tested without models.

## Commands

```powershell
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python scripts/verify.py      # ruff check + pytest -q (pre-push gate)
pytest                        # tests only
ruff check src tests scripts  # lint only
```

CI (GitHub Actions) runs ruff + pytest on Python 3.12 with **mocked and
geometry-only tests** — it never downloads PaddlePaddle or OCR model
weights. Anything needing real inference runs locally only.

## Security and privacy constraints

- Never commit anything under `data/eval/real/`, `data/raw/`, model
  weights, or `.venv/`. Real documents stay local.
- Dataset onboarding requires explicit anonymization confirmation; never
  generate ground truth from model predictions.
- Uploaded/user-provided files are untrusted input: validate size,
  extension, and decodability; never execute content; keep OCR text out
  of routine logs.
- Local-only binding for any server component; no deployment without
  explicit authorization.

## Evaluation metric rules

- Metric definitions (denominators, null semantics, strict matching)
  are documented in `docs/evaluation-spec.md` and versioned by review.
  Changing a denominator or matching rule requires updating that spec
  and the regression tests in the same change.
- Never change metrics to make results look better; never present
  synthetic numbers as real-world accuracy; real-data evaluation is
  pending and must stay marked pending until labeled data exists.

## Git workflow and definition of done

- Feature branches named `feat/<milestone>-<slug>`; small focused
  commits; never force-push; PRs target `main` and stay open for review
  unless explicit permission says otherwise.
- A change is done when: code exists, the main workflow is executable,
  tests cover it (including error paths), CI is green on the final
  commit, and documentation matches reality.
- Documentation must never drift: update README/docs in the same change
  that changes behavior. Avoid hardcoded test-count claims in prose —
  write "run pytest" instead.

## Known limitations (do not claim otherwise)

- CPU-only; first OCR run downloads PP-OCRv6 weights to `~/.paddlex`.
- oneDNN/MKLDNN disabled on Windows (upstream crash).
- Ruled tables only (M3A); borderless tables not supported.
- All current evaluation numbers are synthetic; real-document
  evaluation is pending.

## Agent skills

`.agents/skills/` contains focused instruction files
(`document-pipeline`, `evaluation-integrity`, `privacy-and-upload-safety`,
`performance-benchmark`). They are plain Markdown read on demand — an
agent that has them registered may invoke them as skills; otherwise read
the relevant `SKILL.md` directly before working in that area. Do not
claim they are "active" if your harness has not discovered them.
