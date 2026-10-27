"""Deterministic, layout-aware receipt/invoice extraction from OCR JSON.

Pipeline (see docs/extraction-spec.md for the rule tables):
  1. text normalization          (parsing.normalize_text, per token)
  2. line grouping               (layout.group_lines, bounding-box geometry)
  3. supplier / invoice number   (header heuristics + regex)
  4. date normalization          (keyword line first, then first parseable date)
  5. monetary parsing            (separator rules in parsing.parse_amount)
  6. line items                  (header region or confirmed headerless
                                  region + qty x price + trailing amount)
  7. summary amounts             (keyword rows, rightmost amount wins)
  8. arithmetic validation       (validator.apply_validation)

The baseline is strictly extractive: a value the OCR text does not
contain is left ``None``. Derived arithmetic (e.g. computing a line total
from quantity x price) is deliberately NOT performed. Ambiguous mappings
are reported as ``ambiguous:`` validation notes instead of guesses.
"""

import json
import re
from decimal import Decimal
from pathlib import Path

from .layout import OcrToken, VisualLine, group_lines
from .models import ExtractionResult, Invoice, LineItem, Provenance
from .parsing import (
    CURRENCY_NOISE_RE,
    MERGED_MONEY_RE,
    MONEY_TOKEN_RE,
    QTY_PRICE_RE,
    parse_amount,
    parse_date,
)
from .validator import apply_validation


class OcrInputError(ValueError):
    """Raised when the OCR JSON document cannot be used for extraction."""


HEADER_RE = r"(?i)\bqty\b.*\bprice\b|\bitem\b.*\bqty\b"
SUMMARY_START_RE = (
    r"(?i)\b(sub-?total|tax|vat|total|discount|cash|paid|payment|change|"
    r"amount\s+due)\b"
)
# Header-area lines that must never become the supplier name.
SUPPLIER_STOP_RE = (
    r"(?i)^(receipt|invoice|date|time|currency|tax|vat|tel|phone|address|"
    r"www\.|http)"
)

# Vietnamese label lexicon (diacritic-insensitive; see lexicon_vi.py).
from .lexicon_vi import (  # noqa: E402
    CURRENCY_LABEL_VI,
    DATE_LABEL_VI,
    DONG_SIGN_RE,
    HEADER_ROW_VI,
    INVOICE_NUMBER_LABEL_VI,
    SUMMARY_LABELS_VI,
    SUPPLIER_LABEL_VI,
    VND_WORD_RE,
    fold_vi,
)

HEADER_RE = HEADER_RE + "|" + HEADER_ROW_VI
SUMMARY_START_RE = (
    SUMMARY_START_RE + "|" + INVOICE_NUMBER_LABEL_VI
    # Zone openers must cover every SUMMARY_LABELS_VI keyword: a label
    # that only SUMMARY_FIELDS knows (thue, khach dua, tien mat) would
    # otherwise stay inside the ITEM region and become a bogus line item.
    + r"|\b(tam tinh|tong tien hang|giam gia|chiet khau|thue|"
    r"tien khach dua|khach dua|tien mat|tien thua|tien tra lai|"
    r"tong cong|tong thanh toan|thanh tien|tong tien)\b"
)

