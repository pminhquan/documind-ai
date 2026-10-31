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
(`ManifestError`). Relative paths are not jailed to the manifest's
directory (D-25, by design): a manifest is a locally authored trust
boundary and its paths may point anywhere the user can read — never
treat a manifest from an untrusted source as safe.

**Dataset provenance** is explicit metadata that travels into every
summary (`dataset.provenance`) and generated report. It defaults to
`unknown` when unspecified and is **never classified automatically**:
only the manifest author declares `synthetic` or `real`. Reports render
a provenance-specific caveat line (unknown → "do not treat these
numbers as real-world accuracy").

## Structural validation (D-22)

Nested payload shapes are validated before scoring, for both predictions
and ground truth. Errors identify the role (`prediction` / `ground
truth`), the field path and the source file; they never echo document
contents or cell text.

- Top-level files must be JSON objects with the task key. Invoice and
  table containers follow the rules below; OCR text values are
  stringified as before.
- **Invoice:** `invoice` must be an object or `null`; `line_items` must
  be a list or `null`/omitted, and every entry must be an object. A
  `null` container keeps its legacy meaning "empty"; a present non-null
  container of another type is a structural error.
- **Table:** `tables` must be a list or `null`/omitted, and every entry
  must be an object. `rows` and `columns` must be genuine non-negative
  integers on both sides — booleans, strings, floats, `null`, negative
  values and missing keys are rejected. Ground-truth `cells` must be a
  list of row lists (or `null`/omitted); predicted `cells` must be a
  list of cell objects (or `null`/omitted).
- Predicted cell objects are validated as objects, but their
  **coordinates are not structurally validated**. Non-integer, boolean,
  out-of-shape and duplicate coordinates keep the documented scoring
  rule and count as unexpected predicted cells (Task 3).
- Invoice scalar values may be `null`. Unparseable or non-finite money
  values remain "incorrect" scores, not structural errors.
- Validation happens before scoring. The first malformed document aborts
  the whole run: `documind-eval` prints
  `Evaluation error: <message>` to stderr, exits with code `2`, writes
  no `summary.json`/`report.md`, and leaves files from earlier runs
  untouched. A partially evaluated aggregate is never published.
- Metric definitions, denominators, null semantics and strict matching
  are unchanged by validation.

**Resource allocation (D-22 follow-up, recorded decision).** Structural
validation deliberately sets **no upper cap on `rows × columns`**. A
declared shape cannot inflate memory by itself: ground-truth `cells`
must be a physical `rows × columns` matrix and predicted cells arrive as
an explicit list, so the memory an evaluation pass uses is bounded by
the input file sizes the owner chose to place on disk. `documind-eval`
is a local, single-user tool whose manifests are authored by the same
person who runs it — the trust boundary is the filesystem, not a network
peer. If evaluation ever runs on untrusted uploads, add an explicit
cell-count budget at that new boundary (with tests), not a silent cap
here.

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
- Item-level metrics use **strict item matching**: an exactly correct
  matched item is one true positive; an incorrectly predicted matched
  item is **one false positive and one false negative**; missing items
  are false negatives; extra items are false positives.
  `item_precision` / `item_recall` / `item_f1` (per document and
  micro-aggregated) therefore penalize wrong, missing, and extra items
  alike — a prediction that drops or mangles items can never report a
  perfect item score.
- `item_field_accuracy` separately measures field correctness **among
  matched item pairs only** (documented scope).
- Zero-denominator conventions: precision is `None` when the prediction
  contains no items; recall is `None` when the ground truth contains no
  items; F1 is `None` when either is `None`, and `0.0` when both are
  defined and sum to zero.
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
- **Strict companion metrics** (per comparison, per document, and
  aggregated):
  - `prediction_precision` = matched ÷ (matched + incorrect + extra) —
    everything the predictor emitted but should not have (content on
    empty expected cells, out-of-shape, duplicate, invalid) lowers it.
  - `strict_cell_agreement` = matched ÷ (expected cells + extra) —
    expected cells include completely missed tables, and extra includes
    completely extra tables, so both failure directions lower it.
- **`cell_exact_agreement` (legacy, unchanged)** = matched ÷ expected
  reference cells only. Extra predictions and extra tables do **not**
  enter this denominator by design; consumers who need extra
  predictions penalized must read the strict metrics instead.

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
- Structural validation covers invoice/table containers only; scalar
  invoice values are compared as before, and predicted-cell coordinates
  remain scored rather than rejected.
- All current labeled data is synthetic; **no real-world accuracy is
  claimed anywhere in this repository** (real-data evaluation pending
  licensed data).
