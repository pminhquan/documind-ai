"""Table recognition evaluation against structural ground truth.

Ground truth reuses the M3A truth format:
``{"rows": int, "columns": int, "cells": [[text, ...], ...]}``;
predictions are ``documind-table`` JSON documents.

Tables are matched **by index** in reading order (explicit assumption).
A completely missed table contributes its full expected cell count as
unmatched cells, so it can never score as a perfect document.
"""

import json
import re
from pathlib import Path

from .validation import (
    require_list,
    require_list_of_lists,
    require_non_negative_int,
    require_object_list,
)

WHITESPACE_RE = re.compile(r"\s+")


def _normalize(value) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "")).strip().casefold()


def _predicted_matrix(table: dict, rows: int, columns: int,
                      issues: list[str]) -> tuple[list[list[str | None]], int]:
    """Read a predicted table into an expected-shape text grid.

    Returns the grid plus the count of *unexpected* predicted cells:
    non-integer/missing coordinates, coordinates outside the expected
    shape, and duplicate coordinates. The first write to a coordinate
    wins; every later occurrence is unexpected content and is counted
    (never silently overwritten or ignored).
    """
    matrix: list[list[str | None]] = [[None] * columns for _ in range(rows)]
    unexpected = 0
    for cell in table.get("cells") or []:
        row_index = cell.get("row_index")
        column_index = cell.get("column_index")
        # bool is a subclass of int; "true"/"false" indices are not
        # coordinates and must not silently address cells.
        if not (isinstance(row_index, int) and not isinstance(row_index, bool)
                and isinstance(column_index, int)
                and not isinstance(column_index, bool)):
            unexpected += 1
            issues.append(f"cell with non-integer indices counted as extra: {cell!r}")
            continue
        if 0 <= row_index < rows and 0 <= column_index < columns:
            if matrix[row_index][column_index] is not None:
                unexpected += 1
                issues.append(
                    f"duplicate predicted cell ({row_index}, {column_index}) "
                    f"counted as extra: {cell.get('text')!r} "
                    f"(kept {matrix[row_index][column_index]!r})"
                )
                continue
            matrix[row_index][column_index] = str(cell.get("text") or "")
        else:
            unexpected += 1
            issues.append(
                f"cell ({row_index}, {column_index}) outside expected shape "
                f"{rows}x{columns} counted as extra"
            )
    return matrix, unexpected


def _compare_table(expected: dict, predicted: dict) -> dict:
    rows, columns = expected["rows"], expected["columns"]
    issues: list[str] = []
    predicted_matrix, unexpected = _predicted_matrix(predicted, rows, columns, issues)
    expected_cells = expected.get("cells") or []

    structure_ok = predicted.get("rows") == rows and predicted.get("columns") == columns

    matched = non_empty_matched = empty_preserved = 0
    missing = extra = incorrect = 0
    non_empty_total = empty_total = 0

    for row in range(rows):
        for column in range(columns):
            expected_text = (
                expected_cells[row][column]
                if row < len(expected_cells) and column < len(expected_cells[row])
                else ""
            )
            predicted_text = predicted_matrix[row][column]
            if predicted_text is None:
                missing += 1
                # Same canonicalizer as the present-prediction branch so a
                # JSON null ground-truth cell counts as EMPTY either way
                # (str(None).strip() is truthy "None" and would skew the
                # non-empty/empty denominators depending on the prediction).
                if _normalize(expected_text):
                    non_empty_total += 1
                else:
                    empty_total += 1
                continue
            expected_norm = _normalize(expected_text)
            predicted_norm = _normalize(predicted_text)
            if expected_norm == "":
                empty_total += 1
                if predicted_norm == "":
                    matched += 1
                    empty_preserved += 1
                else:
                    extra += 1
            else:
                non_empty_total += 1
                if predicted_norm == "":
                    missing += 1
                elif predicted_norm == expected_norm:
                    matched += 1
                    non_empty_matched += 1
                else:
                    incorrect += 1

    total = rows * columns
    extra += unexpected  # unplaceable/duplicate predictions are pure extra
    # Precision-aware companion to cell_exact_agreement: everything the
    # predictor emitted but should not have (content on empty expected
    # cells, out-of-shape, duplicate, invalid) lowers it. None when the
    # prediction emitted no placeable cells at all.
    precision_denominator = matched + incorrect + extra
    return {
        "prediction_precision": (
            matched / precision_denominator if precision_denominator else None
        ),
        "structure_ok": structure_ok,
        "expected_shape": [rows, columns],
        "predicted_shape": [predicted.get("rows"), predicted.get("columns")],
        "cells_total": total,
        "cells_matched": matched,
        "cell_exact_agreement": (matched / total) if total else None,
        "non_empty_cells_total": non_empty_total,
        "non_empty_cells_matched": non_empty_matched,
        "non_empty_agreement": (
            non_empty_matched / non_empty_total if non_empty_total else None
        ),
        "empty_cells_total": empty_total,
        "empty_cells_preserved": empty_preserved,
        "empty_cell_preservation": (
            empty_preserved / empty_total if empty_total else None
        ),
        "missing_cells": missing,
        "extra_cells": extra,
        "incorrect_cells": incorrect,
        "issues": issues,
    }


