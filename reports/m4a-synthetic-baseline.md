# M4A Synthetic Baseline — Evaluation Framework

**Date:** 2026-10-25 · **Environment:** Windows, Python 3.12.10,
paddleocr 3.7.0 / paddlepaddle 3.3.1 (CPU, PP-OCRv6 medium det+rec).
Evaluations run on **saved prediction files** — no inference during eval.

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

Interpretation: the gap between CER and WER is dominated by **column
alignment whitespace** — the receipt prints wide gaps that OCR merges or
splits differently (each differing space is one character edit but no
word edit after whitespace collapsing). The dominant word-level errors
were 3 substitutions; error examples are listed in
`outputs/eval/ocr/report.md`. This is exactly why the project reports
both metrics.

### Invoice extraction — sample receipt (1 document)

| Metric | Value |
|---|---|
| Micro field accuracy | **1.0** (9/9 applicable scalar fields) |
| Macro field accuracy | **1.0** |
| Item field accuracy | **1.0** (16/16 across 4 line items) |
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
- Money comparison verified scale-insensitive (`13.530` == `13.53`);
  dates canonicalized as ISO.
- Missed-table rule verified: a document whose expected table is not
  predicted cannot score 1.0 (`tests/test_evaluation_tasks.py`).

## Interpretation constraints

- All numbers above are **synthetic, clean, rendered inputs** — they
  demonstrate that the evaluation framework works end-to-end and give a
  regression baseline. They are **not** real-world accuracy.
- Real-document evaluation remains **pending** until a licensed,
  privacy-cleared dataset is annotated (`docs/dataset-annotation-guide.md`).
- Unit test pass rate (166/166 at merge time) is a separate signal from
  evaluation metrics and is reported independently.
