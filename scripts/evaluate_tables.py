"""Evaluate ruled-table recognition on the synthetic samples.

Runs the full pipeline (real PaddleOCR) on each generated table image
and compares against the committed ground-truth matrices:

- structural correctness: detected (rows, columns) equal the truth
- exact cell-text agreement: normalized (whitespace-collapsed, casefolded)
  cell text equality, empty cells included

These numbers describe synthetic, clean, axis-aligned inputs only and
must not be read as real-world accuracy.

Usage:
    python scripts/evaluate_tables.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from documind.tables.exporters import table_matrix  # noqa: E402
from documind.tables.pipeline import recognize_tables  # noqa: E402

SAMPLES = ["table_products", "table_gaps", "table_large"]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "tables"


def normalize(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def evaluate_one(name: str) -> dict:
    truth = json.loads((FIXTURES / f"{name}.truth.json").read_text(encoding="utf-8"))
    result = recognize_tables(REPO_ROOT / "assets" / "samples" / f"{name}.png")
    warnings = list(result.warnings)

    if len(result.tables) != 1:
        return {
            "name": name,
            "structure_ok": False,
            "cell_exact_rate": 0.0,
            "cells_total": truth["rows"] * truth["columns"],
            "cells_matched": 0,
            "details": [f"expected 1 table, got {len(result.tables)}"],
            "warnings": warnings,
        }

    table = result.tables[0]
    structure_ok = (
        table.rows == truth["rows"] and table.columns == truth["columns"]
    )
    predicted = table_matrix(table)
    expected = truth["cells"]

    cells_total = truth["rows"] * truth["columns"]
    mismatches = []
    matched = 0
    if structure_ok:
        for r in range(truth["rows"]):
            for c in range(truth["columns"]):
                if normalize(predicted[r][c]) == normalize(expected[r][c]):
                    matched += 1
                else:
                    mismatches.append(
                        f"({r},{c}) expected {expected[r][c]!r}, got {predicted[r][c]!r}"
                    )

    return {
        "name": name,
        "structure_ok": structure_ok,
        "detected_shape": [table.rows, table.columns],
        "cell_exact_rate": round(matched / cells_total, 4),
        "cells_total": cells_total,
        "cells_matched": matched,
        "details": mismatches,
        "warnings": warnings + table.warnings,
    }


def main() -> None:
    results = [evaluate_one(name) for name in SAMPLES]
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
