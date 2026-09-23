"""Purchasing demo: streamlit run app/ui/app.py."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import schema  # noqa: E402
from app.adapters import load_clean  # noqa: E402
from app.copilot import explain_line  # noqa: E402
from app.engine.oneoffs import report as oneoff_report  # noqa: E402
from app.export import to_csv, to_table, to_xlsx  # noqa: E402
from app.mock import mock_order_lines  # noqa: E402
from app.pipeline import run  # noqa: E402
from app.ui.state import STATE_FILE, apply_saved, approve_supplier, revoke_line, validate_line  # noqa: E402


st.set_page_config(page_title="Заказы поставщикам", layout="wide")
st.title("Рекомендованные заказы поставщикам")


@st.cache_data(show_spinner="Загрузка подготовленных данных…")
def cached_data() -> dict[str, pd.DataFrame]:
    return load_clean()


def params_sidebar(data: dict[str, pd.DataFrame] | None) -> schema.Params:
    st.sidebar.header("Параметры расчёта")
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
        "use_oneoff_filter": st.sidebar.toggle("Исключать разовые заказы", True),
        "use_stockout_fix": st.sidebar.toggle("Оценивать спрос при дефиците", True),
        "use_seasonality": st.sidebar.toggle("Сезонность", True),
        "use_trend": st.sidebar.toggle("Тренд", True),
        "use_in_transit": st.sidebar.toggle("Товар в пути", True),
    }
    return schema.Params(
        lead_time_days={"IEK": int(lead_iek), "SE": int(lead_se)},
        review_period_days=int(review), service_level=float(service),
        growth_pct=growth, **flags,
    )


def run_mock() -> tuple[schema.PipelineResult, dict[str, pd.DataFrame]]:
    lines = mock_order_lines()
    as_of = pd.Timestamp("2026-09-22")
    demand = lines[["supplier", "sku"]].copy()
    demand["month"] = "2026-09"
    demand["qty_raw"] = lines["avg_daily_regular"] * 30
    demand["qty_regular"] = demand["qty_raw"]
    demand["stockout"] = lines["stockout_months"].gt(0)
    demand["oneoff_excluded_qty"] = lines["oneoff_excluded_qty"]
    demand["stockout_uplift_qty"] = 0.0
    demand["days_in_month_observed"] = 22
    products = lines[["supplier", "sku", "name", "unit", "category"]].copy()
    products["supplier_article"] = products["sku"]
    products["pack_multiple"] = 1.0
    baseline = pd.DataFrame(columns=list(schema.MANAGER_BASELINE))
    return (
        schema.PipelineResult(lines, pd.DataFrame(), demand, schema.empty(schema.SALES_FLAGGED),
                              schema.Params(), as_of),
        {"products": products, "manager_baseline": baseline, "in_transit": schema.empty(schema.IN_TRANSIT)},
    )


def order_tab(result: schema.PipelineResult, data: dict[str, pd.DataFrame], mock: bool) -> None:
    lines = st.session_state.order_lines
    suppliers = sorted(lines["supplier"].dropna().unique().tolist())
    if not suppliers:
        st.info("Нет позиций к заказу при выбранных параметрах.")
        return
    chosen = st.selectbox("Поставщик", suppliers)
    subset = lines[lines["supplier"].eq(chosen)]
    metrics = st.columns(3)
    metrics[0].metric("Позиций к заказу", int(subset["final_qty"].gt(0).sum()))
    metrics[1].metric("Критичных", int((subset["urgency"].eq("critical") & subset["final_qty"].gt(0)).sum()))
    metrics[2].metric("Утверждено", int(subset["status"].eq("approved").sum()))

    categories = sorted(subset["category"].dropna().unique().tolist())
    selected_categories = st.multiselect("Категория", categories, default=categories)
    urgency = st.multiselect("Срочность", list(schema.URGENCY_LEVELS), default=list(schema.URGENCY_LEVELS))
    visible = subset[subset["category"].isin(selected_categories) & subset["urgency"].isin(urgency)].copy()
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
            "final_qty": st.column_config.NumberColumn("Итоговое количество", min_value=0, step=1),
            "recommended_qty": st.column_config.NumberColumn("Рекомендация", disabled=True),
            "override_reason": st.column_config.TextColumn("Причина изменения"),
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
        old_reason = str(current.at[key, "override_reason"])
        new_reason = str(row["override_reason"])
        if new_qty != old_qty or new_reason != old_reason:
            if current.at[key, "status"] == "approved":
                revoke_line(supplier, sku, STATE_FILE.with_name("mock_approvals.json") if mock else STATE_FILE)
            current.at[key, "final_qty"] = new_qty
            current.at[key, "override_reason"] = new_reason
            current.at[key, "status"] = "draft"
    st.session_state.order_lines = current.reset_index(drop=True)
    supplier_rows = st.session_state.order_lines.query("supplier == @chosen")
    problems = [f"{row['sku']}: {issue}" for _, row in supplier_rows.iterrows()
                if (issue := validate_line(row))]
    if problems:
        st.warning("\n".join(problems[:8]))

    if st.button("Утвердить заказ поставщика", disabled=bool(problems), type="primary"):
        try:
            st.session_state.order_lines = approve_supplier(
                st.session_state.order_lines, chosen, result.as_of,
                STATE_FILE.with_name("mock_approvals.json") if mock else STATE_FILE,
            )
            st.success("Заказ утверждён и сохранён локально.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    st.caption("Утверждение сохраняется в data/state/approvals.json. Отправки поставщику нет.")

    # Re-read the persisted approvals for every download. Another browser
    # session may have revoked or changed an order since this page was drawn.
    approval_file = STATE_FILE.with_name("mock_approvals.json") if mock else STATE_FILE
    export_lines = apply_saved(result.order_lines, result.as_of, approval_file)
    shown = st.session_state.order_lines.set_index(["supplier", "sku"])
    saved = export_lines.set_index(["supplier", "sku"])
    if not shown[["status", "final_qty"]].equals(saved[["status", "final_qty"]]):
        st.warning("Сохранённый заказ изменился в другой сессии или имеет несохранённые правки. "
                   "Экспорт использует только актуальные утверждения; пересчитайте для обновления таблицы.")
    approved = to_table(export_lines, data["products"], chosen)
    if not approved.empty:
        left, right = st.columns(2)
        left.download_button("Скачать XLSX", to_xlsx(export_lines, data["products"], chosen),
                             file_name=f"order_{chosen}_{result.as_of.date()}.xlsx")
        right.download_button("Скачать CSV", to_csv(export_lines, data["products"], chosen),
                              file_name=f"order_{chosen}_{result.as_of.date()}.csv", mime="text/csv")
    if mock:
        st.info("Показаны демонстрационные строки. Для реальных заказов выключите «Мок-данные» и пересчитайте.")


def selected_product(lines: pd.DataFrame, key: str) -> tuple[str, str] | None:
    if lines.empty:
        st.info("Нет товаров для отображения.")
        return None
    options = lines[["supplier", "sku", "name"]].drop_duplicates(["supplier", "sku"])
    labels = {f"{row.supplier} | {row.sku}": row.name for row in options.itertuples(index=False)}
    picked = st.selectbox("Товар", list(labels), format_func=lambda value: f"{value} — {labels[value]}", key=key)
    return tuple(picked.split(" | ", 1))


def product_tab(result: schema.PipelineResult) -> None:
    selected = selected_product(st.session_state.order_lines, "product_sku")
    if selected is None:
        return
    supplier, sku = selected
    row = st.session_state.order_lines.set_index(["supplier", "sku"]).loc[(supplier, sku)]
    monthly = result.demand_monthly.query("supplier == @supplier and sku == @sku").copy()
    if not monthly.empty:
        monthly["date"] = pd.to_datetime(monthly["month"] + "-01")
        monthly = monthly.set_index("date")
        chart = monthly.rename(columns={"qty_raw": "Продажи", "qty_regular": "Регулярный спрос"})[
            ["Продажи", "Регулярный спрос"]
        ].copy()
        chart["Прогноз"] = float("nan")
        horizon = max(int(row["horizon_days"]), 1)
        future_days = pd.date_range(result.as_of + pd.Timedelta(days=1), periods=horizon, freq="D")
        days_by_month = future_days.to_series().groupby(future_days.to_period("M")).size()
        for month, days in days_by_month.items():
            chart.loc[month.to_timestamp(), "Прогноз"] = float(row["forecast_H"]) * days / horizon
        st.line_chart(chart.sort_index())
        st.dataframe(monthly.loc[monthly["stockout"] | monthly["oneoff_excluded_qty"].gt(0),
                                 ["qty_raw", "oneoff_excluded_qty", "stockout", "stockout_uplift_qty"]],
                     width="stretch")
    st.write(row["rationale"])
    if st.button("Объяснить подробнее", key=f"explain_{supplier}_{sku}"):
        with st.spinner("Готовлю объяснение…"):
            st.session_state.detail_answer = (selected, explain_line(row))
    detail = st.session_state.get("detail_answer")
    if detail and detail[0] == selected:
        st.write(detail[1].text)
        st.caption(f"Источник: {detail[1].source}")
    st.dataframe(pd.DataFrame({"Показатель": ["Спрос/день", "Сезонность", "Тренд", "Рост", "Горизонт",
                                               "Прогноз", "Страховой запас", "Свободный остаток", "В пути",
                                               "Рекомендация"],
                             "Значение": [row["avg_daily_regular"], row["seasonal_index"], row["trend_factor"],
                                         row["growth_factor"], row["horizon_days"], row["forecast_H"],
                                         row["safety_stock"], row["free_qty"], row["in_transit_H"],
                                         row["recommended_qty"]]}), hide_index=True)
    flagged = result.sales_flagged
    if not flagged.empty:
        cases = flagged.loc[flagged["supplier"].eq(supplier) & flagged["sku"].eq(sku) & flagged["is_oneoff"]]
        if not cases.empty:
            st.caption("Отмеченные разовые строки")
            st.dataframe(cases[["date", "doc_id", "qty", "oneoff_excess_qty", "oneoff_reason"]], hide_index=True)


def checks_tab(result: schema.PipelineResult, data: dict[str, pd.DataFrame], mock: bool) -> None:
    if mock:
        st.info("Проверки факторов доступны после расчёта на реальных данных.")
        return
    selected = selected_product(st.session_state.order_lines, "checks_sku")
    if selected is None:
        return
    supplier, sku = selected
    extra = st.number_input("Добавить в пути, шт", 1, 1_000_000, 100)
    if st.button("Сравнить факторы"):
        enabled = replace(result.params, use_oneoff_filter=True, use_stockout_fix=True,
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
        st.session_state.check_scenarios = (selected, scenarios)
    saved = st.session_state.get("check_scenarios")
    if saved and saved[0] == selected:
        st.dataframe(pd.DataFrame(saved[1]), hide_index=True, width="stretch")


def comparison_tab(result: schema.PipelineResult, data: dict[str, pd.DataFrame]) -> None:
    baseline = data["manager_baseline"]
    if baseline.empty:
        st.info("Таблица менеджера недоступна в демонстрационном наборе.")
        return
    ours = st.session_state.order_lines.query("supplier == 'SE'")[
        ["supplier", "sku", "name", "avg_daily_regular", "free_qty", "recommended_qty"]
    ].rename(columns={"avg_daily_regular": "ours_daily", "free_qty": "ours_free"})
    compare = baseline.merge(ours, on=["supplier", "sku"], how="left")
    compare["ours_month_12"] = compare["ours_daily"] * 30.4
    compare["difference"] = (compare["recommended_qty"] - compare["manager_order"]).abs()
    st.caption("В исходном файле поле «Заказ» может быть пустым. Такие строки не считаются расхождением по заказу.")
    show = compare.sort_values("difference", ascending=False, na_position="last")
    st.dataframe(show[["sku", "name", "avg_month_12", "ours_month_12", "free_qty", "ours_free",
                       "manager_order", "recommended_qty", "difference"]], hide_index=True, width="stretch")


def oneoffs_tab(result: schema.PipelineResult) -> None:
    if result.sales_flagged.empty:
        st.info("В демонстрационном наборе нет строк накладных.")
        return
    cases = oneoff_report(result.sales_flagged)
    st.metric("Разовых строк", len(cases))
    st.dataframe(cases, hide_index=True, width="stretch")


mock = st.sidebar.toggle("Мок-данные", value=False)
data: dict[str, pd.DataFrame] | None = None
if not mock:
    try:
        data = cached_data()
    except (FileNotFoundError, OSError) as exc:
        st.error(f"Нет подготовленных данных: {exc}")
        st.info("Запустите: python -m app.adapters.build --raw datasets")
params = params_sidebar(data)
if st.sidebar.button("Рассчитать", type="primary", disabled=(data is None and not mock)):
    if mock:
        result, mock_data = run_mock()
        data = mock_data
    else:
        with st.spinner("Расчёт рекомендаций…"):
            result = run(data, params)
    st.session_state.result = result
    approval_file = STATE_FILE.with_name("mock_approvals.json") if mock else STATE_FILE
    st.session_state.order_lines = apply_saved(result.order_lines, result.as_of, approval_file)
    st.session_state.result_data = data
    st.session_state.result_mock = mock
    st.session_state.calculation_id = st.session_state.get("calculation_id", 0) + 1
    st.session_state.pop("check_scenarios", None)
    st.session_state.pop("detail_answer", None)

result = st.session_state.get("result")
if result is None:
    st.info("Выберите параметры и нажмите «Рассчитать».")
    st.stop()
if st.session_state.result_mock != mock:
    st.info("Режим данных изменён. Нажмите «Рассчитать» для нового расчёта.")
    st.stop()
data = st.session_state.result_data
st.caption(f"Расчёт на {result.as_of.date()} · {'демонстрационные' if mock else 'реальные'} данные")
tab_order, tab_product, tab_checks, tab_manager, tab_oneoffs = st.tabs(
    ["Заказ", "Товар", "Проверки", "Сравнение с менеджером", "Разовые заказы"]
)
with tab_order:
    order_tab(result, data, mock)
with tab_product:
    product_tab(result)
with tab_checks:
    checks_tab(result, data, mock)
with tab_manager:
    comparison_tab(result, data)
with tab_oneoffs:
    oneoffs_tab(result)