def _validate_tables(tables: list, *, role: str, path: Path,
                     truth: bool) -> None:
    """Validate every table, including ones that are not compared by index."""
    for index, table in enumerate(tables):
        field = f"tables[{index}]"
        if not isinstance(table, dict):
            raise ValueError(f"{role} '{field}' must be an object: {path}")
        for dimension in ("rows", "columns"):
            require_non_negative_int(
                table.get(dimension), role=role,
                field=f"{field}.{dimension}", path=path,
            )
        cells = table.get("cells")
        if truth:
            require_list_of_lists(
                cells, role=role, field=f"{field}.cells", path=path,
                allow_none=True,
            )
        else:
            require_object_list(
                cells, role=role, field=f"{field}.cells", path=path,
                allow_none=True,
            )


def evaluate_document(prediction_path: Path, ground_truth_path: Path) -> dict:
    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    if not isinstance(ground_truth, dict) or "tables" not in ground_truth:
        raise ValueError(f"Table ground truth needs 'tables': {ground_truth_path}")
    prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
    if not isinstance(prediction, dict) or "tables" not in prediction:
        raise ValueError(f"Table prediction needs 'tables': {prediction_path}")

    expected_tables = require_list(
        ground_truth["tables"], role="Table ground truth", field="tables",
        path=ground_truth_path, allow_none=True,
    )
    predicted_tables = require_list(
        prediction["tables"], role="Table prediction", field="tables",
        path=prediction_path, allow_none=True,
    )
    _validate_tables(expected_tables, role="Table ground truth",
                     path=ground_truth_path, truth=True)
    _validate_tables(predicted_tables, role="Table prediction",
                     path=prediction_path, truth=False)
    pair_count = min(len(expected_tables), len(predicted_tables))

    comparisons = [
        {"index": index, **_compare_table(expected_tables[index],
                                          predicted_tables[index])}
        for index in range(pair_count)
    ]
    missed = len(expected_tables) - pair_count
    extra = len(predicted_tables) - pair_count

    # Unmatched tables must still count against the document: every cell
    # of a missed expected table is an unmatched (missing) cell, and an
    # unpredicted extra table contributes its cells as extra.
    def _cell_totals(table: dict) -> tuple[int, int, int]:
        rows, columns = table["rows"], table["columns"]
        non_empty = sum(
            1
            for row in table.get("cells") or []
            for value in row
            if str(value or "").strip()
        )
        total = rows * columns
        return total, non_empty, total - non_empty

    missed_cell_counts = [_cell_totals(table) for table in expected_tables[pair_count:]]
    extra_cell_counts = [_cell_totals(table) for table in predicted_tables[pair_count:]]
    missed_cells = sum(count[0] for count in missed_cell_counts)
    missed_non_empty = sum(count[1] for count in missed_cell_counts)
    missed_empty = sum(count[2] for count in missed_cell_counts)
    extra_cells_from_tables = sum(count[0] for count in extra_cell_counts)

    # Document-level strict metrics: expected cells include completely
    # missed tables, and extra cells include completely extra tables, so
    # both directions of failure lower the strict agreement.
    doc_matched = sum(c["cells_matched"] for c in comparisons)
    doc_incorrect = sum(c["incorrect_cells"] for c in comparisons)
    doc_extra = sum(c["extra_cells"] for c in comparisons) + extra_cells_from_tables
    doc_expected = sum(c["cells_total"] for c in comparisons) + missed_cells
    precision_denominator = doc_matched + doc_incorrect + doc_extra
    strict_denominator = doc_expected + doc_extra

    return {
        "tables_expected": len(expected_tables),
        "tables_predicted": len(predicted_tables),
        "tables_matched_pairs": pair_count,
        "tables_missed": missed,
        "tables_extra": extra,
        "document_metrics": {
            "cells_matched": doc_matched,
            "cells_expected": doc_expected,
            "extra_cells_total": doc_extra,
            "incorrect_cells": doc_incorrect,
            "missing_cells": sum(c["missing_cells"] for c in comparisons)
            + missed_cells,
            "prediction_precision": (
                doc_matched / precision_denominator
                if precision_denominator else None
            ),
            "strict_cell_agreement": (
                doc_matched / strict_denominator if strict_denominator else None
            ),
        },
        "missed_tables_cells": missed_cells,
        "missed_tables_non_empty_cells": missed_non_empty,
        "missed_tables_empty_cells": missed_empty,
        "extra_tables_cells": extra_cells_from_tables,
        "comparisons": comparisons,
    }


