"""Local approval state and validation for the purchasing UI."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

import pandas as pd


STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "state" / "approvals.json"
EDITABLE_FIELDS = {"final_qty", "override_reason", "status"}


def _key(supplier: str, sku: str) -> str:
    return f"{supplier}|{sku}"


def _signature(row: pd.Series, as_of: pd.Timestamp) -> str:
    values = {field: str(row[field]) for field in sorted(row.index) if field not in EDITABLE_FIELDS}
    values["as_of"] = str(as_of.date())
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_state(path: Path = STATE_FILE) -> dict:
    if not path.exists():
        return {"version": 1, "orders": {}}
    with path.open(encoding="utf-8") as source:
        state = json.load(source)
    if state.get("version") != 1 or not isinstance(state.get("orders"), dict):
        raise ValueError(f"Invalid approval state: {path}")
    return state


def _save_state(state: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temp:
        json.dump(state, temp, ensure_ascii=False, indent=2)
        temp_path = Path(temp.name)
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def revoke_line(supplier: str, sku: str, path: Path = STATE_FILE) -> None:
    """Editing an approved line removes its former export authorization."""
    state = load_state(path)
    if state["orders"].pop(_key(supplier, sku), None) is not None:
        _save_state(state, path)


def apply_saved(lines: pd.DataFrame, as_of: pd.Timestamp, path: Path = STATE_FILE) -> pd.DataFrame:
    """Restore only approvals belonging to this exact calculated line."""
    result = lines.copy()
    orders = load_state(path)["orders"]
    for index, row in result.iterrows():
        saved = orders.get(_key(str(row["supplier"]), str(row["sku"])))
        if saved and saved.get("signature") == _signature(row, as_of):
            result.at[index, "final_qty"] = float(saved["final_qty"])
            result.at[index, "override_reason"] = str(saved["override_reason"])
            result.at[index, "status"] = "approved"
    return result


def validate_line(row: pd.Series) -> str | None:
    try:
        qty = float(row["final_qty"])
    except (TypeError, ValueError):
        return "Укажите числовое количество."
    if not math.isfinite(qty) or qty < 0:
        return "Количество должно быть конечным и неотрицательным."
    if not math.isclose(qty, float(row["recommended_qty"]), rel_tol=0, abs_tol=1e-8):
        reason = row["override_reason"]
        if pd.isna(reason) or not str(reason).strip():
            return "Для изменения рекомендации укажите причину."
    return None


def approve_supplier(
    lines: pd.DataFrame, supplier: str, as_of: pd.Timestamp, path: Path = STATE_FILE,
) -> pd.DataFrame:
    """Approve all positive lines of one supplier after validating the whole order."""
    result = lines.copy()
    supplier_rows = result["supplier"].eq(supplier)
    problems = [
        f"{row['sku']}: {message}"
        for _, row in result.loc[supplier_rows].iterrows()
        if (message := validate_line(row))
    ]
    if problems:
        raise ValueError("\n".join(problems[:10]))
    selected = supplier_rows & result["final_qty"].gt(0)
    if not selected.any():
        raise ValueError("У поставщика нет позиций с положительным количеством.")

    state = load_state(path)
    for index, row in result.loc[selected].iterrows():
        state["orders"][_key(str(row["supplier"]), str(row["sku"]))] = {
            "signature": _signature(row, as_of),
            "final_qty": float(row["final_qty"]),
            "override_reason": str(row["override_reason"]),
        }
        result.at[index, "status"] = "approved"
    _save_state(state, path)
    return result
