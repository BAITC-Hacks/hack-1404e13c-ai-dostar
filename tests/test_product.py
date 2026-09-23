"""Approval and export behavior independent of Streamlit session state."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.export import to_csv, to_table, to_xlsx
from app.mock import mock_order_lines
from app.ui.state import apply_saved, approve_supplier, revoke_line, clean_reason, validate_line


def _sample():
    lines = mock_order_lines(8)
    lines["supplier"] = "IEK"
    lines["recommended_qty"] = 10.0
    lines["final_qty"] = 10.0
    lines["name"] = "=HYPERLINK(\"https://example.test\")"
    products = lines[["supplier", "sku"]].copy()
    products["supplier_article"] = "+123"
    return lines, products


def test_changed_quantity_requires_reason_and_approval_survives_restart(tmp_path):
    lines, _ = _sample()
    lines.at[0, "final_qty"] = 20.0
    path = tmp_path / "approvals.json"
    as_of = pd.Timestamp("2026-09-22")
    with pytest.raises(ValueError, match="причину"):
        approve_supplier(lines, "IEK", as_of, path)
    assert not path.exists()

    lines.at[0, "override_reason"] = "Подтвержденный контракт"
    approved = approve_supplier(lines, "IEK", as_of, path)
    assert approved["status"].eq("approved").all()
    restored = apply_saved(_sample()[0], as_of, path)
    assert restored.at[0, "final_qty"] == 20.0
    assert restored.at[0, "override_reason"] == "Подтвержденный контракт"
    changed = _sample()[0]
    changed.at[0, "forecast_H"] += 1
    stale = apply_saved(changed, as_of, path)
    assert stale.at[0, "status"] == "draft"
    changed = _sample()[0]
    changed.at[0, "rationale"] = "Новое обоснование"
    assert apply_saved(changed, as_of, path).at[0, "status"] == "draft"
    revoke_line("IEK", str(lines.at[0, "sku"]), path)
    assert apply_saved(_sample()[0], as_of, path).at[0, "status"] == "draft"


def test_zeroing_recommendation_requires_reason(tmp_path):
    lines, _ = _sample()
    lines.at[0, "final_qty"] = 0.0
    with pytest.raises(ValueError, match="причину"):
        approve_supplier(lines, "IEK", pd.Timestamp("2026-09-22"), tmp_path / "approvals.json")


def test_zero_decisions_survive_recalculation_and_all_zero_order(tmp_path):
    lines, _ = _sample()
    path = tmp_path / "approvals.json"
    date = pd.Timestamp("2026-09-22")
    approve_supplier(lines, "IEK", date, path)
    lines["final_qty"] = 0.0
    lines["override_reason"] = "Отмена закупки"
    approve_supplier(lines, "IEK", date, path)
    restored = apply_saved(_sample()[0], date, path)
    assert restored["final_qty"].eq(0).all()
    assert restored["status"].eq("approved").all()


@pytest.mark.parametrize("missing", [None, pd.NA, float("nan"), "", "  "])
def test_empty_reason_cannot_bypass_validation(missing):
    row = _sample()[0].iloc[0].copy()
    row["final_qty"] += 1
    row["override_reason"] = clean_reason(missing)
    assert validate_line(row)


def test_flagged_lines_require_review_or_exclusion(tmp_path):
    lines, _ = _sample()
    lines.at[0, "flags"] = "needs_review:no_stock"
    with pytest.raises(ValueError, match="Проверьте"):
        approve_supplier(lines, "IEK", pd.Timestamp("2026-09-22"), tmp_path / "a.json")
    lines.at[0, "override_reason"] = "Остаток проверен по складу"
    assert validate_line(lines.iloc[0]) is None


def test_export_only_approved_positive_lines_and_escapes_formulas(tmp_path):
    lines, products = _sample()
    lines.at[0, "status"] = "approved"
    lines.at[1, "status"] = "approved"
    lines.at[1, "final_qty"] = 0
    table = to_table(lines, products, "IEK")
    assert len(table) == 1
    assert table.iloc[0]["Наименование"].startswith("'=HYPERLINK")
    assert table.iloc[0]["Артикул поставщика"] == "'+123"
    assert table.iloc[0]["Склад"] == "Алматы"
    assert to_table(lines, products, "SE").empty

    csv_table = pd.read_csv(io.BytesIO(to_csv(lines, products, "IEK")), encoding="utf-8-sig")
    xlsx_table = pd.read_excel(io.BytesIO(to_xlsx(lines, products, "IEK")))
    assert csv_table.iloc[0]["Количество"] == 10
    assert xlsx_table.iloc[0]["Наименование"].startswith("'=HYPERLINK")
