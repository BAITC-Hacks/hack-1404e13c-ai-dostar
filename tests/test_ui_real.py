"""Full product journey against the actual Excel-derived tables, no mocked pipeline.

Build first: python -m app.adapters.build --raw datasets
Only approval persistence is isolated; paid LLM calls are disabled.
"""

import io
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app import copilot
from app.adapters import CLEAN_DIR
from app.export import to_csv, to_xlsx
from app.ui import state

pytestmark = pytest.mark.skipif(not (CLEAN_DIR / "sales_lines.parquet").exists(), reason="Build real datasets first")
APP = str(Path(__file__).resolve().parents[1] / "app/ui/app.py")


def button(at, label):
    return next(b for b in at.button if b.label == label)


def healthy(at):
    assert not at.exception, [e.message for e in at.exception]


def test_real_ui_order_explanation_checks_approval_exports_restart(tmp_path, monkeypatch):
    approval_path = tmp_path / "approvals.json"
    monkeypatch.setattr(state, "STATE_FILE", approval_path)
    monkeypatch.setattr(copilot, "enabled", lambda: False)
    at = AppTest.from_file(APP, default_timeout=90).run()
    healthy(at)
    assert not any("Мок" in t.label for t in at.toggle)
    button(at, "Рассчитать").click().run()
    healthy(at)
    result = at.session_state.result
    assert len(result.sales_flagged) > 200_000
    assert len(result.order_lines) > 2_000
    assert len(at.tabs) == 6 and at.tabs[-1].label == "Ассистент"

    at.selectbox(key="product_sku").select("IEK | 130300792_").run()
    button(at, "Объяснить подробнее").click().run()
    healthy(at)
    assert at.session_state.detail_answer[1].source == "template"
    at.selectbox(key="product_sku").select("IEK | 130200305_").run()
    healthy(at)
    assert len(at.get("vega_lite_chart")) == 1
    cases = next(d.value for d in at.dataframe if "oneoff_excess_qty" in d.value.columns)
    assert cases["oneoff_excess_qty"].max() == 209990

    at.selectbox(key="checks_sku").select("IEK | 130300792_").run()
    button(at, "Сравнить факторы").click().run()
    healthy(at)
    scenarios = at.session_state.check_scenarios[1]
    assert len(scenarios) == 7
    assert scenarios[-1]["Рекомендация"] <= scenarios[0]["Рекомендация"]
    assert scenarios[3]["Рекомендация"] != scenarios[0]["Рекомендация"]

    # Streamlit's editor transports edits as a row-index delta. Exercise that
    # actual path, including a cleared cell represented as None.
    editor_key = (f"editor_{at.session_state.calculation_id}_IEK_"
                  f"{'-'.join(at.multiselect[0].value)}_{'-'.join(at.multiselect[1].value)}")
    first = at.session_state.order_lines.query("supplier == 'IEK'").iloc[0]
    at.session_state[editor_key] = {"edited_rows": {0: {"final_qty": 0, "override_reason": None}}, "added_rows": [], "deleted_rows": []}
    at.run()
    healthy(at)
    assert button(at, "Утвердить заказ поставщика").disabled
    at.session_state[editor_key] = {"edited_rows": {0: {"final_qty": 0, "override_reason": "Закупка отменена менеджером"}}, "added_rows": [], "deleted_rows": []}
    at.run()
    healthy(at)
    at.checkbox[0].check().run()
    assert not button(at, "Утвердить заказ поставщика").disabled
    button(at, "Сводка по заказу поставщика").click().run()
    healthy(at)
    button(at, "Утвердить заказ поставщика").click().run()
    healthy(at)
    assert len(at.get("download_button")) == 2
    restored = state.apply_saved(result.order_lines, result.as_of, approval_path)
    zero = restored.query("supplier == 'IEK' and sku == @first.sku").iloc[0]
    assert zero.final_qty == 0 and zero.status == "approved"
    for export, reader in ((to_csv, pd.read_csv), (to_xlsx, pd.read_excel)):
        table = reader(io.BytesIO(export(restored, at.session_state.result_data["products"], "IEK")))
        assert len(table) > 600
        assert (table["Количество"] > 0).all()
        assert first.sku not in set(table["Код 1С"])

    restarted = AppTest.from_file(APP, default_timeout=90).run()
    button(restarted, "Рассчитать").click().run()
    healthy(restarted)
    persisted = restarted.session_state.order_lines
    assert persisted.query("supplier == 'IEK' and sku == @first.sku").iloc[0].final_qty == 0
    restarted.selectbox[0].select("SE").run()
    healthy(restarted)
    comparison = next(d.value for d in restarted.dataframe if "Наш факт / месяц" in d.value.columns)
    assert len(comparison) == 497
    assert comparison["Наш факт / месяц"].notna().any()
    assert comparison["Заказ менеджера"].isna().any()


def test_real_assistant_invalidates_answer_after_edit_and_recalculation(tmp_path, monkeypatch):
    """A free-form answer must never show quantities from an older order."""
    from app import assistant

    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "approvals.json")
    monkeypatch.setattr(copilot, "enabled", lambda: False)
    calls = []
    real_ask = assistant.ask

    def tracked_ask(query, lines, signals):
        calls.append(query)
        return real_ask(query, lines, signals)

    monkeypatch.setattr(assistant, "ask", tracked_ask)
    at = AppTest.from_file(APP, default_timeout=90).run()
    button(at, "Рассчитать").click().run()
    at.text_area[0].input("IEK заказ").run()
    button(at, "Спросить").click().run()
    healthy(at)
    found = at.session_state.assistant_answer
    assert found.source == "rules" and not found.rows.empty
    assert found.rows.supplier.eq("IEK").all() and found.rows.final_qty.gt(0).all()
    sku = found.rows.iloc[0].sku
    shown = at.session_state.order_lines.query("supplier == 'IEK'").reset_index(drop=True)
    row_number = int(shown.index[shown.sku.eq(sku)][0])
    editor_key = f"editor_{at.session_state.calculation_id}_IEK__"
    at.session_state[editor_key] = {
        "edited_rows": {row_number: {"final_qty": 0, "override_reason": "Проверка актуальности поиска"}},
        "added_rows": [], "deleted_rows": [],
    }
    at.run()
    healthy(at)
    assert "assistant_answer" not in at.session_state
    assert calls == ["IEK заказ"]  # Editing must not spend another API call.
    button(at, "Спросить").click().run()
    healthy(at)
    assert sku not in set(at.session_state.assistant_answer.rows.sku)
    assert calls == ["IEK заказ", "IEK заказ"]
    button(at, "Рассчитать").click().run()
    healthy(at)
    assert "assistant_answer" not in at.session_state
    assert calls == ["IEK заказ", "IEK заказ"]
