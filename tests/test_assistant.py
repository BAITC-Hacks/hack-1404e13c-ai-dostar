"""Assistant (search, pair review, recommendations) and lifecycle signals. No network."""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from app import assistant, copilot, schema
from app.adapters import CLEAN_DIR, load_clean
from app.engine import lifecycle
from app.mock import mock_order_lines
from app.pipeline import run

real = pytest.mark.skipif(not (CLEAN_DIR / "sales_lines.parquet").exists(), reason="data/clean not built")


class FakeClient:
    def __init__(self, payload):
        self.payload, self.calls = payload, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.payload(kwargs) if callable(self.payload) else json.dumps(self.payload, ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def llm(monkeypatch):
    def install(payload):
        client = FakeClient(payload)
        monkeypatch.setattr(copilot, "enabled", lambda: True)
        monkeypatch.setattr(copilot, "model_name", lambda: "fake-mini")
        monkeypatch.setattr(copilot, "_client", lambda: client)
        return client
    return install


@pytest.fixture
def lines():
    out = mock_order_lines(30)
    out.loc[0, ["supplier", "name", "urgency"]] = ["IEK", "УЗО АД 12 (2ф) 40А IEK", "critical"]
    out.loc[0, "stockout_months"] = 2
    out.loc[1, ["supplier", "name", "urgency", "flags"]] = ["SE", "Розетка Blanca", "normal", "lifecycle:declining"]
    return out


def test_rules_parse_supplier_urgency_terms_and_signals():
    f = assistant.parse_rules("покажи критичные УЗО у IEK где был дефицит")
    assert f["supplier"] == "IEK" and f["urgency"] == ["critical"]
    assert f["name_terms"] == ["узо"] and f["stockout"] == "yes"
    f = assistant.parse_rules("угасающие позиции которые мы заказываем")
    assert f["lifecycle"] == "declining" and f["only_to_order"] and f["name_terms"] == []


def test_search_without_key_uses_rules(monkeypatch, lines):
    monkeypatch.setattr(copilot, "enabled", lambda: False)
    result = assistant.search("критичные узо iek с дефицитом", lines)
    assert result.source == "rules" and list(result.rows["name"]) == ["УЗО АД 12 (2ф) 40А IEK"]


def test_search_with_llm_filter_is_validated(llm, lines):
    client = llm({**assistant.DEFAULT_FILTER, "supplier": "SE", "lifecycle": "declining",
                  "name_terms": ["РОЗЕТК!!"], "limit": 10_000})
    result = assistant.search("какие розетки SE угасают", lines)
    assert result.source == "llm:fake-mini" and result.filter["name_terms"] == ["розетк"]
    assert result.filter["limit"] == 200 and list(result.rows["name"]) == ["Розетка Blanca"]
    call = client.calls[0]
    assert call["response_format"]["json_schema"]["strict"] and "recommended_qty" not in json.dumps(call["messages"])


def test_search_llm_error_falls_back_to_rules(llm, lines):
    llm(lambda kwargs: (_ for _ in ()).throw(TimeoutError("slow")))
    result = assistant.search("критичные узо", lines)
    assert result.source.startswith("rules (ошибка LLM") and len(result.rows) == 1


def _signals():
    return schema.conform(pd.DataFrame([{
        "supplier": "IEK", "sku": "old", "name": "Термостат NC", "signal": "replaced_by", "related_sku": "new",
        "related_name": "Термостат NO", "similarity": 0.96, "avg_last3": 1.0, "avg_prev9": 10.0,
        "first_month": "2025-01", "note": lifecycle.UNVERIFIED}]), schema.LIFECYCLE)


def test_pair_review_uses_fixed_verdicts(llm):
    llm({"items": [{"id": "p0", "verdict": "variant", "reason": "different_parameter"}]})
    table, source = assistant.review_pairs(_signals())
    assert source == "llm:fake-mini" and table.iloc[0]["verdict"] == "variant"
    assert table.iloc[0]["reason"] == assistant.REASONS["different_parameter"]


def test_unverified_replacement_is_not_written_to_order():
    order = mock_order_lines(3)
    order.loc[0, ["supplier", "sku"]] = ["IEK", "old"]
    signals = _signals()
    assert "lifecycle" not in lifecycle.annotate(order, signals).loc[0, "flags"]
    confirmed = lifecycle.annotate(order, signals, {("IEK", "old", "new"): "replacement"})
    assert "lifecycle:replaced_by:new" in confirmed.loc[0, "flags"]
    assert confirmed["recommended_qty"].equals(order["recommended_qty"])


def test_pair_verdict_rules():
    assert lifecycle.pair_verdict("Колодка 1,5мм2 IEK", "Колодка 2,5мм2 IEK", 0.98).startswith("вероятно вариант")
    assert lifecycle.pair_verdict("Блок зажимов ТВ-1504 IEK", "Блок зажимов ТВ-1504 IEK NEW", 1.0) == lifecycle.CONFIRMED


@real
def test_lifecycle_on_real_data_is_advisory():
    data = load_clean()
    result = run(data)
    signals = result.lifecycle
    assert {"declining", "new_item"} <= set(signals["signal"])
    flagged = result.order_lines[result.order_lines["flags"].str.contains("lifecycle:declining")]
    assert len(flagged) > 0 and flagged["rationale"].str.contains("Угасающий спрос").all()
    # Signals never change quantities: same numbers as without annotation.
    plain = lifecycle.annotate(result.order_lines, signals.iloc[0:0])
    assert plain["recommended_qty"].equals(result.order_lines["recommended_qty"])
    fresh = signals[signals["signal"] == "new_item"].set_index(["supplier", "sku"]).index
    declining = signals[signals["signal"] == "declining"].set_index(["supplier", "sku"]).index
    assert not fresh.intersection(declining).isin(
        signals[(signals["signal"] == "new_item") & signals["note"].str.startswith("первая")].set_index(
            ["supplier", "sku"]).index).any()
    recs = assistant.recommendations(result.order_lines, signals)
    assert any("угасающим спросом" in r for r in recs)


def _plan_then(answer_text):
    plan = json.dumps({"intent": "list_items", "filter": {**assistant.DEFAULT_FILTER, "supplier": "IEK",
                                                            "urgency": ["critical"], "name_terms": ["узо"]}})

    def reply(kwargs):
        return plan if "response_format" in kwargs else answer_text
    return reply


def test_ask_grounded_answer(llm, lines):
    client = llm(_plan_then("Критично: УЗО АД 12 (2ф) 40А IEK — заказать {qty} шт."))
    qty = int(lines.loc[0, "recommended_qty"])
    client.payload = _plan_then(f"Критично: УЗО АД 12 (2ф) 40А IEK — заказать {qty} шт.")
    answer = assistant.ask("что срочно заказать из УЗО у IEK?", lines)
    assert answer.source.startswith("llm:fake-mini") and answer.intent == "list_items"
    assert list(answer.rows["name"]) == ["УЗО АД 12 (2ф) 40А IEK"]
    assert answer.text.startswith("Найдено позиций: 1")
    assert len(client.calls) == 1  # Only selection is delegated; no generated quantities.


def test_ask_invented_number_falls_back_to_table(llm, lines):
    llm(_plan_then("Заказать 987654 шт."))
    answer = assistant.ask("что срочно заказать из УЗО у IEK?", lines)
    assert answer.source.startswith("llm:fake-mini") and "987654" not in answer.text
    assert answer.text.startswith("Найдено позиций: 1")


def test_ask_without_key_uses_rules(monkeypatch, lines):
    monkeypatch.setattr(copilot, "enabled", lambda: False)
    answer = assistant.ask("дай рекомендации по заказу", lines)
    assert answer.source == "rules" and answer.intent == "recommendations" and answer.text.startswith("•")


def test_llm_replacement_overruled_by_parameters(llm):
    signals = _signals().assign(note="вероятно вариант исполнения: различаются параметры")
    llm({"items": [{"id": "p0", "verdict": "replacement", "reason": "newer_generation"}]})
    table, _ = assistant.review_pairs(signals)
    assert table.iloc[0]["verdict"] == "variant" and "различаются параметры" in table.iloc[0]["reason"]


@pytest.mark.parametrize("invented", ["999", "40", "один миллион"])
def test_answer_cannot_copy_quantity_from_question_or_other_field(llm, lines, invented):
    lines["final_qty"] = 10
    lines["free_qty"] = 40
    client = llm(_plan_then(f"Заказать {invented} шт."))
    answer = assistant.ask(f"Заказать {invented}?", lines)
    assert len(client.calls) == 1
    assert f"Заказать {invented}" not in answer.text
    assert answer.rows["final_qty"].eq(10).all()


def test_count_before_limit_and_supplier_scope():
    lines = mock_order_lines(100)
    lines["urgency"] = "critical"
    lines["final_qty"] = 10
    facts, rows = assistant._facts_for("list_items", dict(assistant.DEFAULT_FILTER), lines, None)
    assert facts["строк_заказа_по_фильтру"] == 100 and len(rows) == 50
    f = dict(assistant.DEFAULT_FILTER, supplier="SE")
    facts, rows = assistant._facts_for("recommendations", f, lines, None)
    assert any(r.startswith("SE:") for r in facts["рекомендации"])
    assert not any("IEK" in r for r in facts["рекомендации"])
    facts, _ = assistant._facts_for("lifecycle", f, lines, _signals())
    assert "итоги_ассортимента" not in facts  # IEK signals are outside the SE scope.


def test_assistant_answer_invalidated_after_edit_and_recalculation():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string('''
import streamlit as st
from types import SimpleNamespace
from app import assistant
from app.mock import mock_order_lines
from app.ui.tab_assistant import render_ask_panel
if "order_lines" not in st.session_state:
    st.session_state.order_lines = mock_order_lines(3)
    st.session_state.calculation_id = 1
if st.session_state.get("seed", True):
    st.session_state.seed = False
    st.session_state.assistant_answer = assistant.ChatAnswer("OLD ANSWER", "rules", "list_items", dict(assistant.DEFAULT_FILTER), st.session_state.order_lines.copy())
    st.session_state.assistant_answer_key = (st.session_state.calculation_id, st.session_state.order_lines.to_json())
render_ask_panel(SimpleNamespace(lifecycle=None))
''').run()
    assert not at.exception
    assert any(m.value == "OLD ANSWER" for m in at.markdown)
    changed = at.session_state.order_lines.copy()
    changed.loc[0, "final_qty"] = 12345
    at.session_state.order_lines = changed
    at.run()
    assert not at.exception and not any(m.value == "OLD ANSWER" for m in at.markdown)
    at.session_state.seed = True
    at.run()
    assert any(m.value == "OLD ANSWER" for m in at.markdown)
    at.session_state.calculation_id = 2
    at.run()
    assert not at.exception and not any(m.value == "OLD ANSWER" for m in at.markdown)


def test_ask_question_cannot_authorize_invented_quantity(llm, lines):
    llm(_plan_then("Заказать 987654 шт."))
    answer = assistant.ask("Заказать 987654 УЗО у IEK?", lines)
    assert "987654" not in answer.text  # the answer is rendered from calculated facts


def test_ask_client_configuration_error_uses_rules(monkeypatch, lines):
    monkeypatch.setattr(copilot, "enabled", lambda: True)
    monkeypatch.setattr(copilot, "model_name", lambda: (_ for _ in ()).throw(ValueError("bad model")))
    answer = assistant.ask("критичные узо iek", lines)
    assert answer.source.startswith("rules (ошибка LLM: ValueError)")
    assert len(answer.rows) == 1
