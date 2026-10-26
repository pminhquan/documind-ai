# Web API (M5A)

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
pypdfium2 at ~144 DPI with bounds: **10 pages max**, 30 MP per page —
violations return 400. Results are page-indexed
(`{kind: "pdf", page_count, pages: [{page_index, ocr, invoice, tables}],
errors}`); a failing page is recorded in `errors` while others still
process (partial success). The single-page extractor does not infer
cross-page relationships — per-page results are intentionally separate.
Page images live in a temp directory removed after processing.

### Batch processing (M5B, client-orchestrated)

The UI processes up to **10 files per batch run sequentially** (one
document in memory at a time), showing per-file status with error
isolation, partial success, and a Stop button. Batch results export via
`batch-zip` (≤ 10 entries, sanitized deduplicated names, per-entry kind
validation). No job queues or databases.

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
client-side keyed by field path (`invoice.total`,
`tables[0].cells[2][1]`, ...) and exported **alongside** the original
machine output in JSON exports. Ground truth in `data/eval/` is never
touched by the web app.
