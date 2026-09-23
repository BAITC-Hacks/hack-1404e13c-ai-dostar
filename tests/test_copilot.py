"""copilot.py without network: a fake client stands in for the OpenAI API."""

from types import SimpleNamespace

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
    client = llm(f"Рекомендуем заказать {qty} {row['unit']}: остатка не хватает на горизонт.")
    answer = copilot.explain_line(row)
    assert answer.source == "llm:fake-mini" and str(qty) in answer.text
    sent = client.calls[0]["messages"][1]["content"]
    assert "doc_id" not in sent and "рекомендовано_заказать" in sent  # only the fact pack goes out


def test_invented_number_falls_back(llm, row):
    llm("Рекомендуем заказать 987654 шт.")
    answer = copilot.explain_line(row)
    assert answer.text == row["rationale"] and "не из расчета" in answer.source


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

    llm(f"К заказу {facts['позиций_к_заказу']} позиций, критичных {facts['критичных']}.")
    assert copilot.supplier_summary(lines, "IEK").source == "llm:fake-mini"


def test_number_guard():
    facts = {"a": 13900, "b": 2.03, "name": "Труба Ø50 IEK"}
    assert copilot.unsupported_numbers("заказ 13 900, сезонность 2,03, труба Ø50, 3 месяца", facts) == []
    assert copilot.unsupported_numbers("заказ 14 000", facts) == [14000.0]
