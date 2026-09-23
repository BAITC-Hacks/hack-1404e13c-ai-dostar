"""«Ассистент» tab: recommendations, natural-language search, assortment lifecycle."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import assistant, copilot, schema
from app.engine import lifecycle

URGENCY = {"critical": "Критичная", "high": "Высокая", "normal": "Плановая"}
SIGNALS = {"declining": "Угасающий спрос", "new_item": "Новинка"}
COLUMNS = {"supplier": "Поставщик", "sku": "Код 1С", "name": "Наименование", "urgency": "Срочность",
           "recommended_qty": "Рекомендация", "final_qty": "Итог", "days_of_cover": "Запаса, дней",
           "seasonal_index": "Сезонность", "flags": "Сигналы", "rationale": "Обоснование"}


def _source(text: str) -> str:
    if text.startswith("llm:"):
        return "ИИ (" + text.split(":", 1)[1] + ")"
    if text.startswith("шаблон"):
        return text
    return "правила без ИИ" + (text[5:] if text.startswith("rules ") else "")


def render(result: schema.PipelineResult) -> None:
    lines = st.session_state.order_lines
    signals = result.lifecycle if result.lifecycle is not None else schema.empty(schema.LIFECYCLE)
    st.caption("ИИ " + ("подключён" if copilot.enabled() else "не подключён (нет OPENAI_API_KEY): работают правила")
               + ". Ассистент не меняет количества и не утверждает заказы.")

    st.subheader("Рекомендации")
    for item in assistant.recommendations(lines, signals):
        st.write(f"• {item}")

    st.subheader("Спросить ассистента")
    st.caption("Опишите, что нужно получить. ИИ выбирает нужные данные; "
               "ответ и количества формирует приложение из текущего расчета.")
    examples = ["Какие позиции IEK заказать в первую очередь и почему?",
                "Почему по трубе гибкой Ø50 такой большой заказ?",
                "Дай сводку по заказу Systeme Electric",
                "Есть ли товары, которые выходят из ассортимента или заменяются новыми моделями?"]
    pick = st.selectbox("Пример вопроса", ["—"] + examples, key="assistant_example")
    question = st.text_area("Ваш вопрос", value="" if pick == "—" else pick, height=80, key=f"assistant_q_{pick}",
                            placeholder="например: критичные УЗО у IEK, где был дефицит — что заказать?")
    answer_key = (st.session_state.get("calculation_id", 0), lines.to_json())
    if st.session_state.get("assistant_answer_key") != answer_key:
        st.session_state.pop("assistant_answer", None)
    if st.button("Спросить", key="assistant_ask", type="primary") and question.strip():
        with st.spinner("Ассистент готовит ответ…"):
            st.session_state.assistant_answer = assistant.ask(question, lines, signals)
            st.session_state.assistant_answer_key = answer_key
    answer = st.session_state.get("assistant_answer")
    if answer is not None:
        st.markdown(answer.text)
        st.caption(f"Источник: {_source(answer.source)} · данные: {assistant.describe(answer.filter)}")
        if not answer.rows.empty:
            with st.expander(f"На чем основан ответ: {len(answer.rows)} строк заказа"):
                table = answer.rows[list(COLUMNS)].rename(columns=COLUMNS)
                table["Срочность"] = table["Срочность"].map(URGENCY).fillna(table["Срочность"])
                st.dataframe(table, hide_index=True, width="stretch")

    st.subheader("Жизненный цикл ассортимента")
    if signals.empty:
        st.info("Сигналов нет: для оценки нужно минимум 12 полных месяцев продаж.")
        return
    to_order = lines.set_index(["supplier", "sku"])[["recommended_qty"]]
    counts = signals["signal"].value_counts()
    cols = st.columns(3)
    cols[0].metric("Угасающий спрос", int(counts.get("declining", 0)))
    cols[1].metric("Новинки", int(counts.get("new_item", 0)))
    cols[2].metric("Кандидаты в замену", int(counts.get("replaced_by", 0)))
    kind = st.radio("Показать", list(SIGNALS), format_func=SIGNALS.get, horizontal=True, key="lifecycle_kind")
    shown = signals[signals["signal"] == kind].join(to_order, on=["supplier", "sku"])
    shown["Рекомендация по ассортименту"] = shown["signal"].map(lambda s: lifecycle.recommendation(s))
    shown = shown.sort_values("recommended_qty", ascending=False, na_position="last")
    st.dataframe(shown[["supplier", "sku", "name", "avg_prev9", "avg_last3", "first_month", "note",
                        "recommended_qty", "Рекомендация по ассортименту"]].rename(columns={
        "supplier": "Поставщик", "sku": "Код 1С", "name": "Наименование", "avg_prev9": "Спрос/мес ранее",
        "avg_last3": "Спрос/мес 3 мес.", "first_month": "Первая продажа", "note": "Сигнал",
        "recommended_qty": "Рекомендация к заказу"}), hide_index=True, width="stretch")

    st.subheader("Смена моделей")
    st.caption("Пары «старый товар с падающим спросом → новый товар» в той же группе с похожим названием. "
               "Похожие названия часто означают вариант исполнения (другой ток, сечение, цвет), а не замену: "
               "ИИ читает названия и выбирает вердикт из фиксированного списка.")
    run_id = st.session_state.get("calculation_id", 0)
    saved = st.session_state.get("pair_review")
    if st.button("Проверить пары с ИИ", key="review_pairs_button", disabled=not copilot.enabled()):
        with st.spinner("ИИ проверяет пары…"):
            saved = st.session_state.pair_review = (run_id, *assistant.review_pairs(signals))
    if saved is not None and saved[0] == run_id:
        table, source = saved[1], saved[2]
    else:  # deterministic verdicts until the manager asks the LLM
        table = assistant.review_pairs(signals, use_llm=False)[0]
        source = "rules"
    if table.empty:
        st.info("Кандидатов в замену нет.")
        return
    view = table.assign(verdict=table["verdict"].map({**assistant.VERDICTS, "unverified": "не проверено"}))
    st.caption(f"Вердикт: {_source(source)}. В строку заказа попадают только подтвержденные замены.")
    st.dataframe(pd.DataFrame({
        "Поставщик": view["supplier"], "Старый товар": view["name"], "Новый товар": view["related_name"],
        "Сходство": view["similarity"].round(2), "Спрос/мес ранее → сейчас": view["avg_prev9"].round(1).astype(str)
        + " → " + view["avg_last3"].round(1).astype(str), "Вердикт": view["verdict"], "Причина": view["reason"],
    }), hide_index=True, width="stretch")
