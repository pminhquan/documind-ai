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
| 7 | Line items | `extract_line_items` | Explicit header (`QTY...PRICE` / `SỐ LƯỢNG...ĐƠN GIÁ`) is authoritative: items start on the next row. Without a header, the region starts at the first confirmed product row before a summary row (see below). Rows carry `description ... qty x price ... line_total`; amount-free rows inside the region are description continuations (multi-line product names). |
| 8 | Summary amounts | `extract_summary` | Rows matching `discount / subtotal / tax|vat / cash|paid|payment / change / total`; value = rightmost money token on the row. Multiple `TOTAL` rows: keep the bottom-most; differing values or duplicate labels raise an `ambiguous:` note (review). |
| 9 | Validation | `validator.apply_validation` | Checks below; sets `validation_status`. |

## Line-item region selection (D-16)

An explicit table header always wins and keeps its existing behavior:
items start on the row after the header, and rows before it are never
items. The header row itself is never an item. Rows below a header keep
the original rule — a whole-token amount or an explicit `qty x price`
token — so adding a header never changes how those rows are parsed;
merged-row recovery and metadata skipping apply to the headerless path
only.

Short receipts often print **no header** (`COFFEE 25.000` directly
followed by `TOTAL 25.000`). For those documents the region is selected
by content, never by a fixed line number:

1. Scan rows until the first summary boundary. A row that is both
   payment metadata and a tender summary (`CARD PAYMENT 25.00`) is a
   boundary: it ends the item region, and the summary pass still reads it
   as a tender row. Other metadata rows are never boundaries, even when
   their text contains a summary keyword (`Tax ID: ...`, `MST: ...`,
   `Số hóa đơn: ...`, `HÓA ĐƠN VAT: ...`, `Tên cửa hàng: Total Mart`).
   Genuine summary labels remain authoritative and always end the item
   region.
2. A row is an item candidate only when it carries both a product-like
   description (at least two letters, left of the amount) and monetary
   evidence: a whole-token amount, an explicit `qty x price` token, or a
   merged row whose **final** content is an amount with thousands
   grouping or a decimal fraction (`COFFEE 25.000`, `CÀ PHÊ SỮA
   25.000đ`).
   A merged bare integer is never item evidence — even with a currency
   sign elsewhere on the row, `TẠP HÓA 247`, `MINI MART #247 ₫`, and
   `123 Lê Lợi 700000` are indistinguishable from letterhead/address
   numbers. (A whole-token integer on a multi-region row still counts as
   money under the existing token rule.) Rows with an amount before the
   description (`123 Street`), numeric-only rows, addresses, dates,
   times, and ID rows are not candidates.
3. The region starts at the first candidate and is accepted only when a
   summary row exists below it. Without that confirmation the rows stay
   unclassified: a lone `COFFEE 25.000` is **not** turned into an item,
   and when item-like evidence exists an `ambiguous:` note explains why.
   This is deliberately conservative — a single amount row cannot prove
   that it is a product rather than an unlabelled document value.
4. Inside the region, metadata rows are skipped entirely: they never
   become items and never become description continuations. Amount-free,
   non-metadata rows remain description continuations of the next parsed
   item (multi-line product names).
5. Recovered items use the same extractive rules: quantity, unit price,
   and line total come only from printed text. A bare trailing amount
   leaves `quantity`/`unit_price` as `null`; it is never derived.

Metadata exclusion is anchored to the row start and context-aware, so
ordinary product names survive: `PHONE CASE 25.000`, `ADDRESS BOOK
25.000`, `STORE BRAND MILK 25.000`, `Invoice Paper 25.000`, and
`Invoice A4 Paper 25.000` remain items (a `PHONE`-prefixed product line
survives even with larger amounts such as `PHONE CASE 1.250.000`,
because phone detection requires a phone-shaped digit run, not merely
the label word; the run must start at a digit boundary, so two grouped
amounts on one row never form a phone). Folded Vietnamese commodity
words that collide with address words also survive (`1 KG ĐƯỜNG TRẮNG`,
`2 BOWL PHO`, `2 ĐÔI QUẦN JEANS`, `2 PHỞ 100.000`, `2 ĐƯỜNG 20.000`):
Vietnamese street words only count inside a street shape — directly
after a house number and followed by a comma-separated
administrative/postal component (`Quận 1`, `P. Bến Thành`, `700000`) —
while English street words must appear before a comma or the end of the
row.

