"""Fake ORDER_LINES for UI work before the engine is ready. Owner: Person 3 «Продукт»."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app import schema


def mock_order_lines(n: int = 30, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    avg = rng.gamma(2, 5, n).round(1)
    free = rng.integers(0, 500, n).astype(float)
    transit = rng.choice([0, 0, 100, 250], n).astype(float)
    horizon = 37
    fc = avg * horizon
    safety = (avg * 5).round()
    pack = rng.choice([1, 10, 20], n)
    rec = np.ceil(np.clip(fc + safety - free - transit, 0, None) / pack) * pack
    cover = (free + transit) / avg
    df = pd.DataFrame({
        "supplier": rng.choice(["IEK", "SE"], n),
        "sku": [f"0105{i:05d}_" for i in range(n)],
        "name": [f"Товар {i}" for i in range(n)],
        "category": rng.choice(["0105", "1303", "0302"], n),
        "unit": "шт",
        "avg_daily_regular": avg,
        "seasonal_index": rng.uniform(0.8, 1.25, n).round(2),
        "trend_factor": 1.0,
        "growth_factor": 1.0,
        "horizon_days": horizon,
        "forecast_H": fc,
        "safety_stock": safety,
        "free_qty": free,
        "in_transit_H": transit,
        "oneoff_excluded_qty": rng.choice([0, 0, 0, 5000], n).astype(float),
        "stockout_months": rng.choice([0, 0, 1, 3], n),
        "stockout_uplift_qty": 0.0,
        "recommended_qty": rec,
        "final_qty": rec,
        "override_reason": "",
        "days_of_cover": cover,
        "urgency": np.select([cover < 30, cover < horizon], ["critical", "high"], "normal"),
        "rationale": "Mock: обоснование появится после подключения pipeline",
        "flags": "",
        "status": "draft",
    })
    return schema.conform(df, schema.ORDER_LINES, "mock")
