"""Character/word error rate metrics based on Levenshtein edit distance.

Conventions (documented in docs/evaluation-spec.md):

- Normalization: Unicode NFKC; casefold and whitespace collapsing are
  configurable (both on by default).
- ``empty`` reference: CER/WER are ``0.0`` when both reference and
  hypothesis are empty, and ``1.0`` when only the reference is empty
  (the hypothesis is fully wrong by definition). This is an explicit
  convention, not a statistical claim.
- Micro-aggregation across documents: total edits / total reference
  length (words for WER, characters for CER).
- Model confidence is never used as an accuracy metric.
"""

import re
import unicodedata
from dataclasses import dataclass, field

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(
    text: str, *, casefold: bool = True, collapse_whitespace: bool = True
) -> str:
    """NFKC-normalize ``text`` with configurable case/whitespace handling."""
    value = unicodedata.normalize("NFKC", str(text))
    if collapse_whitespace:
        value = _WHITESPACE_RE.sub(" ", value).strip()
    if casefold:
        value = value.casefold()
    return value


def levenshtein_distance(reference: str, hypothesis: str) -> int:
    """Edit distance (insert/delete/substitute, each cost 1)."""
    if reference == hypothesis:
        return 0
    if not reference:
        return len(hypothesis)
    if not hypothesis:
        return len(reference)

    previous = list(range(len(hypothesis) + 1))
    for i, ref_char in enumerate(reference, start=1):
        current = [i]
        for j, hyp_char in enumerate(hypothesis, start=1):
            cost = 0 if ref_char == hyp_char else 1
            current.append(
                min(
                    previous[j] + 1,        # deletion
                    current[j - 1] + 1,     # insertion
                    previous[j - 1] + cost, # substitution / match
                )
            )
        previous = current
    return previous[-1]


def edit_operations(
    reference: str, hypothesis: str
) -> list[dict[str, str | int]]:
    """Non-match edit operations from a Levenshtein backtrace.

    Each operation is ``{"op": "substitute|insert|delete",
    "position": int, "reference": str|None, "hypothesis": str|None}``
    where ``position`` indexes into the reference string. Practical for
    error-examples lists, not for large-scale statistics.
    """
    rows = len(reference) + 1
    cols = len(hypothesis) + 1
    table = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        table[i][0] = i
    for j in range(cols):
        table[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
            table[i][j] = min(
                table[i - 1][j] + 1,
                table[i][j - 1] + 1,
                table[i - 1][j - 1] + cost,
            )

    operations: list[dict[str, str | int]] = []
    i, j = len(reference), len(hypothesis)
    while i > 0 or j > 0:
        if i > 0 and j > 0 and reference[i - 1] == hypothesis[j - 1]:
            i, j = i - 1, j - 1
            continue
        if i > 0 and j > 0 and table[i][j] == table[i - 1][j - 1] + 1:
            operations.append(
                {"op": "substitute", "position": i - 1,
                 "reference": reference[i - 1], "hypothesis": hypothesis[j - 1]}
            )
            i, j = i - 1, j - 1
        elif j > 0 and table[i][j] == table[i][j - 1] + 1:
            operations.append(
                {"op": "insert", "position": i,
                 "reference": None, "hypothesis": hypothesis[j - 1]}
            )
            j -= 1
        else:
            operations.append(
                {"op": "delete", "position": i - 1,
                 "reference": reference[i - 1], "hypothesis": None}
            )
            i -= 1
    operations.reverse()
    return operations


@dataclass
class TextMetricResult:
    """Per-document OCR text quality result."""

    edits: int
    reference_length: int
    hypothesis_length: int
    error_rate: float | None
    operations: list[dict[str, str | int]] = field(default_factory=list)


def error_rate(
    reference: str, hypothesis: str, unit: str, *, casefold: bool = True,
    collapse_whitespace: bool = True,
) -> TextMetricResult:
    """CER (``unit="chars"``) or WER (``unit="words"``) for one document."""
    if unit not in ("chars", "words"):
        raise ValueError(f"unknown unit {unit!r}")
    reference_norm = normalize_text(
        reference, casefold=casefold, collapse_whitespace=collapse_whitespace
    )
    hypothesis_norm = normalize_text(
        hypothesis, casefold=casefold, collapse_whitespace=collapse_whitespace
    )
    ref_units = list(reference_norm) if unit == "chars" else reference_norm.split()
    hyp_units = list(hypothesis_norm) if unit == "chars" else hypothesis_norm.split()

    if not ref_units and not hyp_units:
        return TextMetricResult(0, 0, len(hyp_units), 0.0)
    if not ref_units:
        # Explicit convention: nothing to match against; fully wrong.
        return TextMetricResult(
            len(hyp_units), 0, len(hyp_units), 1.0,
            [{"op": "insert", "position": 0,
              "reference": None, "hypothesis": hypothesis_norm}],
        )

    distance = levenshtein_distance("".join(ref_units), "".join(hyp_units)) \
        if unit == "chars" else levenshtein_distance(ref_units, hyp_units)
    return TextMetricResult(distance, len(ref_units), len(hyp_units),
                            distance / len(ref_units))


def micro_aggregate(results: list[TextMetricResult]) -> dict:
    """Sum-of-edits over sum-of-reference-lengths across documents."""
    total_edits = sum(r.edits for r in results)
    total_ref = sum(r.reference_length for r in results)
    rate = (total_edits / total_ref) if total_ref else (
        0.0 if total_edits == 0 else 1.0
    )
    return {
        "total_edits": total_edits,
        "total_reference_units": total_ref,
        "error_rate": rate,
    }
