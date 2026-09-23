"""Purchasing demo: streamlit run app/ui/app.py."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import schema  # noqa: E402
from app.adapters import load_clean, CLEAN_DIR  # noqa: E402
from app.copilot import explain_line, supplier_summary  # noqa: E402
from app.engine.oneoffs import report as oneoff_report  # noqa: E402
from app.export import to_csv, to_table, to_xlsx  # noqa: E402
from app.pipeline import run  # noqa: E402
from app.ui.state import STATE_FILE, apply_saved, approve_supplier, revoke_line, validate_line, clean_reason  # noqa: E402


st.set_page_config(page_title="Заказы поставщикам", layout="wide")
st.title("Заказы поставщикам")


@st.cache_data(show_spinner="Загрузка подготовленных данных…")
def cached_data(fingerprint: tuple) -> dict[str, pd.DataFrame]:
    return load_clean()


def params_sidebar(data: dict[str, pd.DataFrame] | None) -> schema.Params:
    st.sidebar.header("Параметры расчёта")
    method = st.sidebar.selectbox("Метод прогноза", ["statistical", "ml"],
                                  format_func=lambda value: "ML — обученный бустинг" if value == "ml" else "Статистика — сезонность и тренд")
    ml = method == "ml"
    if ml:
        st.sidebar.caption("Обучение: python -m app.ml.train. Очистка и признаки модели фиксированы; рост категории и товар в пути доступны.")
    lead_iek = st.sidebar.number_input("Срок поставки IEK, дней", 1, 365, 30)
    lead_se = st.sidebar.number_input("Срок поставки SE, дней", 1, 365, 30)
    review = st.sidebar.number_input("Период пересмотра, дней", 1, 90, 7)
    service = st.sidebar.slider("Уровень сервиса", 0.50, 0.999, 0.95, 0.001)
    growth: dict[str, float] = {}
    if data is not None:
        categories = sorted(data["products"]["category"].dropna().astype(str).unique().tolist())
        selected = st.sidebar.multiselect("Категории для сценария роста", categories)
        for category in selected:
            growth[category] = st.sidebar.number_input(
                f"Рост {category}, %", -50.0, 300.0, 0.0, 1.0, key=f"growth_{category}"
            )
    st.sidebar.caption("Переключатели позволяют показать вклад каждого фактора.")
    flags = {
        "use_oneoff_filter": st.sidebar.toggle("Исключать разовые заказы", True, disabled=ml, key=f"oneoffs_{method}"),
        "use_stockout_fix": st.sidebar.toggle("Оценивать спрос при дефиците", True, disabled=ml, key=f"stockout_{method}"),
        "use_seasonality": st.sidebar.toggle("Сезонность", True, disabled=ml, key=f"seasonality_{method}"),
        "use_trend": st.sidebar.toggle("Тренд", True, disabled=ml, key=f"trend_{method}"),
        "use_in_transit": st.sidebar.toggle("Товар в пути", True),
    }
    return schema.Params(
        lead_time_days={"IEK": int(lead_iek), "SE": int(lead_se)},
        review_period_days=int(review), service_level=float(service),
        growth_pct=growth, forecast_method=method, **flags,
    )


def order_tab(result: schema.PipelineResult, data: dict[str, pd.DataFrame]) -> None:
    lines = st.session_state.order_lines
    suppliers = sorted(lines["supplier"].dropna().unique().tolist())
    if not suppliers:
        st.info("Нет позиций к заказу при выбранных параметрах.")
        return
    chosen = st.selectbox("Поставщик", suppliers)
    subset = lines[lines["supplier"].eq(chosen)]
    stock = data["stock_now"].query("supplier == @chosen")
    estimated = stock["source"].astype(str).str.contains("estimat", case=False).any()
    if estimated:
        st.warning(f"У {chosen} есть оценочные остатки из месячного остатка за вычетом продаж. "
                   "Поступления внутри месяца неизвестны. Перед утверждением сверьте количество со складом.")
    metrics = st.columns(3)
    metrics[0].metric("Позиций к заказу", int(subset["final_qty"].gt(0).sum()))
    metrics[1].metric("Критичных", int((subset["urgency"].eq("critical") & subset["final_qty"].gt(0)).sum()))
    metrics[2].metric("Утверждено к заказу", int((subset["status"].eq("approved") & subset["final_qty"].gt(0)).sum()))

    categories = sorted(subset["category"].dropna().unique().tolist())
    selected_categories = st.multiselect("Категория", categories, placeholder="Все категории")
    urgency = st.multiselect("Срочность", list(schema.URGENCY_LEVELS), placeholder="Любая срочность",
                            format_func=lambda v: {"critical": "Критичная", "high": "Высокая", "normal": "Плановая"}[v])
    visible = subset[
        subset["category"].isin(selected_categories or categories)
        & subset["urgency"].isin(urgency or list(schema.URGENCY_LEVELS))
    ].copy()
    visible.insert(0, "key", visible["supplier"] + "|" + visible["sku"])
    columns = ["key", "sku", "name", "category", "urgency", "recommended_qty", "final_qty",
               "override_reason", "status", "flags", "rationale"]
    editor_key = (f"editor_{st.session_state.get('calculation_id', 0)}_{chosen}_"
                  f"{'-'.join(selected_categories)}_{'-'.join(urgency)}")
    edited = st.data_editor(
        visible[columns], hide_index=True, key=editor_key,
        disabled=[column for column in columns if column not in {"final_qty", "override_reason"}],
        column_config={
            "key": None,
            "sku": "Код 1С", "name": "Наименование", "category": "Категория",
            "urgency": "Срочность", "status": "Статус", "flags": "Проверка данных",
            "rationale": "Обоснование",
            "final_qty": st.column_config.NumberColumn("Итоговое количество", min_value=0, step=1),
            "recommended_qty": st.column_config.NumberColumn("Рекомендация", disabled=True),
            "override_reason": st.column_config.TextColumn("Причина изменения / результат проверки"),
        },
        width="stretch",
    )
    # Apply editor values by stable supplier/SKU key. Filtering never changes row identity.
    current = lines.set_index(["supplier", "sku"], drop=False)
    for _, row in edited.iterrows():
        supplier, sku = row["key"].split("|", 1)
        key = (supplier, sku)
        old_qty = float(current.at[key, "final_qty"])
        try:
            new_qty = float(row["final_qty"])
        except (TypeError, ValueError):
            new_qty = float("nan")
        old_reason = clean_reason(current.at[key, "override_reason"])
        new_reason = clean_reason(row["override_reason"])
        if new_qty != old_qty or new_reason != old_reason:
            if current.at[key, "status"] == "approved":
                revoke_line(supplier, sku, STATE_FILE)
            current.at[key, "final_qty"] = new_qty
            current.at[key, "override_reason"] = new_reason
            current.at[key, "status"] = "draft"
    st.session_state.order_lines = current.reset_index(drop=True)
    supplier_rows = st.session_state.order_lines.query("supplier == @chosen")
    problems = [f"{row['sku']}: {issue}" for _, row in supplier_rows.iterrows()
                if (issue := validate_line(row))]
    if problems:
        st.warning("\n".join(problems[:8]))

    summary_key = supplier_rows.to_json(orient="split", force_ascii=False)
    if st.button("Сводка по заказу поставщика", disabled=bool(problems)):
        with st.spinner("Готовлю сводку по итоговым количествам…"):
            st.session_state.supplier_answer = (summary_key, supplier_summary(supplier_rows, chosen))
    summary = st.session_state.get("supplier_answer")
    if summary and summary[0] == summary_key:
        st.write(summary[1].text)
        st.caption(f"Источник: {summary[1].source}. Сводка учитывает правки менеджера.")

    stock_checked = not estimated or st.checkbox(
        "Оценку остатка сверил со складом; итоговые количества проверены",
        key=f"stock_checked_{st.session_state.get('calculation_id', 0)}_{chosen}",
    )

    if st.button("Утвердить заказ поставщика", disabled=bool(problems) or not stock_checked, type="primary"):
        try:
            st.session_state.order_lines = approve_supplier(
                st.session_state.order_lines, chosen, result.as_of,
                STATE_FILE,
            )
            st.success("Заказ утверждён и сохранён локально.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    st.caption("Утверждение сохраняется в data/state/approvals.json. Отправки поставщику нет.")

    # Resolve persisted approvals both when rendering and when downloading.
    approval_file = STATE_FILE
    export_lines = apply_saved(result.order_lines, result.as_of, approval_file)
    shown = st.session_state.order_lines.set_index(["supplier", "sku"])
    saved = export_lines.set_index(["supplier", "sku"])
    if not shown[["status", "final_qty"]].equals(saved[["status", "final_qty"]]):
        st.warning("Сохранённый заказ изменился в другой сессии или имеет несохранённые правки. "
                   "Экспорт использует только актуальные утверждения; пересчитайте для обновления таблицы.")
    approved = to_table(export_lines, data["products"], chosen)
    if not approved.empty:
        left, right = st.columns(2)
        left.download_button("Скачать XLSX", lambda: to_xlsx(
            apply_saved(result.order_lines, result.as_of, approval_file), data["products"], chosen),
                             file_name=f"order_{chosen}_{result.as_of.date()}.xlsx")
        right.download_button("Скачать CSV", lambda: to_csv(
            apply_saved(result.order_lines, result.as_of, approval_file), data["products"], chosen),
                              file_name=f"order_{chosen}_{result.as_of.date()}.csv", mime="text/csv")


def selected_product(lines: pd.DataFrame, key: str) -> tuple[str, str] | None:
    if lines.empty:
        st.info("Нет товаров для отображения.")
        return None
    options = lines[["supplier", "sku", "name"]].drop_duplicates(["supplier", "sku"])
    labels = {f"{row.supplier} | {row.sku}": row.name for row in options.itertuples(index=False)}
    picked = st.selectbox("Товар", list(labels), format_func=lambda value: f"{value} — {labels[value]}", key=key)
    return tuple(picked.split(" | ", 1))


def product_tab(result: schema.PipelineResult) -> None:
    data = st.session_state.result_data
    selected = selected_product(data["products"], "product_sku")
    if selected is None:
        return
    supplier, sku = selected
    found = st.session_state.order_lines.query("supplier == @supplier and sku == @sku")
    row = found.iloc[0] if not found.empty else None
    product = data["products"].query("supplier == @supplier and sku == @sku").iloc[0]
    monthly = result.demand_monthly.query("supplier == @supplier and sku == @sku").copy()
    if not monthly.empty:
        monthly["date"] = pd.to_datetime(monthly["month"] + "-01")
        monthly = monthly.set_index("date")
        chart = monthly.rename(columns={"qty_raw": "Продажи", "qty_regular": "Регулярный спрос"})[
            ["Продажи", "Регулярный спрос"]
        ].copy()
        chart["Прогноз"] = float("nan")
        horizon = max(int(row["horizon_days"]), 1) if row is not None else 0
        future_days = pd.date_range(result.as_of + pd.Timedelta(days=1), periods=horizon, freq="D")
        days_by_month = future_days.to_series().groupby(future_days.to_period("M")).size()
        if result.forecast_details is not None:
            curve = result.forecast_details["monthly"].query("supplier == @supplier and sku == @sku and days > 0")
            for point in curve.itertuples():
                chart.loc[pd.Period(point.month, freq="M").to_timestamp(), "Прогноз"] = point.horizon_qty
            st.caption("ML прогнозирует каждый месяц отдельно. На графике — доля спроса за дни горизонта. Единица: " + str(product["unit"]))
            st.dataframe(curve[["month", "prediction", "baseline", "days", "horizon_qty", "source"]].rename(columns={
                "month": "Месяц", "prediction": "Прогноз / полный месяц", "baseline": "Статистика / полный месяц",
                "days": "Дней в горизонте", "horizon_qty": "Спрос за дни горизонта с ростом", "source": "Метод"}), hide_index=True)
        else:
            for month, days in days_by_month.items():
                chart.loc[month.to_timestamp(), "Прогноз"] = float(row["forecast_H"]) * days / horizon
            st.caption("Прогноз на оставшиеся дни горизонта распределён пропорционально дням; это не прогноз полного месяца. Единица: " + str(product["unit"]))
        plot = chart.sort_index().reset_index(names="date").melt("date", var_name="series", value_name="qty").dropna()
        events = monthly.loc[monthly["stockout"] | monthly["oneoff_excluded_qty"].gt(0)].reset_index()
        events["event"] = ["Разовая продажа + дефицит" if r.stockout and r.oneoff_excluded_qty > 0 else ("Дефицит" if r.stockout else "Разовая продажа") for r in events.itertuples()]
        import altair as alt
        base = alt.Chart(plot).mark_line(point=True).encode(x=alt.X("date:T", title="Месяц"), y=alt.Y("qty:Q", title=str(product["unit"])), color=alt.Color("series:N", title="Ряд"), tooltip=["date:T", "series:N", "qty:Q"])
        marks = alt.Chart(events).mark_point(size=150, filled=True).encode(x="date:T", y="qty_raw:Q", shape=alt.Shape("event:N", title="Событие"), color=alt.value("#dc5b26"), tooltip=["date:T", "event:N", "oneoff_excluded_qty:Q", "stockout_uplift_qty:Q"])
        st.altair_chart(base + marks, width="stretch")
        st.dataframe(monthly.loc[monthly["stockout"] | monthly["oneoff_excluded_qty"].gt(0),
                                 ["qty_raw", "oneoff_excluded_qty", "stockout", "stockout_uplift_qty"]],
                     width="stretch")
    flagged = result.sales_flagged
    if not flagged.empty:
        cases = flagged.loc[flagged["supplier"].eq(supplier) & flagged["sku"].eq(sku) & flagged["is_oneoff"]]
        if not cases.empty:
            st.caption("Отмеченные разовые строки")
            st.dataframe(cases[["date", "doc_id", "qty", "oneoff_excess_qty", "oneoff_reason"]], hide_index=True)
    st.caption(f"Кратность поставщика: {product['pack_multiple']:g} {product['unit']}")
    stock = data["stock_now"].query("supplier == @supplier and sku == @sku")
    if not stock.empty:
        st.caption(f"Остаток на {stock.iloc[0]['as_of']}: источник {stock.iloc[0]['source']}")
    if row is None:
        st.info("Товар отсутствует в текущем расчёте заказа: нет положительной базы регулярного спроса. История показана выше.")
        return
    st.write(row["rationale"])
    detail_key = row.to_json(force_ascii=False)
    if row["flags"]:
        st.warning(f"Проверьте данные перед утверждением: {row['flags']}")
    if st.button("Объяснить подробнее", key=f"explain_{supplier}_{sku}"):
        with st.spinner("Готовлю объяснение…"):
            st.session_state.detail_answer = (detail_key, explain_line(row))
    detail = st.session_state.get("detail_answer")
    if detail and detail[0] == detail_key:
        st.write(detail[1].text)
        st.caption(f"Источник: {detail[1].source}")
    if result.forecast_details is not None:
        st.caption("Спрос/день, сезонность и тренд ниже — ориентиры статистического метода, не разложение ML-прогноза. Страховой запас — историческая оценка, не доверительный интервал ML.")
    st.dataframe(pd.DataFrame({"Показатель": ["Спрос/день", "Сезонность", "Тренд", "Рост", "Горизонт",
                                               "Прогноз", "Страховой запас", "Свободный остаток", "В пути",
                                               "Рекомендация"],
                             "Значение": [row["avg_daily_regular"], row["seasonal_index"], row["trend_factor"],
                                         row["growth_factor"], row["horizon_days"], row["forecast_H"],
                                         row["safety_stock"], row["free_qty"], row["in_transit_H"],
                                         row["recommended_qty"]]}), hide_index=True)


def checks_tab(result: schema.PipelineResult, data: dict[str, pd.DataFrame]) -> None:
    if result.forecast_details is not None:
        st.info("Таблица ниже проверяет факторы статистического метода. Качество ML — в блоке «Проверка ML» над вкладками.")
    selected = selected_product(st.session_state.order_lines, "checks_sku")
    if selected is None:
        return
    extra = st.number_input("Добавить в пути (в единицах товара)", 1, 1_000_000, 100)
    if st.button("Сравнить факторы"):
        with st.spinner("Проверяю семь сценариев на реальных данных…"):
            calculate_checks(result, data, selected, extra)
    saved = st.session_state.get("check_scenarios")
    if saved and saved[0] == (selected, extra):
        st.dataframe(pd.DataFrame(saved[1]), hide_index=True, width="stretch")


def calculate_checks(result, data, selected, extra):
    supplier, sku = selected
    enabled = replace(result.params, forecast_method="statistical", as_of=result.as_of, use_oneoff_filter=True, use_stockout_fix=True,
                      use_seasonality=True, use_trend=True, use_in_transit=True)
    baseline = run(data, enabled).order_lines.query("supplier == @supplier and sku == @sku")
    if baseline.empty:
        st.warning("Товар отсутствует в расчёте.")
        return
    base_qty = float(baseline.iloc[0]["recommended_qty"])
    scenarios = [{"Сценарий": "Все факторы", "Рекомендация": base_qty, "Изменение": 0.0}]
    for flag, label in (
        ("use_oneoff_filter", "Без исключения разовых"),
        ("use_stockout_fix", "Без компенсации дефицита"),
        ("use_seasonality", "Без сезонности"),
        ("use_trend", "Без тренда"),
        ("use_in_transit", "Без товара в пути"),
    ):
        variant = run(data, replace(enabled, **{flag: False}))
        found = variant.order_lines.query("supplier == @supplier and sku == @sku")
        qty = float(found.iloc[0]["recommended_qty"]) if not found.empty else 0.0
        scenarios.append({"Сценарий": label, "Рекомендация": qty, "Изменение": qty - base_qty})
    changed = {**data, "in_transit": data["in_transit"].copy()}
    arrival = result.as_of + pd.Timedelta(days=1)
    new_transit = pd.DataFrame([{"supplier": supplier, "sku": sku, "qty": float(extra),
                                 "eta": arrival, "order_ref": "ui-scenario"}])
    changed["in_transit"] = pd.concat([changed["in_transit"], new_transit], ignore_index=True)
    variant = run(changed, enabled)
    found = variant.order_lines.query("supplier == @supplier and sku == @sku")
    qty = float(found.iloc[0]["recommended_qty"]) if not found.empty else 0.0
    scenarios.append({"Сценарий": f"В пути +{extra}", "Рекомендация": qty, "Изменение": qty - base_qty})
    st.session_state.check_scenarios = ((selected, extra), scenarios)


def comparison_tab(result: schema.PipelineResult, data: dict[str, pd.DataFrame]) -> None:
    baseline = data["manager_baseline"]
    if baseline.empty:
        st.info("Таблица менеджера недоступна в демонстрационном наборе.")
        return
    ours = st.session_state.order_lines.query("supplier == 'SE'")[
        ["supplier", "sku", "name", "avg_daily_regular", "free_qty", "recommended_qty"]
    ].rename(columns={"avg_daily_regular": "ours_daily", "free_qty": "ours_free"})
    compare = baseline.merge(ours, on=["supplier", "sku"], how="left")
    # Match the label: arithmetic mean over exactly 12 complete calendar months,
    # including zero months, rather than a deseasonalised daily base times 30.4.
    end = result.as_of.to_period("M")
    periods = pd.period_range(end=end - 1, periods=12, freq="M").astype(str)
    history = result.demand_monthly[result.demand_monthly["month"].isin(periods)]
    averages = history.groupby(["supplier", "sku"])[["qty_raw", "qty_regular"]].sum().div(12)
    compare = compare.merge(averages.rename(columns={"qty_raw": "actual_month_12", "qty_regular": "regular_month_12"}), on=["supplier", "sku"], how="left")
    compare["difference"] = (compare["recommended_qty"] - compare["manager_order"]).abs()
    compare["demand_difference"] = (compare["regular_month_12"] - compare["avg_month_12"]).abs()
    st.caption(f"Наше среднее: {periods[0]} — {periods[-1]}, 12 полных месяцев с нулевыми месяцами. "
               "Факт — накладные; регулярный спрос — после исключений и оценки дефицита. "
               "Период среднего менеджера задаётся его файлом. Пустой «Заказ» не равен нулю.")
    sort = st.selectbox("Сначала наибольшие расхождения", ["Средний спрос", "Количество заказа"])
    show = compare.sort_values("difference" if sort == "Количество заказа" else "demand_difference", ascending=False, na_position="last")
    labels = {"sku": "Код 1С", "name": "Наименование", "avg_month_12": "Среднее менеджера",
              "actual_month_12": "Наш факт / месяц", "regular_month_12": "Наш регулярный спрос / месяц",
              "free_qty": "Остаток менеджера", "ours_free": "Наш остаток", "manager_order": "Заказ менеджера",
              "recommended_qty": "Наша рекомендация", "difference": "Разница заказа",
              "demand_difference": "Разница спроса"}
    st.dataframe(show[list(labels)].rename(columns=labels), hide_index=True, width="stretch")


def oneoffs_tab(result: schema.PipelineResult) -> None:
    if result.sales_flagged.empty:
        st.info("В демонстрационном наборе нет строк накладных.")
        return
    cases = oneoff_report(result.sales_flagged)
    st.metric("Разовых строк", len(cases))
    st.dataframe(cases, hide_index=True, width="stretch")


data: dict[str, pd.DataFrame] | None = None
try:
    fingerprint = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(CLEAN_DIR.glob("*.parquet")))
    data = cached_data(fingerprint)
except (FileNotFoundError, OSError) as exc:
    st.error(f"Нет подготовленных данных: {exc}")
    st.info("Запустите: python -m app.adapters.build --raw datasets")
params = params_sidebar(data)
if st.sidebar.button("Рассчитать", type="primary", disabled=(data is None)):
    try:
        with st.spinner("Расчёт рекомендаций по реальным Excel…"):
            result = run(data, params)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    st.session_state.result = result
    st.session_state.order_lines = apply_saved(result.order_lines, result.as_of, STATE_FILE)
    st.session_state.result_data = data
    st.session_state.result_fingerprint = fingerprint
    st.session_state.calculation_id = st.session_state.get("calculation_id", 0) + 1
    st.session_state.pop("check_scenarios", None)
    st.session_state.pop("detail_answer", None)
    st.session_state.pop("supplier_answer", None)
    st.session_state.pop("assistant_found", None)
    st.session_state.pop("assistant_answer", None)
    st.session_state.pop("assistant_answer_context", None)
    st.session_state.pop("assistant_answer_key", None)
    st.session_state.pop("pair_review", None)

result = st.session_state.get("result")
if result is None:
    st.info("Выберите параметры и нажмите «Рассчитать».")
    st.stop()
if st.session_state.get("result_fingerprint") != fingerprint:
    st.info("Подготовленные данные изменились. Нажмите «Рассчитать» для нового расчёта.")
    st.stop()
data = st.session_state.result_data
if params != result.params:
    st.warning("Параметры изменены. Нажмите «Рассчитать», чтобы обновить заказ и проверки.")
st.caption(f"Расчёт на {result.as_of.date()} · реальные данные Excel · {len(result.sales_flagged):,} строк продаж")
if result.forecast_details is not None:
    meta = result.forecast_details["metadata"]
    st.success(f"Прогноз: обученный ML · {meta['model']} · обучение по {meta['trained_through']} · {meta['training_rows']:,} примеров")
    if result.forecast_details["monthly"].query("days > 0")["source"].ne("ML").any():
        st.warning("ML обучен на 1–3 месяца вперёд от конца последнего полного месяца. Более дальние месяцы рассчитаны статистически и помечены в карточке товара.")
    with st.expander("Проверка ML на отложенных месяцах"):
        report = meta["evaluation"]
        st.write("Ошибка — средняя абсолютная ошибка, делённая на предыдущий средний объём товара. Меньше — лучше; это не процент точности.")
        st.dataframe(pd.DataFrame(report["folds"]), hide_index=True)
        st.dataframe(pd.DataFrame(report["by_supplier_unit"]), hide_index=True)
        worse = [f"{g['supplier']} ({g['unit']})" for g in report["by_supplier_unit"]
                 if g["ml_wape"] is not None and g["baseline_wape"] is not None and g["ml_wape"] > g["baseline_wape"]]
        if worse:
            st.warning("По объёмно-взвешенной ошибке WAPE ML хуже статистики: " + ", ".join(worse)
                       + ". Общий выигрыш по нормированной ошибке не означает улучшение каждой группы.")
        st.caption("Сравнение со статистическим алгоритмом без недатированных коэффициентов компании. Проверяются очищенные продажи при положительном начальном остатке; истинный упущенный спрос неизвестен. Горизонты проверок частично пересекаются.")
        st.write(f"Средняя ошибка: статистика {report['overall']['baseline_scaled_mae']:.3f}; ML {report['overall']['ml_scaled_mae']:.3f}.")
        if report["overall"]["ml_scaled_mae"] >= report["overall"]["baseline_scaled_mae"]:
            st.warning("На проверочных периодах ML не улучшил выбранную метрику. Рекомендуется статистический метод до следующего обучения/проверки.")
        if "last_month_check" in report:
            held = report["last_month_check"]
            st.write(f"Последний месяц проверки {held['month']}: статистика {held['baseline_scaled_mae']:.3f}; ML {held['ml_scaled_mae']:.3f}.")
else:
    st.caption("Прогноз: статистический. Обучаемая модель доступна в параметре «Метод прогноза».")
tab_order, tab_product, tab_checks, tab_manager, tab_oneoffs, tab_assist = st.tabs(
    ["Заказ", "Товар", "Проверки", "Сравнение с менеджером", "Разовые заказы", "Ассистент"]
)
with tab_order:
    order_tab(result, data)
with tab_product:
    product_tab(result)
with tab_checks:
    checks_tab(result, data)
with tab_manager:
    comparison_tab(result, data)
with tab_oneoffs:
    oneoffs_tab(result)
with tab_assist:
    from app.ui import tab_assistant
    tab_assistant.render(result)
