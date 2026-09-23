"""Build data/clean/*.parquet from the supplier folders in data/raw/.

    python -m app.adapters.build [--raw data/raw] [--out data/clean]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from app import schema
from app.adapters import CLEAN_DIR, RAW_DIR, iek, se
from app.adapters.common import nfc

# Raw folder name (as unzipped from the partner archives) -> adapter.
ADAPTERS = {"iek": iek.load, "systeme electric": se.load}


def build(raw_dir: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    parts: dict[str, list[pd.DataFrame]] = {name: [] for name in schema.INPUT_TABLES}
    for folder in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        loader = ADAPTERS.get(nfc(folder.name).lower())
        if loader is None:
            print(f"skip {folder.name}: no adapter")
            continue
        started = time.time()
        for name, df in loader(folder).items():
            parts[name].append(df)
        print(f"{folder.name}: parsed in {time.time() - started:.0f}s")
    return {
        name: schema.conform(pd.concat(dfs, ignore_index=True), schema.INPUT_TABLES[name], name)
        if dfs else schema.empty(schema.INPUT_TABLES[name])
        for name, dfs in parts.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=RAW_DIR)
    parser.add_argument("--out", type=Path, default=CLEAN_DIR)
    args = parser.parse_args()
    tables = build(args.raw)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(args.out / f"{name}.parquet", index=False)
        print(f"{name:17s} {len(df):>8d} rows")


if __name__ == "__main__":
    main()
