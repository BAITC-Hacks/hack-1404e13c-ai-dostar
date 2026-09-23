"""A pooled gradient-boosted demand model, trained across products.

Every training origin has its own causally rebuilt cleaning/seasonal history.
The target is observed sales minus one-off excess in months with positive
opening stock, never the unobservable stockout uplift. Current inventory and
future deliveries are not features: those belong to replenishment.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from app import schema
from app.adapters import CLEAN_DIR
from app.engine import demand, forecast, oneoffs

MODEL_DIR = Path(__file__).resolve().parents[2] / "data/models"
MODEL_PATH = MODEL_DIR / "demand.joblib"
FORMAT_VERSION = 1
MAX_LEAD = 3
KEYS = ["supplier", "sku"]
CATEGORICAL = ["supplier", "category", "unit"]
FEATURES = CATEGORICAL + [
    "log_scale", "lag_1", "lag_2", "lag_3", "lag_6", "lag_12",
    "mean_3", "mean_6", "nonzero_12", "cv_12", "baseline_ratio",
    "seasonal_index", "trend_factor", "month_sin", "month_cos", "lead",
]


def neutral_seasonality(data):
    """Undated partner coefficients may include the holdout: exclude them.

SKU/group seasonal patterns are still estimated from each available prefix.
"""
    result = data["seasonality"].copy()
    result["coef"] = 1.0
    return result


def snapshot(data, month: pd.Period):
    """Recompute ALL cleaning on the prefix, never slice a globally cleaned series."""
    cutoff = month.end_time.normalize()
    params = schema.Params(as_of=cutoff)
    sales = data["sales_lines"].loc[data["sales_lines"]["date"] < month.end_time].copy()
    stocks = data["stock_monthly"].loc[data["stock_monthly"]["month"] <= str(month)]
    flagged = oneoffs.flag_oneoffs(sales, params)
    return demand.build_monthly(flagged, stocks, params, cutoff,
                                seasonality=neutral_seasonality(data))


def features(monthly, data, origin: pd.Period, target: pd.Period):
    """Features depend exclusively on months <= origin; output one row per SKU."""
    monthly = monthly.loc[monthly["month"] <= str(origin)]
    reports = data["monthly_sales"].loc[data["monthly_sales"]["month"] <= str(origin)]
    params = schema.Params(lead_time_days={"IEK": target.days_in_month, "SE": target.days_in_month},
                           review_period_days=0)
    base = forecast.forecast(monthly, reports, neutral_seasonality(data), data["products"],
                             params, (target - 1).end_time.normalize()).set_index(KEYS)
    hist = monthly.pivot(index=KEYS, columns="month", values="qty_regular").reindex(base.index)
    periods = pd.period_range(end=origin, periods=12, freq="M").astype(str)
    hist = hist.reindex(columns=periods).fillna(0)
    scale = hist.mean(axis=1).clip(lower=1.0)
    products = data["products"].set_index(KEYS).reindex(base.index)
    result = base.reset_index()[KEYS].copy()
    result["category"] = products["category"].fillna("unknown").to_numpy()
    result["unit"] = products["unit"].fillna("unknown").to_numpy()
    for col in CATEGORICAL:
        result[col] = result[col].astype("category")
    result["log_scale"] = np.log1p(scale.to_numpy())
    for lag in (1, 2, 3, 6, 12):
        result[f"lag_{lag}"] = (hist.iloc[:, -lag] / scale).to_numpy()
    for window in (3, 6):
        result[f"mean_{window}"] = (hist.iloc[:, -window:].mean(axis=1) / scale).to_numpy()
    result["nonzero_12"] = hist.gt(0).mean(axis=1).to_numpy()
    result["cv_12"] = (hist.std(axis=1, ddof=0) / scale).to_numpy()
    result["baseline_ratio"] = (base["forecast_H"] / scale).to_numpy()
    result["seasonal_index"] = base["seasonal_index"].to_numpy()
    result["trend_factor"] = base["trend_factor"].to_numpy()
    result["month_sin"] = np.sin(2 * np.pi * target.month / 12)
    result["month_cos"] = np.cos(2 * np.pi * target.month / 12)
    result["lead"] = target.ordinal - origin.ordinal
    result["scale"] = scale.to_numpy()
    result["baseline"] = base["forecast_H"].to_numpy()
    result["origin"] = str(origin)
    result["target_month"] = str(target)
    return result


def training_panel(data):
    last = data["sales_lines"]["date"].max().to_period("M") - 1
    months = pd.period_range("2025-01", last, freq="M")
    if len(months) < 12:
        raise ValueError("ML needs at least 12 complete invoice months.")
    snapshots = {}
    for month in months[5:]:
        snapshots[str(month)] = snapshot(data, month)
        print(f"Causal history through {month}", flush=True)
    rows = []
    stocks = data["stock_monthly"].set_index(KEYS + ["month"])["qty_start"]
    for origin in months[5:-1]:
        for lead in range(1, MAX_LEAD + 1):
            target = origin + lead
            if target > last:
                continue
            frame = features(snapshots[str(origin)], data, origin, target)
            actual = snapshots[str(target)].query("month == @target_str", local_dict={"target_str": str(target)}).set_index(KEYS)
            idx = pd.MultiIndex.from_frame(frame[KEYS])
            frame["actual"] = (actual["qty_raw"] - actual["oneoff_excluded_qty"]).clip(lower=0).reindex(idx).fillna(0).to_numpy()
            stock_idx = pd.MultiIndex.from_arrays([frame["supplier"], frame["sku"], [str(target)] * len(frame)])
            frame["observable"] = stocks.reindex(stock_idx).fillna(0).gt(0).to_numpy()
            rows.append(frame)
    panel = pd.concat(rows, ignore_index=True)
    for col in CATEGORICAL:
        panel[col] = panel[col].astype("category")
    return panel, last


def fit_model(panel, loss="absolute_error"):
    usable = panel.loc[panel["observable"]]
    if len(usable) < 100 or usable["actual"].sum() <= 0:
        raise ValueError("Not enough observable demand for ML training.")
    model = HistGradientBoostingRegressor(
        loss=loss, max_iter=150, max_leaf_nodes=15, min_samples_leaf=30,
        l2_regularization=10.0, learning_rate=0.05, categorical_features="from_dtype",
        early_stopping=False, random_state=42,
    )
    with threadpool_limits(limits=4):
        model.fit(usable[FEATURES], usable["actual"] / usable["scale"])
    return model


def predict(model, frame):
    with threadpool_limits(limits=4):
        values = model.predict(frame[FEATURES]) * frame["scale"].to_numpy()
    if not np.isfinite(values).all():
        raise ValueError("ML produced non-finite demand.")
    return np.maximum(values, 0)


def scores(frame):
    """Dimensionless per-series scaled MAE; never sum metres and pieces as units."""
    out = {"rows": len(frame)}
    for method in ("baseline", "ml"):
        out[f"{method}_scaled_mae"] = float(((frame[method] - frame["actual"]).abs() / frame["scale"]).mean())
    out["improvement_pct"] = 100 * (1 - out["ml_scaled_mae"] / out["baseline_scaled_mae"]) if out["baseline_scaled_mae"] else None
    return out


def evaluate(panel, last):
    """Expanding-origin validation; train labels end strictly before each origin.

