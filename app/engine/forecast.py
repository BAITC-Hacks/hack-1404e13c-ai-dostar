"""Demand forecast for the replenishment horizon. Owner: Person 2 «Расчет» (task 2.1).

Method (details in docs/methodology-forecast.md):
1. History per SKU: regular demand from invoices (2025+) with the 2024 monthly report
   rescaled to the invoice level in front of it.
2. Seasonal index per calendar month: ratio to a centred 12-month moving average,
   averaged over years, shrunk to the product group and then to the company profile.
3. Base level: mean deseasonalised demand of the last 12 full months.
4. Trend: slope of the deseasonalised last 12 months, used only when the growth is
   sustained (slope and half-year comparison agree), damped and capped.
5. forecast_H = base/day x H x seasonal index of the horizon days x trend x growth.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app import schema

KEYS = ["supplier", "sku"]
BASE_MONTHS = 12
DAYS_PER_MONTH = 30.4
SKU_SHRINK = 24  # w_sku = nonzero_months / (nonzero_months + SKU_SHRINK)
GROUP_SHRINK = 12  # same for the product group against the company profile
SEASONAL_CLIP = (0.4, 2.5)
TREND_DAMPING = 0.5
TREND_CLIP = (0.8, 1.25)
TREND_MIN_NONZERO = 8  # of the last 12 months


def _history(demand_monthly: pd.DataFrame, monthly_sales: pd.DataFrame, current: str) -> pd.DataFrame:
    """SKU x month matrix of full months: rescaled report before invoices, then qty_regular."""
    reg = demand_monthly[demand_monthly["month"] < current].pivot_table(
        index=KEYS, columns="month", values="qty_regular", aggfunc="sum")
    rep = monthly_sales[monthly_sales["month"] < current].pivot_table(
        index=KEYS, columns="month", values="qty", aggfunc="sum").reindex(reg.index).fillna(0).clip(lower=0)
    overlap = [m for m in reg.columns if m in rep.columns]
    rep_sum = rep[overlap].sum(axis=1)
    scale = (reg[overlap].sum(axis=1) / rep_sum.where(rep_sum > 0)).fillna(1.0).clip(0.2, 5.0)
    early = rep[[m for m in rep.columns if m < reg.columns.min()]].mul(scale, axis=0)
    return pd.concat([early, reg], axis=1).fillna(0).clip(lower=0)


def _shape(matrix: pd.DataFrame) -> pd.DataFrame:
    """Rows x 12 calendar-month seasonal ratios (NaN where not observable), mean 1."""
    cma = matrix.T.rolling(12, center=True, min_periods=12).mean().T
    ratio = (matrix / cma.where(cma > 0)).clip(0, 3)
    months = pd.to_datetime(pd.Index(ratio.columns) + "-01").month
    cal = ratio.T.groupby(months).mean().T.reindex(columns=range(1, 13))
    return cal.div(cal.mean(axis=1), axis=0)


def _company_profile(seasonality: pd.DataFrame) -> pd.DataFrame:
    prof = seasonality.pivot_table(index="supplier", columns="month_num", values="coef").reindex(columns=range(1, 13))
    return prof.div(prof.mean(axis=1), axis=0).fillna(1.0)


def seasonal_indices(history: pd.DataFrame, products: pd.DataFrame, seasonality: pd.DataFrame) -> pd.DataFrame:
    """(supplier, sku) x 12 calendar months, blended SKU -> group -> company, mean 1."""
    company = _company_profile(seasonality)
    groups = products.set_index(KEYS)["category"].reindex(history.index).fillna("прочее")
    group_hist = history.groupby([history.index.get_level_values("supplier"), groups.values]).sum()
    group_shape = _shape(group_hist)
    group_w = (group_hist > 0).sum(axis=1) / ((group_hist > 0).sum(axis=1) + GROUP_SHRINK)
    group_company = company.reindex(group_shape.index.get_level_values(0)).set_axis(group_shape.index)
    group_idx = (group_shape.mul(group_w, axis=0) + group_company.mul(1 - group_w, axis=0)).fillna(group_company)

    prior = group_idx.reindex(list(zip(history.index.get_level_values("supplier"), groups.values)))
    prior = prior.set_axis(history.index)
    sku_w = (history > 0).sum(axis=1) / ((history > 0).sum(axis=1) + SKU_SHRINK)
    idx = (_shape(history).mul(sku_w, axis=0) + prior.mul(1 - sku_w, axis=0)).fillna(prior).fillna(1.0)
    idx = idx.clip(*SEASONAL_CLIP)
    return idx.div(idx.mean(axis=1), axis=0)


def _horizon_weights(as_of: pd.Timestamp, horizon_days: int) -> np.ndarray:
    """Share of the horizon's days falling into each calendar month (12-vector)."""
    days = pd.date_range(as_of + pd.Timedelta(days=1), periods=horizon_days, freq="D")
    return np.bincount(days.month - 1, minlength=12) / horizon_days


