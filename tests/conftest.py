import pytest


@pytest.fixture(autouse=True)
def _no_paid_llm_calls(monkeypatch):
    """Tests never call the real OpenAI API, even when a local .env holds a key.

    Tests that exercise the LLM path patch `copilot.enabled` and `copilot._client` themselves.
    """
    monkeypatch.setenv("COPILOT_ENABLED", "0")
