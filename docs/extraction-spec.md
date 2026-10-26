# Extraction Specification (M2)

Deterministic, layout-aware transformation of a saved `documind-ocr`
JSON document into structured invoice data. **No model, no LLM, no
training**: only regex rules, text patterns, and bounding-box geometry.
Command: `documind-extract <ocr-json-path> -o <invoice-json-path>`.

## Output schema

```jsonc
{
  "source": "<path to the OCR JSON>",
  "invoice": {
    "supplier": "string | null",
    "invoice_number": "string | null",
    "invoice_date": "ISO date | null",
    "currency": "ISO 4217 code | null",
    "line_items": [{
      "description": "string",
      "quantity":    "decimal-string | null",
      "unit_price":  "decimal-string | null",
      "line_total":  "decimal-string | null"
    }],
    "subtotal": "decimal-string | null",
    "tax": "decimal-string | null",
    "discount": "decimal-string | null",
    "total": "decimal-string | null",
    "payment_amount": "decimal-string | null",
    "change_amount": "decimal-string | null",
    "validation_status": "ok | review_required | invalid",
    "validation_errors": ["string", ...]
  },
  "provenance": {
    "<field-path>": {
      "ocr_index": "<index into OCR items[]>",
      "text": "<source OCR text>",
      "box": "[[x, y], ...] or []"
    }
  }
}
```

- Financial values are parsed into `decimal.Decimal` internally and
  serialized as strings preserving the printed scale (`"9.57"`), never
  floats.
- Absent or ambiguous values are `null` — the extractor never fabricates.
- Provenance keys: `supplier`, `invoice_number`, `invoice_date`,
  `currency`, `subtotal`, `tax`, `discount`, `total`,
  `payment_amount`, `change_amount`, `line_items[i].description`,
  `line_items[i].quantity`, `line_items[i].unit_price`,
  `line_items[i].line_total`. Every entry points at the OCR region the
  value was actually parsed from (for multi-line descriptions: the
  first description-continuation region).

## Pipeline stages

| # | Stage | Module | Rule summary |
|---|-------|--------|--------------|
| 1 | Text normalization | `parsing.normalize_text` | Unicode NFKC (fullwidth digits, NBSP), whitespace collapse. |
| 2 | Line grouping | `layout.group_lines` | Tokens whose vertical ranges overlap ≥ 50 % of the smaller height share a visual row; inside a row, order by `x0`; row order follows OCR reading order. Tokens without a box become single-token lines. |
| 3 | Supplier | `extract_supplier` | First of the top 3 lines that is not label-prefixed (`receipt/invoice/date/currency/tel/...`), contains no date and no amount. |
| 4 | Invoice number | `extract_invoice_number` | First match of `(?i)\b(receipt|invoice) [#+no]?\s*[:#]?\s*([A-Za-z0-9/-]{3,})`. |
| 5 | Date | `extract_date` | Parse the first date token on a line containing "date"; otherwise the first parseable date token in the document. Formats tried in order: `%Y-%m-%d, %Y/%m/%d, %d/%m/%Y, %d-%m-%Y, %d.%m.%Y, %m/%d/%Y, %m-%d-%Y, %d %b %Y, %d %B %Y, %d/%m/%y` — day-first before month-first, so `05/04/2026` → 5 April. |
| 6 | Currency | `extract_currency` | `currency: XXX` label first; else symbol map `$→USD, €→EUR, £→GBP, đ→VND`. |
| 7 | Line items | `extract_line_items` | Region = after a header row matching `QTY...PRICE` (fallback: after the first 3 lines) until the first summary keyword row. Rows carry `description ... qty x price ... line_total`; amount-free rows inside the region are description continuations (multi-line product names). |
| 8 | Summary amounts | `extract_summary` | Rows matching `discount / subtotal / tax|vat / cash|paid|payment / change / total`; value = rightmost money token on the row. Multiple `TOTAL` rows: keep the bottom-most; differing values or duplicate labels raise an `ambiguous:` note (review). |
| 9 | Validation | `validator.apply_validation` | Checks below; sets `validation_status`. |

## Vietnamese labels (M5C)

