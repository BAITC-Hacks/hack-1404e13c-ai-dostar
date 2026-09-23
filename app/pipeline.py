"""End-to-end calculation. Owner: Person 2 «Расчет».

    from app.pipeline import run
    result = run()                      # data from data/clean, default Params
    result.order_lines                  # ORDER_LINES
"""

from __future__ import annotations

import pandas as pd

from app import schema
from app.adapters import load_clean
from app.engine import demand, explain, forecast, oneoffs, replenish


def run(data: dict[str, pd.DataFrame] | None = None, params: schema.Params | None = None) -> schema.PipelineResult:
    data = data if data is not None else load_clean()
    params = params or schema.Params()
    as_of = params.as_of or data["sales_lines"]["date"].max().normalize()

    sales_flagged = oneoffs.flag_oneoffs(data["sales_lines"], params)
    demand_monthly = demand.build_monthly(sales_flagged, data["stock_monthly"], params, as_of,
                                         seasonality=data["seasonality"])
    fc = forecast.forecast(demand_monthly, data["monthly_sales"], data["seasonality"],
                           data["products"], params, as_of)
    order_lines = replenish.calc(fc, demand_monthly, data["stock_now"], data["in_transit"],
                                 data["products"], params, as_of)
    order_lines = explain.add_rationale(order_lines, data["products"], sales_flagged)
    order_lines = order_lines.sort_values(["supplier", "urgency", "recommended_qty"],
                                          ascending=[True, True, False], ignore_index=True)
    return schema.PipelineResult(order_lines, fc, demand_monthly, sales_flagged, params, as_of)