Each fold predicts the next three months where available. Last fold's origin
is May for an Aug endpoint: all three leads have observed test outcomes.
"""
    origins = pd.period_range(end=last - MAX_LEAD, periods=3, freq="M")
    candidates = []
    for loss in ("poisson", "absolute_error"):
        validation = []
        for origin in origins[:2]:
            training = panel.loc[panel["target_month"] <= str(origin)]
            checking = panel.loc[panel["origin"].eq(str(origin)) & panel["observable"]].copy()
            fitted = fit_model(training, loss=loss)
            checking["ml"] = predict(fitted, checking)
            validation.append(checking)
        candidates.append({"loss": loss, **scores(pd.concat(validation, ignore_index=True))})
        print(f"Model selection (before final fold): {candidates[-1]}", flush=True)
    selected_loss = min(candidates, key=lambda row: row["ml_scaled_mae"])["loss"]
    predictions, folds = [], []
    for origin in origins:
        train = panel.loc[panel["target_month"] <= str(origin)]
        test = panel.loc[panel["origin"].eq(str(origin)) & panel["observable"]].copy()
        model = fit_model(train, loss=selected_loss)
        test["ml"] = predict(model, test)
        folds.append({"origin": str(origin), "train_target_max": train["target_month"].max(),
                      "train_rows": int(train["observable"].sum()), **scores(test)})
        predictions.append(test)
        print(f"Validation origin {origin}: {folds[-1]}", flush=True)
    tested = pd.concat(predictions, ignore_index=True)
    groups = []
    for (supplier, unit), group in tested.groupby(["supplier", "unit"], observed=True):
        record = {"supplier": str(supplier), "unit": str(unit), **scores(group)}
        denom = group["actual"].sum()
        for method in ("baseline", "ml"):
            record[f"{method}_wape"] = float((group[method] - group["actual"]).abs().sum() / denom) if denom > 0 else None
        groups.append(record)
    final_month = tested.loc[tested["target_month"].eq(str(last))]
    return {"metric": "mean(abs(prediction - cleaned_sales) / max(prior_12_month_mean, 1))",
            "selected_loss": selected_loss, "candidate_validation": candidates,
            "selection_target_max": str(last - 1),
            "last_month_check": {"month": str(last), **scores(final_month)},
            "overall": scores(tested), "folds": folds, "by_supplier_unit": groups,
            "by_lead": [{"lead": int(lead), **scores(group)} for lead, group in tested.groupby("lead")],
            "target": "Sales minus one-off excess; only months with positive opening stock. Unobserved lost demand is not ground truth.",
            "limitations": "Overlapping test horizons; short history; positive opening stock does not prove availability throughout the month. Undated external seasonality coefficients excluded."}


def data_fingerprint():
    digest = hashlib.sha256()
    for name in ("sales_lines", "monthly_sales", "stock_monthly", "products", "seasonality"):
        path = CLEAN_DIR / f"{name}.parquet"
        digest.update(path.read_bytes())
    return digest.hexdigest()


def train(data, path=MODEL_PATH):
    panel, last = training_panel(data)
    evaluation = evaluate(panel, last)
    model = fit_model(panel, loss=evaluation["selected_loss"])
    metadata = {"format_version": FORMAT_VERSION, "sklearn_version": sklearn.__version__,
                "trained_through": str(last), "training_rows": int(panel["observable"].sum()),
                "training_products": int(panel.loc[panel["observable"], KEYS].drop_duplicates().shape[0]),
                "model": f"HistGradientBoostingRegressor({evaluation['selected_loss']})", "max_lead_months": MAX_LEAD,
                "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "data_sha256": data_fingerprint(), "evaluation": evaluation}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    joblib.dump({"model": model, "metadata": metadata}, temporary, compress=3)
    temporary.replace(path)
    metadata["artifact_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


@lru_cache(maxsize=2)
def _load(path: str, modified: int):
    # This is a locally trained artifact, not an upload endpoint. Never load
    # arbitrary joblib files received from untrusted users.
    bundle = joblib.load(path)
    bundle["metadata"]["model_id"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    return bundle


def load_model(path=MODEL_PATH):
    path = Path(path)
    if not path.exists():
        raise ValueError("ML-модель не обучена. Выполните: python -m app.ml.train")
    bundle = _load(str(path.resolve()), path.stat().st_mtime_ns)
    meta = bundle["metadata"]
    if meta["format_version"] != FORMAT_VERSION or meta["sklearn_version"] != sklearn.__version__:
        raise ValueError("Версия ML-модели устарела. Повторите: python -m app.ml.train")
    return bundle


def forecast_horizon(data, params, as_of, baseline, path=MODEL_PATH):
    bundle = load_model(path)
    if bundle["metadata"]["data_sha256"] != data_fingerprint():
        raise ValueError("Исходные таблицы изменились после обучения ML. Повторите: python -m app.ml.train")
    origin = as_of.to_period("M") - 1
    if pd.Period(bundle["metadata"]["trained_through"], freq="M") > origin:
        raise ValueError("Модель обучена на будущем относительно даты расчета. Для исторической проверки используйте backtest.")
    monthly = snapshot(data, origin)
    out = baseline.copy()
    details = []
    end = as_of + pd.Timedelta(days=int(baseline["horizon_days"].max()))
    for target in pd.period_range(as_of, end, freq="M"):
        frame = features(monthly, data, origin, target)
        within = target.ordinal - origin.ordinal <= MAX_LEAD
        frame["prediction"] = predict(bundle["model"], frame) if within else frame["baseline"]
        frame["source"] = "ML" if within else "statistical (beyond trained horizon)"
        frame["month"] = str(target)
        details.append(frame[KEYS + ["month", "prediction", "baseline", "source"]])
    months = pd.concat(details, ignore_index=True)
    months = months.merge(baseline[KEYS + ["horizon_days", "growth_factor"]], on=KEYS, how="inner")
    periods = pd.PeriodIndex(months["month"], freq="M")
    starts = pd.Series(periods.start_time, index=months.index).clip(lower=as_of + pd.Timedelta(days=1))
    ends = pd.concat([pd.Series(periods.end_time.normalize(), index=months.index),
                      as_of + pd.to_timedelta(months["horizon_days"], unit="D")], axis=1).min(axis=1)
    months["days"] = ((ends - starts).dt.days + 1).clip(lower=0)
    months["horizon_qty"] = months["prediction"] * months["days"] / periods.days_in_month * months["growth_factor"]
    total = months.groupby(KEYS)["horizon_qty"].sum()
    values = total.reindex(pd.MultiIndex.from_frame(out[KEYS])).to_numpy()
    out["forecast_H"] = np.where(np.isfinite(values), values, baseline["forecast_H"].to_numpy())
    return out, {"method": "ml", "metadata": bundle["metadata"], "monthly": months,
                 "baseline_forecast": baseline[KEYS + ["forecast_H"]].copy()}
