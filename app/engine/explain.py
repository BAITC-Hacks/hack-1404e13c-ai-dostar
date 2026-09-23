"""Human-readable rationale per order line. Owner: Person 2 «Расчет» (task 2.3)."""

from __future__ import annotations

import pandas as pd


def _fmt(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ") if abs(x) >= 10 else f"{x:.1f}"


def _line(r) -> str:
    parts = [f"Регулярный спрос {_fmt(r.avg_daily_regular)} {r.unit}/день"]
    notes = []
    if r.oneoff_excluded_qty > 0:
        notes.append(f"исключено разовых {_fmt(r.oneoff_excluded_qty)}")
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
    if "estimated_stock" in str(r.flags):
        text += ". Остаток оценочный: начало месяца минус продажи, поступления неизвестны; требуется сверка"
    return text


def add_rationale(order_lines: pd.DataFrame) -> pd.DataFrame:
    """Fill `rationale` from calculated values, keeping stock uncertainty visible."""
    out = order_lines.copy()
    out["rationale"] = [_line(r) for r in out.itertuples()]
    return out
