"""Deterministic text parsing helpers: amounts and dates.

Rules are intentionally explicit and documented so behaviour is
reproducible; see docs/extraction-spec.md for the full rule table.
"""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CURRENCY_NOISE_RE = re.compile(r"(?i)\b(?:usd|vnd|eur|gbp|jpy)\b|[$€£¥]|đ")

# Candidate date tokens: 2026-10-25, 25/10/2026, 25.10.2026, 25 Oct 2026.
DATE_TOKEN_RE = re.compile(
    r"\d{1,4}[./-]\d{1,2}[./-]\d{2,4}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{2,4}"
)
DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%d/%m/%y",
)

# Money-like token used as a fallback for the rightmost amount on a
# merged text line: requires an explicit 2-decimal fraction so pure
# integers inside descriptions ("EGGS X12") are never mistaken for money.
MONEY_TOKEN_RE = re.compile(r"\d{1,3}(?:[.,\s]\d{3})*[.,]\d{2}")

# quantity x unit_price, e.g. "2 x 2.50" (also accepts "*" and unicode x).
QTY_PRICE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[xX×*]\s*(\d+(?:[.,]\d+)?)"
)


def normalize_text(text: str) -> str:
    """NFKC-normalize (fullwidth digits, non-breaking spaces) and collapse."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def to_decimal(number_text: str) -> Decimal | None:
    """Parse a bare numeric token like ``2``, ``2.50`` or ``2,50``."""
    cleaned = number_text.strip().replace(" ", "")
    cleaned = re.sub(CURRENCY_NOISE_RE, "", cleaned)
    if not cleaned:
        return None
    try:
        return Decimal(cleaned.replace(",", "."))
    except InvalidOperation:
        return None


def parse_amount(text: str | None) -> Decimal | None:
    r"""Parse a full cell/line as one monetary amount, or return None.

    Separator rules (deterministic):
    - both ``.`` and ``,`` present -> the later one is the decimal mark.
    - only ``,`` -> thousands if it matches ``1,234,567`` groups, else decimal.
    - only ``.`` -> thousands if it matches ``1.234.567`` groups AND is not
      a plain ``\d+.\d{1,2}`` decimal, else decimal.
    """
    if text is None:
        return None
    s = normalize_text(str(text))
    s = re.sub(CURRENCY_NOISE_RE, "", s).strip()
    if not s or not re.fullmatch(r"-?[\d.,\s]+", s):
        return None
    s = re.sub(r"\s+", "", s)

    last_dot = s.rfind(".")
    last_comma = s.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        if last_dot > last_comma:  # 1,234.56
            s = s.replace(",", "")
        else:  # 1.234,56
            s = s.replace(".", "").replace(",", ".")
    elif last_comma >= 0:
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s):  # 1,234,567
            s = s.replace(",", "")
        else:  # 12,30
            s = s.replace(",", ".")
    elif last_dot >= 0:
        if (
            re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s)
            and not re.fullmatch(r"-?\d+\.\d{1,2}", s)
        ):  # 1.234.567
            s = s.replace(".", "")
        # else: dot stays the decimal mark (1.23, 5.00)

    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_date(text: str | None) -> date | None:
    """Find and parse the first date token in ``text``.

    Format precedence follows :data:`DATE_FORMATS`; day-first
    (``%d/%m/%Y``) is tried before month-first because receipts in the
    project's target locale use day-first. Returns an ISO date or None.
    """
    if not text:
        return None
    s = normalize_text(str(text))
    for token in DATE_TOKEN_RE.findall(s) or [s]:
        token = normalize_text(token)
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(token, fmt).date()
            except ValueError:
                continue
    return None