def _trend(deseason: pd.DataFrame, nonzero: pd.Series, months_ahead: pd.Series) -> pd.Series:
    """Damped, capped trend factor; 1.0 unless growth/decline is sustained."""
    y = deseason.to_numpy()
    t = np.arange(y.shape[1]) - (y.shape[1] - 1) / 2
    mean = y.mean(axis=1)
    slope = (y * t).sum(axis=1) / (t ** 2).sum()
    half = y.shape[1] // 2
    halves = y[:, half:].mean(axis=1) - y[:, :half].mean(axis=1)
    sustained = (np.sign(slope) == np.sign(halves)) & (nonzero.to_numpy() >= TREND_MIN_NONZERO) & (mean > 0)
    target_t = t[-1] + months_ahead.to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = (mean + slope * target_t) / mean
    factor = np.clip(1 + TREND_DAMPING * (raw - 1), *TREND_CLIP)
    return pd.Series(np.where(sustained, factor, 1.0), index=deseason.index)


def forecast(demand_monthly: pd.DataFrame, monthly_sales: pd.DataFrame, seasonality: pd.DataFrame,
             products: pd.DataFrame, params: schema.Params, as_of: pd.Timestamp) -> pd.DataFrame:
    """DEMAND_MONTHLY -> FORECAST."""
    current = as_of.strftime("%Y-%m")
    history = _history(demand_monthly, monthly_sales, current)
    last = sorted(history.columns)[-BASE_MONTHS:]
    recent = history[last]
    last_months = pd.to_datetime(pd.Index(last) + "-01").month

    if params.use_seasonality:
        idx = seasonal_indices(history, products, seasonality)
    else:
        idx = pd.DataFrame(1.0, index=history.index, columns=range(1, 13))
    recent_idx = idx[list(last_months)].to_numpy()
    deseason = recent / recent_idx
    base_monthly = deseason.mean(axis=1)

    out = pd.DataFrame(index=history.index)
    out["horizon_days"] = (out.index.get_level_values("supplier").map(params.lead_time_days)
                           .fillna(30).astype(int) + params.review_period_days)
    weights = {h: _horizon_weights(as_of, h) for h in out["horizon_days"].unique()}
    horizon_w = np.vstack([weights[h] for h in out["horizon_days"]])
    out["seasonal_index"] = (idx.to_numpy() * horizon_w).sum(axis=1)

    if params.use_trend:
        end_of_history = pd.Period(last[-1], freq="M").end_time.normalize()
        mid_horizon_days = (as_of - end_of_history).days + out["horizon_days"] / 2
        out["trend_factor"] = _trend(deseason, (recent > 0).sum(axis=1), mid_horizon_days / DAYS_PER_MONTH)
    else:
        out["trend_factor"] = 1.0

    category = products.set_index(KEYS)["category"].reindex(out.index)
    out["growth_factor"] = 1 + category.map(params.growth_pct).fillna(0.0).to_numpy() / 100

    # Robust residual spread: one leftover spike should not inflate safety stock.
    resid = recent - base_monthly.to_numpy()[:, None] * recent_idx
    # IQR uses the central half of the residual distribution. On a short monthly
    # window, nested medians (MAD) can jump when one ordinary-sized sale moves
    # the centre, amplifying a small demand change into a large safety-stock jump.
    iqr = resid.quantile(0.75, axis=1) - resid.quantile(0.25, axis=1)
    sigma_monthly = (iqr / 1.349).where(iqr > 0, resid.std(axis=1, ddof=0) * 0.5)
    out["sigma_daily"] = sigma_monthly / np.sqrt(DAYS_PER_MONTH)

    out["avg_daily_regular"] = base_monthly / DAYS_PER_MONTH
    out["forecast_H"] = (out["avg_daily_regular"] * out["horizon_days"] * out["seasonal_index"]
                         * out["trend_factor"] * out["growth_factor"])
    return schema.conform(out.reset_index(), schema.FORECAST, "forecast")