# Headerless receipts: document-metadata rows that carry digits must never
# be mistaken for products. Patterns are anchored to the row start (matched
# on folded text) and ID labels additionally require a digit-bearing token,
# so ordinary product names that merely contain these words stay eligible.
# Tax identifier shapes ("Tax ID:", "MST:", "Mã số thuế:", "VAT code:")
# as opposed to monetary tax rows ("VAT 10%", "THUẾ GTGT 5.500").
TAX_IDENTIFIER_PATTERN = (
    r"tax\s*(?:id|code|no\.?)|mst|ma\s+so\s+thue|vat\s*(?:id|no\.?|code)"
)
TAX_IDENTIFIER_RE = re.compile(
    r"^(?:" + TAX_IDENTIFIER_PATTERN + r")\b", re.IGNORECASE
)
METADATA_LABEL_RE = re.compile(
    r"^(?:"
    r"(?:so\s+hoa\s+don|so\s+hd|hoa\s+don|ma\s+giao\s+dich|ma\s+don\s+hang)\b"
    r"|(?:" + TAX_IDENTIFIER_PATTERN + r")\b"
    # Phone labels require a separator here; unpunctuated labels are
    # handled by _is_unpunctuated_phone_label_row, which accepts only
    # digit-only phone-like tails, so products such as "TEL 40W LAMP"
    # and "ĐIỆN THOẠI" survive.
    r"|(?:tel|phone|mobile|hotline|fax|dien\s+thoai|sdt|dt|dtdd|"
    r"so\s+dt)\b\s*[:#]"
    r"|(?:address|dia\s+chi)\s*[:#]"
    r"|(?:address|dia\s+chi)\b[^\n]*"
    r"\b(?:street|st|road|rd|duong|pho|ward|phuong|quan|district)\b"
    r"|(?:store|shop|branch|outlet|terminal|register|quay|"
    r"cua\s+hang|chi\s+nhanh)\b"
    r"(?:\s*(?:#|no\.?|number|so)\s*[:#]?\s*\d{1,6}|\s+\d{1,6})\s*$"
    r"|(?:cashier|thu\s+ngan|server|waiter|staff|nhan\s+vien)\b\s*[:#]"
    r"|(?:customer|khach\s+hang|member|thanh\s+vien)\b"
    r"(?:\s*[:#]|\s*(?:#|no\.?|id)?\s*\d{1,12}\s*$)"
    r"|(?:currency|tien\s+te)\b"
    r"|(?:ten\s+cua\s+hang|don\s+vi\s+ban\s+hang)\b"
    r"|(?:table|ban)\b\s*[:#.]?\s*\w{0,8}\d+\s*$"
    r"|(?:www\.|https?://|@)"
    r")",
    re.IGNORECASE,
)
# Payment-card rows are metadata for ITEM exclusion but are legitimate
# tender rows for SUMMARY parsing ("CARD PAYMENT 110.00" feeds
# payment_amount). Kept separate so the summary pass can opt out.
PAYMENT_CARD_RE = re.compile(
    r"^(?:card|visa|mastercard|debit|credit)\b\s*"
    r"(?:(?:payment|tender|card|debit|credit)\s*){0,2}"
    r"[:#]?\s*[*x]*\d",
    re.IGNORECASE,
)
# A whole row that is only an identifier label + code ("HĐ 000123",
# "No. 000123", "Invoice No. 1.234", "TXN 1,234,567", "Số: 000123").
# Requiring the label and a digit-bearing code token to fill the ENTIRE
# row keeps product names that merely start with those words eligible
# ("NO. 5 PERFUME 25.000", "Invoice A4 Paper 25.000"). Dots and commas
# are allowed inside the code so dotted/grouped document numbers are
# recognized instead of becoming phantom line items.
IDENTIFIER_ROW_RE = re.compile(
    r"^(?:"
    r"(?:receipt|invoice|inv|bill|order|transaction|txn|trx|"
    r"ref(?:erence)?|auth(?:orization)?|approval|trace)\s*"
    r"(?:#|no\.?|num(?:ber)?|id)?\s*[:#]?\s*"
    r"[A-Za-z0-9][A-Za-z0-9/.,-]*\d[A-Za-z0-9/.,-]*"
    r"|(?:no\.?|so|phieu|hd|h\s*d|bien\s+lai|"
    r"ma\s+(?:kh|khach(?:\s+hang)?|don(?:\s+hang)?|hd|giao\s+dich))"
    r"\s*[:#]?\s*"
    r"[A-Za-z0-9][A-Za-z0-9/.,-]*\d[A-Za-z0-9/.,-]*"
    r")\s*(?:[đ₫$€£¥]|d|vnd|usd|eur|gbp|jpy)?\s*$",
    re.IGNORECASE,
)
# Street-shaped rows: a house number followed by an English street word
# before a comma/end of row, or a Vietnamese street word immediately
# after the house number with an administrative/postal comma component
# ("123 Đường Lê Lợi, Quận 1"). Street words are NOT matched anywhere
# later in the row: folded Vietnamese commodities collide with them
# ("1 KG ĐƯỜNG TRẮNG", "2 BOWL PHO", "2 PHỞ 100.000").
STREET_ADDRESS_RE = re.compile(
    r"^\s*(?:"
    r"(?:\d{1,5}[A-Za-z]?|(?:so|no\.?|#)\s*\d{1,5})\s+(?:duong|pho)\s+"
    r"\S.*,\s*(?:p\.|q\.|phuong|quan|huyen|ward|district|tp\.?|tinh|"
    r"city|\d{5,6}\b)"
    r"|\d{1,5}[A-Za-z]?\s+\S.*\b(?:street|st|road|rd|avenue|ave|lane|"
    r"boulevard|blvd)\b(?=\s*(?:,|$))"
    r"|(?:so|no\.?|#)\s*\d{1,5}\b.*\b(?:street|st|road|rd|avenue|ave|"
    r"lane|boulevard|blvd)\b(?=\s*(?:,|$))"
    r")",
    re.IGNORECASE,
)
# House number + comma-separated address tail: postal code or an
# administrative component ("123 Lê Lợi, Bến Thành, 700000",
# "123 Lê Lợi, P. Bến Thành, Q.1", "123 Lê Lợi, Quận 1"). A product row
# almost never starts with a house number followed by a comma; non-money
# commas are required so "1 KG ĐƯỜNG TRẮNG, 20.000" stays an item.
POSTAL_ADDRESS_RE = re.compile(
    r"^\d{1,5}[A-Za-z]?(?:[/-]\d{1,5})?\s+\S.*"
    r"(?:,\s*\d{5,6}\s*$"
    r"|,\s*(?:p\.|q\.|phuong|quan|huyen|ward|district)\b)",
    re.IGNORECASE,
)
ADMIN_AREA_RE = re.compile(
    r"^(?:(?:phuong|quan|huyen|ward|district)\b\s*(?:so)?\s*\d+"
    r"|[pq]\.\s*(?:\d{1,2}\b|[a-z]\w*))",
    re.IGNORECASE,
)
# Phone-shaped digit runs: leading 0, +country code, or parenthesised
# area code, with 9-12 digits. The run must start at a digit boundary
# and grouped money ("1.250.000", "25.000.000") never starts with 0, so
# product names such as "PHONE CASE 1.250.000" stay items; the digit
# count check rejects short runs that merely look grouped.
PHONE_SHAPE_RE = re.compile(
    r"(?<![\d.,])(?:"
    r"\+\d{1,3}(?:[\s.-]?\d{2,4}){2,5}"
    r"|\(\d{1,4}\)(?:[\s.-]?\d{2,4}){2,3}"
    r"|0(?:[\s.-]?\d{1,4}){2,4}"
    r")(?!\d)"
)
# 1900/1800 hotlines are 8 digits, but the bare prefix also occurs in
# product model numbers followed by a price ("BÀN ỦI 1800 25.000"), so
# a hotline run only counts at the start of the row or right after a
# phone label.
HOTLINE_RE = re.compile(
    r"(?<![\d.,])(?:1900|1800)(?:[\s.-]?\d{2,4}){1,3}(?!\d)"
)
PHONE_LABEL_CONTEXT_RE = re.compile(
    r"(?:tel|phone|mobile|hotline|fax|dien\s+thoai|sdt|dt|dtdd|so\s+dt|lh)"
    r"[\s:#.-]*$",
    re.IGNORECASE,
)
# An unpunctuated label is metadata only when its value is phone-shaped
# or a bare 7+ digit run ("Fax 3825 1234"); product rows such as
# "TEL 40W LAMP 25.000" and "ĐIỆN THOẠI 2.000.000" keep their amounts.
PHONE_LABEL_NO_SEP_RE = re.compile(
    r"^(?:tel|phone|mobile|hotline|fax|dien\s+thoai|sdt|dt|dtdd|"
    r"so\s+dt|lh)\b",
    re.IGNORECASE,
)
TIME_LABEL_RE = re.compile(
    r"^(?:\d{1,2}:\d{2}(?::\d{2})?"
    r"(?:\s*[-–]\s*\d{1,2}:\d{2}(?::\d{2})?)?"
    r"|(?:open(?:ing)?|hours|gio|thoi\s+gian)\b.*\d{1,2}:\d{2})",
    re.IGNORECASE,
)

