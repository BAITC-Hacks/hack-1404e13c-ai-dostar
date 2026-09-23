"""Export approved orders for 1C. Owner: Person 3 «Продукт» (task 3.3)."""

from __future__ import annotations

import io

import pandas as pd

COLUMNS = {  # ORDER_LINES / products column -> export header
    "sku": "Код 1С",
    "supplier_article": "Артикул поставщика",
    "name": "Наименование",
    "unit": "Ед.",
    "final_qty": "Количество",
    "supplier": "Поставщик",
    "rationale": "Обоснование",
}


def _safe(value):
    # Spreadsheet formula injection guard.
    return "'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@") else value


def to_table(order_lines: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """STUB: approved lines with positive quantity in export layout."""
    lines = order_lines[(order_lines["status"] == "approved") & (order_lines["final_qty"] > 0)]
    lines = lines.merge(products[["supplier", "sku", "supplier_article"]], on=["supplier", "sku"], how="left")
    return lines[list(COLUMNS)].rename(columns=COLUMNS).map(_safe)


def to_xlsx(table: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    table.to_excel(buf, index=False)
    return buf.getvalue()
