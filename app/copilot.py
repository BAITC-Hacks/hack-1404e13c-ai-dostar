"""LLM explanations on top of the deterministic calculation.

Two features for the UI:
    explain_line(row)                          -> Answer   # «Объяснить подробнее» for one order line
    supplier_summary(order_lines, supplier)    -> Answer   # note shown before approving a supplier order

Rules (docs/architecture.md §6):
- the model gets only the numbers of the calculation (fact pack), never invoice lines;
- the model only words the facts: an answer with a number not present in the facts,
  an API error, a timeout or a missing key falls back to the template text;
- nothing here changes quantities, approves or sends orders.

Configuration (env or .env in the repo root, never committed):
    OPENAI_API_KEY=...
    OPENAI_MODEL=...          # optional; default: first "gpt-*mini*" model available to the key
    COPILOT_ENABLED=0         # optional kill switch

UI usage (Person 3):
    from app import copilot
    if st.button("Объяснить подробнее"):
        answer = copilot.explain_line(row)       # row: one ORDER_LINES record (Series)
        st.write(answer.text); st.caption(answer.source)
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_S = 20
MAX_OUTPUT_TOKENS = 400
URGENCY_RU = {"critical": "критично", "high": "высокая", "normal": "плановая"}

SYSTEM_PROMPT = (
    "Ты помощник менеджера по закупкам компании-дистрибьютора электротехники. "
    "Тебе дают факты расчета рекомендованного заказа поставщику в JSON. "
    "Объясняй по-русски, коротко и по делу, для менеджера, без формул и без markdown-заголовков. "
    "Используй только числа из фактов, ничего не пересчитывай и не придумывай новых чисел, "
    "не давай советов отправить заказ — решение принимает менеджер."
)


@dataclass(frozen=True)
class Answer:
    text: str
    source: str  # "llm:<model>" | "template" | "template (<reason>)"


# ---------------------------------------------------------------- config / client

def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def enabled() -> bool:
    _load_dotenv()
    return bool(os.environ.get("OPENAI_API_KEY")) and os.environ.get("COPILOT_ENABLED", "1") != "0"


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI

    return OpenAI(timeout=TIMEOUT_S, max_retries=1)


@lru_cache(maxsize=1)
def model_name() -> str:
    _load_dotenv()
    if os.environ.get("OPENAI_MODEL"):
        return os.environ["OPENAI_MODEL"]
    ids = sorted(m.id for m in _client().models.list())
    minis = [i for i in ids if i.startswith("gpt-") and "mini" in i and not re.search(r"image|audio|realtime|tts|transcribe|search", i)]
    if not minis:
        raise RuntimeError("set OPENAI_MODEL: no gpt-*mini* model visible for this key")
    return minis[-1]


# ---------------------------------------------------------------- facts

def _num(x, digits: int = 0):
    x = float(x)
    if not math.isfinite(x):
        return None
    return round(x, digits) if digits else int(round(x))


def line_facts(row: pd.Series) -> dict:
    """Compact, rounded numbers of one ORDER_LINES record — the only input to the model."""
    return {
        "товар": str(row["name"]),
        "поставщик": str(row["supplier"]),
        "ед": str(row["unit"]),
        "регулярный_спрос_в_день": _num(row["avg_daily_regular"], 1),
        "сезонный_коэффициент": _num(row["seasonal_index"], 2),
        "тренд": _num(row["trend_factor"], 2),
        "рост_категории": _num(row["growth_factor"], 2),
        "горизонт_дней": _num(row["horizon_days"]),
        "прогноз_на_горизонт": _num(row["forecast_H"]),
        "страховой_запас": _num(row["safety_stock"]),
        "свободный_остаток": _num(row["free_qty"]),
        "в_пути_до_конца_горизонта": _num(row["in_transit_H"]),
        "исключено_разовых_продаж": _num(row["oneoff_excluded_qty"]),
        "месяцев_дефицита": _num(row["stockout_months"]),
        "восстановлено_спроса_за_дефицит": _num(row["stockout_uplift_qty"]),
        "запаса_хватит_дней": _num(min(row["days_of_cover"], 9999)),
        "срочность": URGENCY_RU.get(str(row["urgency"]), str(row["urgency"])),
        "рекомендовано_заказать": _num(row["recommended_qty"]),
        "шаблонное_обоснование": str(row["rationale"]),
    }


def supplier_facts(order_lines: pd.DataFrame, supplier: str, top: int = 5) -> dict:
    lines = order_lines[order_lines["supplier"] == supplier]
    to_order = lines[lines["final_qty"] > 0]
    urgent = to_order[to_order["urgency"] == "critical"].sort_values("days_of_cover").head(top)
    seasonal = to_order[to_order["seasonal_index"] >= 1.3].sort_values("seasonal_index", ascending=False).head(top)
    return {
        "поставщик": supplier,
        "позиций_проанализировано": int(len(lines)),
        "позиций_к_заказу": int(len(to_order)),
        "критичных": int((to_order["urgency"] == "critical").sum()),
        "высокой_срочности": int((to_order["urgency"] == "high").sum()),
        "с_исключенными_разовыми_продажами": int((to_order["oneoff_excluded_qty"] > 0).sum()),
        "с_восстановленным_спросом_после_дефицита": int((to_order["stockout_uplift_qty"] > 0).sum()),
        "с_сезонным_ростом_спроса": int((to_order["seasonal_index"] >= 1.3).sum()),
        "с_товаром_в_пути": int((to_order["in_transit_H"] > 0).sum()),
        "требуют_проверки": int(to_order["flags"].astype(str).str.contains("needs_review").sum()),
        "самые_срочные": [
            {"товар": r.name, "запаса_дней": _num(r.days_of_cover), "заказать": _num(r.final_qty), "ед": r.unit}
            for r in urgent.itertuples()
        ],
        "самые_сезонные": [
            {"товар": r.name, "сезонный_коэффициент": _num(r.seasonal_index, 2)} for r in seasonal.itertuples()
        ],
    }


# ---------------------------------------------------------------- guard

_NUMBER = re.compile(r"\d+(?:[   ]\d{3})*(?:[.,]\d+)?")


def _numbers(text: str) -> list[float]:
    out = []
    for token in _NUMBER.findall(text):
        clean = re.sub(r"[   ]", "", token).replace(",", ".")
        try:
            out.append(float(clean))
        except ValueError:
            pass
    return out


def _fact_numbers(facts) -> set[float]:
    if isinstance(facts, dict):
        return set().union(*(_fact_numbers(v) for v in facts.values())) if facts else set()
    if isinstance(facts, list):
        return set().union(*(_fact_numbers(v) for v in facts)) if facts else set()
    if isinstance(facts, (int, float)):
        return {float(facts)}
    if isinstance(facts, str):
        return set(_numbers(facts))
    return set()


def unsupported_numbers(text: str, facts: dict) -> list[float]:
    """Reject numbers absent from facts, including small invented quantities."""
    known = _fact_numbers(facts)

    def ok(x: float) -> bool:
        return any(abs(x - k) < 1e-8 for k in known)

    return [x for x in _numbers(text) if not ok(x)]


# ---------------------------------------------------------------- templates

def template_line(row: pd.Series) -> str:
    return str(row["rationale"])


def template_summary(facts: dict) -> str:
    parts = [f"{facts['поставщик']}: к заказу {facts['позиций_к_заказу']} из {facts['позиций_проанализировано']} позиций, "
             f"критичных {facts['критичных']}, высокой срочности {facts['высокой_срочности']}."]
    drivers = [
        (facts["с_сезонным_ростом_спроса"], "сезонный рост спроса"),
        (facts["с_восстановленным_спросом_после_дефицита"], "восстановлен спрос после дефицита"),
        (facts["с_исключенными_разовыми_продажами"], "исключены разовые продажи"),
        (facts["с_товаром_в_пути"], "учтен товар в пути"),
    ]
    drivers = [f"{text} — {n}" for n, text in drivers if n]
    if drivers:
        parts.append("Факторы: " + "; ".join(drivers) + ".")
    if facts["самые_срочные"]:
        parts.append("Срочнее всего: " + ", ".join(
            f"{i['товар']} (запаса на {i['запаса_дней']} дн.)" for i in facts["самые_срочные"][:3]) + ".")
    if facts["требуют_проверки"]:
        parts.append(f"Требуют проверки данных: {facts['требуют_проверки']}.")
    return " ".join(parts)


# ---------------------------------------------------------------- LLM calls

@lru_cache(maxsize=512)
def _ask(task: str, facts_json: str, model: str) -> str:
    response = _client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{task}\n\nФакты:\n{facts_json}"},
        ],
        max_completion_tokens=MAX_OUTPUT_TOKENS,
        store=False,
    )
    return (response.choices[0].message.content or "").strip()


def _answer(task: str, facts: dict, fallback: str) -> Answer:
    if not enabled():
        return Answer(fallback, "template")
    try:
        model = model_name()
        text = _ask(task, json.dumps(facts, ensure_ascii=False, sort_keys=True), model)
    except Exception as exc:  # network, auth, quota, timeout: the demo must not break
        return Answer(fallback, f"template (ошибка LLM: {type(exc).__name__})")
    if not text:
        return Answer(fallback, "template (пустой ответ)")
    bad = unsupported_numbers(text, facts)
    if bad:
        return Answer(fallback, f"template (в ответе числа не из расчета: {bad[:3]})")
    return Answer(text, f"llm:{model}")


def explain_line(row: pd.Series) -> Answer:
    task = ("Объясни в 2–4 предложениях, почему по этому товару рекомендовано именно такое количество: "
            "что определяет спрос (сезонность, тренд, исключенные разовые продажи, дефицит), "
            "что уже есть на складе и в пути, и насколько это срочно.")
    return _answer(task, line_facts(row), template_line(row))


def supplier_summary(order_lines: pd.DataFrame, supplier: str) -> Answer:
    facts = supplier_facts(order_lines, supplier)
    task = ("Составь для менеджера сводку по заказу этому поставщику перед утверждением: 3–5 предложений. "
            "Сколько позиций и насколько срочно, какие факторы главные, на что обратить внимание при проверке.")
    return _answer(task, facts, template_summary(facts))
