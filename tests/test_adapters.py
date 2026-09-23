"""Smoke checks for the built contract tables. Run `python -m app.adapters.build` first."""

import pandas as pd
import pytest

from app import schema
from app.adapters import CLEAN_DIR, load_clean

pytestmark = pytest.mark.skipif(not (CLEAN_DIR / "sales_lines.parquet").exists(),
                                reason="data/clean not built")


@pytest.fixture(scope="module")
def data():
    return load_clean()


def test_tables_follow_contract(data):
    for name, table in schema.INPUT_TABLES.items():
        assert list(data[name].columns) == list(table), name


def test_both_suppliers_present(data):
    for name in ("sales_lines", "monthly_sales", "stock_monthly", "stock_now", "products", "seasonality"):
        assert set(data[name]["supplier"]) == {"IEK", "SE"}, name


def test_products_unique_and_packs_valid(data):
    products = data["products"]
    assert not products.duplicated(["supplier", "sku"]).any()
    assert (products["pack_multiple"] >= 1).all()


def test_every_referenced_sku_has_product(data):
    known = set(zip(data["products"]["supplier"], data["products"]["sku"]))
    for name in ("sales_lines", "stock_now", "in_transit"):
        refs = set(zip(data[name]["supplier"], data[name]["sku"]))
        assert refs <= known, name


def test_totals_rows_removed(data):
    assert data["sales_lines"]["qty"].max() < 1_000_000
    assert data["stock_now"]["free_qty"].ge(0).all()


def test_oneoff_control_case_present(data):
    sales = data["sales_lines"]
    loop = sales[(sales["sku"] == "130200305_") & (sales["qty"] == 210000)]
    assert len(loop) == 1 and loop["date"].iloc[0].normalize() == pd.Timestamp("2025-06-09")


def test_seasonality_has_12_months(data):
    assert data["seasonality"].groupby("supplier")["month_num"].nunique().eq(12).all()