# Ordered: a summary row is classified by the FIRST matching pattern, so
# DISCOUNT/SUBTOTAL must precede TOTAL (regex word boundaries already stop
# \btotal\b from matching inside "SUBTOTAL", but ordering keeps intent
# clear). Vietnamese patterns match against the diacritic-folded row text.
SUMMARY_FIELDS: tuple[tuple[str, str], ...] = (
    ("discount", r"(?i)\bdiscount\b"),
    ("subtotal", r"(?i)\bsub-?total\b"),
    ("tax", r"(?i)\b(?:tax|vat)\b"),
    ("payment_amount", r"(?i)\b(?:cash|paid|payment)\b"),
    ("change_amount", r"(?i)\bchange\b"),
    ("total", r"(?i)\b(?:grand\s+)?total(?:\s+due)?\b"),
    *SUMMARY_LABELS_VI,
)

CURRENCY_LABEL_RE = re.compile(r"(?i)\bcurrency\b\s*[:.]?\s*([A-Za-z]{3})\b")
# The capture must contain a digit: an optional label group followed by an
# all-optional separator otherwise grabs the NEXT WORD on label lines
# ("Invoice Date: ..." -> "Date", "RECEIPT FROM ..." -> "FROM") and stops
# the scan before the real number is reached.
INVOICE_NUMBER_RE = re.compile(
    r"(?i)\b(?:receipt|invoice)\s*(?:#|no\.?|num(?:ber)?)?\s*[:#]?\s*"
    r"((?=[A-Za-z0-9/-]*\d)[A-Za-z0-9][A-Za-z0-9/-]{2,})"
)
# đ/₫ are deliberately NOT here: as plain substrings they sit inside common
# Vietnamese words ("đơn giá", "đã"). The standalone-sign rule lives in
# DONG_SIGN_RE and is applied by the VND pass in extract_currency.
SYMBOL_TO_CODE = {"$": "USD", "€": "EUR", "£": "GBP"}
DATE_LABELS_RE = re.compile(r"(?i)\bdate\b|" + DATE_LABEL_VI)

