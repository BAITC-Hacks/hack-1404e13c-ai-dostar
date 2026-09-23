"""Tests for engine/oneoffs.py and engine/demand.py. Owner: Person 1 «Спрос» (task 1.3)."""

import pytest

from app import schema
from app.adapters import CLEAN_DIR, load_clean
from app.engine import demand, oneoffs

pytestmark = pytest.mark.skipif(not (CLEAN_DIR / "sales_lines.parquet").exists(),
                                reason="data/clean not built")


@pytest.fixture(scope="module")
def data():
    return load_clean()


def test_demand_monthly_contract(data):
    params = schema.Params()
    as_of = data["sales_lines"]["date"].max().normalize()
    flagged = oneoffs.flag_oneoffs(data["sales_lines"], params)
    monthly = demand.build_monthly(flagged, data["stock_monthly"], params, as_of)
    assert list(monthly.columns) == list(schema.DEMAND_MONTHLY)
    assert monthly["qty_regular"].ge(0).all()
    assert not monthly.duplicated(["supplier", "sku", "month"]).any()
