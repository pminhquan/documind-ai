---
name: document-pipeline
description: Work on DocuMind OCR, invoice extraction, or table recognition pipelines (src/documind/ocr, extraction, tables) — use when changing pipeline code, adding pipeline features, or debugging pipeline output.
---

# Document pipeline work

## Purpose

Guide changes to the three processing pipelines (OCR, invoice extraction,
table recognition) without breaking their contracts or test strategy.

## When to use

- Modifying anything under `src/documind/ocr/`, `src/documind/extraction/`,
  `src/documind/tables/`, or their CLIs.
- Debugging wrong OCR JSON, invoice fields, or table cells.

## Relevant modules

- `src/documind/ocr/{engine,validation,preprocessing,results}.py`
- `src/documind/extraction/{parsing,layout,extractor,validator}.py`
- `src/documind/tables/{geometry,assign,exporters,pipeline}.py`
- Specs: `docs/extraction-spec.md`, `docs/table-recognition-spec.md`
- Fixtures: `tests/fixtures/` (synthetic OCR JSONs, table truth)

## Workflow

1. Reproduce with an existing fixture or add a minimal fixture first.
2. Write the failing regression test (tests are mocked — no model runs).
3. Apply the minimal fix; keep CLI and service layers thin.
4. If a rule table changed, update the matching spec doc in the same commit.

## Verification

```
python scripts/verify.py
pytest tests/test_extraction.py tests/test_tables_geometry.py -q   # focused
```

End-to-end confidence (local, optional): run `documind-ocr` /
`documind-extract` / `documind-table` on `assets/samples/` inputs and
compare against the documented sample outputs.

## Failure and rollback criteria

- If mocked tests pass but a synthetic sample regresses (e.g. cell counts
  change), stop and re-examine — do not update expected outputs to make
  tests pass without understanding why.
- Revert the commit if the pipeline loses provenance, starts fabricating
  values, or changes an output schema without a versioned spec update.