MAX_OCR_JSON_BYTES = 50 * 1024 * 1024


def load_ocr_document(path: str | Path) -> dict:
    """Load and structurally validate a saved OCR JSON document."""
    document_path = Path(path)
    raw = document_path.read_text(encoding="utf-8")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OcrInputError(f"Malformed JSON in '{document_path}': {exc}") from exc
    if not isinstance(document, dict):
        raise OcrInputError(
            f"OCR JSON must be an object with an 'items' array: '{document_path}'"
        )
    if not isinstance(document.get("items"), list):
        raise OcrInputError(
            f"OCR JSON is missing the 'items' array: '{document_path}'"
        )
    return document


def _clean_money_text(text: str) -> str:
    return re.sub(CURRENCY_NOISE_RE, "", text).strip()


def _is_money_token(token: OcrToken) -> bool:
    """A token is a money candidate when the whole token is an amount."""
    cleaned = _clean_money_text(token.text)
    if not any(ch.isdigit() for ch in cleaned):
        return False
    return bool(
        re.fullmatch(MONEY_TOKEN_RE, cleaned)
        or re.fullmatch(r"-?\d+", cleaned)
        # Vietnamese grouping without decimals ("10.000", "1.234.567")
        or re.fullmatch(r"-?\d{1,3}(?:[.,]\d{3})+", cleaned)
    )


def _line_has_amount(line: VisualLine) -> bool:
    return any(_is_money_token(token) for token in line.tokens)


def _line_has_item_amount(line: VisualLine) -> bool:
    """Whole-token amount, qty x price, or a merged trailing amount."""
    return bool(
        _line_has_amount(line)
        or QTY_PRICE_RE.search(line.text)
        or _merged_trailing_amount(line.text) is not None
    )


def _rightmost_amount(line: VisualLine) -> Decimal | None:
    """Rightmost money token on the line; regex fallback for merged text.

    The token pass takes the rightmost whole-token amount. The fallback
    scans the merged line text with MERGED_MONEY_RE (decimal fraction,
    thousands-grouped, or bare integer) and takes the LAST complete
    match (rightmost in reading order); malformed runs match nothing
    rather than a substring of a larger amount.
    """
    for token in reversed(line.tokens):
        if _is_money_token(token):
            amount = parse_amount(token.text)
            if amount is not None:
                return amount
    matches = list(re.finditer(MERGED_MONEY_RE, _clean_money_text(line.text)))
    if matches:
        return parse_amount(matches[-1].group(0))
    return None


def _has_description(text: str) -> bool:
    """At least two letters: enough to be a product name, not a stray ID."""
    return sum(1 for char in text if char.isalpha()) >= 2


def _amount_token(line: VisualLine, amount_text: str) -> OcrToken | None:
    """Token that actually contains ``amount_text`` (not a trailing ``đ``)."""
    for token in reversed(line.tokens):
        if amount_text in token.text:
            return token
    return None


