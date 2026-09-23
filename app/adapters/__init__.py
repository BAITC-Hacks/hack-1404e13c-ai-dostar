"""Raw 1C/Excel exports -> contract tables (app/schema.py).

Build parquet once:   python -m app.adapters.build
Use in code:          from app.adapters import load_clean; data = load_clean()
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app import schema

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"


def load_clean(clean_dir: Path = CLEAN_DIR) -> dict[str, pd.DataFrame]:
    """Contract tables from data/clean/*.parquet (run the build first)."""
    return {name: pd.read_parquet(clean_dir / f"{name}.parquet") for name in schema.INPUT_TABLES}
