# Dataset Annotation Guide (M4A/M4B)

How to create labeled ground truth for the three DocuMind evaluation
tasks, and the rules that keep datasets legal, private, and reusable.

## Real-document onboarding workflow (M4B)

The `documind-dataset` CLI automates the local dataset lifecycle. The
default root is `data/eval/real/` and **the whole directory is
git-ignored** — nothing from a real dataset is committed by default.

```powershell
# 1. One-time layout (raw/, anonymized/, ground_truth/, predictions/, reports/)
documind-dataset init

# 2. Copy your anonymized image into the dataset (explicit confirmation
#    required — you assert personal data was removed):
documind-dataset add path\to\anonymized-receipt.jpg --id receipt-001 --confirm-anonymized

# 3. Annotate by hand (templates in data/annotation/templates/):
#    data/eval/real/ground_truth/receipt-001.ocr.json
#    data/eval/real/ground_truth/receipt-001.invoice.json
#    data/eval/real/ground_truth/receipt-001.table.json

# 4. Check structure + annotation completeness (placeholders, required
#    keys, table matrix shapes, manifest validity):
documind-dataset validate

# 5. Run the existing pipelines on annotated documents (local venv;
#    runs PaddleOCR — never in CI):
documind-dataset predict --task ocr
documind-dataset predict --task invoice   # reuses saved OCR predictions
documind-dataset predict --task table
# each step writes manifest-<task>.json (provenance: real)

# 6. Evaluate with the existing framework:
documind-eval --task ocr --manifest data/eval/real/manifest-ocr.json --output outputs/eval/real-ocr
```

`add` refuses to register a document without `--confirm-anonymized`,
and `predict` generates predictions only for documents that already
have ground truth — predictions are never used to create labels.

## Directory convention

```
data/
├── annotation/templates/       # committed JSON templates (one per task)
├── eval/<dataset-name>/        # one directory per labeled dataset
│   ├── ocr/
│   │   ├── manifest.json       # pairs predictions with ground truth
│   │   └── ground_truth/       # committed annotations
│   ├── invoice/…
│   └── table/…
├── raw/                        # private source images (NEVER committed)
└── processed/                  # derived artifacts (NEVER committed)
```

- `data/eval/**/manifest.json` and `ground_truth/` **are** committed
  (they contain no personal data once anonymized).
- `data/raw/` and `data/processed/` are git-ignored: source documents
  stay local.
- Predictions referenced by a manifest are generated locally
  (`outputs/…`) and not committed.

## Templates

Start from `data/annotation/templates/`:

| File | Task | Notes |
|---|---|---|
| `ocr-ground-truth.json` | OCR | `reference_text` = exact content transcription in reading order. |
| `invoice-ground-truth.json` | Invoice | Field names mirror `docs/extraction-spec.md`; ISO dates; decimal strings; `null` = absent; `[]` = no line items. |
| `table-ground-truth.json` | Table | `rows`/`columns` describe the full grid; every cell present, `""` for empty. |
| `manifest.json` | all | Paths resolve relative to the manifest file. |

## Labeling guidelines

1. **Transcribe what is printed, not what it means.** Fix obvious OCR
   noise only in the sense of reading the image carefully; never invent
   values that are unreadable — leave the field `null`/`""`.
2. **Normalize as specified**: ISO dates (`2026-10-25`), decimal money
   strings with the printed scale preserved, uppercase ISO currency
   codes.
3. **Empty vs missing**: a cell/field that is printed but unreadable is
   still annotated as best read; a field the document does not contain
   is `null`. Do not use `""` and `null` interchangeably — the
   evaluation treats them differently (empty vs missing).
4. **One annotation pass per document**, then a second independent
   review pass; record the annotator and date in the dataset README.
5. Keep each document's `id` stable across tasks and reruns.

## Privacy, consent, licensing

- **Never commit real personal or financial documents** (receipts,
  invoices with names, card numbers, addresses). Anonymize before use:
  physically redact or replace personal data **in the image itself**
  (blur/paint over) — cropping filenames is not enough. The `add`
  command requires `--confirm-anonymized` precisely because the tool
  cannot verify this for you.
- Anonymization checklist before `add --confirm-anonymized`:
  personal names, phone numbers, full addresses, card/account numbers,
  loyalty IDs, handwritten signatures, and any unique long identifiers.
  Replacing printed values with fictional ones in the annotation only
  is **not** sufficient — the image must be redacted too.
- Only annotate documents you have **permission to use** (your own
  test documents, or openly licensed ones with compatible terms).
- Record provenance for every real document: source, date obtained,
  license/consent note. No provenance → do not include. Keep these
  notes in the dataset `README.md` (local, not committed).
- Do not upload private documents to third-party labeling services or
  cloud OCR consoles; the project's pipeline runs locally on CPU.

## Train / dev / test split policy

- **Split by document** (never by page/cell) to avoid leakage: all
  rows of one document stay in one split.
- Suggested default for future experiments: **70% train / 15% dev /
  15% test**, stratified by document type (receipt, invoice, table)
  and by source/layout template.
- Splits are frozen in a committed `split.json` (document id lists)
  before any tuning; dev may guide iteration, test is touched once per
  milestone.
- Synthetic documents (generated by `scripts/`) never mix into a
  real-data split; they form their own dataset with their own
  manifests.

## Status

Real labeled data: **pending** — no licensed real-document dataset is
available in this repository yet. All current evaluation numbers are
synthetic (`reports/m4a-synthetic-baseline.md`).