Covered metadata includes receipt/invoice/order/transaction numbers
that fill the whole row (`Invoice No. 1.234`, `Receipt No: 1.234`,
`TXN 1,234,567`, optionally followed by a standalone currency token; a
product row such as `Invoice A4 Paper 25.000` is not an identifier
row), Vietnamese invoice labels (`SỐ HÓA ĐƠN`, `HÓA ĐƠN`, `HĐ:`) and
identifier-only rows (`HĐ 000123`, `No. 000123`, `Số: 000123`, `Phiếu
000123`, `No. 1.234`, `HD 123.456`, `Mã KH 123.456`),
phone/hotline/fax labels (`Tel`, `Phone`, `Mobile`, `Hotline`, `Fax`,
`ĐT`, `LH`, `SĐT`, and `Điện thoại`; an unpunctuated label counts only
when its value is phone-shaped — `Hotline 1900 1234`, `Tel 090 123
4567`, `ĐT 04 3825 1234` — or a bare 7+ digit run such as `Fax 3825
1234`, so products such as `TEL 40W LAMP 25.000`, `ĐIỆN THOẠI 25.000`,
and `BÀN ỦI 1800 25.000` survive) and unlabelled
phone-shaped digit runs (9–12 digits with a leading `0`, `+country
code`, or parenthesised area code; 1900/1800 hotlines count at 8 digits
only at the row start or right after a phone label), address labels,
street/ward lines,
house-number rows with a comma-separated postal code or administrative
component (`Quận 1`, `P. Bến Thành`, `Q.1`), store/branch/table
numbers, tax IDs (MST/VAT ID), cashier/customer/member rows,
payment-card rows, currency labels, dates/times, URLs, and supplier
labels. Summary rows (`subtotal`, `tax`, `discount`, `cash`, `payment`,
`change`, `total`, and their Vietnamese labels) are never items.
Tax-identifier rows (`Tax ID:`, `MST:`, `Mã số thuế:`, `VAT code:`) are
ignored by summary parsing, so they are never read as a monetary tax;
tender rows such as `CARD PAYMENT 110.00` remain summary-eligible. When
a row satisfies both classifiers (payment-card metadata and tender
summary), summary precedence applies in the headerless path: the row
ends the item region instead of being skipped, so rows printed below it
can never be misread as items, while the summary pass still records the
tender amount.

Provenance follows the source regions exactly: for a merged product row
(`COFFEE 25.000` returned as one OCR region), the description and
line total both point at that region; when the amount and a separate
currency sign are different regions (`COFFEE 25.000` + `đ`), the line
total points at the token that contains the amount, not the currency
token. For a multi-line description, the description points at the
first contributing continuation region and the line total at the amount
region. Absent values have no provenance entry.

Limitations of the headerless path: a first item whose description is on
the row(s) above its amount row is not reconstructed (later multiline
continuations are supported); a row containing a full date is treated as
metadata; a merged bare integer is never item evidence (a whole-token
integer on a multi-region row still counts under the token rule);
metadata skipping applies to the headerless region only, so with an
explicit header an amount-free metadata row before an item can still
join that item's description, and a standalone currency token between
the description and amount can appear in a description (both pre-
existing behavior, unchanged by D-16); a tax identifier printed as a
bare `VAT:` number without an `ID`/`code` qualifier is still read as a
monetary tax and treated as a summary boundary (pre-existing); a VAT
token on a metadata row such as `HÓA ĐƠN VAT: 000123` is also still
read as a monetary tax by the summary pass (pre-existing), but that
metadata row never ends the item region; a Vietnamese address without a
postal code or an administrative comma component is not recognized;
metadata recognition is pattern-based, so an unlabelled identifier that
matches none of the listed shapes can still receive candidate
treatment; and word-level `qty x price` splitting remains D-31 scope.

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
stripped as a prefix, and on merged item rows an attached sign is also
stripped as a suffix (`CÀ PHÊ SỮA 25.000đ`). `1.234.567` and
`1.234.567,89` parse via the existing separator rules; a bare "tiền" is
never a total.

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
Recovering a genuine headerless item adds a monetary anchor, so a
document that previously looked incomplete can legitimately become `ok`;
arithmetic checks then include the recovered item like any other item.

## Explicit limitations (M2 baseline)

- Strictly extractive: line totals are never derived from
  `quantity × price`; if the receipt doesn't print them, they stay `null`.
- Single currency per document; no multi-page documents.
- Keyword matching covers the English summary/header labels plus the
  Vietnamese lexicon above; other languages are not recognized.
- Line grouping trusts the OCR engine's page reading order and only
  re-derives within-row order geometrically.
- Multi-line descriptions are supported as *name continuation before*
  the qty/price row; name text printed *after* the amount row is dropped.
- No accuracy claims: measuring field-level precision/recall requires a
  labeled dataset (future milestone).