def _merged_trailing_amount(text: str) -> tuple[str, Decimal, str] | None:
    """Split a merged ``description + trailing amount`` row.

    Returns ``(description_prefix, amount, amount_text)`` only when the
    amount is the final content of the row and has an unambiguous
    monetary shape: thousands grouping or a decimal fraction. A bare
    integer is never accepted here — without formatting evidence it is
    indistinguishable from a store/table/model/house number, and a
    currency sign elsewhere on the row does not prove the number is
    money ("MINI MART #247 ₫"). A whole-token integer amount on a
    multi-region row is still handled by the token rule. An attached
    đồng sign (``25.000đ``, ``₫25.000``) is stripped for matching so
    Vietnamese merged rows are not lost.
    """
    cleaned = _clean_money_text(text).strip()
    cleaned = re.sub(r"(?<=\d)[đ₫]\s*$", "", cleaned)
    cleaned = re.sub(r"(?<![\w])[đ₫](?=\d)", "", cleaned).strip()
    matches = list(re.finditer(MERGED_MONEY_RE, cleaned))
    if not matches:
        return None
    match = matches[-1]
    if cleaned[match.end():].strip():
        return None
    amount_text = match.group(0)
    if re.fullmatch(r"\d+", amount_text):
        return None
    amount = parse_amount(amount_text)
    if amount is None:
        return None
    return cleaned[: match.start()].strip(" -–:|"), amount, amount_text


def _is_summary_line(line: VisualLine) -> bool:
    return bool(
        re.search(SUMMARY_START_RE, line.text)
        or re.search(SUMMARY_START_RE, fold_vi(line.text))
    )


def _looks_like_phone(text: str) -> bool:
    """True when the row contains a phone-shaped digit run.

    Standard runs need at least 9 digits because 8-digit digit runs occur
    in ordinary amounts. 1900/1800 hotlines are legitimately 8 digits,
    but only at the row start or after a phone label.
    """
    for match in PHONE_SHAPE_RE.finditer(text):
        digits = "".join(char for char in match.group(0) if char.isdigit())
        if 9 <= len(digits) <= 12:
            return True
    for match in HOTLINE_RE.finditer(text):
        digits = "".join(char for char in match.group(0) if char.isdigit())
        if not 8 <= len(digits) <= 12:
            continue
        prefix = text[: match.start()].rstrip()
        if not prefix or PHONE_LABEL_CONTEXT_RE.search(prefix):
            return True
    return False


def _is_unpunctuated_phone_label_row(folded: str) -> bool:
    """Metadata label without a separator whose value is digit-only."""
    match = PHONE_LABEL_NO_SEP_RE.match(folded)
    if match is None:
        return False
    tail = folded[match.end():]
    if sum(char.isdigit() for char in tail) < 7:
        return False
    if re.search(r"[a-z]", tail):
        return False
    # Grouped/decimal amounts are money, not phone numbers.
    return not (
        re.search(r"\d[.,]\d{3}", tail)
        or re.search(r"\d[.,]\d{1,2}\b", tail)
    )


def _is_metadata_line(line: VisualLine) -> bool:
    """True for letterhead/metadata rows that must never become products."""
    text = line.text.strip()
    if not text:
        return True
    folded = fold_vi(text)
    if METADATA_LABEL_RE.match(folded) or IDENTIFIER_ROW_RE.match(folded):
        return True
    if PAYMENT_CARD_RE.match(folded):
        return True
    if _is_unpunctuated_phone_label_row(folded):
        return True
    if (
        STREET_ADDRESS_RE.match(folded)
        or POSTAL_ADDRESS_RE.match(folded)
        or ADMIN_AREA_RE.match(folded)
    ):
        return True
    if _looks_like_phone(folded):
        return True
    if parse_date(text) is not None:
        return True
    return bool(TIME_LABEL_RE.match(folded))


def _is_item_candidate(line: VisualLine) -> bool:
    """A headerless row is a candidate only with description + amount.

    The description must sit before the amount (or before the
    ``qty x price`` token), so reversed rows like ``123 Street`` and
    letterhead values carry no product evidence.
    """
    if _is_metadata_line(line) or _is_summary_line(line):
        return False
    if not line.tokens:
        return False
    qty_match = QTY_PRICE_RE.search(line.text)
    if qty_match:
        return _has_description(line.text[: qty_match.start()])
    merged = _merged_trailing_amount(line.text)
    if merged is not None:
        return _has_description(merged[0])
    amount_positions = [
        position
        for position, token in enumerate(line.tokens)
        if _is_money_token(token)
    ]
    if not amount_positions:
        return False
    before = " ".join(
        token.text
        for token in line.tokens[: amount_positions[-1]]
        if not _is_money_token(token)
    )
    return _has_description(before)


