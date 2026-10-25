# M4A Synthetic Baseline — Evaluation Framework

**Date:** 2026-10-25 · **Environment:** Windows, Python 3.12.10,
paddleocr 3.7.0 / paddlepaddle 3.3.1 (CPU, PP-OCRv6 medium det+rec).
Evaluations run on **saved prediction files** — no inference during eval.
**Dataset provenance: synthetic** (declared in every committed manifest).

## Method

1. Predictions generated once with the current pipelines
   (`documind-ocr` → `documind-extract` → `documind-table`) on the
   committed synthetic samples.
2. Ground truth authored from the generators' known values
   (`data/eval/synthetic/<task>/ground_truth/`, manifests committed).
3. `documind-eval` runs per task and writes `summary.json` + `report.md`.

Reproduce:

```powershell
# regenerate predictions locally, then:
documind-eval --task ocr     --manifest data/eval/synthetic/ocr/manifest.json
documind-eval --task invoice --manifest data/eval/synthetic/invoice/manifest.json
documind-eval --task table   --manifest data/eval/synthetic/table/manifest.json
```

## Results (actual run, 2026-10-25)

### OCR — sample receipt (1 document)

| Metric | Value | Detail |
|---|---|---|
| CER (micro) | **0.2421** | 99 char edits / 409 reference chars |
| WER (micro) | **0.0462** | 3 word edits / 65 reference words |
| Edit mix | 0 substitutions, 0 insertions, **99 deletions** | see below |

**Verified error analysis (reproducible via the report's operation
counts and `edit_operations`):** all 99 character edits are **deletions,
and all of them are the dashed separator lines**. The ground truth
contains four `--------------------------------` rules (33 dashes each);
PaddleOCR's detector recognizes one of them but skips the other three,
contributing 33 × 3 = 99 deleted characters and the 3 deleted "words"
(the dash runs) that make up the entire WER. After whitespace
normalization there are **zero substitutions and zero insertions** —
every readable text token (items, quantities, totals, dates) matches the
reference exactly. An earlier draft of this report attributed the CER to
column-alignment whitespace, which was unsupported: the default
normalization collapses whitespace, and the recorded edit mix proves the
separators are the sole cause.

### Invoice extraction — sample receipt (1 document)

| Metric | Value |
|---|---|
| Micro field accuracy | **1.0** (9/9 applicable scalar fields) |
| Macro field accuracy | **1.0** |
| Item field accuracy | **1.0** (16/16 across 4 matched line items) |
| Item precision / recall / F1 | **1.0 / 1.0 / 1.0** (4 expected, 4 predicted, index-matched) |
| Missing / extra line items | 0 / 0 |

`discount` is `null` on both sides → counted as a true negative and
excluded from the denominator, per the documented null semantics.

### Table recognition — 3 synthetic tables

| Metric | Value |
|---|---|
| Tables detected | **3/3** (0 missed, 0 extra) |
| Cell exact agreement | **1.0** (62/62 cells) |
| Non-empty agreement | **1.0** (59/59) |
| Empty-cell preservation | **1.0** (3/3) |
| Structure-OK documents | 3/3 |

## Metric correctness checks

- CER/WER verified against hand-computed cases in the test suite
  (`kitten → sitting`: 3 edits / 6 chars = 0.5; `the cat sat → the bat
  sat`: 1/3 WER; empty-reference conventions).
- Money comparison verified scale-insensitive (`13.530` == `13.53`),
  including for line-item amounts; non-finite values (NaN/Infinity)
  never match.
- Item-level precision/recall/F1 verified to penalize missing items
  (a perfect single item among two expected scores P 1.0 / R 0.5 /
  F1 0.667 even when matched-pair field accuracy is 1.0).
- Missed-table rule verified: a document whose expected table is not
  predicted cannot score 1.0 (`tests/test_evaluation_tasks.py`).
- Unexpected predicted table cells (outside shape, duplicate or invalid
  coordinates) are counted as extra cells, never silently overwritten
  or ignored (`tests/test_evaluation_tasks.py`).

## Interpretation constraints

- The dataset provenance is explicitly declared (`synthetic`) in the
  manifests and echoed in every generated report; provenance defaults
  to `unknown` when unspecified and is never auto-classified as real.
- These are **clean, rendered, axis-aligned inputs** — they demonstrate
  that the evaluation framework works end-to-end and give a regression
  baseline. They are **not** real-world accuracy.
- The 0.2421 CER is dominated by decorative separator rules the OCR
  detector skips; on documents without such rules the same pipeline
  scores materially better. Metric consumers should read the edit mix
  before drawing conclusions.
- Real-document evaluation remains **pending** until a licensed,
  privacy-cleared dataset is annotated (`docs/dataset-annotation-guide.md`).
- Unit test pass rate (166/166 at merge time) is a separate signal from
  evaluation metrics and is reported independently.
