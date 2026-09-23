"""Causality, persistence and real integration of the trained forecaster."""
import numpy as np
import pandas as pd
import pytest

from app import schema
from app.adapters import CLEAN_DIR, load_clean
from app.ml import model
from app.pipeline import run


@pytest.fixture(scope="module")
def data():
    if not (CLEAN_DIR / "sales_lines.parquet").exists():
        pytest.skip("Build the real Excel data first")
    return load_clean()


def test_features_and_cleaning_cannot_see_future(data):
    # Small real slice keeps the causality regression fast; no fabricated sales.
    small = {name: table.loc[table["sku"].isin(["130300792_", "130300791_"])].copy()
             if "sku" in table else table.copy() for name, table in data.items()}
    origin, target = pd.Period("2026-03"), pd.Period("2026-04")
    before = model.snapshot(small, origin)
    expected = model.features(before, small, origin, target)
    changed = {name: table.copy() for name, table in small.items()}
    changed["sales_lines"].loc[changed["sales_lines"]["date"] > origin.end_time, "qty"] *= 1000
    changed["monthly_sales"].loc[changed["monthly_sales"]["month"] > str(origin), "qty"] *= 1000
    changed["stock_monthly"].loc[changed["stock_monthly"]["month"] > str(origin), "qty_start"] *= 1000
    changed["seasonality"]["coef"] *= 1000  # undated external coefficients excluded
    actual = model.features(model.snapshot(changed, origin), changed, origin, target)
    pd.testing.assert_frame_equal(expected, actual)


def test_missing_artifact_is_explicit(tmp_path):
    with pytest.raises(ValueError, match="не обучена"):
        model.load_model(tmp_path / "missing.joblib")


def test_training_artifact_and_temporal_validation():
    if not model.MODEL_PATH.exists():
        pytest.skip("Train the real model first: python -m app.ml.train")
    bundle = model.load_model()
    assert hasattr(bundle["model"], "n_iter_")  # fitted estimator, not a formula stub
    meta = bundle["metadata"]
    assert meta["training_rows"] > 1000
    assert meta["training_products"] > 100
    for fold in meta["evaluation"]["folds"]:
        assert fold["train_target_max"] <= fold["origin"] < meta["trained_through"]
        assert np.isfinite(fold["ml_scaled_mae"])


def test_real_ml_changes_forecast_and_preserves_order_rules(data):
    if not model.MODEL_PATH.exists():
        pytest.skip("Train the real model first")
    statistical = run(data)
    result = run(data, schema.Params(forecast_method="ml"))
    assert result.forecast_details["method"] == "ml"
    assert np.isfinite(result.forecast["forecast_H"]).all()
    assert result.forecast["forecast_H"].ge(0).all()
    assert not np.allclose(result.forecast["forecast_H"], statistical.forecast["forecast_H"])
    months = result.forecast_details["monthly"]
    assert set(months["source"]) == {"ML"}
    summed = months.groupby(model.KEYS)["horizon_qty"].sum()
    indexed = result.forecast.set_index(model.KEYS)
    np.testing.assert_allclose(indexed.loc[summed.index, "forecast_H"], summed)
    lines = result.order_lines.merge(data["products"][[*model.KEYS, "pack_multiple"]], on=model.KEYS)
    assert np.allclose(lines["recommended_qty"] % lines["pack_multiple"], 0)
    assert lines["rationale"].str.startswith("ML-прогноз").all()
    assert lines["status"].eq("draft").all()
    category = lines.iloc[0]["category"]
    grown = run(data, schema.Params(forecast_method="ml", growth_pct={category: 20}))
    keys = result.order_lines.loc[result.order_lines["category"].eq(category), model.KEYS]
    joined = keys.merge(result.forecast[model.KEYS + ["forecast_H"]], on=model.KEYS).merge(
        grown.forecast[model.KEYS + ["forecast_H"]], on=model.KEYS, suffixes=("_before", "_after"))
    np.testing.assert_allclose(joined["forecast_H_after"], joined["forecast_H_before"] * 1.2)
    # Order calculation remains deterministic; incoming deliveries cannot raise it.
    pick = lines.loc[lines["recommended_qty"].gt(0)].iloc[0]
    changed = {**data, "in_transit": pd.concat([data["in_transit"], pd.DataFrame([{
        "supplier": pick.supplier, "sku": pick.sku, "qty": pick.recommended_qty,
        "eta": result.as_of + pd.Timedelta(days=1), "order_ref": "ml-test",
    }])], ignore_index=True)}
    with_transit = run(changed, schema.Params(forecast_method="ml"))
    assert with_transit.order_lines.set_index(model.KEYS).loc[(pick.supplier, pick.sku), "recommended_qty"] <= pick.recommended_qty


def test_ml_rejects_backdated_inference_and_incompatible_preprocessing(data):
    if not model.MODEL_PATH.exists():
        pytest.skip("Train the real model first")
    with pytest.raises(ValueError, match="отключения факторов"):
        run(data, schema.Params(forecast_method="ml", use_trend=False))
    # Guard must reject artifacts whose training targets would leak into history.
    from app.engine.forecast import forecast
    origin = pd.Period("2026-03")
    monthly = model.snapshot(data, origin)
    params = schema.Params(forecast_method="ml")
    as_of = pd.Timestamp("2026-04-01")
    base = forecast(monthly, data["monthly_sales"], data["seasonality"], data["products"], params, as_of)
    with pytest.raises(ValueError, match="будущем"):
        model.forecast_horizon(data, params, as_of, base)


def test_real_ml_ui_selects_trained_model(monkeypatch, tmp_path):
    if not model.MODEL_PATH.exists():
        pytest.skip("Train the real model first")
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    import streamlit as st
    from app.ui import state
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "approvals.json")
    st.cache_data.clear()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/ui/app.py"), default_timeout=90).run()
    app.sidebar.selectbox[0].select("ml").run()
    next(b for b in app.button if b.label == "Рассчитать").click().run()
    assert not app.exception, [e.message for e in app.exception]
    assert not app.error, [e.value for e in app.error]
    assert app.session_state.result.forecast_details["method"] == "ml"
    assert any("обученный ML" in e.value for e in app.success)
    app.selectbox(key="product_sku").select("IEK | 130300792_").run()
    assert not app.exception
    curve = next(d.value for d in app.dataframe if "Прогноз / полный месяц" in d.value.columns)
    assert len(curve) == 2
    assert curve["Метод"].eq("ML").all()
    st.cache_data.clear()