class _Extractor:
    def __init__(self, source: str) -> None:
        self.source = source
        self.invoice = Invoice()
        self.provenance: dict[str, Provenance] = {}
        self.ambiguities: list[str] = []

    def _record(self, field_path: str, token: OcrToken) -> None:
        self.provenance[field_path] = Provenance(
            ocr_index=token.index,
            text=token.text,
            box=[list(point) for point in token.box],
        )

    # -- stages 3/4: header fields -------------------------------------------

    def extract_supplier(self, lines: list[VisualLine]) -> None:
        for line in lines[:3]:
            if not line.text or re.match(SUPPLIER_STOP_RE, line.text):
                continue
            # "TÊN CỬA HÀNG: MINIMART" — take the labelled value, not the label.
            labelled = re.search(
                r"(?i)(?:ten cua hang|don vi ban hang|cua hang)\s*[:.-]?\s*(.+)",
                fold_vi(line.text),
            )
            if labelled:
                # Preserve the original (diacritic) tail after the label.
                raw_tail = re.split(r"(?i)[:] ", line.text, maxsplit=1)
                value = (raw_tail[1] if len(raw_tail) == 2
                         else labelled.group(1)).strip(" :.-")
                # A label-only line ("TEN CUA HANG:") backtracks the regex
                # into matching the bare ":" separator; reject anything
                # without a word character and keep scanning.
                if re.search(r"\w", value):
                    self.invoice.supplier = value
                    self._record("supplier", line.tokens[0])
                    return
            if parse_date(line.text) or _rightmost_amount(line) is not None:
                continue
            if re.search(SUPPLIER_LABEL_VI, fold_vi(line.text)):
                continue  # a bare label line, not a supplier name
            self.invoice.supplier = line.text
            self._record("supplier", line.tokens[0])
            return

    def extract_invoice_number(self, lines: list[VisualLine]) -> None:
        vi_number = re.compile(
            r"(?:so hoa don|so hd)\s*[:#]?\s*"
            r"((?=[A-Za-z0-9/-]*\d)[A-Za-z0-9][A-Za-z0-9/-]{2,})"
        )
        for line in lines:
            match = re.search(INVOICE_NUMBER_RE, line.text) or vi_number.search(
                fold_vi(line.text)
            )
            if match:
                self.invoice.invoice_number = match.group(1)
                self._record("invoice_number", line.tokens[0])
                return

    def extract_date(self, lines: list[VisualLine]) -> None:
        labelled = [
            line for line in lines if DATE_LABELS_RE.search(fold_vi(line.text))
        ]
        for line in labelled + lines:
            parsed = parse_date(line.text)
            if parsed is not None:
                self.invoice.invoice_date = parsed
                self._record("invoice_date", line.tokens[0])
                return

    def extract_currency(self, lines: list[VisualLine]) -> None:
        for line in lines:
            match = re.search(CURRENCY_LABEL_RE, line.text) or re.search(
                CURRENCY_LABEL_VI + r"\s*[:.]?\s*([A-Za-z]{3})", fold_vi(line.text)
            )
            if match:
                self.invoice.currency = match.group(1).upper()
                self._record("currency", line.tokens[0])
                return
        for line in lines:
            if VND_WORD_RE.search(line.text) or DONG_SIGN_RE.search(line.text):
                self.invoice.currency = "VND"
                self._record("currency", line.tokens[0])
                return
        for line in lines:
            for symbol, code in SYMBOL_TO_CODE.items():
                if symbol in line.text:
                    self.invoice.currency = code
                    self._record("currency", line.tokens[0])
                    return

    # -- stage 6: line items ---------------------------------------------------

    def extract_line_items(self, lines: list[VisualLine]) -> None:
        """Extract line items between the item region and the summary zone.

        With a header row (``QTY ... PRICE`` / ``SỐ LƯỢNG ... ĐƠN GIÁ``),
        the header is authoritative and items start on the next line.
        Without one, the region starts at the first row that has both a
        product-like description and monetary evidence, and only when a
        summary row below confirms the document's item/summary layout.
        Metadata rows never become items or description continuations;
        amount-free rows inside the region remain multi-line description
        continuations of the next parsed row.
        """
        header_index = next(
            (
                position
                for position, line in enumerate(lines)
                if re.search(HEADER_RE, line.text)
                or re.search(HEADER_RE, fold_vi(line.text))
            ),
            None,
        )
        headerless = header_index is None
        if headerless:
            start = self._headerless_item_start(lines)
            if start is None:
                return
        else:
            start = header_index + 1
        pending_description: list[tuple[str, OcrToken]] = []

        for line in lines[start:]:
            if headerless:
                if _is_metadata_line(line):
                    continue
                has_item_amount = _line_has_item_amount(line)
            else:
                # Explicit-header rows keep the original rule: a whole-token
                # amount or a qty x price token. Merged-row recovery and
                # metadata skipping are headerless-only, so adding a header
                # never changes how the rows below it are parsed.
                has_item_amount = _line_has_amount(line) or bool(
                    QTY_PRICE_RE.search(line.text)
                )
            if _is_summary_line(line):
                break  # summary zone reached: item region ended
            if not has_item_amount:
                pending_description.append((line.text, line.tokens[0]))
                continue

            item, prov_tokens = _parse_item_line(line, pending_description)
            pending_description.clear()
            if item is None:
                continue
            index = len(self.invoice.line_items)
            self.invoice.line_items.append(item)
            for suffix, token in prov_tokens.items():
                if token is not None:
                    self._record(f"line_items[{index}].{suffix}", token)

    def _headerless_item_start(self, lines: list[VisualLine]) -> int | None:
        """Index of the first confirmed item row, or ``None``.

        A headerless region is only trusted when a summary row below it
        confirms that the rows before the summary are items. Rows without
        that confirmation stay unclassified (reported as ambiguous when
        item-like evidence exists) instead of being guessed.
        """
        first_candidate: VisualLine | None = None
        first_candidate_index: int | None = None
        for index, line in enumerate(lines):
            if _is_metadata_line(line):
                continue
            if _is_summary_line(line):
                return first_candidate_index
            if first_candidate_index is None and _is_item_candidate(line):
                first_candidate = line
                first_candidate_index = index
        if first_candidate is not None:
            self.ambiguities.append(
                f"headerless amount row {first_candidate.text!r} is not "
                "confirmed by a summary row; no line items extracted"
            )
        return None

    # -- stage 7: summary amounts ----------------------------------------------

    def extract_summary(self, lines: list[VisualLine]) -> None:
        total_candidates: list[tuple[Decimal, VisualLine]] = []
        summary_zone = False

        for line in lines:
            folded = fold_vi(line.text)
            if not summary_zone and (
                re.search(SUMMARY_START_RE, line.text)
                or re.search(SUMMARY_START_RE, folded)
            ):
                summary_zone = True
            if not summary_zone:
                continue
            if TAX_IDENTIFIER_RE.match(folded):
                # "Tax ID: 0123456789" is an identifier, not a monetary
                # tax row; tender rows keep feeding summary parsing.
                continue
            matched_field = None
            for field_name, pattern in SUMMARY_FIELDS:
                if re.search(pattern, line.text) or re.search(pattern, folded):
                    matched_field = field_name
                    break
            if matched_field is None:
                continue
            amount = _rightmost_amount(line)
            if amount is None:
                continue

            if matched_field == "total":
                total_candidates.append((amount, line))
                continue
            setattr(self.invoice, matched_field, amount)
            self._record(matched_field, line.tokens[-1])

        if total_candidates:
            amount, line = total_candidates[-1]
            self.invoice.total = amount
            self._record("total", line.tokens[-1])
            if len({value for value, _ in total_candidates}) > 1:
                self.ambiguities.append(
                    "multiple differing TOTAL rows found ("
                    + ", ".join(str(value) for value, _ in total_candidates)
                    + "); kept the bottom-most one"
                )
            elif len(total_candidates) > 1:
                self.ambiguities.append(
                    "TOTAL label appears more than once with the same value"
                )

    # -- driver ------------------------------------------------------------------

    def run(self, ocr_items: list) -> ExtractionResult:
        lines = group_lines(ocr_items)
        self.extract_supplier(lines)
        self.extract_invoice_number(lines)
        self.extract_date(lines)
        self.extract_currency(lines)
        self.extract_line_items(lines)
        self.extract_summary(lines)
        apply_validation(self.invoice, self.ambiguities)
        return ExtractionResult(
            source=self.source, invoice=self.invoice, provenance=self.provenance
        )