Language-specific recognition lives in `extraction/lexicon_vi.py`;
matching is diacritic-insensitive (NFD strip + đ→d + casefold), applied
to a folded copy of the row text — the OCR text itself is never
modified. Supported: HÓA ĐƠN/SỐ HÓA ĐƠN, NGÀY LẬP/NGÀY BÁN, TÊN CỬA
HÀNG/ĐƠN VỊ BÁN HÀNG (labelled values become supplier), TẠM TÍNH/TỔNG
TIỀN HÀNG → subtotal, THÀNH TIỀN/TỔNG CỘNG/TỔNG THANH TOÁN → total,
THUẾ (GTGT)/VAT → tax, GIẢM GIÁ/CHIẾT KHẤU → discount, TIỀN MẶT/TIỀN
KHÁCH ĐƯA/KHÁCH ĐƯA → payment, TIỀN THỪA/TIỀN TRẢ LẠI → change, SỐ
LƯỢNG…ĐƠN GIÁ header. Every summary keyword also OPENS the summary zone
(a cash/tax row before the subtotal ends the item region instead of
becoming a bogus line item). Invoice numbers must contain a digit —
label words on neighbouring lines ("Invoice Date: …") are never
captured.

Monetary: `đ`/`₫`/VNĐ count as currency only as standalone tokens, so
"đơn giá" is never currency noise; attached signs (`₫125.000`) are
stripped as a prefix. `1.234.567` and `1.234.567,89` parse via the
existing separator rules; a bare "tiền" is never a total.

**Reality check:** these are extraction RULES over OCR output. The
pinned PP-OCRv6 models were NOT evaluated for Vietnamese text
recognition (engine default `lang="en"`); real Vietnamese-document
accuracy remains pending labeled data.

## Monetary parsing rules

`parse_amount` (deterministic):

- Both `.` and `,` present → the **later** one is the decimal mark
  (`1,234.56` = `1.234,56` = 1234.56).
- Only `,` → thousands if `1,234,567`-shaped, else decimal
  (`12,30` → 12.30).
- Only `.` → thousands if `1.234.567`-shaped and not `\d+.\d{1,2}`,
  else decimal (`12.30` → 12.30, `1.234` → 1234).
- Currency symbols/words (`$ € £ ¥ đ usd vnd ...`) are stripped first.
- The money-token fallback (`MONEY_TOKEN_RE` for whole tokens,
  `MERGED_MONEY_RE` when a label and its amount share one OCR region,
  e.g. `TONG CONG: 97.200`) accepts **unbounded ungrouped integer
  digits** (`1234.56`, `12345.67`, `1234567,89`, bare `97200` and
  thousands-grouped `20.000` all match completely) and uses lookarounds
  so a malformed run (`12.34.56.78`) matches **nothing** instead of a
  substring — a value that cannot be parsed reliably stays `null`.
- When a row holds several candidates, the **rightmost complete match**
  wins.
- A bare token qualifies as money only with an explicit 2-decimal
  fraction or being an integer token — descriptions like `EGGS X12`
  are never amounts.

## Validation semantics

Completeness and arithmetic consistency are judged separately:

| Status | Meaning |
|---|---|
| `ok` | Sufficiently complete, no arithmetic inconsistency, no ambiguity. |
| `review_required` | Critical information missing/incomplete (`incomplete:` notes) or ambiguous (`ambiguous:` notes). |
| `invalid` | An arithmetic inconsistency is demonstrated by sufficient extracted operands. |

**Sufficiently complete (M2 baseline)** = at least one *monetary
anchor* — a grand total, a subtotal, or a line item carrying a
`line_total` — AND at least one *identification field* (supplier,
invoice number, or invoice date). Optional fields (tax, discount,
payment, change) never affect completeness when absent from the
document.

## Validation checks (only when all operands exist)

| Check | Error string |
|---|---|
| `quantity × unit_price == line_total` per item | `line_items[i]: quantity x unit_price != line_total` |
| `sum(line_totals) == subtotal` — requires **every** extracted line item to have a `line_total`; a partially extracted item list is never reported as a mismatch | `subtotal != sum(line_items.line_total)` |
| `total == subtotal + tax - discount` (or `== subtotal` when neither exists) | `total != subtotal + tax - discount` |
| `change == payment - total` | `change_amount != payment_amount - total` |

Missing values never produce errors — absence is not an inconsistency.

## Explicit limitations (M2 baseline)

- Strictly extractive: line totals are never derived from
  `quantity × price`; if the receipt doesn't print them, they stay `null`.
- Single currency per document; no multi-page documents.
- Keyword matching is English (`TOTAL`, `CASH`, ...); Vietnamese receipts
  need a lexicon extension (future work).
- Line grouping trusts the OCR engine's page reading order and only
  re-derives within-row order geometrically.
- Multi-line descriptions are supported as *name continuation before*
  the qty/price row; name text printed *after* the amount row is dropped.
- No accuracy claims: measuring field-level precision/recall requires a
  labeled dataset (future milestone).
