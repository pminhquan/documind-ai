# Web API (M5A; M5B and D-18 included)

Local-first HTTP API served by `documind-web` (FastAPI). Default binding
**127.0.0.1:8000** — the app never deploys publicly and no CORS is
enabled by default.

## Start

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[web]"
documind-web
# open http://127.0.0.1:8000
```

## Security posture

- Uploads are untrusted: extension allowlist (PNG/JPG/BMP/TIFF/WEBP),
  **10 MB** hard limit, Pillow decoded-content check, safe temp storage
  unlinked on every code path (including failures).
- OCR inference is serialized on a single lazy engine (PaddleOCR is not
  thread-safe) — bounded concurrency by design; model load is lazy.
- OCR text never enters logs; errors return stable messages.
- Exports re-apply the CSV formula-injection policy and sanitize
  filenames (`[^A-Za-z0-9._-]` → `_`, length-capped).
- CSV output is **UTF-8 without BOM** everywhere (CLI tables CSV and web
  exports, D-21). Data is intact; Excel-on-Windows renders Vietnamese
  incorrectly unless the file is imported explicitly (Data → From
  Text/UTF-8) or opened in LibreOffice. Switching the default to
  `utf-8-sig` is a recorded owner decision, not a silent change — it
  would alter the byte output of every export and can upset BOM-sensitive
  tooling.

## Endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/health` | — | `{status, engine_loaded, version}` |
| POST | `/api/ocr` | multipart `upload` (image) | `OcrResponse` |
| POST | `/api/invoice` | multipart `upload` | `InvoiceResponse` (runs OCR internally) |
| POST | `/api/table` | multipart `upload` | `TableResponse` (ruled tables only) |
| POST | `/api/process` | multipart `upload` (image **or PDF**) + `workflow` | `UnifiedResponse` (image) or multi-page PDF result |
| POST | `/api/export` | JSON `{kind, data, filename?}` | file download |

`OcrResponse` = `{source, engine, items: [{text, confidence, box}],
full_text}` — one `items` entry per OCR region; `full_text` is one line
per region (line grouping happens inside extraction).

**Source identifiers are stable labels, never filesystem paths**: image
responses carry `"source": "upload"` (tables: `"source_image": "upload"`);
PDF page results carry `"upload#page0"`, `"upload#page1"`, ... — page
identity and ordering stay with `page_index`. Server-local temporary
upload/render paths never appear in any response, including error
messages (client-safe error text keeps the failure reason, not the
location).

`InvoiceResponse` = `{source, invoice, provenance}` — same schema as
`documind-extract` output; `provenance` maps fields to OCR regions
(index + text + box) so the UI can highlight sources.

`TableResponse` = `{source_image, tables, warnings}` — same schema as
`documind-table` output.

Export `kind`: `ocr-json`, `ocr-txt`, `invoice-json`, `invoice-csv`,
`invoice-xlsx`, `table-json`, `table-csv`, `table-xlsx`, `batch-zip`.
Unknown kind → 422; table export with no tables → 422. Malformed table
export payloads (non-object tables/cells, non-integer or boolean
dimensions/coordinates, negative or out-of-bounds coordinates, missing
required cell fields, unknown cell fields, non-list warnings) are
rejected with 422 and stable detail messages — never an uncontrolled
500. Zero dimensions (`rows: 0` / `columns: 0`) stay tolerated for
export compatibility and produce empty artifacts; the recognition
pipeline itself always emits at least 1×1. JSON exports pass through
untouched by design; the materializing paths (CSV/XLSX, invoice and
table corrections) validate before use.
Invoice
CSV/XLSX materialize `user_corrections` (validated client paths) into a
fresh copy; formula-injection policy re-applied.

### PDF input (M5B)

`/api/process` accepts PDFs (detected by `%PDF` magic). Pages render via
pypdfium2 at ~144 DPI with bounds: **10 pages max**, **30 MP per page**,
**60 MP cumulative** across pages, and **15,000 PDF points per side**
(checked before scaling) — violations return 400. Results are page-indexed
(`{kind: "pdf", page_count, pages: [{page_index, ocr, invoice, tables}],
errors}`); a failing page is recorded in `errors` while others still
process (partial success). The single-page extractor does not infer
cross-page relationships — per-page results are intentionally separate.
Page images live in a temp directory removed after processing.

### PDF page-level exports (D-18, client-orchestrated)

For a PDF result the UI exports **the selected page only** — never the
whole-document object read as if it were an image. The active page is
tracked by `page_index` (not array position), and package exports are
named `<stem>-page-<N>-<artifact>.<ext>` (N = `page_index + 1`), e.g.
`document-page-1-invoice.csv`, `document-page-2-tables.xlsx`. If the
selected page has no result for the requested artifact, the UI reports
a clear error instead of generating an empty financial export. A page
with several tables exports `table-csv` as
`<stem>-page-<N>-tables.zip` (the server packages multiple tables as a
ZIP archive). Image results keep the pre-D-18 payload shapes and
filenames (`invoice-result.csv`, `tables.csv`, ...).

Corrections stay isolated per document and page: each selected file
instance gets an opaque run-local document id (filenames are display and
export labels only), and correction keys are `<document-id>#<page_index>`.
Switching pages restores the corrected values and edited markers, and
Reset Invoice / Reset Tables remove only that page's corrections of the
matching family. Machine output is never mutated. Two files with the
same filename therefore keep separate corrections and batch entries.

