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
    return "ИИ (" + text.split(":", 1)[1] + ")" if text.startswith("llm:") else "правила без ИИ" + (
        text[5:] if text.startswith("rules ") else "")


def render(result: schema.PipelineResult) -> None:
    lines = st.session_state.order_lines
    signals = result.lifecycle if result.lifecycle is not None else schema.empty(schema.LIFECYCLE)
    st.caption("ИИ " + ("подключён" if copilot.enabled() else "не подключён (нет OPENAI_API_KEY): работают правила")
               + ". Ассистент не меняет количества и не утверждает заказы.")

    st.subheader("Рекомендации")
    for item in assistant.recommendations(lines, signals):
        st.write(f"• {item}")

    st.subheader("Поиск по заказу")
    query = st.text_input("Опишите, что найти", placeholder="например: критичные УЗО у IEK, где был дефицит",
                          key="assistant_query")
    if st.button("Найти", key="assistant_search") and query.strip():
        with st.spinner("Разбираю запрос…"):
            st.session_state.assistant_found = assistant.search(query, lines)
    found = st.session_state.get("assistant_found")
    if found is not None:
        # Keep the parsed filter, but always apply it to the current manager
        # decision. Editing quantities must not leave a stale search snapshot
        # or trigger another paid language-model request.
        found.rows = assistant.apply_filter(lines, found.filter)
        found.notes = [] if len(found.rows) else ["Ничего не найдено: попробуйте убрать часть условий."]
        st.caption(f"Фильтр: {assistant.describe(found.filter)} · источник: {_source(found.source)}")
        for note in found.notes:
            st.info(note)
        if found.filter.get("lifecycle") == "replacement" and found.rows.empty:
            st.info("Подтвержденных замен в заказе нет. Кандидатов можно проверить ниже, в «Смене моделей».")
        if not found.rows.empty:
            table = found.rows[list(COLUMNS)].rename(columns=COLUMNS)
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
