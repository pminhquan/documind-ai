"""Deterministic text parsing helpers: amounts and dates.

Rules are intentionally explicit and documented so behaviour is
reproducible; see docs/extraction-spec.md for the full rule table.
"""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Currency noise stripped before amount parsing. The Vietnamese đồng
# markers (đ, ₫, VNĐ) match only as STANDALONE tokens — stripping every
# "đ" would corrupt words like "đơn giá".
CURRENCY_NOISE_RE = re.compile(
    r"(?i)\b(?:usd|vnd|vnđ|eur|gbp|jpy)\b|[$€£¥]|(?<![\w])[đ₫](?![\w])"
)
# The đồng signs need their own prefix strip because the standalone-token
# lookarounds above intentionally reject "₫125.000" (sign attached to digits).
CURRENCY_PREFIX_RE = re.compile(r"^[$€£¥đ₫]+")

# Candidate date tokens: 2026-10-25, 25/10/2026, 25.10.2026, 25 Oct 2026.
DATE_TOKEN_RE = re.compile(
    r"\d{1,4}[./-]\d{1,2}[./-]\d{2,4}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{2,4}"
)
# Day-first before month-first (target locale); two-digit years follow
# their four-digit sibling per separator. Textual month names are NOT
# parsed with %b/%B here — those are locale-sensitive (LC_TIME), so they
# are resolved through the explicit English MONTHS table below (D-20).
DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d-%m-%y",
    "%d.%m.%y",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%d/%m/%y",
)

# Explicit English month names (D-20): deterministic regardless of the
# host LC_TIME or the locale active when _strptime was first imported.
# Same pivot as %y: 00-68 -> 2000-2068, 69-99 -> 1969-1999.
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}
TEXT_DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{2,4})")

# Money-like token used as a fallback for the rightmost amount on a
# merged text line. Ungrouped integer digits are unbounded (1234.56,
# 12345.67, 1234567,89 all match completely); the lookarounds reject
# partial matches inside malformed runs like 12.34.56.78 — such tokens
# yield no candidate instead of a silently reinterpreted value. A single
# leading minus is part of the value (refund/credit totals, D-29): it
# binds when it directly precedes the digits; a hyphen attached to
# letters (`A-12.50`) is ambiguous noise and matches nothing.
MONEY_TOKEN_RE = re.compile(
    r"(?<![\d.,])-?\d+(?:[.,\s]\d{3})*[.,]\d{2}(?![\d.,])"
)

# Merged-text amount scanner: every shape the token-level classifier
# accepts (decimal fraction, thousands-grouped, bare integer), matched
# with the same lookaround discipline. Used when a label and its amount
# share ONE OCR region ("TONG CONG: 97.200") so no whole token is an
# amount; integer VND totals must not vanish the way MONEY_TOKEN_RE
# (2-digit fraction required) would. The grouped branch accepts space
# separators (consistent with the decimal branch), and bare integers
# need >= 2 digits so a stray single digit after the amount ("97.20 0")
# cannot win the rightmost-match rule. A single leading minus binds only
# when it directly precedes the digits and the preceding character is
# not a word character — whitespace, line start, or punctuation such as
# the label colon ("TOTAL:-5.00"); a hyphen attached to letters
# ("A-12.50") is identifier noise and matches nothing. A spaced minus
# ("- 5.00") never binds. Trade-off: a bare multi-digit run such as a
# year can match when the fallback fires — summary/item rows are
# amount-dominated text, and the arithmetic validation surfaces a wrong
# value instead of it appearing silently.
MERGED_MONEY_RE = re.compile(
    r"(?<![\d.,])(?<!\w-)(?:(?<!\w)-)?(?:\d+(?:[.,\s]\d{3})*[.,]\d{2}"
    r"|\d{1,3}(?:[.,\s]\d{3})+|\d{2,})(?![\d.,])"
)

# quantity x unit_price, e.g. "2 x 2.50" (also accepts "*" and unicode x).
QTY_PRICE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[xX×*]\s*(\d+(?:[.,]\d+)?)"
)


def normalize_text(text: str) -> str:
    """NFKC-normalize (fullwidth digits, non-breaking spaces) and collapse."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


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
    s = CURRENCY_PREFIX_RE.sub("", normalize_text(str(text))).strip()
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


def _parse_text_date(token: str) -> date | None:
    """Parse a ``25 Oct 2026``-shaped token via the explicit MONTHS table.

    Two-digit years follow the same pivot as ``%y`` (00-68 -> 2000s).
    Returns None for unknown months or impossible dates.
    """
    match = TEXT_DATE_RE.fullmatch(token)
    if match is None:
        return None
    day_text, month_text, year_text = match.groups()
    month = MONTHS.get(month_text.lower())
    if month is None:
        return None
    year = int(year_text)
    if year < 100:
        year = 2000 + year if year < 69 else 1900 + year
    try:
        return date(year, month, int(day_text))
    except ValueError:
        return None


def parse_date(text: str | None) -> date | None:
    """Find and parse the first date token in ``text``.

    Numeric format precedence follows :data:`DATE_FORMATS`; day-first
    (``%d/%m/%Y``) is tried before month-first because receipts in the
    project's target locale use day-first. Textual month names resolve
    through the explicit English :data:`MONTHS` table, never through the
    locale-sensitive ``%b``/``%B`` (D-20). Returns an ISO date or None.
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
        parsed = _parse_text_date(token)
        if parsed is not None:
            return parsed
    return None