### Batch processing (M5B, client-orchestrated)

The UI processes up to **10 files per batch run sequentially** (one
document in memory at a time), showing per-file status with error
isolation, partial success, and a Stop button. A new run replaces the
previous run's results **and** its corrections: edits belong to one
machine-output generation and are never silently re-applied to fresh
output. A cancelled run exports only the documents it actually
completed. Batch results export via `batch-zip` (≤ 10 entries including
the failure report, sanitized deterministically deduplicated names,
per-entry kind validation) through the "Export batch ZIP" control,
shown once a multi-file run has produced results. Name uniqueness is
case-insensitive (sanitized names are ASCII): the first entry keeps its
original case, later colliding names get `_2`, `_3`, ... suffixes, since
case-distinct ZIP entries merge when extracted on Windows/macOS. No job
queues or databases.

Each successfully processed PDF contributes **one** JSON entry (`kind:
"ocr-json"`) carrying the complete page-level result rather than an
uncontrolled number of CSV/XLSX files:

```json
{
  "kind": "pdf",
  "page_count": 2,
  "workflows": ["ocr", "invoice", "table"],
  "errors": ["page 0: <message>"],
  "pages": [
    {"page_index": 0, "error": "<message>"},
    {
      "page_index": 1,
      "source": "upload#page1",
      "ocr": {...},
      "invoice": {...},
      "tables": {...},
      "user_corrections": {"invoice.total": "20.00"}
    }
  ]
}
```

Failed pages carry only `page_index` and `error` — no fabricated OCR,
invoice, or table records. `user_corrections` is kept separate from the
machine result and is page-local; data from different documents never
mixes. Each PDF is one entry even when files share a name: ZIP entry
names are sanitized, capped, and deterministically suffixed (`_2`,
`_3`, ...) with the extension preserved, so no entry is overwritten
and every extracted file keeps a usable name.

Image batch entries:

- OCR workflow: the raw `OcrResponse`.
- Invoice workflow: `{machine_output: InvoiceResponse,
  user_corrections}` (corrections keep their verbatim paths such as
  `invoice.total`).
- Table workflow: `{machine_output: TableResponse, user_corrections}`
  (paths such as `tables[0].cells[0][0]`).
- Auto workflow: one full JSON snapshot — `kind: "ocr-json"` with
  `{workflow: "auto", ocr, invoice, tables, user_corrections}` — so no
  generated artifact is dropped.

Processing failures remain explicit in `batch-errors.json`, which is
written as the first entry whenever failures exist; if a successful
document's derived name collides with it, that document's entry is
deterministically suffixed (`batch-errors_2.json`) and both artifacts
are kept. Failed documents never become fake OCR/invoice/table results.

### Corrections materialization (CSV/XLSX)

`table-csv` / `table-xlsx` **materialize** `user_corrections` into a
fresh copy of the machine result: keys must be exactly
`tables[T].cells[R][C]` with indices inside the machine output's bounds —
invalid paths, wrong shapes, or out-of-bounds coordinates are rejected
with 422 (no silent ignoring, no arbitrary object paths). The original
`machine_output` is never mutated; JSON exports keep both parts separate.

### Multi-table CSV

`table-csv` with **one** table returns a single CSV file; with **two or
more** tables it returns a ZIP archive (`tables.zip`) containing
`tables_t0.csv`, `tables_t1.csv`, ... (sanitized entry names). Zero
tables → 422.

### XLSX worksheet naming

Sheet names are generated from `table_id` at export time and never
mutate the JSON result: Excel-illegal characters (`\ / * ? : [ ]`)
become `_`, titles are capped at Excel's 31-character limit, empty
titles fall back to `"Table"`, and case-insensitive collisions get
deterministic `_2`, `_3`… suffixes. Every table keeps a distinct sheet
(no table is dropped).

### Resource limits

- Uploads: 10 MB bytes, extension allowlist, decoded-image limits
  (10,000 px per side / 30 MP) — 413/415/400.
- Exports: ≤ 50 tables, ≤ 500 rows/columns per table, ≤ 20,000 cells — 422.
- Inference is serialized on one shared engine (PaddleOCR is not
  thread-safe); the table pipeline reuses the shared engine runner
  instead of constructing its own, and unified processing reuses OCR
  items so OCR runs at most once per request.

Error codes: `413` file too large (10 MB), `415` unsupported extension,
`400` not a decodable image / empty upload, `422` unknown workflow or
export kind, `500` inference failure (message without OCR content).

## Human-in-the-loop corrections

The UI never overwrites machine output. Corrections are collected
client-side keyed by an opaque run-local document id plus `page_index`
and field path (`invoice.total`, `tables[0].cells[2][1]`, ...), then
exported **alongside** the original machine output in JSON exports.
Selecting new documents or starting a new processing run clears the
previous correction state; page switches and repeated exports within a
completed run preserve it. CSV/XLSX export materializes only the
selected page's corrections into a fresh copy. Revisiting a page
re-applies its stored corrections and edited markers; Reset removes one
correction family for the active page only. Ground truth in `data/eval/`
is never touched by the web app.
