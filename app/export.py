"""Export approved supplier orders as safe CSV or XLSX bytes."""

from __future__ import annotations

import io

import pandas as pd

HEADERS = {
    "sku": "Код 1С",
    "supplier_article": "Артикул поставщика",
    "name": "Наименование",
    "unit": "Ед.",
    "final_qty": "Количество",
    "supplier": "Поставщик",
    "warehouse": "Склад",
    "rationale": "Обоснование",
}


def _safe(value: object) -> object:
    """Stop spreadsheet applications interpreting untrusted text as a formula."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def to_table(order_lines: pd.DataFrame, products: pd.DataFrame, supplier: str) -> pd.DataFrame:
    """Positive, approved lines for one supplier, in the 1C export layout."""
    lines = order_lines.loc[
        (order_lines["supplier"] == supplier)
        & (order_lines["status"] == "approved")
        & (order_lines["final_qty"] > 0)
    ].copy()
    if not lines.empty:
        articles = products[["supplier", "sku", "supplier_article"]].drop_duplicates(["supplier", "sku"])
        lines = lines.merge(articles, on=["supplier", "sku"], how="left", validate="many_to_one")
    else:
        lines["supplier_article"] = pd.Series(dtype="string")
    # All supplied sales are for Алматы; no per-order warehouse selector exists.
    lines["warehouse"] = "Алматы"
    for column in ("supplier_article", "name", "unit", "rationale"):
        lines[column] = lines[column].fillna("")
    reasons = lines["override_reason"].fillna("").astype(str).str.strip()
    edited = reasons.ne("")
    lines.loc[edited, "rationale"] = (
        lines.loc[edited, "rationale"] + " Решение менеджера: " + reasons[edited]
    )
    return lines[list(HEADERS)].rename(columns=HEADERS).map(_safe)


def to_xlsx(order_lines: pd.DataFrame, products: pd.DataFrame, supplier: str) -> bytes:
    buf = io.BytesIO()
    to_table(order_lines, products, supplier).to_excel(buf, index=False)
    return buf.getvalue()


def to_csv(order_lines: pd.DataFrame, products: pd.DataFrame, supplier: str) -> bytes:
    return to_table(order_lines, products, supplier).to_csv(index=False).encode("utf-8-sig")
