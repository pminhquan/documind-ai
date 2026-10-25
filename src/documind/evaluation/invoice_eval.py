"""Invoice extraction evaluation: predicted structured invoice vs labels.

Ground truth uses the same field names as the extraction output schema
(``docs/extraction-spec.md``). Comparison rules:

- ``supplier`` / ``invoice_number``: normalized strings (whitespace
  collapse; currency compared casefolded upper).
- ``invoice_date``: canonical ISO date comparison.
- monetary fields: canonical :class:`~decimal.Decimal` comparison
  (``"8.70"`` equals ``"8.7"``); unparseable values count as incorrect.
- null handling: both null -> true negative (excluded from accuracy
  denominator); GT value with null prediction -> ``missing``; null GT
  with predicted value -> ``extra``; differing values -> ``incorrect``.
  Missing predictions are never treated as correct.
- ``line_items`` are matched **by index** (explicit assumption: our
  pipeline preserves reading order; content-based matching is future
  work). Item fields use the same rules.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCALAR_FIELDS = (
    "supplier", "invoice_number", "invoice_date", "currency",
    "subtotal", "tax", "discount", "total", "payment_amount", "change_amount",
)
MONEY_FIELDS = frozenset(
    {"subtotal", "tax", "discount", "total", "payment_amount", "change_amount"}
)
LINE_ITEM_FIELDS = ("description", "quantity", "unit_price", "line_total")

MATCHED = "matched"
MISSING = "missing"
EXTRA = "extra"
INCORRECT = "incorrect"
TRUE_NEGATIVE = "true_negative"


@dataclass
class FieldOutcome:
    status: str
    expected: object = None
    predicted: object = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "expected": self.expected,
            "predicted": self.predicted,
        }


def _canonical_date(value) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        return str(value)


def _canonical_money(value) -> str | None:
    if value is None:
        return None
    try:
        return str(Decimal(str(value)))
    except InvalidOperation:
        return f"<unparseable:{value}>"


def _canonical_text(value, casefold: bool) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text.casefold() if casefold else text


def _compare_scalar(field_name, expected, predicted) -> FieldOutcome:
    if expected is None and predicted is None:
        return FieldOutcome(TRUE_NEGATIVE, None, None)
    if expected is not None and predicted is None:
        return FieldOutcome(MISSING, expected, None)
    if expected is None and predicted is not None:
        return FieldOutcome(EXTRA, None, predicted)

    if field_name == "invoice_date":
        equal = _canonical_date(expected) == _canonical_date(predicted)
    elif field_name in MONEY_FIELDS:
        # Numeric comparison: scale-insensitive (13.530 == 13.53) and
        # robust against exponent forms; unparseable values never match.
        try:
            equal = Decimal(str(expected)) == Decimal(str(predicted))
        except InvalidOperation:
            equal = False
    elif field_name == "currency":
        equal = _canonical_text(expected, True) == _canonical_text(predicted, True)
    else:
        equal = _canonical_text(expected, True) == _canonical_text(predicted, True)
    status = MATCHED if equal else INCORRECT
    return FieldOutcome(status, expected, predicted)


def _compare_line_items(expected_items, predicted_items) -> dict:
    expected_items = expected_items or []
    predicted_items = predicted_items or []
    item_outcomes = []
    matched_items = 0
    field_correct = field_total = 0

    for index in range(max(len(expected_items), len(predicted_items))):
        expected = expected_items[index] if index < len(expected_items) else None
        predicted = predicted_items[index] if index < len(predicted_items) else None
        if expected is None:
            item_outcomes.append({"index": index, "status": EXTRA})
            continue
        if predicted is None:
            item_outcomes.append({"index": index, "status": MISSING,
                                  "expected": expected})
            continue

        item_match = True
        fields = {}
        for item_field in LINE_ITEM_FIELDS:
            expected_value = expected.get(item_field)
            predicted_value = predicted.get(item_field)
            if item_field == "description":
                outcome = _compare_scalar(
                    "description", expected_value, predicted_value
                )
            else:
                outcome = _compare_scalar(
                    item_field,
                    None if expected_value is None else str(expected_value),
                    None if predicted_value is None else str(predicted_value),
                )
            fields[item_field] = outcome.to_dict()
            if outcome.status in (MATCHED, TRUE_NEGATIVE):
                if outcome.status == MATCHED:
                    field_correct += 1
            else:
                item_match = False
            if outcome.status != TRUE_NEGATIVE:
                field_total += 1
        if item_match:
            matched_items += 1
        item_outcomes.append({"index": index, "status":
                              MATCHED if item_match else INCORRECT,
                              "fields": fields})

    return {
        "expected_items": len(expected_items),
        "predicted_items": len(predicted_items),
        "items_matched": matched_items,
        "item_field_correct": field_correct,
        "item_field_total": field_total,
        "missing_items": sum(1 for o in item_outcomes if o["status"] == MISSING),
        "extra_items": sum(1 for o in item_outcomes if o["status"] == EXTRA),
        "items": item_outcomes,
        "matching_assumption": "index-based (reading order preserved)",
    }


@dataclass
class InvoiceDocumentResult:
    id: str
    field_outcomes: dict = field(default_factory=dict)
    line_items: dict = field(default_factory=dict)
    matched: int = 0
    applicable: int = 0  # fields where at least one side is non-null
    accuracy: float | None = None


def evaluate_document(prediction_path: Path, ground_truth_path: Path) -> dict:
    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    if not isinstance(ground_truth, dict) or "invoice" not in ground_truth:
        raise ValueError(f"Invoice ground truth needs 'invoice': {ground_truth_path}")
    prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
    if not isinstance(prediction, dict) or "invoice" not in prediction:
        raise ValueError(f"Invoice prediction needs 'invoice': {prediction_path}")

    expected_invoice = ground_truth["invoice"] or {}
    predicted_invoice = prediction["invoice"] or {}

    outcomes: dict[str, FieldOutcome] = {}
    matched = applicable = 0
    for field_name in SCALAR_FIELDS:
        outcome = _compare_scalar(
            field_name,
            expected_invoice.get(field_name),
            predicted_invoice.get(field_name),
        )
        outcomes[field_name] = outcome
        if outcome.status != TRUE_NEGATIVE:
            applicable += 1
            if outcome.status == MATCHED:
                matched += 1

    line_items = _compare_line_items(
        expected_invoice.get("line_items"), predicted_invoice.get("line_items")
    )

    accuracy = (matched / applicable) if applicable else None
    return {
        "fields": {name: outcome.to_dict() for name, outcome in outcomes.items()},
        "summary": {
            "matched": matched,
            "applicable": applicable,
            "missing": sum(1 for o in outcomes.values() if o.status == MISSING),
            "extra": sum(1 for o in outcomes.values() if o.status == EXTRA),
            "incorrect": sum(1 for o in outcomes.values() if o.status == INCORRECT),
            "true_negatives": sum(
                1 for o in outcomes.values() if o.status == TRUE_NEGATIVE
            ),
            "accuracy": accuracy,
        },
        "line_items": line_items,
    }


def evaluate_manifest(manifest) -> dict:
    documents = []
    total_matched = total_applicable = 0
    accuracies: list[float] = []
    item_field_correct = item_field_total = 0
    tables_missing_items = tables_extra_items = 0

    for entry in manifest.entries:
        outcome = evaluate_document(entry.prediction, entry.ground_truth)
        summary = outcome["summary"]
        documents.append({"id": entry.id, **outcome})
        total_matched += summary["matched"]
        total_applicable += summary["applicable"]
        if summary["accuracy"] is not None:
            accuracies.append(summary["accuracy"])
        line_items = outcome["line_items"]
        item_field_correct += line_items["item_field_correct"]
        item_field_total += line_items["item_field_total"]
        tables_missing_items += line_items["missing_items"]
        tables_extra_items += line_items["extra_items"]

    macro = (sum(accuracies) / len(accuracies)) if accuracies else None
    micro = (total_matched / total_applicable) if total_applicable else None
    return {
        "task": "invoice",
        "documents": documents,
        "aggregate": {
            "micro_field_accuracy": micro,
            "macro_field_accuracy": macro,
            "fields_matched": total_matched,
            "fields_applicable": total_applicable,
            "item_field_accuracy": (
                item_field_correct / item_field_total if item_field_total else None
            ),
            "item_field_correct": item_field_correct,
            "item_field_total": item_field_total,
            "missing_line_items": tables_missing_items,
            "extra_line_items": tables_extra_items,
        },
        "conventions": {
            "null_handling": (
                "both null = true_negative (excluded); GT value + null "
                "prediction = missing (never counted as correct)"
            ),
            "canonicalization": (
                "dates as ISO dates; money as Decimal (scale-insensitive); "
                "text whitespace-collapsed casefolded"
            ),
            "line_items": "index-based matching, reading order assumed",
        },
    }
