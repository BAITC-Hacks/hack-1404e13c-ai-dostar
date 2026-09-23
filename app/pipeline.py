"""End-to-end calculation. Owner: Person 2 «Расчет».

    from app.pipeline import run
    result = run()                      # data from data/clean, default Params
    result.order_lines                  # ORDER_LINES
"""

from __future__ import annotations

import pandas as pd

from app import schema
from app.adapters import load_clean
from app.engine import demand, explain, forecast, lifecycle, oneoffs, replenish


def run(data: dict[str, pd.DataFrame] | None = None, params: schema.Params | None = None) -> schema.PipelineResult:
    data = data if data is not None else load_clean()
    params = params or schema.Params()
    if params.forecast_method not in {"statistical", "ml"}:
        raise ValueError("Unknown forecast_method")
    if params.forecast_method == "ml" and not all((params.use_oneoff_filter, params.use_stockout_fix,
                                                  params.use_seasonality, params.use_trend)):
        raise ValueError("ML обучен с обработкой разовых продаж и дефицитов. Для отключения факторов выберите статистический прогноз.")
    as_of = params.as_of or data["sales_lines"]["date"].max().normalize()

    sales_flagged = oneoffs.flag_oneoffs(data["sales_lines"], params)
    demand_monthly = demand.build_monthly(sales_flagged, data["stock_monthly"], params, as_of,
                                         seasonality=data["seasonality"])
    fc = forecast.forecast(demand_monthly, data["monthly_sales"], data["seasonality"],
                           data["products"], params, as_of)
    details = None
    if params.forecast_method == "ml":
        from app.ml.model import forecast_horizon
        fc, details = forecast_horizon(data, params, as_of, fc)
    order_lines = replenish.calc(fc, demand_monthly, data["stock_now"], data["in_transit"],
                                 data["products"], params, as_of)
    forecast_description = None
    if details is not None:
        model_date = details["metadata"]["trained_through"]
        model_id = details["metadata"]["model_id"]
        mixed = details["monthly"].query("days > 0")["source"].ne("ML").any()
        method_label = "ML + статистика дальних месяцев" if mixed else "ML-прогноз"
        forecast_description = f"{method_label} (градиентный бустинг {model_id}, обучение по {model_date})"
    order_lines = explain.add_rationale(order_lines, data["products"], sales_flagged,
                                        forecast_description=forecast_description)
    signals = lifecycle.detect(demand_monthly, data["products"], as_of)
    order_lines = lifecycle.annotate(order_lines, signals)
    order_lines = order_lines.sort_values(["supplier", "urgency", "recommended_qty"],
                                          ascending=[True, True, False], ignore_index=True)
    return schema.PipelineResult(order_lines, fc, demand_monthly, sales_flagged, params, as_of, details, signals)