def evaluate_manifest(manifest) -> dict:
    documents = []
    totals = {
        "tables_expected": 0, "tables_predicted": 0, "tables_matched_pairs": 0,
        "tables_missed": 0, "tables_extra": 0, "cells_total": 0,
        "cells_matched": 0,
        "non_empty_cells_total": 0, "non_empty_cells_matched": 0,
        "empty_cells_total": 0, "empty_cells_preserved": 0,
        "missing_cells": 0, "extra_cells": 0, "incorrect_cells": 0,
        "structure_ok_documents": 0,
    }

    for entry in manifest.entries:
        outcome = evaluate_document(entry.prediction, entry.ground_truth)
        for key in ("tables_expected", "tables_predicted", "tables_matched_pairs",
                    "tables_missed", "tables_extra"):
            totals[key] += outcome[key]
        # Document metrics already fold missed/extra table cells in, so
        # summing them cannot double-count.
        doc_metrics = outcome["document_metrics"]
        totals["cells_total"] += doc_metrics["cells_expected"]
        totals["cells_matched"] += doc_metrics["cells_matched"]
        totals["extra_cells"] += doc_metrics["extra_cells_total"]
        totals["incorrect_cells"] += doc_metrics["incorrect_cells"]
        totals["missing_cells"] += doc_metrics["missing_cells"]
        totals["non_empty_cells_total"] += (
            sum(c["non_empty_cells_total"] for c in outcome["comparisons"])
            + outcome["missed_tables_non_empty_cells"]
        )
        totals["non_empty_cells_matched"] += sum(
            c["non_empty_cells_matched"] for c in outcome["comparisons"]
        )
        totals["empty_cells_total"] += (
            sum(c["empty_cells_total"] for c in outcome["comparisons"])
            + outcome["missed_tables_empty_cells"]
        )
        totals["empty_cells_preserved"] += sum(
            c["empty_cells_preserved"] for c in outcome["comparisons"]
        )
        doc_structure_ok = True
        for comparison in outcome["comparisons"]:
            if not comparison["structure_ok"]:
                doc_structure_ok = False
        # A missed table means structure cannot be considered correct.
        if outcome["tables_missed"] or outcome["tables_extra"]:
            doc_structure_ok = False
        if doc_structure_ok and outcome["tables_expected"] > 0:
            totals["structure_ok_documents"] += 1
        documents.append({"id": entry.id, **outcome})

    return {
        "task": "table",
        "documents": documents,
        "aggregate": {
            **totals,
            "cell_exact_agreement": (
                totals["cells_matched"] / totals["cells_total"]
                if totals["cells_total"] else None
            ),
            "non_empty_agreement": (
                totals["non_empty_cells_matched"] / totals["non_empty_cells_total"]
                if totals["non_empty_cells_total"] else None
            ),
            "empty_cell_preservation": (
                totals["empty_cells_preserved"] / totals["empty_cells_total"]
                if totals["empty_cells_total"] else None
            ),
            # Strict companion metrics: precision penalizes everything the
            # predictor emitted but should not have; strict agreement also
            # puts extra predictions in the denominator.
            "prediction_precision": (
                totals["cells_matched"]
                / (totals["cells_matched"] + totals["incorrect_cells"]
                   + totals["extra_cells"])
                if totals["cells_matched"] + totals["incorrect_cells"]
                + totals["extra_cells"] else None
            ),
            "strict_cell_agreement": (
                totals["cells_matched"]
                / (totals["cells_total"] + totals["extra_cells"])
                if totals["cells_total"] + totals["extra_cells"] else None
            ),
        },
        "conventions": {
            "table_matching": "index-based in reading order",
            "missed_tables": (
                "a missed table contributes all its expected cells as "
                "unmatched, so it never scores as perfect"
            ),
            "normalization": "whitespace collapse + casefold per cell",
        },
    }
