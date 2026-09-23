"""Human-readable rationale per order line. Owner: Person 2 «Расчет» (task 2.3)."""

from __future__ import annotations

import pandas as pd


def _fmt(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ") if abs(x) >= 10 else f"{x:.1f}"


def _line(r, pack: float, oneoff: str) -> str:
    parts = [f"Регулярный спрос {_fmt(r.avg_daily_regular)} {r.unit}/день"]
    notes = []
    if r.oneoff_excluded_qty > 0:
        notes.append(f"исключено разовых {_fmt(r.oneoff_excluded_qty)}{oneoff}")
    if r.stockout_uplift_qty > 0:
        notes.append(f"+{_fmt(r.stockout_uplift_qty)} за {int(r.stockout_months)} мес. дефицита")
    if notes:
        parts[0] += f" ({'; '.join(notes)})"
    factors = [f"{name} ×{v:.2f}" for name, v in
               (("сезонность", r.seasonal_index), ("тренд", r.trend_factor), ("рост", r.growth_factor))
               if abs(v - 1) >= 0.01]
    if factors:
        parts.append(", ".join(factors))
    parts.append(f"на {r.horizon_days} дн. нужно {_fmt(r.forecast_H)} + страховой {_fmt(r.safety_stock)}")
    parts.append(f"есть {_fmt(r.free_qty)}, в пути {_fmt(r.in_transit_H)}")
    text = "; ".join(parts) + f" → заказ {_fmt(r.recommended_qty)}"
    if pack > 1 and r.recommended_qty > 0:
        text += f" (кратн. {_fmt(pack)})"
    if "estimated_stock" in str(r.flags):
        text += ". Остаток оценочный: начало месяца минус продажи, поступления неизвестны; требуется сверка"
    return text


def _largest_oneoffs(sales_flagged: pd.DataFrame | None) -> dict:
    """(supplier, sku) -> ', крупнейшая 210 000 от 09.06.2025, накл. 20000064179'."""
    if sales_flagged is None or sales_flagged.empty:
        return {}
    cases = sales_flagged[sales_flagged["is_oneoff"]].sort_values("qty", ascending=False)
    top = cases.drop_duplicates(["supplier", "sku"])
    return {(r.supplier, r.sku): f": крупнейшая {_fmt(r.qty)} от {r.date:%d.%m.%Y}, накл. {r.doc_id}"
            for r in top.itertuples()}


def add_rationale(order_lines: pd.DataFrame, products: pd.DataFrame | None = None,
                  sales_flagged: pd.DataFrame | None = None) -> pd.DataFrame:
    """Fill `rationale` from calculated values, keeping stock uncertainty visible.

    Optional `products` adds the supplier pack multiple, `sales_flagged` the largest
    excluded one-off line (date and invoice) for SKUs with excluded sales.
    """
    out = order_lines.copy()
    packs = {} if products is None else products.set_index(["supplier", "sku"])["pack_multiple"].to_dict()
    oneoffs = _largest_oneoffs(sales_flagged)
    out["rationale"] = [_line(r, float(packs.get((r.supplier, r.sku), 1.0) or 1.0), oneoffs.get((r.supplier, r.sku), ""))
                        for r in out.itertuples()]
    return out
