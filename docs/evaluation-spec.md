# Evaluation Specification (M4A)

Reproducible evaluation for the three existing pipelines, driven by
manifests pairing **saved prediction files** with **ground-truth
annotations**. Evaluation never runs OCR inference and never uses model
confidence as an accuracy metric.

Command:

```
documind-eval --task ocr|invoice|table --manifest <path> [--output <dir>]
              [--case-sensitive] [--preserve-whitespace]
```

Outputs: `<output>/summary.json` (machine-readable) and
`<output>/report.md` (readable). Default output: `outputs/eval/<task>`.
Exit codes: `0` success, `2` invalid manifest/files.

## Manifest schema

```jsonc
{
  "task": "ocr" | "invoice" | "table",
  "provenance": "synthetic" | "real" | "unknown",   // optional, default "unknown"
  "documents": [
    {"id": "unique-id",           // non-empty, unique
     "prediction": "path.json",   // saved documind prediction
     "ground_truth": "path.json"} // labeled annotation
  ]
}
```

Paths resolve **relative to the manifest file's directory**. Validation
is strict: unknown task, unknown provenance, empty `documents`, missing
fields, duplicate ids, or malformed JSON all fail loudly
(`ManifestError`).

**Dataset provenance** is explicit metadata that travels into every
summary (`dataset.provenance`) and generated report. It defaults to
`unknown` when unspecified and is **never classified automatically**:
only the manifest author declares `synthetic` or `real`. Reports render
a provenance-specific caveat line (unknown → "do not treat these
numbers as real-world accuracy").

## Task 1 — OCR (CER / WER)

- Prediction: `documind-ocr` JSON (`full_text`).
- Ground truth: `{"id", "reference_text"}`.
- **Normalization**: Unicode NFKC; casefold and whitespace collapsing
  are on by default (`--case-sensitive` / `--preserve-whitespace`
  disable them for the OCR task).
- **CER** = Levenshtein edit distance over characters ÷ reference
  character count. **WER** = distance over whitespace-delimited words ÷
  reference word count (same normalization).
- **Empty reference convention** (explicit): both empty → `0.0`; empty
  reference with non-empty hypothesis → `1.0`.
- **Aggregation**: micro — total edits ÷ total reference units across
  documents; per-document rates reported alongside.
- **Error analysis**: every summary carries per-document and aggregate
  **operation counts** (substitutions / insertions / deletions) from a
  Levenshtein backtrace, plus the first 5 character-level operations as
  examples — so the dominant error source is always reproducible
  evidence, not narrative.

## Task 2 — Invoice extraction

- Prediction: `documind-extract` JSON (`invoice` object).
- Ground truth: `{"id", "invoice": {...}}` using the same field names.
- Scalar fields evaluated: `supplier`, `invoice_number`, `invoice_date`,
  `currency`, `subtotal`, `tax`, `discount`, `total`, `payment_amount`,
  `change_amount`.
- **Canonical comparison**: dates as ISO dates; money as `Decimal`
  numeric equality (scale-insensitive: `13.530 == 13.53`); text
  whitespace-collapsed and casefolded (currency uppercased).
- **Null semantics**: both null → `true_negative` (excluded from the
  accuracy denominator); ground-truth value with null prediction →
  `missing` (**never counted as correct**); null ground truth with
  predicted value → `extra`; both non-null and different → `incorrect`.
- **Field accuracy** (per document) = matched ÷ applicable; `None` when
  every field is null on both sides. **Micro** = matched ÷ applicable
  summed over documents; **macro** = mean of per-document accuracies.
- **Line items** are matched **by index** — an explicit assumption that
  reading order is preserved (content-based matching is future work).
- Item-level metrics: `item_field_accuracy` measures field correctness
  **among matched item pairs only**; `item_precision` / `item_recall` /
  `item_f1` (per document and micro-aggregated) reflect missing items
  (false negatives) and extra items (false positives), so a prediction
  that drops items can never report a perfect item-extraction score.
- Item amount fields (`quantity`, `unit_price`, `line_total`) compare
  as **Decimals** (scale-insensitive: `2.50 == 2.5`, `2 == 2.0`);
  unparseable or non-finite values (NaN, Infinity) are invalid and
  never equal anything.

## Task 3 — Table recognition

- Prediction: `documind-table` JSON (`tables` array).
- Ground truth: `{"id", "tables": [{"rows", "columns", "cells"}]}` —
  the committed M3A truth format.
- Tables matched **by index** in reading order. A **completely missed
  table contributes all its expected cells as unmatched**, so it can
  never score as a perfect document; unpredicted extra tables count as
  `tables_extra` (their cells count as extra cells).
- Per matched table: `structure_ok` (rows/columns equal), exact
  cell-text agreement (whitespace-collapsed, casefolded), non-empty
  cell agreement, empty-cell preservation, missing cells (expected
  content absent in prediction), extra cells (content where the ground
  truth is empty, **plus** unexpected predicted cells), incorrect cells
  (both non-empty, different).
- **Unexpected predicted cells** — coordinates outside the expected
  shape, duplicate coordinates (first write wins), or non-integer
  coordinates — are counted in `extra_cells` with a detailed issue
  entry each; they are never silently overwritten or ignored.
- Aggregate: sums across documents plus `structure_ok_documents` (a
  document with shape mismatch, missed, or extra tables is not
  structure-ok).

## Dataset conventions

See `docs/dataset-annotation-guide.md` and the committed templates in
`data/annotation/templates/`. Synthetic example manifests + ground
truth live in `data/eval/synthetic/` and reproduce
`reports/m4a-synthetic-baseline.md` given locally generated predictions.

## Limitations

- Only the pipelines above are evaluated; no end-to-end (image →
  invoice) metric yet.
- Table and line-item matching are index-based; content-based matching
  may be added later (it changes denominators, so it is a versioned
  metric change).
- WER tokenization is plain whitespace splitting (no punctuation
  normalization beyond NFKC/casefold).
- All current labeled data is synthetic; **no real-world accuracy is
  claimed anywhere in this repository** (real-data evaluation pending
  licensed data).
