"""Structural validation shared by the invoice and table evaluators (D-22).

Malformed prediction or ground-truth structures must fail as clean
``ValueError`` input errors before scoring, never as ``AttributeError``,
``KeyError`` or ``TypeError`` escaping the CLI error contract.

Null or missing containers are treated as empty: this preserves the
invoice/line-items/truth-cells behavior and makes a null predicted
``cells`` container equivalent to an empty list. A present non-null
container must have the documented shape. Predicted cell *coordinates*
are deliberately not validated here: the table metrics intentionally
score non-integer, out-of-shape and duplicate coordinates as unexpected
predicted cells.
"""

from pathlib import Path


def require_object(value, *, role: str, field: str, path: Path,
                   allow_none: bool = False) -> dict:
    if value is None:
        if allow_none:
            return {}
        raise ValueError(f"{role} '{field}' must be an object: {path}")
    if not isinstance(value, dict):
        suffix = " or null" if allow_none else ""
        raise ValueError(f"{role} '{field}' must be an object{suffix}: {path}")
    return value


def require_list(value, *, role: str, field: str, path: Path,
                 allow_none: bool = True) -> list:
    if value is None:
        if allow_none:
            return []
        raise ValueError(f"{role} '{field}' must be a list: {path}")
    if not isinstance(value, list):
        suffix = " or null" if allow_none else ""
        raise ValueError(f"{role} '{field}' must be a list{suffix}: {path}")
    return value


def require_object_list(value, *, role: str, field: str, path: Path,
                        allow_none: bool = True) -> list[dict]:
    items = require_list(
        value, role=role, field=field, path=path, allow_none=allow_none
    )
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{role} '{field}[{index}]' must be an object: {path}")
    return items


def require_list_of_lists(value, *, role: str, field: str, path: Path,
                          allow_none: bool = True) -> list[list]:
    rows = require_list(
        value, role=role, field=field, path=path, allow_none=allow_none
    )
    for index, row in enumerate(rows):
        if not isinstance(row, list):
            raise ValueError(f"{role} '{field}[{index}]' must be a list: {path}")
    return rows


def require_non_negative_int(value, *, role: str, field: str, path: Path) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{role} '{field}' must be a non-negative integer: {path}"
        )
    return value
