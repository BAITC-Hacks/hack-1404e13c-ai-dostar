"""copilot.py without network: a fake client stands in for the OpenAI API."""

from types import SimpleNamespace
import json

import pandas as pd

import pytest

from app import copilot
from app.mock import mock_order_lines


class FakeClient:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))])


@pytest.fixture
def row():
    lines = mock_order_lines()
    return lines[lines["recommended_qty"] > 0].iloc[0]


@pytest.fixture
def llm(monkeypatch):
    def install(reply=None, error=None):
        client = FakeClient(reply, error)
        copilot._ask.cache_clear()
        monkeypatch.setattr(copilot, "enabled", lambda: True)
        monkeypatch.setattr(copilot, "model_name", lambda: "fake-mini")
        monkeypatch.setattr(copilot, "_client", lambda: client)
        return client
    return install


def test_no_key_uses_template(monkeypatch, row):
    monkeypatch.setattr(copilot, "enabled", lambda: False)
    answer = copilot.explain_line(row)
    assert answer.source == "template" and answer.text == row["rationale"]


def test_llm_answer_with_known_numbers(llm, row):
    qty = int(round(row["recommended_qty"]))
    client = llm(json.dumps({"fact_ids": ["inventory", "horizon"]}))
    answer = copilot.explain_line(row)
    assert answer.source.startswith("llm:fake-mini") and str(qty) in answer.text
    assert client.calls[0]["response_format"]["json_schema"]["strict"]
    sent = client.calls[0]["messages"][1]["content"]
    assert "doc_id" not in sent and "рекомендовано_заказать" in sent  # only the fact pack goes out


def test_invented_number_falls_back(llm, row):
    llm("Рекомендуем заказать 987654 шт.")
    answer = copilot.explain_line(row)
    assert answer.text == row["rationale"] and answer.source.startswith("template")


def test_api_error_falls_back(llm, row):
    llm(error=TimeoutError("slow"))
    answer = copilot.explain_line(row)
    assert answer.text == row["rationale"] and "TimeoutError" in answer.source


def test_supplier_summary_template_and_llm(monkeypatch, llm):
    lines = mock_order_lines()
    facts = copilot.supplier_facts(lines, "IEK")
    monkeypatch.setattr(copilot, "enabled", lambda: False)
    text = copilot.supplier_summary(lines, "IEK").text
    assert text.startswith("IEK: к заказу") and str(facts["позиций_к_заказу"]) in text

    llm(json.dumps({"fact_ids": ["decision"]}))
    assert copilot.supplier_summary(lines, "IEK").source.startswith("llm:fake-mini")


@pytest.mark.parametrize("reply", [
    "Order 7 units.", "Order 37 units.", "Order seven units.",
    '{"fact_ids": ["decision"], "text": "Order 7 units."}',
    '{"fact_ids": ["unknown"]}', '{"fact_ids": []}',
    '{"fact_ids": ["decision", "decision"]}', '{"fact_ids": [7]}',
    '{"fact_ids": "decision"}', 'null', '',
])
def test_untrusted_model_text_never_reaches_manager(llm, row, reply):
    llm(reply)
    answer = copilot.explain_line(row)
    assert answer.source.startswith("template")
    assert answer.text == row["rationale"]


def test_model_default_does_not_discover_image_models(monkeypatch):
    monkeypatch.setattr(copilot, "_load_dotenv", lambda: None)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr(copilot, "_client", lambda: pytest.fail("model discovery must not use API"))
    assert copilot.model_name() == "gpt-4o-mini"
    monkeypatch.setenv("OPENAI_MODEL", "gpt-image-1-mini")
    with pytest.raises(ValueError):
        copilot.model_name()
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    assert copilot.model_name() == "gpt-4.1-mini"


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("missing", [float("nan"), float("inf"), pd.NA])
def test_missing_fact_falls_back_without_network(monkeypatch, row, enabled, missing):
    monkeypatch.setattr(copilot, "enabled", lambda: enabled)
    monkeypatch.setattr(copilot, "_client", lambda: pytest.fail("incomplete facts must not reach API"))
    row = row.copy()
    row["free_qty"] = missing
    answer = copilot.explain_line(row)
    assert answer.source.startswith("template") and answer.text == row["rationale"]


def test_supplier_summary_uses_manager_quantities(monkeypatch):
    lines = mock_order_lines()
    lines["final_qty"] = 0.0
    facts = copilot.supplier_facts(lines, "IEK")
    assert facts["позиций_к_заказу"] == 0
    assert facts["критичных"] == 0 and not facts["самые_срочные"]
    row_index = lines.index[lines.supplier.eq("IEK")][0]
    lines.at[row_index, "final_qty"] = 17.5
    lines.at[row_index, "urgency"] = "critical"
    facts = copilot.supplier_facts(lines, "IEK")
    assert facts["позиций_к_заказу"] == 1
    assert facts["самые_срочные"][0]["заказать"] == 17.5


def test_required_decision_and_estimated_stock_cannot_be_omitted(llm, row):
    row = row.copy()
    row["final_qty"] = 0.0
    row["flags"] = "needs_review:estimated_stock"
    llm('{"fact_ids": ["demand"]}')
    answer = copilot.explain_line(row)
    assert "итоговое количество менеджера — 0" in answer.text
    assert "поступления IEK неизвестны" in answer.text


def test_summary_uses_manager_edits(monkeypatch):
    lines = mock_order_lines()
    lines["final_qty"] = 0.0
    assert copilot.supplier_facts(lines, "IEK")["позиций_к_заказу"] == 0


def test_missing_numeric_fact_does_not_crash(monkeypatch, row):
    monkeypatch.setattr(copilot, "enabled", lambda: False)
    row["free_qty"] = float("nan")
    assert copilot.explain_line(row).text == row["rationale"]
