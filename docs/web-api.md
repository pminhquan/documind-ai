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
| POST | `/api/process` | multipart `upload` + `workflow` = `auto\|ocr\|invoice\|table` | `UnifiedResponse` |
| POST | `/api/export` | JSON `{kind, data, filename?}` | file download |

`OcrResponse` = `{source, engine, items: [{text, confidence, box}],
full_text}` — one `items` entry per OCR region; `full_text` is one line
per region (line grouping happens inside extraction).

`InvoiceResponse` = `{source, invoice, provenance}` — same schema as
`documind-extract` output; `provenance` maps fields to OCR regions
(index + text + box) so the UI can highlight sources.

`TableResponse` = `{source_image, tables, warnings}` — same schema as
`documind-table` output.

Export `kind`: `ocr-json`, `invoice-json`, `table-json` (JSON pass-through
— human-in-the-loop payloads keep `machine_output` and `user_corrections`
separate), `table-csv`, `table-xlsx` (formula-injection safe). Unknown
kind → 422; table export with no tables → 422.

Error codes: `413` file too large (10 MB), `415` unsupported extension,
`400` not a decodable image / empty upload, `422` unknown workflow or
export kind, `500` inference failure (message without OCR content).

## Human-in-the-loop corrections

The UI never overwrites machine output. Corrections are collected
client-side keyed by field path (`invoice.total`,
`tables[0].cells[2][1]`, ...) and exported **alongside** the original
machine output in JSON exports. Ground truth in `data/eval/` is never
touched by the web app.
