"""Deterministic, layout-aware receipt/invoice extraction from OCR JSON.

Pipeline (see docs/extraction-spec.md for the rule tables):
  1. text normalization          (parsing.normalize_text, per token)
  2. line grouping               (layout.group_lines, bounding-box geometry)
  3. supplier / invoice number   (header heuristics + regex)
  4. date normalization          (keyword line first, then first parseable date)
  5. monetary parsing            (separator rules in parsing.parse_amount)
  6. line items                  (table header + qty x price + trailing amount)
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

# Ordered: a summary row is classified by the FIRST matching pattern, so
# DISCOUNT/SUBTOTAL must precede TOTAL (regex word boundaries already stop
# \btotal\b from matching inside "SUBTOTAL", but ordering keeps intent clear).
SUMMARY_FIELDS: tuple[tuple[str, str], ...] = (
    ("discount", r"(?i)\bdiscount\b"),
    ("subtotal", r"(?i)\bsub-?total\b"),
    ("tax", r"(?i)\b(?:tax|vat)\b"),
    ("payment_amount", r"(?i)\b(?:cash|paid|payment)\b"),
    ("change_amount", r"(?i)\bchange\b"),
    ("total", r"(?i)\b(?:grand\s+)?total(?:\s+due)?\b"),
)

CURRENCY_LABEL_RE = re.compile(r"(?i)\bcurrency\b\s*[:.]?\s*([A-Za-z]{3})\b")
INVOICE_NUMBER_RE = re.compile(
    r"(?i)\b(?:receipt|invoice)\s*(?:#|no\.?|num(?:ber)?)?\s*[:#]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9/-]{2,})"
)
SYMBOL_TO_CODE = {"$": "USD", "€": "EUR", "£": "GBP", "đ": "VND"}

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
        re.fullmatch(MONEY_TOKEN_RE, cleaned) or re.fullmatch(r"-?\d+", cleaned)
    )


def _line_has_amount(line: VisualLine) -> bool:
    return any(_is_money_token(token) for token in line.tokens)


def _rightmost_amount(line: VisualLine) -> Decimal | None:
    """Rightmost money token on the line; regex fallback for merged text."""
    for token in reversed(line.tokens):
        if _is_money_token(token):
            amount = parse_amount(token.text)
            if amount is not None:
                return amount
    match = re.search(MONEY_TOKEN_RE, _clean_money_text(line.text))
    if match:
        return parse_amount(match.group(0))
    return None


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
            if parse_date(line.text) or _rightmost_amount(line) is not None:
                continue
            self.invoice.supplier = line.text
            self._record("supplier", line.tokens[0])
            return

    def extract_invoice_number(self, lines: list[VisualLine]) -> None:
        for line in lines:
            match = re.search(INVOICE_NUMBER_RE, line.text)
            if match:
                self.invoice.invoice_number = match.group(1)
                self._record("invoice_number", line.tokens[0])
                return

    def extract_date(self, lines: list[VisualLine]) -> None:
        labelled = [line for line in lines if re.search(r"(?i)\bdate\b", line.text)]
        for line in labelled + lines:
            parsed = parse_date(line.text)
            if parsed is not None:
                self.invoice.invoice_date = parsed
                self._record("invoice_date", line.tokens[0])
                return

    def extract_currency(self, lines: list[VisualLine]) -> None:
        for line in lines:
            match = re.search(CURRENCY_LABEL_RE, line.text)
            if match:
                self.invoice.currency = match.group(1).upper()
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
        """Extract line items between the table header and the summary zone.

        With a header row (``QTY ... PRICE``), items start on the next
        line. Without one, the first three lines are treated as
        letterhead and every later amount-bearing row is a candidate.
        Amount-free rows inside the item region are description
        continuations of the next parsed row (multi-line product names).
        """
        header_index = next(
            (
                position
                for position, line in enumerate(lines)
                if re.search(HEADER_RE, line.text)
            ),
            None,
        )
        start = header_index + 1 if header_index is not None else 3
        pending_description: list[str] = []

        for line in lines[start:]:
            if re.search(SUMMARY_START_RE, line.text):
                break  # summary zone reached: item region ended
            if not _line_has_amount(line) and not QTY_PRICE_RE.search(line.text):
                pending_description.append(line.text)
                continue

            item, total_token = _parse_item_line(line, pending_description)
            pending_description.clear()
            if item is None:
                continue
            index = len(self.invoice.line_items)
            self.invoice.line_items.append(item)
            if total_token is not None:
                self._record(f"line_items[{index}].line_total", total_token)
            if line.tokens:
                self._record(f"line_items[{index}].description", line.tokens[0])

    # -- stage 7: summary amounts ----------------------------------------------

    def extract_summary(self, lines: list[VisualLine]) -> None:
        total_candidates: list[tuple[Decimal, VisualLine]] = []
        summary_zone = False

        for line in lines:
            if not summary_zone and re.search(SUMMARY_START_RE, line.text):
                summary_zone = True
            if not summary_zone:
                continue
            matched_field = None
            for field_name, pattern in SUMMARY_FIELDS:
                if re.search(pattern, line.text):
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
    line: VisualLine, pending_description: list[str]
) -> tuple[LineItem | None, OcrToken | None]:
    """Parse one item row into ``(LineItem, line_total_token)``.

    Layout contract: description tokens sit left of the ``qty x price``
    token, and the line total is the rightmost money token. Rows with no
    money token and no ``qty x price`` pattern are not items (the caller
    routes them to description continuation). Ambiguous rows (a bare
    trailing amount with no explicit quantity) keep quantity/unit_price
    as ``None`` instead of guessing.
    """
    amount_tokens = [token for token in line.tokens if _is_money_token(token)]
    if len(line.tokens) > 1:
        joined = " ".join(
            token.text for token in line.tokens if token not in amount_tokens
        )
    else:
        joined = line.text

    quantity = unit_price = None
    description_parts = list(pending_description)

    qty_match = QTY_PRICE_RE.search(joined)
    if qty_match:
        quantity = parse_amount(qty_match.group(1))
        unit_price = parse_amount(qty_match.group(2))
        prefix = joined[: qty_match.start()].strip(" -–")
        if prefix:
            description_parts.append(prefix)
    else:
        prefix = " ".join(
            token.text for token in line.tokens if token not in amount_tokens
        )
        if prefix:
            description_parts.append(prefix)

    description = " ".join(part for part in description_parts if part).strip()
    if not description and quantity is None and unit_price is None:
        return None, None

    item = LineItem(description=description, quantity=quantity, unit_price=unit_price)
    total_token = None
    if amount_tokens:
        total_token = amount_tokens[-1]
        item.line_total = parse_amount(total_token.text)
    elif qty_match:
        # Merged single-token row like "SOAP 2 x 2.50 5.00": the line
        # total is the first money token after the qty x price pattern.
        tail_match = re.search(MONEY_TOKEN_RE, _clean_money_text(joined[qty_match.end():]))
        if tail_match:
            item.line_total = parse_amount(tail_match.group(0))
            total_token = line.tokens[-1]
    return item, total_token


def extract(ocr_document: dict, source: str = "") -> ExtractionResult:
    """Extract an :class:`ExtractionResult` from one OCR JSON document."""
    items = ocr_document.get("items") or []
    return _Extractor(source=source).run(items)
