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
  "documents": [
    {"id": "unique-id",           // non-empty, unique
     "prediction": "path.json",   // saved documind prediction
     "ground_truth": "path.json"} // labeled annotation
  ]
}
```

Paths resolve **relative to the manifest file's directory**. Validation
is strict: unknown task, empty `documents`, missing fields, duplicate
ids, or malformed JSON all fail loudly (`ManifestError`).

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
- **Error examples**: character-level backtrace operations
  (substitute/insert/delete with reference position), first 5 per
  document.

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
  Item fields use the same rules; missing/extra items counted.

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
  truth is empty), incorrect cells (both non-empty, different).
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
