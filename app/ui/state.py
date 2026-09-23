"""Local approval state and validation for the purchasing UI."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
from functools import wraps
from pathlib import Path

import pandas as pd


STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "state" / "approvals.json"
EDITABLE_FIELDS = {"final_qty", "override_reason", "status"}
_STATE_LOCK = threading.RLock()


def synchronized(function):
    """Serialize read-modify-write across sessions of the local Streamlit server."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _STATE_LOCK:
            return function(*args, **kwargs)
    return wrapped


def clean_reason(value: object) -> str:
    """Preserve missing cells, including legacy stringified nulls, as empty."""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"<na>", "nan", "none"} else text


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


@synchronized
def revoke_line(supplier: str, sku: str, path: Path = STATE_FILE) -> None:
    """Editing an approved line removes its former export authorization."""
    state = load_state(path)
    if state["orders"].pop(_key(supplier, sku), None) is not None:
        _save_state(state, path)


@synchronized
def apply_saved(lines: pd.DataFrame, as_of: pd.Timestamp, path: Path = STATE_FILE) -> pd.DataFrame:
    """Restore only approvals belonging to this exact calculated line."""
    result = lines.copy()
    orders = load_state(path)["orders"]
    for index, row in result.iterrows():
        saved = orders.get(_key(str(row["supplier"]), str(row["sku"])))
        if saved and saved.get("signature") == _signature(row, as_of):
            candidate = row.copy()
            candidate["final_qty"] = saved["final_qty"]
            candidate["override_reason"] = clean_reason(saved["override_reason"])
            if validate_line(candidate):
                continue
            result.at[index, "final_qty"] = float(saved["final_qty"])
            result.at[index, "override_reason"] = candidate["override_reason"]
            result.at[index, "status"] = "approved"
    return result


def validate_line(row: pd.Series) -> str | None:
    try:
        qty = float(row["final_qty"])
    except (TypeError, ValueError):
        return "Укажите числовое количество."
    if not math.isfinite(qty) or qty < 0:
        return "Количество должно быть конечным и неотрицательным."
    reason = clean_reason(row["override_reason"])
    if not math.isclose(qty, float(row["recommended_qty"]), rel_tol=0, abs_tol=1e-8):
        if not reason:
            return "Для изменения рекомендации укажите причину."
    # Estimated stock is acknowledged once for the supplier in the UI; actual
    # missing/invalid input still needs a per-line review result or exclusion.
    flags = str(row.get("flags", "")).replace("needs_review:estimated_stock", "")
    if qty > 0 and "needs_review" in flags and not reason:
        return "Проверьте данные и укажите результат проверки в причине либо исключите позицию."
    return None


@synchronized
def approve_supplier(
    lines: pd.DataFrame, supplier: str, as_of: pd.Timestamp, path: Path = STATE_FILE,
) -> pd.DataFrame:
    """Persist the whole supplier decision, including explicitly excluded rows."""
    result = lines.copy()
    supplier_rows = result["supplier"].eq(supplier)
    problems = [
        f"{row['sku']}: {message}"
        for _, row in result.loc[supplier_rows].iterrows()
        if (message := validate_line(row))
    ]
    if problems:
        raise ValueError("\n".join(problems[:10]))
    selected = supplier_rows
    if not selected.any():
        raise ValueError("У поставщика нет позиций.")

    state = load_state(path)
    for index, row in result.loc[selected].iterrows():
        state["orders"][_key(str(row["supplier"]), str(row["sku"]))] = {
            "signature": _signature(row, as_of),
            "final_qty": float(row["final_qty"]),
            "override_reason": clean_reason(row["override_reason"]),
            "approved_at": pd.Timestamp.now(tz="UTC").isoformat(),
        }
        result.at[index, "status"] = "approved"
    _save_state(state, path)
    return result