def _parse_item_line(
    line: VisualLine,
    pending_description: list[tuple[str, OcrToken]],
) -> tuple[LineItem | None, dict[str, OcrToken | None]]:
    """Parse one item row into ``(LineItem, provenance_tokens)``.

    Layout contract: description tokens sit left of the ``qty x price``
    token, and the line total is the rightmost monetary value. The caller
    routes rows with monetary evidence, so a row can arrive with a
    whole-token amount, a ``qty x price`` pair (optionally followed by
    its line total), or a merged ``description + trailing amount`` row.
    Ambiguous rows (a bare trailing amount with no explicit quantity)
    keep quantity/unit_price as ``None`` instead of guessing.

    The provenance map links each extracted value to the OCR region it
    was actually parsed from: ``description`` points at the first
    description-continuation region when one exists (multi-line product
    names), otherwise at the row's leftmost token; ``quantity`` and
    ``unit_price`` point at the region containing the qty x price
    pattern; ``line_total`` at the amount region.
    """
    amount_tokens = [token for token in line.tokens if _is_money_token(token)]
    non_amount_tokens = [token for token in line.tokens if token not in amount_tokens]
    if len(line.tokens) > 1:
        parts: list[str] = []
        spans: list[tuple[int, int, OcrToken]] = []
        offset = 0
        for token in non_amount_tokens:
            spans.append((offset, offset + len(token.text), token))
            parts.append(token.text)
            offset += len(token.text) + 1
        joined = " ".join(parts)
    else:
        only = line.tokens[0] if line.tokens else None
        spans = [(0, len(line.text), only)] if only is not None else []
        joined = line.text

    def _token_at(position: int) -> OcrToken | None:
        for start, end, token in spans:
            if start <= position < end:
                return token
        return spans[-1][2] if spans else None

    quantity = unit_price = None
    description_parts: list[str] = [text for text, _ in pending_description]
    description_token = (
        pending_description[0][1]
        if pending_description
        else (non_amount_tokens[0] if non_amount_tokens else None)
    )

    prov: dict[str, OcrToken | None] = {
        "description": description_token,
        "quantity": None,
        "unit_price": None,
        "line_total": None,
    }

    qty_match = QTY_PRICE_RE.search(joined)
    merged = (
        _merged_trailing_amount(joined)
        if not amount_tokens and not qty_match
        else None
    )
    if qty_match:
        quantity = parse_amount(qty_match.group(1))
        unit_price = parse_amount(qty_match.group(2))
        prov["quantity"] = _token_at(qty_match.start())
        prov["unit_price"] = _token_at(qty_match.end(2) - 1)
        prefix = joined[: qty_match.start()].strip(" -–")
        if prefix:
            description_parts.append(prefix)
    elif merged is not None:
        if merged[0]:
            description_parts.append(merged[0])
    elif non_amount_tokens:
        description_parts.append(" ".join(token.text for token in non_amount_tokens))

    description = " ".join(part for part in description_parts if part).strip()
    if not description and quantity is None and unit_price is None:
        return None, prov

    item = LineItem(description=description, quantity=quantity, unit_price=unit_price)
    if amount_tokens:
        total_token = amount_tokens[-1]
        item.line_total = parse_amount(total_token.text)
        prov["line_total"] = total_token
    elif qty_match:
        # Merged single-token row like "SOAP 2 x 2.50 5.00": the line
        # total is the rightmost complete money token after the
        # qty x price pattern (MERGED_MONEY_RE so integer totals,
        # e.g. "CA PHE 2 x 10.000 20.000", are not dropped).
        tail_matches = list(
            re.finditer(MERGED_MONEY_RE, _clean_money_text(joined[qty_match.end():]))
        )
        if tail_matches:
            tail_text = tail_matches[-1].group(0)
            item.line_total = parse_amount(tail_text)
            prov["line_total"] = _amount_token(line, tail_text) or line.tokens[-1]
    elif merged is not None:
        # Merged row like "COFFEE 25.000" where OCR returned the whole
        # product row as one region: the trailing amount is the line total.
        item.line_total = merged[1]
        prov["line_total"] = _amount_token(line, merged[2]) or line.tokens[-1]
    return item, prov


def extract(ocr_document: dict, source: str = "") -> ExtractionResult:
    """Extract an :class:`ExtractionResult` from one OCR JSON document."""
    items = ocr_document.get("items") or []
    return _Extractor(source=source).run(items)
