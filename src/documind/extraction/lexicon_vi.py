"""Vietnamese label lexicon for invoice extraction (M5C).

Language-specific label recognition lives HERE, separate from the core
parsing/validator: the extractor merges these patterns into its existing
English rule tables, so money parsing, Decimal handling, provenance, and
validation semantics stay shared and unchanged.

Matching is diacritic-insensitive: labels fold via NFD + strip combining
marks + casefold, so "TỔNG CỘNG", "Tong cong", and "tổng cộng" all hit.
OCR text itself is never modified.

Ambiguity policy (documented in docs/extraction-spec.md):
- "THÀNH TIỀN" maps to TOTAL (amount to pay on typical retail receipts);
  "TẠM TÍNH"/"TỔNG TIỀN HÀNG" map to SUBTOTAL. These are heuristics, not
  guarantees — conflicting values surface via existing arithmetic checks.
- A bare "tiền"/"đ" token is NEVER treated as a total/currency.
"""

import re
import unicodedata


def fold_vi(text: str) -> str:
    """Diacritic-insensitive, case-insensitive fold for label matching."""
    decomposed = unicodedata.normalize("NFD", str(text))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    # NFD does not decompose the stroke of đ/Đ — map it explicitly so
    # "đơn" folds to "don" and no-diacritic labels match.
    return stripped.casefold().replace("đ", "d")


# Semantic field -> Vietnamese label patterns (matched on folded text).
SUMMARY_LABELS_VI: tuple[tuple[str, str], ...] = (
    ("discount", r"\b(giam gia|chiet khau)\b"),
    ("subtotal", r"\b(tam tinh|tong tien hang)\b"),
    ("tax", r"\b(thue|thue gtgt|vat)\b"),
    ("payment_amount", r"\b(tien khach dua|khach dua|tien mat)\b"),
    ("change_amount", r"\b(tien thua|tien tra lai)\b"),
    ("total", r"\b(tong cong|tong thanh toan|thanh tien|tong tien)\b"),
)

INVOICE_NUMBER_LABEL_VI = r"\b(so hoa don|so hd)\b"
DATE_LABEL_VI = r"\b(ngay lap|ngay ban|ngay)\b"
CURRENCY_LABEL_VI = r"\b(tien te|don vi tien te)\b"
SUPPLIER_LABEL_VI = r"\b(ten cua hang|don vi ban hang|cua hang)\b"

# Table header row marker (like the English "QTY ... PRICE"); matched on
# folded text, so no inline flags (they are only legal at pattern start).
HEADER_ROW_VI = r"\b(so luong)\b.*\b(don gia)\b"

# Standalone Vietnamese currency markers: đ / VNĐ / ₫ as separate tokens
# only — a "đ" inside "đơn giá" must never read as currency.
VND_WORD_RE = re.compile(r"(?i)(?<![\w])vnd(?![\w])|(?<![\w])vnđ(?![\w])")
DONG_SIGN_RE = re.compile(r"(?<![\w])[đ₫](?![\w])")
