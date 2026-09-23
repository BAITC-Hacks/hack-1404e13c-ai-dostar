"""Rebuild actual Excel, convert CSV, retrain ML and verify both order pipelines.

python scripts/verify_real_system.py [--report docs/verification/real-system.json]
Uses isolated temporary outputs and approvals. Never calls a paid API, overwrites
the production model or modifies source datasets. Pytest/browser checks are separate.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import assistant, copilot, schema
from app.adapters import load_clean
from app.adapters.build import build
from app.export import to_csv, to_xlsx
from app.ml import model
from app.pipeline import run
from app.ui import state
from scripts.excel_to_csv import SOURCES, convert_folder


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "docs/verification/real-system.json")
    args = parser.parse_args()
    before = {"model": digest(model.MODEL_PATH), "approvals": digest(state.STATE_FILE),
              "data": model.data_fingerprint()}
    files = sorted(p for name in SOURCES for p in (ROOT / "datasets" / name).rglob("*") if p.is_file())
    source_hashes = {str(p.relative_to(ROOT)): digest(p) for p in files}
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "checks": {},
              "scope": "Actual Excel and local model; no mocked pipeline, no external API calls"}
    start = time.perf_counter()
    cache = ROOT / ".pytest_cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="real-system-", dir=cache) as temporary:
        work = Path(temporary).resolve()
        assert work.is_relative_to(cache.resolve())
        print("Rebuilding actual supplier Excel...", flush=True)
        rebuilt, existing = build(ROOT / "datasets"), load_clean()
        for name in existing:
            pd.testing.assert_frame_equal(rebuilt[name], existing[name])
        report["checks"]["excel_tables"] = {name: len(table) for name, table in rebuilt.items()}
        print("All 8 rebuilt tables match runtime values and dtypes.", flush=True)

        conversions = {}
        for name in SOURCES:
            source = ROOT / "datasets" / name
            copied = work / "csv" / name
            shutil.copytree(source, copied)
            books, sheets = convert_folder(copied)
            generated = copied.with_name(name + "_CSV")
            expected = source.with_name(name + "_CSV")
            csv_paths = sorted(generated.rglob("*.csv"))
            assert len(csv_paths) == sheets > 0
            for path in csv_paths:
                assert path.stat().st_size > 3, path.name
                assert digest(path) == digest(expected / path.relative_to(generated)), path.name
            assert {str(p.relative_to(generated)) for p in csv_paths} == {
                str(p.relative_to(expected)) for p in expected.rglob("*.csv")}
            conversions[name] = {"workbooks": books, "csv_files": sheets, "matches_committed_csv": True}
        report["checks"]["csv_conversion"] = conversions

        print("Training and evaluating a new model in isolated storage...", flush=True)
        trained_path = work / "models/demand.joblib"
        metadata = model.train(rebuilt, path=trained_path)
        fresh = model.load_model(trained_path)
        production = model.load_model()
        origin = pd.Period(metadata["trained_through"], "M")
        inputs = model.features(model.snapshot(rebuilt, origin), rebuilt, origin, origin + 1)
        np.testing.assert_allclose(model.predict(fresh["model"], inputs),
                                   model.predict(production["model"], inputs), rtol=1e-10, atol=1e-10)
        report["checks"]["training"] = {"rows": metadata["training_rows"],
            "products": metadata["training_products"], "selected_loss": metadata["evaluation"]["selected_loss"],
            "future_predictions_matching_production": len(inputs), "evaluation": metadata["evaluation"]}

        methods = {}
        for method in ("statistical", "ml"):
            print(f"Verifying {method} pipeline, approvals and both export formats...", flush=True)
            result = run(rebuilt, schema.Params(forecast_method=method))
            lines = result.order_lines.copy()
            assert len(result.sales_flagged) == len(rebuilt["sales_lines"]) > 200_000
            assert len(lines) > 2_000
            numeric = lines[["forecast_H", "recommended_qty", "final_qty", "free_qty", "in_transit_H"]]
            assert np.isfinite(numeric.to_numpy(dtype=float)).all() and numeric.ge(0).all().all()
            assert not lines.duplicated(model.KEYS).any()
            packs = lines.merge(rebuilt["products"][[*model.KEYS, "pack_multiple"]], on=model.KEYS)
            assert np.allclose(packs.recommended_qty % packs.pack_multiple, 0)
            assert lines.rationale.str.len().gt(20).all()
            assert lines.status.eq("draft").all()
            assert {"declining", "new_item"} <= set(result.lifecycle.signal)
            # Only the parsed rule filter is exercised; external LLM validation is
            # explicitly reported separately rather than pretending a fake is live.
            query = assistant.parse_rules("IEK заказ")
            found = assistant.apply_filter(lines, query)
            assert not found.empty and found.supplier.eq("IEK").all() and found.final_qty.gt(0).all()
            reviews, source = assistant.review_pairs(result.lifecycle, use_llm=False)
            assert source == "rules"

            exported = {}
            lines["override_reason"] = "Verification in isolated storage; source inventory reviewed for test only"
            approval_file = work / f"{method}-approvals.json"
            for supplier in ("IEK", "SE"):
                state.approve_supplier(lines, supplier, result.as_of, approval_file)
            approved = state.apply_saved(lines, result.as_of, approval_file)
            for supplier in ("IEK", "SE"):
                expected = approved.loc[approved.supplier.eq(supplier) & approved.final_qty.gt(0)]
                for fmt, exporter, reader in (("csv", to_csv, pd.read_csv), ("xlsx", to_xlsx, pd.read_excel)):
                    table = reader(io.BytesIO(exporter(approved, rebuilt["products"], supplier)))
                    assert len(table) == len(expected) > 0
                    assert table["Количество"].gt(0).all()
                    assert set(table["Код 1С"].astype(str)) == set(expected.sku.astype(str))
                    expected_quantities = expected.set_index("sku").final_qty
                    actual_quantities = table.set_index("Код 1С")["Количество"]
                    np.testing.assert_allclose(actual_quantities.reindex(expected_quantities.index), expected_quantities)
                    exported[f"{supplier}_{fmt}"] = len(table)
            methods[method] = {"order_rows": len(lines), "forecast_rows": len(result.forecast),
                "sales_rows": len(result.sales_flagged), "lifecycle_signals": len(result.lifecycle),
                "replacement_pairs_reviewed_by_rules": len(reviews), "search_rows": len(found),
                "exports": exported, "as_of": str(result.as_of.date())}
        report["checks"]["pipelines"] = methods

    after = {"model": digest(model.MODEL_PATH), "approvals": digest(state.STATE_FILE),
             "data": model.data_fingerprint()}
    assert before == after, "Production model, approvals or runtime data changed"
    assert source_hashes == {str(p.relative_to(ROOT)): digest(p) for p in files}
    report["checks"]["production_unchanged"] = after
    report["checks"]["source_excel_files_unchanged"] = len(files)
    report["live_llm"] = {"configured": copilot.enabled(), "verified": False,
        "reason": "External API not called by this local verification; fallback and response validation tested separately"}
    report["elapsed_seconds"] = time.perf_counter() - start
    report["status"] = "passed_local_checks"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PASS: local real-data verification. Report: {args.report}", flush=True)


if __name__ == "__main__":
    main()
