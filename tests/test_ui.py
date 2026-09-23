"""Exercise actual Streamlit wiring, editor deltas, approval and recalculation."""

import pytest
import io
from pathlib import Path
import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.testing.v1 import AppTest

from app import copilot, schema, adapters, pipeline
from app.mock import mock_order_lines
from app.ui import state


def button(app, label):
    return next(widget for widget in app.button if widget.label == label)


@pytest.fixture
def mock_app(monkeypatch, tmp_path):
    # Synthetic fixture only: the production UI always uses real tables.
    lines = mock_order_lines()
    demand = lines[["supplier", "sku"]].copy()
    demand["month"] = "2026-09"
    demand["qty_raw"] = lines["avg_daily_regular"] * 30
    demand["qty_regular"] = demand["qty_raw"]
    demand["stockout"] = False
    demand["oneoff_excluded_qty"] = 0.0
    demand["stockout_uplift_qty"] = 0.0
    demand["days_in_month_observed"] = 22
    products = lines[["supplier", "sku", "name", "unit", "category"]].copy()
    products["supplier_article"] = products["sku"]
    products["pack_multiple"] = 1.0
    data = {"products": products, "stock_now": schema.empty(schema.STOCK_NOW),
            "manager_baseline": schema.empty(schema.MANAGER_BASELINE),
            "in_transit": schema.empty(schema.IN_TRANSIT)}
    result = schema.PipelineResult(lines, pd.DataFrame(), demand, schema.empty(schema.SALES_FLAGGED),
                                   schema.Params(), pd.Timestamp("2026-09-22"))
    monkeypatch.setattr(adapters, "load_clean", lambda: data)
    monkeypatch.setattr(pipeline, "run", lambda *args: result)
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "approvals.json")
    monkeypatch.setattr(copilot, "enabled", lambda: True)
    monkeypatch.setattr(copilot, "model_name", lambda: "test-mini")
    monkeypatch.setattr(copilot, "_ask", lambda *args: '{"fact_ids": ["decision"]}')
    st.cache_data.clear()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/ui/app.py"), default_timeout=60).run()
    button(app, "Рассчитать").click().run()
    assert not app.exception
    yield app
    st.cache_data.clear()


def edit_first(app, qty, reason):
    key = next(key for key in app.session_state if key.startswith("editor_"))
    app.session_state[key] = {
        "edited_rows": {0: {"final_qty": qty, "override_reason": reason}},
        "added_rows": [], "deleted_rows": [],
    }
    app.run()
    assert not app.exception


def test_explanation_buttons_receive_complete_rows(mock_app):
    app = mock_app
    button(app, "Объяснить подробнее").click().run()
    assert not app.exception
    assert app.session_state.detail_answer[1].source.startswith("llm:")
    button(app, "Сводка по заказу поставщика").click().run()
    assert not app.exception
    assert app.session_state.supplier_answer[1].source.startswith("llm:")


def test_cleared_reason_blocks_approval_and_zero_survives_restart(mock_app):
    app = mock_app
    row = app.session_state.order_lines.query("supplier == 'IEK'").iloc[0]
    sku = row.sku
    edit_first(app, float(row.final_qty) + 1, None)
    assert button(app, "Утвердить заказ поставщика").disabled
    assert not app.get("download_button")
    edit_first(app, 0, "Не требуется")
    assert not button(app, "Утвердить заказ поставщика").disabled
    button(app, "Утвердить заказ поставщика").click().run()
    assert not app.exception
    assert len(app.get("download_button")) == 2
    button(app, "Рассчитать").click().run()
    restored = app.session_state.order_lines.set_index(["supplier", "sku"]).loc[("IEK", sku)]
    assert restored.final_qty == 0 and restored.status == "approved"
    assert restored.override_reason == "Не требуется"


def test_download_reloads_approvals_after_another_session_revokes(mock_app, monkeypatch):
    app = mock_app
    downloads = {}
    original = DeltaGenerator.download_button

    def capture(self, label, data, **kwargs):
        downloads[label] = data
        return original(self, label, data, **kwargs)

    monkeypatch.setattr(DeltaGenerator, "download_button", capture)
    button(app, "Утвердить заказ поставщика").click().run()
    assert not app.exception
    callback = downloads["Скачать CSV"]
    assert callable(callback)
    before = pd.read_csv(io.BytesIO(callback()), encoding="utf-8-sig")
    sku = str(before.iloc[0]["Код 1С"])
    state.revoke_line("IEK", sku, state.STATE_FILE)
    # No page rerun: the download must still use the latest persisted decision.
    after = pd.read_csv(io.BytesIO(callback()), encoding="utf-8-sig")
    assert len(after) == len(before) - 1
    assert sku not in after["Код 1С"].astype(str).tolist()


def test_changed_quantity_hides_previous_explanation(mock_app):
    app = mock_app
    button(app, "Объяснить подробнее").click().run()
    answer = app.session_state.detail_answer[1].text
    assert any(element.value == answer for element in app.markdown)
    # The default product selector and first IEK editor row select the same SKU.
    edit_first(app, 0, "Не требуется")
    assert all(element.value != answer for element in app.markdown)
